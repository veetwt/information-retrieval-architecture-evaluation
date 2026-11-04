"""Arquitetura de recuperação VETORIAL (semântica, baseada em embeddings).

Recebe uma pergunta em linguagem natural, gera sua representação vetorial com o
mesmo modelo usado na indexação, compara-a (cosseno) às passagens indexadas de
ASSUNTO+ACORDAO e consolida os resultados por documento (doc_id).

Princípios metodológicos:
- Entrada é apenas o TEXTO da consulta (cumpre a interface comum `Retriever`).
- NÃO usa filtros de metadados, nem a natureza/ficha/gold.
- Usa exclusivamente a representação de ASSUNTO+ACORDAO (via índice).
- `score` é a similaridade de cosseno (vetores L2-normalizados → produto interno).

Consolidação de passagens por documento: MAX-POOLING — o score de um documento é
o maior score entre seus chunks, e a `evidence` guarda a passagem (chunk) que
fundamentou a recuperação. A avaliação permanece por `doc_id` (um documento
aparece uma única vez no resultado; não há duplicação por chunk).

O `display_limit` é um teto PROVISÓRIO de exibição para testes exploratórios —
NÃO é o top-k definitivo do experimento.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    from retrieval.base import RetrievalResult, RetrievedDocument
    from retrieval.vector_index import VectorIndex, load_index
except ImportError:  # pragma: no cover
    from .base import RetrievalResult, RetrievedDocument
    from .vector_index import VectorIndex, load_index


DEFAULT_DISPLAY_LIMIT = 10


class VectorRetriever:
    """Recuperação vetorial com consolidação por documento (max-pooling)."""

    architecture_name = "vector"
    VERSION = "0.2.0"

    def __init__(self, index: VectorIndex, model=None, display_limit: int = DEFAULT_DISPLAY_LIMIT) -> None:
        """Inicializa com um índice carregado.

        `model` pode ser injetado (testes) ou carregado sob demanda a partir do
        `model_name` registrado no índice. `display_limit` é provisório.
        """
        self._index = index
        self._model = model
        self._display_limit = display_limit
        # Pré-computa o mapeamento doc_id -> posições de chunk, de forma estável.
        self._doc_ids = index.chunk_doc_ids

    def _ensure_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._index.meta["model_name"], device="cpu")
        return self._model

    def _encode_query(self, query: str) -> np.ndarray:
        model = self._ensure_model()
        vec = model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vec, dtype=np.float32)[0]

    def retrieve(self, query: str) -> RetrievalResult:
        """Executa a recuperação vetorial para a consulta textual."""
        qvec = self._encode_query(query)
        emb = self._index.embeddings  # [n_chunks, dim], normalizado
        # Similaridade de cosseno = produto interno (vetores normalizados).
        sims = emb @ qvec  # [n_chunks]

        # Consolidação por documento: para cada doc_id, o melhor chunk.
        best_by_doc: dict[str, tuple[float, int]] = {}  # doc_id -> (score, chunk_pos)
        doc_ids = self._doc_ids
        for pos in range(sims.shape[0]):
            did = str(doc_ids[pos])
            sc = float(sims[pos])
            cur = best_by_doc.get(did)
            if cur is None or sc > cur[0]:
                best_by_doc[did] = (sc, pos)

        # Ordenação determinística: score desc, depois doc_id asc (desempate estável).
        ordered = sorted(best_by_doc.items(), key=lambda kv: (-kv[1][0], kv[0]))

        limited = ordered[: self._display_limit]
        documents: list[RetrievedDocument] = []
        for rank, (did, (score, pos)) in enumerate(limited, start=1):
            passage = self._index.chunk_texts[pos]
            documents.append(
                RetrievedDocument(
                    doc_id=did,
                    rank=rank,
                    score=score,
                    evidence={
                        "passage": passage[:500],
                        "chunk_index": int(self._index.chunk_indices[pos]),
                        "consolidation": "max_pooling",
                    },
                )
            )

        diagnostics = {
            "architecture_version": self.VERSION,
            "model_name": self._index.meta.get("model_name"),
            "embedding_dim": self._index.meta.get("embedding_dim"),
            "similarity": "cosine_via_normalized_dot",
            "consolidation": "max_pooling_by_doc_id",
            "n_chunks_indexed": self._index.n_chunks,
            "n_docs_candidates": len(best_by_doc),
            "n_docs_indexed": self._index.meta.get("n_docs_indexed"),
            "is_partial_index": self._index.meta.get("is_partial_index"),
            "selection_fingerprint": self._index.meta.get("selection_fingerprint"),
            "display_limit_provisional": self._display_limit,
            "chunking": self._index.meta.get("chunking"),
            "max_tokens": self._index.meta.get("max_tokens"),
            "overlap_tokens": self._index.meta.get("overlap_tokens"),
        }
        return RetrievalResult(
            query=query,
            architecture=self.architecture_name,
            documents=documents,
            fields_used=["ASSUNTO", "ACORDAO"],
            diagnostics=diagnostics,
        )

    @classmethod
    def from_index_dir(cls, index_dir: Path, model=None, display_limit: int = DEFAULT_DISPLAY_LIMIT) -> "VectorRetriever":
        """Carrega o índice do diretório e constrói o retriever."""
        return cls(load_index(index_dir), model=model, display_limit=display_limit)

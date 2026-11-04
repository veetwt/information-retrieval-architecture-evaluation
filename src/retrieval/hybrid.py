"""Arquitetura de recuperação HÍBRIDA (estruturada + vetorial).

Combina, por COMPOSIÇÃO, as duas arquiteturas já existentes — sem alterá-las:

- `StructuredRetriever` (v0.3.0): interpreta condições de metadados a partir do
  TEXTO da consulta e devolve o conjunto de documentos que satisfazem TODAS as
  condições reconhecidas (filtro booleano). A ordem que a estruturada usa é por
  `doc_id` e NÃO representa relevância.
- `VectorRetriever` (v0.2.0): codifica a consulta e pontua os documentos por
  similaridade de cosseno das passagens (ASSUNTO+ACORDAO), consolidando por
  documento via max-pooling.

Estratégia FIXA de combinação (sem LLM, sem roteamento por natureza da
necessidade, sem qualquer informação das fichas/gold):

1. Recebe a pergunta textual original.
2. Interpreta possíveis filtros de metadados usando a arquitetura estruturada.
3. Se houver condições reconhecidas E documentos candidatos correspondentes
   (Caso C): aplica o filtro e ordena os candidatos por similaridade vetorial.
   A similaridade é calculada sobre TODOS os chunks dos documentos candidatos
   elegíveis (não apenas pela interseção com um top-k vetorial prévio) e
   consolidada por documento com max-pooling.
4. Se houver condições reconhecidas, mas a interseção dos filtros for VAZIA
   (Caso B): retorna conjunto VAZIO. NÃO executa fallback vetorial global, NÃO
   relaxa filtros e NÃO inventa candidatos. Registra
   `path="structured_no_candidates"`, `n_structured_candidates=0`,
   `n_ranked_candidates=0`, `structured_intersection_empty=True` e preserva as
   condições reconhecidas.
5. Se NÃO houver condição reconhecida (Caso A): usa a recuperação vetorial
   GLOBAL (`path="vector_global_fallback"`,
   `fallback_reason="no_conditions_identified"`).
6. Retorna `doc_id`, `rank`, `score`, `evidence` e diagnósticos que registram os
   filtros aplicados e o caminho percorrido.

Reprodutibilidade e eficiência:
- Reutiliza o índice vetorial completo já construído (não gera embeddings).
- No caminho filtrado, pontua apenas as linhas de embedding dos chunks dos
  documentos candidatos, por meio de uma máscara de posições — evita copiar a
  matriz inteira de embeddings.
- Parâmetros fixos; a ordenação é determinística (score desc, depois doc_id asc).

Limitações (registradas também nos diagnósticos):
- O recall do caminho estruturado é limitado pela interpretação de condições da
  estruturada: condições não reconhecidas levam ao fallback vetorial global.
- A precisão do filtro depende da qualidade/cobertura dos metadados do corpus.
- Quando um filtro reconhecido é mais restritivo que a necessidade real (ex.:
  casa só uma condição de uma necessidade com várias), o conjunto candidato pode
  excluir documentos relevantes; este é um efeito da estratégia fixa, não
  corrigido aqui.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from retrieval.base import RetrievalResult, RetrievedDocument
    from retrieval.structured import StructuredRetriever
    from retrieval.vector import VectorRetriever
    from retrieval.vector_index import load_index
    from utils.hashing import compute_dataset_fingerprint
except ImportError:  # pragma: no cover
    from .base import RetrievalResult, RetrievedDocument
    from .structured import StructuredRetriever
    from .vector import VectorRetriever
    from .vector_index import load_index
    from ..utils.hashing import compute_dataset_fingerprint


class HybridIntegrityError(ValueError):
    """Incompatibilidade de integridade entre a seleção e o índice vetorial."""


DEFAULT_DISPLAY_LIMIT = 10


class HybridRetriever:
    """Recuperação híbrida: filtro estruturado + ordenação vetorial, com fallback.

    Compõe instâncias já construídas de `StructuredRetriever` e `VectorRetriever`.
    Não herda nem modifica nenhuma delas.
    """

    architecture_name = "hybrid"
    # 0.2.0: política de fallback revista — interseção estruturada vazia agora
    #        retorna conjunto VAZIO (path="structured_no_candidates"), sem
    #        fallback vetorial global. O fallback global ocorre apenas quando
    #        NENHUMA condição é reconhecida (path="vector_global_fallback").
    VERSION = "0.2.0"

    def __init__(
        self,
        structured: StructuredRetriever,
        vector: VectorRetriever,
        display_limit: int = DEFAULT_DISPLAY_LIMIT,
    ) -> None:
        self._structured = structured
        self._vector = vector
        self._display_limit = display_limit
        # Mapa doc_id -> posições (índices de linha) dos seus chunks no índice.
        # Construído uma vez; usado para pontuar apenas os candidatos.
        idx = vector._index
        self._chunk_doc_ids = idx.chunk_doc_ids
        self._doc_to_positions: dict[str, list[int]] = {}
        for pos, did in enumerate(self._chunk_doc_ids.tolist()):
            self._doc_to_positions.setdefault(str(did), []).append(pos)

    # ------------------------------------------------------------------ #
    # Caminho filtrado: ordenar candidatos por similaridade vetorial
    # ------------------------------------------------------------------ #

    def _rank_candidates_by_similarity(
        self, qvec: np.ndarray, candidate_doc_ids: list[str]
    ) -> list[tuple[str, float, int]]:
        """Para cada doc candidato, calcula o melhor score entre seus chunks.

        Retorna lista de (doc_id, score, chunk_pos) ordenada por score desc e,
        em empate, por doc_id asc. A similaridade é computada SOMENTE sobre as
        linhas de embedding dos chunks dos candidatos (máscara de posições), sem
        copiar a matriz inteira.
        """
        emb = self._vector._index.embeddings  # [n_chunks, dim], L2-normalizado

        # Posições de chunk de todos os candidatos (contíguas por doc na ordem do índice).
        # Um candidato estruturado SEM chunks no índice é violação de integridade:
        # falha-se de forma explícita em vez de descartá-lo silenciosamente.
        positions: list[int] = []
        missing: list[str] = []
        for did in candidate_doc_ids:
            pos = self._doc_to_positions.get(did)
            if not pos:
                missing.append(did)
            else:
                positions.extend(pos)
        if missing:
            raise HybridIntegrityError(
                f"{len(missing)} candidato(s) estruturado(s) sem embedding no índice "
                f"(ex.: {missing[:3]}). Seleção e índice estão inconsistentes."
            )
        if not positions:
            return []
        pos_arr = np.asarray(sorted(positions), dtype=np.int64)

        # Produto interno apenas nas linhas selecionadas (cosseno, vetores normalizados).
        sub = np.asarray(emb[pos_arr])            # cópia pequena (só candidatos)
        sims = sub @ qvec                          # [n_candidate_chunks]

        # Consolidação por documento (max-pooling): melhor chunk por doc_id.
        best_by_doc: dict[str, tuple[float, int]] = {}
        for local_i, global_pos in enumerate(pos_arr.tolist()):
            did = str(self._chunk_doc_ids[global_pos])
            sc = float(sims[local_i])
            cur = best_by_doc.get(did)
            if cur is None or sc > cur[0]:
                best_by_doc[did] = (sc, global_pos)

        ordered = sorted(
            ((did, s, p) for did, (s, p) in best_by_doc.items()),
            key=lambda t: (-t[1], t[0]),
        )
        return ordered

    # ------------------------------------------------------------------ #
    # Interface comum
    # ------------------------------------------------------------------ #

    def retrieve(self, query: str) -> RetrievalResult:
        """Executa a recuperação híbrida para a consulta textual."""
        # 1-2) Interpretação de filtros via estruturada (sem ficha/gold).
        structured_res = self._structured.retrieve(query)
        conditions = structured_res.diagnostics.get("identified_conditions", {})
        candidate_doc_ids = structured_res.doc_ids  # ordenados por doc_id (não é relevância)

        diagnostics: dict = {
            "architecture_version": self.VERSION,
            "structured_version": getattr(self._structured, "VERSION", None),
            "vector_version": getattr(self._vector, "VERSION", None),
            "combination_rule": (
                "filtro estruturado (AND das condições) + ordenação por "
                "similaridade vetorial sobre TODOS os candidatos. Fallback "
                "vetorial global SOMENTE quando NENHUMA condição é reconhecida; "
                "quando há condições mas a interseção dos filtros é vazia, o "
                "resultado é VAZIO (sem fallback global, sem relaxar filtros)"
            ),
            "identified_conditions": dict(conditions),
            "n_structured_candidates": len(candidate_doc_ids),
            "similarity": "cosine_via_normalized_dot",
            "consolidation": "max_pooling_by_doc_id",
            "display_limit_provisional": self._display_limit,
            "selection_fingerprint": self._vector._index.meta.get("selection_fingerprint"),
            "is_partial_index": self._vector._index.meta.get("is_partial_index"),
        }

        # Caso B) Condições reconhecidas, mas interseção estruturada VAZIA.
        # Política aprovada: retornar conjunto vazio, SEM fallback vetorial
        # global, SEM relaxar filtros e SEM inventar candidatos. Preserva as
        # condições reconhecidas e os campos de metadados usados.
        if conditions and not candidate_doc_ids:
            diagnostics["path"] = "structured_no_candidates"
            diagnostics["structured_intersection_empty"] = True
            diagnostics["n_ranked_candidates"] = 0
            return RetrievalResult(
                query=query,
                architecture=self.architecture_name,
                documents=[],
                fields_used=list(conditions.keys()),
                diagnostics=diagnostics,
            )

        # Caso A) NENHUMA condição reconhecida -> recuperação vetorial global.
        if not conditions:
            diagnostics["path"] = "vector_global_fallback"
            diagnostics["fallback_reason"] = "no_conditions_identified"
            vector_res = self._vector.retrieve(query)
            # Reembala os diagnósticos do vetorial sob a arquitetura híbrida.
            diagnostics["vector_diagnostics"] = vector_res.diagnostics
            documents = [
                RetrievedDocument(
                    doc_id=d.doc_id,
                    rank=d.rank,
                    score=d.score,
                    evidence={**d.evidence, "path": "vector_global_fallback"},
                )
                for d in vector_res.documents
            ]
            return RetrievalResult(
                query=query,
                architecture=self.architecture_name,
                documents=documents,
                fields_used=["ASSUNTO", "ACORDAO"],
                diagnostics=diagnostics,
            )

        # 3) Caminho filtrado: ordenar candidatos por similaridade vetorial.
        diagnostics["path"] = "structured_filter_then_vector_rank"
        qvec = self._vector._encode_query(query)
        ordered = self._rank_candidates_by_similarity(qvec, candidate_doc_ids)
        diagnostics["n_ranked_candidates"] = len(ordered)

        index = self._vector._index
        limited = ordered[: self._display_limit]
        documents = []
        for rank, (did, score, pos) in enumerate(limited, start=1):
            passage = index.chunk_texts[pos]
            documents.append(
                RetrievedDocument(
                    doc_id=did,
                    rank=rank,
                    score=score,
                    evidence={
                        "passage": passage[:500],
                        "chunk_index": int(index.chunk_indices[pos]),
                        "consolidation": "max_pooling",
                        "matched_conditions": dict(conditions),
                        "path": "structured_filter_then_vector_rank",
                    },
                )
            )

        # Campos usados = metadados filtrados + campos textuais da ordenação.
        fields_used = list(conditions.keys()) + ["ASSUNTO", "ACORDAO"]
        return RetrievalResult(
            query=query,
            architecture=self.architecture_name,
            documents=documents,
            fields_used=fields_used,
            diagnostics=diagnostics,
        )

    # ------------------------------------------------------------------ #
    # Construção a partir dos artefatos congelados
    # ------------------------------------------------------------------ #

    @staticmethod
    def _find_manifest(selection_parquet: Path) -> Path | None:
        """Localiza o manifesto sidecar da seleção (..._manifest.json), se houver."""
        cand = selection_parquet.with_name(selection_parquet.stem + "_manifest.json")
        return cand if cand.exists() else None

    @classmethod
    def from_artifacts(
        cls,
        selection_parquet: Path,
        index_dir: Path,
        *,
        model=None,
        display_limit: int = DEFAULT_DISPLAY_LIMIT,
        verify_integrity: bool = True,
    ) -> "HybridRetriever":
        """Constrói o híbrido a partir da seleção congelada e do índice vetorial.

        Reutiliza o índice já construído (não gera embeddings). O mesmo DataFrame
        da seleção alimenta a estruturada; o índice alimenta a vetorial.

        Integridade (quando `verify_integrity=True`, padrão):
        1. `load_index` valida a integridade intrínseca do índice (completo, não
           parcial, contagens e dimensão consistentes).
        2. O fingerprint da seleção é RECALCULADO a partir do DataFrame com a
           mesma função do projeto (`compute_dataset_fingerprint`, sort por
           doc_id) — origem confiável, não um valor arbitrário do chamador.
        3. Esse fingerprint recalculado é comparado ao do manifesto da seleção
           (quando existe) e ao `selection_fingerprint` registrado no índice.
        4. Verifica-se a correspondência EXATA dos conjuntos de doc_id entre a
           seleção e o índice (sem ausentes nem adicionais; sem duplicatas).

        Qualquer divergência interrompe a construção com `HybridIntegrityError`.
        O fingerprint NÃO é passado pelo chamador: deriva-se dos artefatos reais.
        """
        selection_parquet = Path(selection_parquet)
        index_dir = Path(index_dir)

        # (1) Índice: integridade intrínseca validada no carregamento.
        index = load_index(index_dir)

        # DataFrame da seleção (leitura única, reaproveitada pela estruturada).
        df = pd.read_parquet(selection_parquet, engine="pyarrow")

        recomputed_fp = compute_dataset_fingerprint(df, sort_col="doc_id")
        index_fp = index.meta.get("selection_fingerprint")
        manifest_path = cls._find_manifest(selection_parquet)
        manifest_fp = None
        if manifest_path is not None:
            manifest_fp = json.loads(
                manifest_path.read_text(encoding="utf-8")
            ).get("selection_fingerprint")

        if verify_integrity:
            # (3a) fingerprint recalculado deve bater com o do manifesto (se houver).
            if manifest_fp is not None and recomputed_fp != manifest_fp:
                raise HybridIntegrityError(
                    "Fingerprint da seleção recalculado diverge do manifesto: "
                    f"recalculado={recomputed_fp}, manifesto={manifest_fp}. "
                    "A seleção pode ter sido alterada após o congelamento."
                )
            # (3b) fingerprint recalculado deve bater com o registrado no índice.
            if index_fp is None:
                raise HybridIntegrityError(
                    "O índice não registra 'selection_fingerprint'; não é possível "
                    "comprovar que foi construído sobre esta seleção."
                )
            if recomputed_fp != index_fp:
                raise HybridIntegrityError(
                    "Seleção incompatível com o índice (fingerprints divergem): "
                    f"seleção(recalculada)={recomputed_fp}, índice={index_fp}. "
                    "O índice foi construído sobre outra versão da seleção."
                )

            # (4) Correspondência exata de doc_id entre seleção e índice.
            cls._check_doc_id_correspondence(df, index)

        structured = StructuredRetriever(df, corpus_fingerprint=recomputed_fp)
        vector = VectorRetriever(index, model=model, display_limit=display_limit)
        return cls(structured, vector, display_limit=display_limit)

    @staticmethod
    def _check_doc_id_correspondence(df: "pd.DataFrame", index) -> None:
        """Verifica correspondência exata dos doc_id entre seleção e índice.

        Rejeita: documentos da seleção ausentes do índice, documentos do índice
        fora da seleção, e doc_id duplicados/inválidos no índice. Executado UMA
        vez na construção (não por consulta).
        """
        sel_ids = [str(x) for x in df["doc_id"].tolist()]
        sel_set = set(sel_ids)
        if len(sel_set) != len(sel_ids):
            raise HybridIntegrityError("Seleção contém doc_id duplicados.")
        if any((s is None or s == "" or s == "nan") for s in sel_set):
            raise HybridIntegrityError("Seleção contém doc_id nulo/inválido.")

        idx_ids = [str(x) for x in index.chunk_doc_ids.tolist()]
        idx_set = set(idx_ids)
        if any((s is None or s == "" or s == "nan") for s in idx_set):
            raise HybridIntegrityError("Índice contém doc_id nulo/inválido nos chunks.")

        missing = sel_set - idx_set   # docs elegíveis da seleção sem embedding
        extra = idx_set - sel_set     # docs no índice que não pertencem à seleção
        if missing or extra:
            raise HybridIntegrityError(
                "Conjuntos de doc_id divergem entre seleção e índice: "
                f"{len(missing)} doc(s) da seleção ausente(s) no índice, "
                f"{len(extra)} doc(s) do índice fora da seleção. "
                "Reconstrua o índice sobre a mesma seleção congelada."
            )

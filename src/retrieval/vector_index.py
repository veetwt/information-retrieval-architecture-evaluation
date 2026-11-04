"""Construção e carregamento do índice vetorial da seleção experimental.

Produz, de forma reprodutível, auditável e RETOMÁVEL, um índice de embeddings
das passagens (chunks) de ASSUNTO+ACORDAO dos acórdãos da Selecao_Experimental
congelada.

Artefatos do índice (gravados fora do versionamento Git — ver .gitignore:
`embeddings/`, `*.npy`):
- `chunks.parquet`     : colunas doc_id, chunk_index, text (vínculo chunk→doc_id);
  escrito ANTES dos embeddings e define a ORDEM canônica dos chunks.
- `build_state.json`   : estado reprodutível da construção (fingerprint da
  seleção, modelo, parâmetros de chunking, n_chunks, dim, tamanho de shard e
  shards já concluídos). Usado para retomar e para detectar incompatibilidades.
- `shards/emb_NNNNN.npy`: blocos independentes de embeddings, um por intervalo
  contíguo de chunks. Cada bloco é escrito de forma ATÔMICA (arquivo temporário
  + rename) e validado por shape antes de ser considerado concluído.
- `embeddings.npy`     : matriz float32 [n_chunks, dim] consolidada (vetores
  L2-normalizados). Gravada SOMENTE após todos os shards estarem concluídos.
- `index_meta.json`    : metadados finais (modelo, dim, parâmetros, fingerprint,
  versões de dependências, contagens e timestamps). Gravado SOMENTE no fim.

Retomabilidade (Tarefa 1):
- Os chunks são preparados e persistidos de forma determinística ANTES de
  qualquer embedding, com ids/vínculo ao doc_id e ordem explícita.
- Os embeddings são gerados em blocos pequenos independentes (shards).
- Cada bloco é gravado de forma segura e verificável (temp + rename + shape).
- Uma reexecução pula blocos já concluídos e compatíveis (não recalcula).
- Blocos incompletos/incompatíveis são detectados e refeitos.
- A retomada valida: fingerprint da seleção, nome do modelo, versão do índice,
  parâmetros de chunking e a ordem/contagem dos chunks (via chunks.parquet).
- O índice só é considerado COMPLETO após todos os blocos validados.

Chunking por TOKENS reais (Tarefa 2):
- O modelo tem janela de 128 tokens. Verificou-se que chunks de ~100 palavras
  geram ~227 tokens em média (94,8% acima de 128) → truncamento silencioso.
- Por isso o índice real é construído com chunking por TOKENS do tokenizer do
  modelo (max_tokens=128, overlap=16), o que garante 0 chunks truncados.

NÃO altera o corpus nem os manifestos (leitura apenas).
"""

from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from retrieval.text_prep import (
        MAX_TOKENS,
        OVERLAP_TOKENS,
        build_document_text,
        chunk_text_by_tokens,
    )
except ImportError:  # pragma: no cover
    from .text_prep import (
        MAX_TOKENS,
        OVERLAP_TOKENS,
        build_document_text,
        chunk_text_by_tokens,
    )


DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
INDEX_VERSION = "0.2.0"  # 0.2.0: chunking por tokens + construção retomável (shards)

EMBEDDINGS_FILE = "embeddings.npy"
CHUNKS_FILE = "chunks.parquet"
META_FILE = "index_meta.json"
STATE_FILE = "build_state.json"
SHARDS_DIR = "shards"

DEFAULT_SHARD_SIZE = 2000  # chunks por shard (bloco independente e verificável)


@dataclass
class VectorIndex:
    """Índice vetorial carregado em memória (somente leitura)."""

    embeddings: np.ndarray          # [n_chunks, dim] float32, L2-normalizado
    chunk_doc_ids: np.ndarray       # [n_chunks] str
    chunk_indices: np.ndarray       # [n_chunks] int
    chunk_texts: list[str]          # [n_chunks]
    meta: dict

    @property
    def n_chunks(self) -> int:
        return int(self.embeddings.shape[0])

    @property
    def dim(self) -> int:
        return int(self.embeddings.shape[1])


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dep_versions() -> dict:
    vers = {"python": platform.python_version()}
    for mod in ("sentence_transformers", "transformers", "torch", "numpy", "pandas"):
        try:
            m = __import__(mod)
            vers[mod] = getattr(m, "__version__", "?")
        except Exception:  # pragma: no cover
            vers[mod] = "ausente"
    return vers


def _load_model(model_name: str):
    """Carrega o SentenceTransformer em CPU (import tardio para testes leves)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device="cpu")


def _shard_path(index_dir: Path, start: int) -> Path:
    return index_dir / SHARDS_DIR / f"emb_{start:08d}.npy"


def _shard_bounds(n_chunks: int, shard_size: int) -> list[tuple[int, int]]:
    """Intervalos [start, end) contíguos que cobrem todos os chunks."""
    return [(s, min(s + shard_size, n_chunks)) for s in range(0, n_chunks, shard_size)]


def _save_npy_atomic(path: Path, arr: np.ndarray) -> None:
    """Grava .npy de forma atômica: escreve em .tmp e renomeia ao final."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    # Escreve via file handle: assim `np.save` NÃO acrescenta `.npy` ao nome do
    # arquivo temporário (comportamento que ocorre quando se passa um caminho
    # que não termina em `.npy`).
    with open(tmp, "wb") as fh:
        np.save(fh, arr, allow_pickle=False)
    os.replace(tmp, path)


def _shard_is_complete(path: Path, expected_rows: int, expected_dim: int) -> bool:
    """Verifica se o shard existe e tem o shape esperado (sem carregar tudo)."""
    if not path.exists():
        return False
    try:
        arr = np.load(path, mmap_mode="r")
    except Exception:
        return False
    ok = arr.shape == (expected_rows, expected_dim) and arr.dtype == np.float32
    del arr
    return bool(ok)


def _chunk_plan(
    df: pd.DataFrame,
    tokenizer,
    max_tokens: int,
    overlap_tokens: int,
) -> tuple[list[str], list[int], list[str]]:
    """Gera o plano determinístico de chunks (ordem canônica) por TOKENS.

    Retorna listas paralelas (doc_ids, chunk_indices, texts) na ordem em que os
    documentos aparecem na seleção e os chunks dentro de cada documento.
    """
    doc_ids: list[str] = []
    chunk_idx: list[int] = []
    texts: list[str] = []
    for row in df.itertuples(index=False):
        text = build_document_text(row.ASSUNTO, row.ACORDAO)
        pieces = chunk_text_by_tokens(text, tokenizer, max_tokens, overlap_tokens)
        for i, piece in enumerate(pieces):
            doc_ids.append(str(row.doc_id))
            chunk_idx.append(i)
            texts.append(piece)
    return doc_ids, chunk_idx, texts


def _build_fingerprint(
    *,
    model_name: str,
    max_tokens: int,
    overlap_tokens: int,
    selection_fingerprint: str | None,
    n_docs_indexed: int,
    n_chunks: int,
    dim: int,
) -> dict:
    """Identidade lógica da construção; usada para validar retomadas."""
    return {
        "index_version": INDEX_VERSION,
        "model_name": model_name,
        "max_tokens": int(max_tokens),
        "overlap_tokens": int(overlap_tokens),
        "selection_fingerprint": selection_fingerprint,
        "n_docs_indexed": int(n_docs_indexed),
        "n_chunks": int(n_chunks),
        "embedding_dim": int(dim),
        "chunking": "by_tokens",
    }


def _incompatible(prev: dict, cur: dict) -> list[str]:
    """Campos de identidade que divergem entre um estado salvo e o atual."""
    keys = [
        "index_version",
        "model_name",
        "max_tokens",
        "overlap_tokens",
        "selection_fingerprint",
        "n_docs_indexed",
        "n_chunks",
        "embedding_dim",
        "chunking",
    ]
    return [k for k in keys if prev.get(k) != cur.get(k)]


def build_index(
    selection_parquet: Path,
    index_dir: Path,
    *,
    model_name: str = DEFAULT_MODEL,
    selection_fingerprint: str | None = None,
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
    batch_size: int = 8,
    shard_size: int = DEFAULT_SHARD_SIZE,
    limit: int | None = None,
    overwrite: bool = False,
    progress: bool = True,
    model=None,
    tokenizer=None,
) -> dict:
    """Constrói (ou retoma) o índice vetorial a partir da seleção congelada.

    Fluxo retomável:
      1. Prepara e PERSISTE `chunks.parquet` (ordem canônica) antes de embutir.
      2. Registra/valida `build_state.json` (fingerprint, modelo, parâmetros).
      3. Codifica em SHARDS independentes, gravados de forma atômica.
      4. Pula shards já concluídos e compatíveis; refaz os incompletos.
      5. Só consolida `embeddings.npy` + `index_meta.json` quando todos os
         shards estão presentes e com shape correto.

    `limit` indexa apenas os primeiros N documentos (teste técnico); registra
    `is_partial_index=True` e `n_docs_indexed < total`. `model`/`tokenizer`
    permitem injetar um encoder determinístico em testes (sem rede).

    Retorna o dicionário de metadados do índice. Se o índice já está completo e
    compatível e `overwrite=False`, retorna o meta existente sem recomputar.
    """
    index_dir = Path(index_dir)
    meta_path = index_dir / META_FILE
    chunks_path = index_dir / CHUNKS_FILE
    state_path = index_dir / STATE_FILE
    emb_path = index_dir / EMBEDDINGS_FILE

    def _log(msg: str) -> None:
        if progress:
            print(msg, flush=True)

    # Índice já consolidado e compatível → não recomputa.
    if meta_path.exists() and not overwrite:
        return json.loads(meta_path.read_text(encoding="utf-8"))

    if overwrite:
        _reset_index_dir(index_dir)

    index_dir.mkdir(parents=True, exist_ok=True)

    # --- Modelo/tokenizer (necessários tanto para chunking quanto embedding) ---
    if model is None:
        model = _load_model(model_name)
    if tokenizer is None:
        tokenizer = getattr(model, "tokenizer", None)
        if tokenizer is None:
            raise ValueError(
                "Nenhum tokenizer disponível: passe `tokenizer=` ou um `model` "
                "que exponha `.tokenizer` (chunking por tokens é obrigatório)."
            )
    # O tokenizer emite um aviso ("sequence length ... > 128") ao tokenizar o
    # documento INTEIRO durante o planejamento de chunks. Isso é esperado: o
    # texto é fatiado em janelas <= max_tokens em seguida, então NÃO há
    # truncamento. Silenciamos o aviso para não induzir a leitura equivocada.
    try:
        from transformers.utils import logging as _hf_logging
        _hf_logging.set_verbosity_error()
    except Exception:  # pragma: no cover
        pass
    # `get_sentence_embedding_dimension` foi renomeado; usa o novo nome quando
    # disponível (evita FutureWarning), com fallback para compatibilidade.
    if hasattr(model, "get_embedding_dimension"):
        dim = int(model.get_embedding_dimension())
    else:
        dim = int(model.get_sentence_embedding_dimension())

    # --- 1) Plano de chunks (determinístico) + persistência ANTES de embutir ---
    df = pd.read_parquet(selection_parquet, columns=["doc_id", "ASSUNTO", "ACORDAO"])
    n_total_docs = int(len(df))
    if limit is not None:
        df = df.iloc[:limit].copy()
    n_docs_indexed = int(len(df))

    reuse_chunks = (
        chunks_path.exists() and state_path.exists() and not overwrite
    )
    if reuse_chunks:
        prev_state = json.loads(state_path.read_text(encoding="utf-8"))
        chunks_df = pd.read_parquet(chunks_path)
        doc_ids = chunks_df["doc_id"].astype(str).tolist()
        chunk_idx = chunks_df["chunk_index"].astype(int).tolist()
        texts = chunks_df["text"].tolist()
        n_chunks = len(texts)
        _log(f"[retomada] chunks.parquet reaproveitado: n_chunks={n_chunks}")
    else:
        _log("[plano] gerando chunks por tokens (determinístico)...")
        doc_ids, chunk_idx, texts = _chunk_plan(
            df, tokenizer, max_tokens, overlap_tokens
        )
        n_chunks = len(texts)
        if n_chunks == 0:
            raise ValueError("Nenhum chunk gerado; verifique a seleção e os campos.")
        chunks_df = pd.DataFrame(
            {"doc_id": doc_ids, "chunk_index": chunk_idx, "text": texts}
        )
        _write_parquet_atomic(chunks_df, chunks_path)
        prev_state = None
        _log(f"[plano] chunks.parquet gravado: n_chunks={n_chunks}")

    # --- 2) Fingerprint da construção + validação de compatibilidade ---
    cur_fp = _build_fingerprint(
        model_name=model_name,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
        selection_fingerprint=selection_fingerprint,
        n_docs_indexed=n_docs_indexed,
        n_chunks=n_chunks,
        dim=dim,
    )
    bounds = _shard_bounds(n_chunks, shard_size)

    if prev_state is not None:
        diff = _incompatible(prev_state.get("fingerprint", {}), cur_fp)
        same_shard = int(prev_state.get("shard_size", -1)) == int(shard_size)
        if diff or not same_shard:
            reason = ", ".join(diff) if diff else "shard_size"
            raise ValueError(
                "Estado de construção incompatível com os parâmetros atuais "
                f"(divergência: {reason}). Use overwrite=True para reconstruir "
                "do zero em um diretório limpo."
            )
        state = prev_state
    else:
        state = {
            "fingerprint": cur_fp,
            "shard_size": int(shard_size),
            "n_shards": len(bounds),
            "completed_shards": [],
            "created_at": _utcnow(),
            "updated_at": _utcnow(),
        }
        _write_json_atomic(state, state_path)

    # --- 3) Codificar em SHARDS independentes (pula concluídos/compatíveis) ---
    completed = set(int(s) for s in state.get("completed_shards", []))
    total_shards = len(bounds)
    for si, (start, end) in enumerate(bounds):
        rows = end - start
        spath = _shard_path(index_dir, start)
        if start in completed and _shard_is_complete(spath, rows, dim):
            _log(f"[shard {si + 1}/{total_shards}] pulado (concluído) {start}:{end}")
            continue
        # Shard ausente/incompleto/incompatível → (re)computa.
        _log(f"[shard {si + 1}/{total_shards}] codificando {start}:{end} ({rows} chunks)")
        batch = texts[start:end]
        vecs = model.encode(
            batch,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,  # L2-normalizado → cosseno = produto interno
            show_progress_bar=False,
        ).astype(np.float32)
        if vecs.shape != (rows, dim):
            raise ValueError(
                f"Shard {start}:{end} com shape inesperado {vecs.shape}, "
                f"esperado {(rows, dim)}."
            )
        _save_npy_atomic(spath, vecs)
        completed.add(start)
        state["completed_shards"] = sorted(completed)
        state["updated_at"] = _utcnow()
        _write_json_atomic(state, state_path)

    # --- 4) Verificar que TODOS os shards estão completos antes de consolidar ---
    missing = [
        (s, e) for (s, e) in bounds
        if not _shard_is_complete(_shard_path(index_dir, s), e - s, dim)
    ]
    if missing:
        raise RuntimeError(
            f"Consolidação abortada: {len(missing)} shard(s) ausente(s)/incompleto(s). "
            "Reexecute para retomar."
        )

    # --- 5) Consolidar embeddings.npy (memmap) e index_meta.json (só no fim) ---
    _log("[consolidação] escrevendo embeddings.npy a partir dos shards...")
    tmp_emb = emb_path.with_suffix(".npy.tmp")
    out = np.lib.format.open_memmap(
        tmp_emb, mode="w+", dtype=np.float32, shape=(n_chunks, dim)
    )
    try:
        for (start, end) in bounds:
            shard = np.load(_shard_path(index_dir, start))
            out[start:end] = shard
            del shard
        out.flush()
    finally:
        del out
    os.replace(tmp_emb, emb_path)

    try:
        import sentence_transformers as _st
        st_ver = _st.__version__
    except Exception:  # pragma: no cover
        st_ver = "?"
    meta = {
        "index_version": INDEX_VERSION,
        "model_name": model_name,
        "embedding_dim": dim,
        "similarity": "cosine_via_normalized_dot",
        "chunking": "by_tokens",
        "max_tokens": int(max_tokens),
        "overlap_tokens": int(overlap_tokens),
        "batch_size": int(batch_size),
        "shard_size": int(shard_size),
        "n_shards": len(bounds),
        "n_total_docs_in_selection": n_total_docs,
        "n_docs_indexed": n_docs_indexed,
        "is_partial_index": n_docs_indexed < n_total_docs,
        "n_chunks": n_chunks,
        "selection_parquet": Path(selection_parquet).name,
        "selection_fingerprint": selection_fingerprint,
        "dependency_versions": _dep_versions(),
        "sentence_transformers_version": st_ver,
        "embeddings_file": EMBEDDINGS_FILE,
        "chunks_file": CHUNKS_FILE,
        "built_at": _utcnow(),
    }
    _write_json_atomic(meta, meta_path)
    _log(f"[ok] índice consolidado: n_docs={n_docs_indexed} n_chunks={n_chunks} dim={dim}")
    return meta


def _write_json_atomic(obj: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _write_parquet_atomic(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, engine="pyarrow", index=False)
    os.replace(tmp, path)


def _reset_index_dir(index_dir: Path) -> None:
    """Remove artefatos de uma construção anterior (usado com overwrite=True)."""
    for name in (EMBEDDINGS_FILE, CHUNKS_FILE, META_FILE, STATE_FILE):
        p = index_dir / name
        if p.exists():
            p.unlink()
        tmp = p.with_suffix(p.suffix + ".tmp")
        if tmp.exists():
            tmp.unlink()
    shards = index_dir / SHARDS_DIR
    if shards.exists():
        for f in shards.iterdir():
            if f.is_file():
                f.unlink()


class IndexIntegrityError(ValueError):
    """Erro de integridade do índice vetorial carregado (fail-fast, claro)."""


def load_index(index_dir: Path, *, allow_partial: bool = False) -> VectorIndex:
    """Carrega o índice vetorial do diretório (somente leitura).

    Valida a integridade intrínseca do índice no carregamento (fail-fast), sem
    alterar sua estrutura nem seus parâmetros:
    - presença dos arquivos obrigatórios (meta, embeddings, chunks);
    - consistência entre `len(embeddings)`, `len(chunks)` e `meta["n_chunks"]`;
    - dimensão dos embeddings == `meta["embedding_dim"]`;
    - índice NÃO parcial (`is_partial_index` falso), salvo `allow_partial=True`.

    Um índice completo e válido (como o de produção) passa sem alteração de
    comportamento; apenas índices corrompidos/parciais são rejeitados com
    mensagem clara. Levanta `IndexIntegrityError` em caso de inconsistência e
    `FileNotFoundError` quando um arquivo obrigatório está ausente.
    """
    index_dir = Path(index_dir)
    meta_path = index_dir / META_FILE
    if not meta_path.exists():
        raise FileNotFoundError(
            f"Índice incompleto: '{META_FILE}' ausente em '{index_dir}'. "
            "O índice só é consolidado após todos os shards; verifique a construção."
        )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    emb_name = meta.get("embeddings_file", EMBEDDINGS_FILE)
    chunks_name = meta.get("chunks_file", CHUNKS_FILE)
    emb_path = index_dir / emb_name
    chunks_path = index_dir / chunks_name
    if not emb_path.exists():
        raise FileNotFoundError(f"Arquivo de embeddings ausente: '{emb_path}'.")
    if not chunks_path.exists():
        raise FileNotFoundError(f"Arquivo de chunks ausente: '{chunks_path}'.")

    if meta.get("is_partial_index") and not allow_partial:
        raise IndexIntegrityError(
            "Índice PARCIAL não pode ser usado nos experimentos: "
            f"n_docs_indexed={meta.get('n_docs_indexed')} de "
            f"n_total_docs_in_selection={meta.get('n_total_docs_in_selection')}. "
            "Reconstrua o índice completo (ou use allow_partial=True apenas para teste técnico)."
        )

    embeddings = np.load(emb_path, mmap_mode="r")
    chunks = pd.read_parquet(chunks_path)

    n_emb = int(embeddings.shape[0])
    n_chunks_df = int(len(chunks))
    n_chunks_meta = int(meta.get("n_chunks", -1))
    if not (n_emb == n_chunks_df == n_chunks_meta):
        raise IndexIntegrityError(
            "Inconsistência de contagem no índice: "
            f"embeddings={n_emb}, chunks.parquet={n_chunks_df}, meta.n_chunks={n_chunks_meta}."
        )

    dim_meta = int(meta.get("embedding_dim", -1))
    dim_emb = int(embeddings.shape[1]) if embeddings.ndim == 2 else -1
    if dim_emb != dim_meta:
        raise IndexIntegrityError(
            f"Dimensão incompatível: embeddings.dim={dim_emb}, meta.embedding_dim={dim_meta}."
        )

    for col in ("doc_id", "chunk_index", "text"):
        if col not in chunks.columns:
            raise IndexIntegrityError(
                f"'{chunks_name}' sem a coluna obrigatória '{col}'."
            )

    return VectorIndex(
        embeddings=np.asarray(embeddings),
        chunk_doc_ids=chunks["doc_id"].to_numpy(),
        chunk_indices=chunks["chunk_index"].to_numpy(),
        chunk_texts=chunks["text"].tolist(),
        meta=meta,
    )

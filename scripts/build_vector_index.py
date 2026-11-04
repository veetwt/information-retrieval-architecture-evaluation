"""Ponto de entrada: construção do índice vetorial da seleção congelada.

Uso:
    python scripts/build_vector_index.py                 # índice completo
    python scripts/build_vector_index.py --limit 500     # teste técnico parcial
    python scripts/build_vector_index.py --overwrite      # reconstruir

Grava o índice em `embeddings/<batch_id>/` (fora do Git). Não altera o corpus.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data.config import CorpusConfig  # noqa: E402
from retrieval.vector_index import DEFAULT_MODEL, build_index  # noqa: E402


def _latest_selection(experimental_dir: Path, batch_id: str) -> Path:
    cands = sorted(experimental_dir.glob(f"selection_{batch_id}_*.parquet"))
    if not cands:
        raise FileNotFoundError(f"Seleção não encontrada em {experimental_dir}")
    return cands[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "configs" / "acordaos_tcu_2024.yaml"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--index-dir", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=8,
                        help="chunks por lote no encoder (padrão 8, seguro p/ 8GB RAM)")
    parser.add_argument("--shard-size", type=int, default=2000,
                        help="chunks por shard independente/retomável (padrão 2000)")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    config = CorpusConfig.load(Path(args.config))
    sel = _latest_selection(Path(config.experimental_dir), config.batch_id)
    manifest = sel.parent / f"{sel.stem}_manifest.json"
    fingerprint = None
    if manifest.exists():
        fingerprint = json.loads(manifest.read_text(encoding="utf-8")).get("selection_fingerprint")

    index_dir = (
        Path(args.index_dir) if args.index_dir
        else PROJECT_ROOT / "embeddings" / config.batch_id
    )

    print(f"Seleção : {sel.name}")
    print(f"Modelo  : {args.model}")
    print(f"Índice  : {index_dir}")
    print(f"Limite  : {args.limit if args.limit is not None else 'completo'}")
    t0 = time.time()
    meta = build_index(
        sel,
        index_dir,
        model_name=args.model,
        selection_fingerprint=fingerprint,
        batch_size=args.batch_size,
        shard_size=args.shard_size,
        limit=args.limit,
        overwrite=args.overwrite,
    )
    dt = time.time() - t0
    print(f"\nConcluído em {dt:.1f}s")
    print(f"  docs indexados : {meta['n_docs_indexed']} / {meta['n_total_docs_in_selection']}")
    print(f"  parcial?       : {meta['is_partial_index']}")
    print(f"  chunks         : {meta['n_chunks']}")
    print(f"  dim            : {meta['embedding_dim']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

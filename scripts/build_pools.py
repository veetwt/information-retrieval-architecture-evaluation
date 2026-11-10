"""Ponto de entrada: geração de pools de candidatos para julgamento.

Executa os três recuperadores sobre as formulações das fichas e grava os
artefatos do pool em `runs/pools/<run_id>/` (SEM rótulos de relevância, SEM gold).

Uso:
    python scripts/build_pools.py --run-id teste_exploratorio --seed 20240101
    python scripts/build_pools.py --needs NI-001 NI-002 --run-id r1 --seed 7

Observações:
- A execução é `exploratory` por padrão; fichas em `draft` NÃO geram pool oficial.
- Não constrói nem preenche o gold.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data.config import CorpusConfig  # noqa: E402
from evaluation.need_sheet import NeedSheet  # noqa: E402
from evaluation.pool_generator import (  # noqa: E402
    DEFAULT_D,
    DEFAULT_T,
    DEFAULT_T_COND,
    PoolGenerator,
    validate_official,
)


def _latest_selection(experimental_dir: Path, batch_id: str) -> Path:
    cands = sorted(experimental_dir.glob(f"selection_{batch_id}_*.parquet"))
    if not cands:
        raise FileNotFoundError(f"Seleção não encontrada em {experimental_dir}")
    return cands[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "configs" / "acordaos_tcu_2024.yaml"))
    parser.add_argument("--index-dir", default=None)
    parser.add_argument("--needs-dir", default=str(PROJECT_ROOT / "evaluation" / "questions" / "needs"))
    parser.add_argument("--needs", nargs="*", default=None, help="need_ids a incluir (padrão: todos)")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--D", type=int, default=DEFAULT_D)
    parser.add_argument("--T", type=int, default=DEFAULT_T)
    parser.add_argument("--T-cond", type=int, default=DEFAULT_T_COND)
    args = parser.parse_args(argv)

    config = CorpusConfig.load(Path(args.config))
    sel = _latest_selection(Path(config.experimental_dir), config.batch_id)
    index_dir = Path(args.index_dir) if args.index_dir else PROJECT_ROOT / "embeddings" / config.batch_id
    needs_dir = Path(args.needs_dir)
    out_dir = Path(args.out_dir) if args.out_dir else PROJECT_ROOT / "runs" / "pools" / args.run_id

    # Carrega fichas.
    sheet_paths = sorted(needs_dir.glob("NI-*.yaml"))
    sheets = [NeedSheet.from_yaml(p) for p in sheet_paths]
    if args.needs:
        wanted = set(args.needs)
        sheets = [s for s in sheets if s.need_id in wanted]
    if not sheets:
        print("Nenhuma ficha selecionada.")
        return 1

    print(f"Seleção : {sel.name}")
    print(f"Índice  : {index_dir}")
    print(f"Fichas  : {[s.need_id for s in sheets]}")
    print(f"run_id  : {args.run_id}  seed: {args.seed}")

    gen = PoolGenerator.from_artifacts(
        sel, index_dir, D=args.D, T=args.T, T_cond=args.T_cond,
    )
    manifest = gen.run(sheets, out_dir, run_id=args.run_id, run_seed=args.seed, status="exploratory")

    check = validate_official(manifest, sheets)
    print(f"\nPool gravado em: {out_dir}")
    print(f"  candidatos: {manifest['counts']['n_candidates']}")
    print(f"  status gravado: {manifest['status']}")
    print(f"  elegível a oficial? {check.ok}")
    if not check.ok:
        print(f"  impedimentos: {check.reasons}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

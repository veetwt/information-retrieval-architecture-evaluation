"""Ponto de entrada: seleção reduzida para JULGAMENTO HUMANO (Alternativa B).

Deriva uma lista determinística de até 67 pares `(need_id, doc_id)` para
avaliação humana, SEM rótulos de relevância e SEM gold, preservando a
recuperação sobre os 21.631 acórdãos e a profundidade D=50 no registro.

Uso:
    python scripts/build_judgment_set.py --run-id julgamento_altb
    python scripts/build_judgment_set.py --run-id r1 --needs NI-001 NI-002 NI-003

Observações:
- Esta etapa NÃO executa o experimento oficial, NÃO julga relevância e NÃO
  constrói gold.
- O teto de 67 é RÍGIDO: se o conjunto obrigatório ultrapassar, a preparação é
  interrompida com a contagem (nada é descartado para caber).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data.config import CorpusConfig  # noqa: E402
from evaluation.need_sheet import NeedSheet  # noqa: E402
from evaluation.judgment_selection import (  # noqa: E402
    JUDGMENT_CAP,
    JUDGMENT_TOPK,
    RECORD_DEPTH,
    JudgmentCapExceeded,
    JudgmentSelector,
    validate_judgment_manifest,
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
    parser.add_argument("--needs", nargs="*", default=None)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--topk", type=int, default=JUDGMENT_TOPK)
    parser.add_argument("--cap", type=int, default=JUDGMENT_CAP)
    args = parser.parse_args(argv)

    config = CorpusConfig.load(Path(args.config))
    sel = _latest_selection(Path(config.experimental_dir), config.batch_id)
    index_dir = Path(args.index_dir) if args.index_dir else PROJECT_ROOT / "embeddings" / config.batch_id
    needs_dir = Path(args.needs_dir)
    out_dir = Path(args.out_dir) if args.out_dir else PROJECT_ROOT / "runs" / "judgment" / args.run_id

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
    print(f"topk julgamento: {args.topk}  |  D (registro): {RECORD_DEPTH}  |  teto: {args.cap}")

    selector = JudgmentSelector.from_artifacts(
        sel, index_dir, topk=args.topk, cap=args.cap,
    )
    try:
        manifest = selector.run(sheets, out_dir, run_id=args.run_id, enforce_cap=True)
    except JudgmentCapExceeded as exc:
        print("\n[INTERROMPIDO] Teto de julgamento excedido — nada foi gravado.")
        print(f"  obrigatórios: {exc.required}  |  teto: {exc.cap}")
        print(f"  composição  : {exc.breakdown}")
        return 2

    check = validate_judgment_manifest(manifest, sheets)
    print(f"\nConjunto de julgamento gravado em: {out_dir}")
    print(f"  total de julgamentos: {manifest['counts']['n_judgments']} (teto {args.cap})")
    for n in manifest["per_need"]:
        print(f"  {n['need_id']}: {n['n_judgments']}  {n['by_source']}")
    print(f"  sobreposições: {manifest['overlaps']}")
    print(f"  válido? {check.ok}")
    if not check.ok:
        print(f"  impedimentos: {check.reasons}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

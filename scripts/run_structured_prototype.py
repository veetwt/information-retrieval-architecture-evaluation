"""Teste funcional (exploratório) do protótipo de recuperação estruturada.

Executa as TRÊS formulações (direct/paraphrase/verbose) de cada ficha de
desenvolvimento (NI-001, NI-002, NI-003) na arquitetura estruturada, usando
APENAS o texto de cada formulação. Não usa mandatory_conditions, nature,
requested_facts, respostas candidatas nem gold.

Uso:
    python scripts/run_structured_prototype.py

Não é avaliação científica: serve para verificar se o sistema localiza
documentos e para expor limitações da interpretação.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data.config import CorpusConfig  # noqa: E402
from evaluation.need_sheet import NeedSheet  # noqa: E402
from retrieval.structured import StructuredRetriever  # noqa: E402


def _latest_selection(experimental_dir: Path, batch_id: str) -> Path:
    cands = sorted(experimental_dir.glob(f"selection_{batch_id}_*.parquet"))
    if not cands:
        raise FileNotFoundError(f"Seleção não encontrada em {experimental_dir}")
    return cands[-1]


def main() -> int:
    config = CorpusConfig.load(PROJECT_ROOT / "configs" / "acordaos_tcu_2024.yaml")
    sel = _latest_selection(Path(config.experimental_dir), config.batch_id)
    manifest = sel.parent / f"{sel.stem}_manifest.json"
    fingerprint = None
    if manifest.exists():
        fingerprint = json.loads(manifest.read_text(encoding="utf-8")).get(
            "selection_fingerprint"
        )

    retriever = StructuredRetriever.from_selection(sel, fingerprint=fingerprint)

    needs_dir = PROJECT_ROOT / "evaluation" / "questions" / "needs"
    for nid in ["NI-001", "NI-002", "NI-003"]:
        sheet = NeedSheet.from_yaml(needs_dir / f"{nid}.yaml")
        print("\n" + "=" * 72)
        print(f"{nid}  (nature={sheet.nature.value})")
        for label in ["direct", "paraphrase", "verbose"]:
            query = getattr(sheet.formulations, label)
            res = retriever.retrieve(query)
            print("-" * 72)
            print(f"[{label}] QUERY: {query}")
            print(f"  condições identificadas: {res.diagnostics.get('identified_conditions')}")
            if res.diagnostics.get("no_conditions_identified"):
                print("  (NENHUMA condição identificada — resultado vazio, sem invenção)")
            print(f"  n_documentos: {res.n_documents}")
            preview = res.doc_ids[:10]
            print(f"  doc_ids (até 10): {preview}")
            if res.n_documents > 10:
                print(f"  ... (+{res.n_documents - 10})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

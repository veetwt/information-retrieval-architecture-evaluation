"""Teste funcional (exploratório) da arquitetura vetorial.

Executa as TRÊS formulações de cada ficha (NI-001, NI-002, NI-003) na arquitetura
vetorial, usando APENAS o texto de cada formulação (sem natureza, filtros ou gold).

Uso:
    python scripts/run_vector_prototype.py [--index-dir DIR] [--display-limit N]

Não é avaliação científica; os números de exibição são provisórios.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data.config import CorpusConfig  # noqa: E402
from evaluation.need_sheet import NeedSheet  # noqa: E402
from retrieval.vector import VectorRetriever  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-dir", default=None)
    parser.add_argument("--display-limit", type=int, default=10)
    args = parser.parse_args(argv)

    config = CorpusConfig.load(PROJECT_ROOT / "configs" / "acordaos_tcu_2024.yaml")
    index_dir = (
        Path(args.index_dir) if args.index_dir
        else PROJECT_ROOT / "embeddings" / config.batch_id
    )
    retriever = VectorRetriever.from_index_dir(index_dir, display_limit=args.display_limit)

    needs_dir = PROJECT_ROOT / "evaluation" / "questions" / "needs"
    for nid in ["NI-001", "NI-002", "NI-003"]:
        sheet = NeedSheet.from_yaml(needs_dir / f"{nid}.yaml")
        print("\n" + "=" * 72)
        print(f"{nid}  (nature={sheet.nature.value})")
        for label in ["direct", "paraphrase", "verbose"]:
            query = getattr(sheet.formulations, label)
            res = retriever.retrieve(query)
            print("-" * 72)
            print(f"[{label}] {query[:100]}{'...' if len(query) > 100 else ''}")
            if res.diagnostics.get("is_partial_index"):
                print(f"  [AVISO] índice PARCIAL: {res.diagnostics.get('n_docs_indexed')} docs")
            for d in res.documents[:5]:
                passage = d.evidence.get("passage", "")[:120]
                print(f"  #{d.rank} {d.doc_id} score={d.score:.4f} :: {passage}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

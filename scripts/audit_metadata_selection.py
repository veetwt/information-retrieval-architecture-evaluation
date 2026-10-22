"""Ponto de entrada: auditoria exploratória (somente leitura) dos metadados da
Selecao_Experimental.

Uso típico (a partir da raiz do projeto):

    python scripts/audit_metadata_selection.py \
        --config configs/acordaos_tcu_2024.yaml

Opções:
    --config PATH       Config_File YAML/TOML (default: configs/acordaos_tcu_2024.yaml).
    --parquet PATH      Parquet da seleção. Se omitido, usa o Parquet mais recente
                        em ``experimental_dir`` que casa com o batch_id.
    --reports-dir PATH  Diretório de saída do relatório (default: reports_dir do config).

O script NÃO modifica o corpus, os manifestos nem os critérios de elegibilidade;
apenas lê o Parquet e grava um relatório Markdown em reports/corpus/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite importar o pacote em src/ sem instalação (mesmo padrão dos testes).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data.config import CorpusConfig  # noqa: E402
from data.metadata_profiler import MetadataProfiler  # noqa: E402


def _latest_selection_parquet(experimental_dir: Path, batch_id: str) -> Path:
    """Retorna o Parquet de seleção mais recente para o batch_id informado."""
    pattern = f"selection_{batch_id}_*.parquet"
    candidatos = sorted(experimental_dir.glob(pattern))
    if not candidatos:
        raise FileNotFoundError(
            f"Nenhum Parquet de seleção encontrado em '{experimental_dir}' "
            f"com padrão '{pattern}'."
        )
    # Nome inclui timestamp YYYYMMDD_HHMMSS; ordenação lexicográfica = cronológica.
    return candidatos[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "configs" / "acordaos_tcu_2024.yaml"),
    )
    parser.add_argument("--parquet", default=None)
    parser.add_argument("--reports-dir", default=None)
    args = parser.parse_args(argv)

    config = CorpusConfig.load(Path(args.config))

    if not config.metadata_fields:
        print(
            "ERRO: 'metadata_fields' não declarado no Config_File; nada a perfilar.",
            file=sys.stderr,
        )
        return 2

    if args.parquet is not None:
        parquet_path = Path(args.parquet)
    else:
        parquet_path = _latest_selection_parquet(
            Path(config.experimental_dir), config.batch_id
        )

    reports_dir = (
        Path(args.reports_dir) if args.reports_dir is not None
        else Path(config.reports_dir)
    )

    profiler = MetadataProfiler(config.metadata_fields)
    result = profiler.run(parquet_path)
    report_path = profiler.save_report(result, reports_dir)

    # Resumo no stdout para rastreabilidade da execução.
    print(f"Arquivo de origem : {result.source_parquet}")
    print(f"Documentos        : {result.n_documents}")
    print(f"Fingerprint (calc): {result.fingerprint_recomputed}")
    if result.fingerprint_expected is not None:
        status = "OK" if result.fingerprint_matches else "DIVERGENTE"
        print(f"Fingerprint vs manifesto: {status}")
    else:
        print("Fingerprint vs manifesto: manifesto ausente")
    if result.config_inconsistencies:
        print("Inconsistências de configuração:")
        for item in result.config_inconsistencies:
            print(f"  - {item}")
    print(f"Relatório gravado : {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

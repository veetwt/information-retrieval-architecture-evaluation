# Feature: construcao-corpus-piloto
# Requirements: 3.1–3.9, 4.1–4.5, 8.7, 8.8, 8.9

import sys
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from data.config import CorpusConfig
from data.manifest import ManifestWriter
from data.ingestor import Ingestor
from data.auditor import (
    Auditor,
    AuditResult,
    ConditionalAnalysis,
    FieldAnalysisStatus,
    PendingManifestError,
    ProvenanceError,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def make_config(
    tmp_path: Path,
    *,
    primary_key_field: str | None = None,
    text_field: str | None = None,
    metadata_fields: list[str] | None = None,
    allowed_fields: list[str] | None = None,
) -> CorpusConfig:
    """CorpusConfig apontando para diretórios temporários."""
    if allowed_fields is None:
        allowed_fields = ["KEY", "TEXTO", "RELATOR", "ANO", "COLEGIADO"]
    return CorpusConfig(
        source_identifier="TCU-portal-publico",
        batch_id="tcu-2024-v1",
        schema_version="1.0",
        config_version="1.0",
        allowed_fields=allowed_fields,
        dataset="acordaos-tcu",
        dataset_year=2024,
        source_url="https://portal.tcu.gov.br",
        primary_key_field=primary_key_field,
        text_field=text_field,
        metadata_fields=metadata_fields,
        staging_dir=str(tmp_path / "interim"),
        raw_dir=str(tmp_path / "raw"),
        manifests_dir=str(tmp_path / "manifests"),
        reports_dir=str(tmp_path / "reports"),
    )


def make_manifest(tmp_path: Path) -> ManifestWriter:
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    return ManifestWriter(manifest_dir / "manifest.jsonl")


def write_csv(tmp_path: Path, df: pd.DataFrame, name: str = "corpus.csv") -> Path:
    """Grava um CSV de origem em tmp_path/source/<name>."""
    src = tmp_path / "source" / name
    src.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(src, index=False)
    return src


def ingest_csv(
    config: CorpusConfig, manifest: ManifestWriter, src: Path
) -> Path:
    """Ingere o CSV para data/raw/ e retorna o caminho do arquivo em raw."""
    ingestor = Ingestor(config, manifest)
    result = ingestor.ingest(src, "2026-01-15T10:00:00Z")
    assert result.status == "ingested", result.message
    return Path(config.raw_dir) / result.stored_filename


def setup_audited_corpus(
    tmp_path: Path,
    df: pd.DataFrame,
    *,
    primary_key_field: str | None = None,
    text_field: str | None = None,
    metadata_fields: list[str] | None = None,
    allowed_fields: list[str] | None = None,
) -> tuple[Auditor, Path, ManifestWriter, CorpusConfig]:
    """Prepara config + manifest + CSV ingerido + Auditor prontos para run()."""
    config = make_config(
        tmp_path,
        primary_key_field=primary_key_field,
        text_field=text_field,
        metadata_fields=metadata_fields,
        allowed_fields=allowed_fields,
    )
    manifest = make_manifest(tmp_path)
    src = write_csv(tmp_path, df)
    raw_path = ingest_csv(config, manifest, src)
    auditor = Auditor(config, manifest)
    return auditor, raw_path, manifest, config


# --------------------------------------------------------------------------- #
# Análises condicionais
# --------------------------------------------------------------------------- #

def test_duplicatas_n_menos_1(tmp_path):
    """Grupo de N registros com mesmo identificador → result == N-1. (Property 7)"""
    df = pd.DataFrame(
        {
            "KEY": ["a", "a", "a", "b", "c", "c"],  # grupo a=3, b=1, c=2
            "TEXTO": ["x"] * 6,
        }
    )
    auditor, raw_path, _, _ = setup_audited_corpus(
        tmp_path, df, primary_key_field="KEY"
    )
    result = auditor.run(raw_path)
    # duplicatas = (3-1) + (1-1) + (2-1) = 2 + 0 + 1 = 3
    assert result.duplicates_analysis.status == FieldAnalysisStatus.OK
    assert result.duplicates_analysis.result == 3


def test_documentos_sem_texto_nulo_vazio_espacos(tmp_path):
    """Nulo, "", "   ", "\\t" → todos contabilizados como Documento_Sem_Texto. (Property 9)"""
    df = pd.DataFrame(
        {
            "KEY": ["1", "2", "3", "4", "5", "6"],
            "TEXTO": ["conteudo real", None, "", "   ", "\t", "\n"],
        }
    )
    auditor, raw_path, _, _ = setup_audited_corpus(
        tmp_path, df, primary_key_field="KEY", text_field="TEXTO"
    )
    result = auditor.run(raw_path)
    assert result.docs_without_text.status == FieldAnalysisStatus.OK
    # 5 registros sem texto (todos exceto o primeiro)
    assert result.docs_without_text.result["count"] == 5


def test_distribuicao_tamanho_texto(tmp_path):
    """text_field configurado e presente → métricas calculadas com status OK."""
    df = pd.DataFrame(
        {
            "KEY": ["1", "2", "3"],
            "TEXTO": ["ab", "abcd", "abcdef"],  # comprimentos 2, 4, 6
        }
    )
    auditor, raw_path, _, _ = setup_audited_corpus(
        tmp_path, df, primary_key_field="KEY", text_field="TEXTO"
    )
    result = auditor.run(raw_path)
    r = result.text_length_analysis.result
    assert result.text_length_analysis.status == FieldAnalysisStatus.OK
    assert r["min"] == 2
    assert r["max"] == 6
    assert r["mean"] == 4.0
    assert r["median"] == 4.0


def test_auditoria_estrutural_sem_config(tmp_path):
    """Sem primary_key_field/text_field/metadata_fields → condicionais NOT_CONFIGURED."""
    df = pd.DataFrame({"KEY": ["1", "2"], "TEXTO": ["a", "b"]})
    auditor, raw_path, _, _ = setup_audited_corpus(tmp_path, df)
    result = auditor.run(raw_path)

    assert result.n_rows == 2
    assert result.n_cols == 2
    assert result.duplicates_analysis.status == FieldAnalysisStatus.NOT_CONFIGURED
    assert result.text_length_analysis.status == FieldAnalysisStatus.NOT_CONFIGURED
    assert result.docs_without_text.status == FieldAnalysisStatus.NOT_CONFIGURED
    assert result.metadata_coverage.status == FieldAnalysisStatus.NOT_CONFIGURED
    # result é None (nunca 0) para análises não executadas
    assert result.duplicates_analysis.result is None
    assert result.text_length_analysis.result is None


def test_campo_configurado_ausente_no_dataset(tmp_path):
    """primary_key_field configurado mas ausente → FIELD_MISSING + config_inconsistencies."""
    df = pd.DataFrame({"OUTRO": ["1", "2"], "TEXTO": ["a", "b"]})
    auditor, raw_path, _, _ = setup_audited_corpus(
        tmp_path, df, primary_key_field="KEY", allowed_fields=["KEY", "TEXTO", "OUTRO"]
    )
    result = auditor.run(raw_path)

    assert result.duplicates_analysis.status == FieldAnalysisStatus.FIELD_MISSING
    assert any("KEY" in msg for msg in result.config_inconsistencies)
    # Análises estruturais continuam normais
    assert result.n_rows == 2
    assert "OUTRO" in result.column_names


def test_metadata_coverage_ok(tmp_path):
    """metadata_fields presentes → cobertura calculada por campo."""
    df = pd.DataFrame(
        {
            "KEY": ["1", "2", "3", "4"],
            "RELATOR": ["r1", None, "r3", "   "],  # 2 preenchidos de 4 = 50%
        }
    )
    auditor, raw_path, _, _ = setup_audited_corpus(
        tmp_path,
        df,
        primary_key_field="KEY",
        metadata_fields=["RELATOR"],
        allowed_fields=["KEY", "RELATOR"],
    )
    result = auditor.run(raw_path)
    assert result.metadata_coverage.status == FieldAnalysisStatus.OK
    assert result.metadata_coverage.result["coverage_pct"]["RELATOR"] == 50.00


# --------------------------------------------------------------------------- #
# Cobertura estrutural
# --------------------------------------------------------------------------- #

def test_cobertura_intervalo_e_valor(tmp_path):
    """Cobertura por coluna em [0.00, 100.00] com valor esperado."""
    df = pd.DataFrame(
        {
            "KEY": ["1", "2", "3", "4"],       # 100%
            "TEXTO": ["a", None, "", "d"],     # 2 de 4 = 50%
        }
    )
    auditor, raw_path, _, _ = setup_audited_corpus(tmp_path, df)
    result = auditor.run(raw_path)
    assert result.coverage_pct["KEY"] == 100.00
    assert result.coverage_pct["TEXTO"] == 50.00
    for pct in result.coverage_pct.values():
        assert 0.00 <= pct <= 100.00


# --------------------------------------------------------------------------- #
# Bloqueio por proveniência e pending
# --------------------------------------------------------------------------- #

def test_arquivo_sem_manifest_bloqueia_auditor(tmp_path):
    """Arquivo em data/raw/ sem entrada no Manifest → ProvenanceError(provenance_missing)."""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    # Gravar arquivo diretamente em raw sem passar pelo Ingestor
    raw_dir = Path(config.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    orphan = raw_dir / "orfao.csv"
    pd.DataFrame({"KEY": ["1"]}).to_csv(orphan, index=False)

    auditor = Auditor(config, manifest)
    with pytest.raises(ProvenanceError) as exc:
        auditor.run(orphan)
    assert exc.value.reason == "provenance_missing"
    # Nenhum relatório produzido
    assert not Path(config.reports_dir).exists() or not any(
        Path(config.reports_dir).iterdir()
    )


def test_hash_divergente_manifest_bloqueia_auditor(tmp_path):
    """SHA-256 atual diverge do registrado → ProvenanceError(integrity_mismatch)."""
    df = pd.DataFrame({"KEY": ["1", "2"], "TEXTO": ["a", "b"]})
    auditor, raw_path, _, config = setup_audited_corpus(tmp_path, df)

    # Corromper o arquivo em data/raw/ após a ingestão
    raw_path.write_text("KEY,TEXTO\n9,corrompido\n", encoding="utf-8")

    with pytest.raises(ProvenanceError) as exc:
        auditor.run(raw_path)
    assert exc.value.reason == "integrity_mismatch"


def test_pending_manifest_bloqueia_auditor(tmp_path):
    """pending.jsonl com entrada → PendingManifestError; nenhuma análise."""
    df = pd.DataFrame({"KEY": ["1"], "TEXTO": ["a"]})
    auditor, raw_path, manifest, _ = setup_audited_corpus(tmp_path, df)

    manifest.append_pending_entry({
        "original_filename": "x.csv",
        "stored_filename": "x.csv",
        "downloaded_at": "2026-01-01T00:00:00Z",
        "ingested_at": "2026-01-01T00:00:01Z",
        "file_size_bytes": 10,
        "sha256": "c" * 64,
        "source_url": "https://portal.tcu.gov.br",
        "source_identifier": "TCU-portal-publico",
        "dataset": "acordaos-tcu",
        "dataset_year": 2024,
        "schema_version": "1.0",
        "batch_id": "tcu-2024-v1",
    })

    with pytest.raises(PendingManifestError):
        auditor.run(raw_path)


def test_corpus_inexistente_levanta_filenotfound(tmp_path):
    """corpus_path inexistente → FileNotFoundError."""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    auditor = Auditor(config, manifest)
    with pytest.raises(FileNotFoundError):
        auditor.run(Path(config.raw_dir) / "nao_existe.csv")


# --------------------------------------------------------------------------- #
# Persistência dos relatórios
# --------------------------------------------------------------------------- #

def test_cinco_outputs_produzidos_sem_config_semantico(tmp_path):
    """Auditoria sem config semântica → 5 arquivos produzidos; sem 0 para não executada."""
    df = pd.DataFrame({"KEY": ["1", "2"], "TEXTO": ["a", "b"]})
    auditor, raw_path, _, config = setup_audited_corpus(tmp_path, df)
    result = auditor.run(raw_path)
    paths = auditor.save_reports(result, Path(config.reports_dir))

    assert set(paths.keys()) == {
        "raw_summary",
        "column_profile",
        "text_length_profile",
        "sample_records",
        "audit_report",
    }
    for p in paths.values():
        assert p.exists()

    import json
    summary = json.loads(paths["raw_summary"].read_text(encoding="utf-8"))
    # análises não executadas: status not_configured e result None (nunca 0)
    assert summary["duplicates_analysis"]["status"] == "not_configured"
    assert summary["duplicates_analysis"]["result"] is None
    assert summary["text_length_analysis"]["result"] is None


def test_save_reports_cria_diretorio(tmp_path):
    """reports_dir inexistente → criado; arquivos gravados sem erro."""
    df = pd.DataFrame({"KEY": ["1"], "TEXTO": ["a"]})
    auditor, raw_path, _, config = setup_audited_corpus(tmp_path, df)
    result = auditor.run(raw_path)

    reports_dir = Path(config.reports_dir) / "subdir_novo"
    assert not reports_dir.exists()
    paths = auditor.save_reports(result, reports_dir)
    assert reports_dir.exists()
    for p in paths.values():
        assert p.exists()


def test_save_reports_nao_sobrescreve(tmp_path):
    """save_reports duas vezes → segundo conjunto com sufixo de timestamp; primeiro intacto."""
    df = pd.DataFrame({"KEY": ["1", "2"], "TEXTO": ["a", "b"]})
    auditor, raw_path, _, config = setup_audited_corpus(tmp_path, df)
    result = auditor.run(raw_path)
    reports_dir = Path(config.reports_dir)

    paths1 = auditor.save_reports(result, reports_dir)
    conteudo_original = paths1["raw_summary"].read_text(encoding="utf-8")

    paths2 = auditor.save_reports(result, reports_dir)

    # O segundo conjunto não pode reutilizar exatamente os mesmos caminhos
    assert paths2["raw_summary"] != paths1["raw_summary"]
    assert paths2["raw_summary"].exists()
    # Primeiro arquivo permanece inalterado
    assert paths1["raw_summary"].read_text(encoding="utf-8") == conteudo_original


def test_sample_records_dataset_vazio_so_header(tmp_path):
    """Dataset vazio → sample_records.csv com apenas header, zero linhas de dados."""
    df = pd.DataFrame({"KEY": [], "TEXTO": []})
    auditor, raw_path, _, config = setup_audited_corpus(tmp_path, df)
    result = auditor.run(raw_path)
    assert result.n_rows == 0
    paths = auditor.save_reports(result, Path(config.reports_dir))

    sample = pd.read_csv(paths["sample_records"])
    assert len(sample) == 0


def test_text_length_profile_status_quando_nao_configurado(tmp_path):
    """text_length_profile.csv indica status explícito quando não configurado."""
    df = pd.DataFrame({"KEY": ["1"], "TEXTO": ["a"]})
    auditor, raw_path, _, config = setup_audited_corpus(tmp_path, df)
    result = auditor.run(raw_path)
    paths = auditor.save_reports(result, Path(config.reports_dir))

    perfil = pd.read_csv(paths["text_length_profile"])
    assert "status" in perfil.columns
    assert perfil.iloc[0]["status"] == "not_configured"


# --------------------------------------------------------------------------- #
# Suporte a campos CSV grandes
# --------------------------------------------------------------------------- #

def test_campo_csv_grande_e_lido_sem_erro(tmp_path):
    """Campo textual muito grande (> limite padrão do csv) é lido sem erro."""
    texto_grande = "x" * 200_000  # excede o field_size_limit padrão (131072)
    df = pd.DataFrame({"KEY": ["1", "2"], "TEXTO": [texto_grande, "pequeno"]})
    auditor, raw_path, _, _ = setup_audited_corpus(
        tmp_path, df, primary_key_field="KEY", text_field="TEXTO"
    )
    result = auditor.run(raw_path)
    assert result.n_rows == 2
    assert result.text_length_analysis.result["max"] == 200_000


# --------------------------------------------------------------------------- #
# Property test — cobertura sempre em [0, 100]
# --------------------------------------------------------------------------- #

@given(
    n_rows=st.integers(min_value=1, max_value=30),
    fill_ratio=st.floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property_cobertura_intervalo_valido(tmp_path_factory, n_rows, fill_ratio):
    """
    Feature: construcao-corpus-piloto
    Property 6: Intervalo válido de cobertura por coluna

    **Validates: Requirements 3.3**

    Para qualquer DataFrame com pelo menos uma linha, coverage_pct[col] ∈ [0.00, 100.00].
    """
    # Diretório único por exemplo: evita colisão de conteúdo (duplicate_content)
    # entre execuções sucessivas do Hypothesis sobre o mesmo fixture.
    tmp_path = tmp_path_factory.mktemp("prop_cobertura")
    n_fill = int(round(n_rows * fill_ratio))
    valores = ["conteudo"] * n_fill + [None] * (n_rows - n_fill)
    df = pd.DataFrame({"KEY": [str(i) for i in range(n_rows)], "TEXTO": valores})

    auditor, raw_path, _, _ = setup_audited_corpus(tmp_path, df)
    result = auditor.run(raw_path)
    for pct in result.coverage_pct.values():
        assert 0.00 <= pct <= 100.00

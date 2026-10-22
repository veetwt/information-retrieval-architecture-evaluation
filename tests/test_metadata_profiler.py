# Feature: auditoria-exploratoria-metadados (Selecao_Experimental)
# Valida a rotina MetadataProfiler: perfis diagnósticos, distinção
# nulo/vazio/bruto/normalizado, campos multivalorados, outlier e verificação
# de fingerprint contra o manifesto. Somente leitura; não altera o corpus.

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from data.metadata_profiler import (  # noqa: E402
    MetadataProfiler,
    normalize_for_diagnostic,
    profile_field,
)
from utils.hashing import compute_dataset_fingerprint  # noqa: E402


# --------------------------------------------------------------------------- #
# normalize_for_diagnostic
# --------------------------------------------------------------------------- #

def test_normalize_strips_collapses_drops_dot_and_casefolds():
    assert normalize_for_diagnostic("  Ministério  da Saúde. ") == "ministério da saúde"
    assert normalize_for_diagnostic("Plenário") == "plenário"


def test_normalize_distinguishes_only_formatting():
    # Dois valores que diferem apenas por espaço/ponto/caixa colapsam para o mesmo.
    a = normalize_for_diagnostic(" Comando da Marinha. ")
    b = normalize_for_diagnostic("COMANDO DA MARINHA")
    assert a == b


# --------------------------------------------------------------------------- #
# profile_field — distinção nulo / vazio / bruto / normalizado
# --------------------------------------------------------------------------- #

def test_profile_field_distinguishes_null_from_empty():
    s = pd.Series(["Plenário", None, "   ", "Plenário", ""])
    p = profile_field(s, "COLEGIADO", n_total=len(s))
    assert p.null_count == 1               # apenas o None
    assert p.empty_count == 2              # "   " e ""
    assert p.missing_count == 3
    assert p.distinct_raw == 1             # só "Plenário" é valor presente
    # cobertura = presentes (2) / total (5) * 100
    assert p.coverage_pct == 40.00


def test_profile_field_raw_vs_normalized_distinct():
    # Mesma entidade com variações de espaço/ponto/caixa: 3 brutos, 1 normalizado.
    s = pd.Series([
        "Ministério da Saúde.",
        " Ministério da Saúde. ",
        "MINISTÉRIO DA SAÚDE",
    ])
    p = profile_field(s, "ENTIDADE", n_total=len(s))
    assert p.distinct_raw == 3
    assert p.distinct_normalized == 1
    assert p.leading_trailing_ws_count == 1   # só o valor com espaço nas bordas
    assert p.trailing_dot_count == 2


def test_profile_field_multivalue_detection():
    s = pd.Series([
        "AudRecursos; AudTCE.",
        "AudPessoal.",
        "AudA; AudB; AudC",
    ])
    p = profile_field(s, "UNIDADETECNICA", n_total=len(s))
    assert p.multivalue_count == 2


def test_profile_field_rare_value_outlier():
    s = pd.Series(["A"] * 5 + ["B"] * 5 + ["C"])  # C é singleton
    p = profile_field(s, "RELATOR", n_total=len(s))
    assert p.rare_values_total == 1
    assert p.rare_values[0] == ("C", 1)


def test_profile_field_does_not_mutate_input():
    s = pd.Series(["X", None, " Y "])
    before = s.copy()
    profile_field(s, "F", n_total=len(s))
    pd.testing.assert_series_equal(s, before)


def test_profile_field_empty_series():
    s = pd.Series([None, None], dtype="object")
    p = profile_field(s, "F", n_total=len(s))
    assert p.null_count == 2
    assert p.distinct_raw == 0
    assert p.coverage_pct == 0.00


# --------------------------------------------------------------------------- #
# MetadataProfiler.run — verificação de fingerprint e perfis
# --------------------------------------------------------------------------- #

CANONICAL_COLUMNS = [
    "doc_id", "source_key", "COLEGIADO", "RELATOR",
    "TIPOPROCESSO", "DATASESSAO", "ENTIDADE", "UNIDADETECNICA",
]

META = ["COLEGIADO", "RELATOR", "TIPOPROCESSO", "DATASESSAO", "ENTIDADE", "UNIDADETECNICA"]


def _make_selection(tmp_path: Path, with_manifest: bool = True) -> Path:
    df = pd.DataFrame({
        "doc_id": ["d1", "d2", "d3"],
        "source_key": ["k1", "k2", "k3"],
        "COLEGIADO": ["Plenário", "Plenário", "Segunda Câmara"],
        "RELATOR": ["X", "X", "Y"],
        "TIPOPROCESSO": ["REPR", None, "APOS"],
        "DATASESSAO": ["05/03/2024", "06/03/2024", "05/03/2024"],
        "ENTIDADE": [" Órgão A. ", "Órgão A.", "Órgão B; Órgão C."],
        "UNIDADETECNICA": ["AudA.", "AudA; AudB.", "AudC."],
    })[CANONICAL_COLUMNS]
    parquet = tmp_path / "selection_test-v1_20260101_000000.parquet"
    df.to_parquet(parquet, engine="pyarrow", index=False)
    if with_manifest:
        fp = compute_dataset_fingerprint(df, sort_col="doc_id")
        manifest = parquet.parent / f"{parquet.stem}_manifest.json"
        manifest.write_text(
            json.dumps({
                "selection_fingerprint": fp,
                "config_version": "1.0",
                "eligibility_policy_version": "1.0",
            }),
            encoding="utf-8",
        )
    return parquet


def test_run_fingerprint_matches_manifest(tmp_path):
    parquet = _make_selection(tmp_path, with_manifest=True)
    result = MetadataProfiler(META).run(parquet)
    assert result.n_documents == 3
    assert result.fingerprint_matches is True
    assert result.fingerprint_recomputed == result.fingerprint_expected
    assert [p.name for p in result.profiles] == META


def test_run_detects_fingerprint_mismatch(tmp_path):
    parquet = _make_selection(tmp_path, with_manifest=True)
    # Corromper o manifesto para simular divergência (não toca no Parquet).
    manifest = parquet.parent / f"{parquet.stem}_manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["selection_fingerprint"] = "0" * 64
    manifest.write_text(json.dumps(data), encoding="utf-8")
    result = MetadataProfiler(META).run(parquet)
    assert result.fingerprint_matches is False


def test_run_without_manifest_sets_match_none(tmp_path):
    parquet = _make_selection(tmp_path, with_manifest=False)
    result = MetadataProfiler(META).run(parquet)
    assert result.fingerprint_expected is None
    assert result.fingerprint_matches is None


def test_run_flags_missing_configured_field(tmp_path):
    parquet = _make_selection(tmp_path, with_manifest=True)
    result = MetadataProfiler(META + ["CAMPO_INEXISTENTE"]).run(parquet)
    assert any("CAMPO_INEXISTENTE" in m for m in result.config_inconsistencies)
    # O campo ausente não gera perfil.
    assert "CAMPO_INEXISTENTE" not in [p.name for p in result.profiles]


def test_run_missing_parquet_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        MetadataProfiler(META).run(tmp_path / "nao_existe.parquet")


# --------------------------------------------------------------------------- #
# save_report — escrita Markdown sem sobrescrita
# --------------------------------------------------------------------------- #

def test_save_report_writes_markdown(tmp_path):
    parquet = _make_selection(tmp_path, with_manifest=True)
    profiler = MetadataProfiler(META)
    result = profiler.run(parquet)
    reports_dir = tmp_path / "reports" / "corpus"
    path = profiler.save_report(result, reports_dir)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Auditoria de Metadados" in text
    assert "selection_fingerprint" in text
    assert "COLEGIADO" in text


def test_save_report_does_not_overwrite(tmp_path):
    parquet = _make_selection(tmp_path, with_manifest=True)
    profiler = MetadataProfiler(META)
    result = profiler.run(parquet)
    reports_dir = tmp_path / "reports" / "corpus"
    p1 = profiler.save_report(result, reports_dir)
    p2 = profiler.save_report(result, reports_dir)
    assert p1 != p2
    assert p1.exists() and p2.exists()

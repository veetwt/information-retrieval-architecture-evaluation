# Feature: construcao-corpus-piloto
# Requirements: 10.1–10.16

import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from data.config import CorpusConfig
from data.seletor import SeletorExperimental, SelectionResult, FingerprintMismatchError
from utils.hashing import compute_dataset_fingerprint

CANONICAL_COLUMNS = [
    "doc_id", "source_key", "ASSUNTO", "ACORDAO", "COLEGIADO", "RELATOR",
    "TIPOPROCESSO", "DATASESSAO", "ENTIDADE", "UNIDADETECNICA",
    "SUMARIO", "RELATORIO", "VOTO",
]

SIGILO = "Documento classificado como sigiloso com fundamento no art. X"


def make_config(tmp_path: Path) -> CorpusConfig:
    """Config sintética com política de elegibilidade declarada."""
    return CorpusConfig(
        source_identifier="TCU-portal-publico",
        batch_id="tcu-test-v1",
        schema_version="1.0",
        config_version="1.0",
        allowed_fields=CANONICAL_COLUMNS,  # inclui doc_id/source_key só para validação simples
        dataset="acordaos-tcu",
        dataset_year=2024,
        source_url="https://portal.tcu.gov.br",
        experimental_eligibility={
            "eligibility_policy_version": "1.0",
            "required_text_fields": ["ACORDAO", "ASSUNTO"],
            "forbidden_exact_values": {"ASSUNTO": ["SIGILOSO"]},
            "sigilo_placeholder": {
                "field": "ACORDAO",
                "match": "prefix",
                "patterns": ["Documento classificado como sigiloso"],
            },
        },
        staging_dir=str(tmp_path / "interim"),
        processed_dir=str(tmp_path / "processed" / "original"),
        experimental_dir=str(tmp_path / "processed" / "experimental"),
    )


def write_canonical(tmp_path: Path, df: pd.DataFrame) -> Path:
    """Escreve um Parquet canônico sintético + sidecar com dataset_fingerprint correto.

    Retorna o caminho do Parquet.
    """
    original_dir = tmp_path / "processed" / "original"
    original_dir.mkdir(parents=True, exist_ok=True)
    # Garantir ordem canônica das colunas
    df = df[CANONICAL_COLUMNS].reset_index(drop=True)
    parquet = original_dir / "corpus_tcu-test-v1_20260101_000000.parquet"
    df.to_parquet(parquet, engine="pyarrow", index=False)
    fp = compute_dataset_fingerprint(df, sort_col="doc_id")
    sidecar = original_dir / f"{parquet.stem}_metadata.json"
    sidecar.write_text(json.dumps({"dataset_fingerprint": fp}), encoding="utf-8")
    return parquet


def doc(key, *, assunto="assunto ok", acordao="acordao ok", **meta):
    """Constrói uma linha canônica sintética. doc_id derivado do key para simplicidade."""
    import hashlib
    doc_id = "tcu-" + hashlib.sha256(str(key).encode()).hexdigest()[:12]
    base = {c: None for c in CANONICAL_COLUMNS}
    base["doc_id"] = doc_id
    base["source_key"] = str(key)
    base["ASSUNTO"] = assunto
    base["ACORDAO"] = acordao
    base.update(meta)
    return base


def build(tmp_path, rows: list[dict]) -> tuple[SeletorExperimental, Path, CorpusConfig]:
    df = pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
    config = make_config(tmp_path)
    parquet = write_canonical(tmp_path, df)
    return SeletorExperimental(config), parquet, config


# --------------------------------------------------------------------------- #
# Critérios de inelegibilidade
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("acordao", [None, "", "   ", "\t", "\n"])
def test_acordao_nulo_vazio_espacos_inelegivel(tmp_path, acordao):
    seletor, parquet, _ = build(tmp_path, [doc("A", acordao=acordao)])
    result = seletor.run(parquet)
    assert result.n_eligible == 0
    assert result.ineligible_log[0]["reasons"] == ["acordao_null_or_empty"]


def test_acordao_apenas_placeholder_sigilo_inelegivel(tmp_path):
    seletor, parquet, _ = build(tmp_path, [doc("A", acordao=SIGILO)])
    result = seletor.run(parquet)
    assert result.n_eligible == 0
    assert result.ineligible_log[0]["reasons"] == ["acordao_sigilo_placeholder"]


def test_acordao_placeholder_com_html_ainda_detectado(tmp_path):
    """Placeholder envolto em HTML é detectado após normalização de elegibilidade."""
    seletor, parquet, _ = build(tmp_path, [doc("A", acordao=f"<p>  {SIGILO} </p>")])
    result = seletor.run(parquet)
    assert result.ineligible_log[0]["reasons"] == ["acordao_sigilo_placeholder"]


@pytest.mark.parametrize("assunto", [None, "", "   "])
def test_assunto_nulo_vazio_inelegivel(tmp_path, assunto):
    seletor, parquet, _ = build(tmp_path, [doc("A", assunto=assunto)])
    result = seletor.run(parquet)
    assert result.n_eligible == 0
    assert result.ineligible_log[0]["reasons"] == ["assunto_null_or_empty"]


def test_assunto_sigiloso_exato_inelegivel(tmp_path):
    seletor, parquet, _ = build(tmp_path, [doc("A", assunto="SIGILOSO")])
    result = seletor.run(parquet)
    assert result.n_eligible == 0
    assert result.ineligible_log[0]["reasons"] == ["assunto_forbidden_value"]


def test_documento_valido_elegivel(tmp_path):
    seletor, parquet, _ = build(tmp_path, [doc("A", assunto="tema x", acordao="<p>decisao</p>")])
    result = seletor.run(parquet)
    assert result.n_eligible == 1
    assert result.n_ineligible == 0
    assert result.ineligible_log == []


def test_metadado_ausente_permanece_elegivel(tmp_path):
    """Documento sem ENTIDADE/UNIDADETECNICA/etc. continua elegível."""
    seletor, parquet, _ = build(tmp_path, [
        doc("A", assunto="tema", acordao="decisao", COLEGIADO=None, RELATOR=None,
            ENTIDADE=None, UNIDADETECNICA=None),
    ])
    result = seletor.run(parquet)
    assert result.n_eligible == 1
    assert result.n_ineligible == 0


def test_multiplos_criterios_registra_todos_reasons_ordenados(tmp_path):
    """ACORDAO placeholder + ASSUNTO proibido → ambos os reasons em ordem canônica."""
    seletor, parquet, _ = build(tmp_path, [doc("A", assunto="SIGILOSO", acordao=SIGILO)])
    result = seletor.run(parquet)
    assert result.ineligible_log[0]["reasons"] == [
        "acordao_sigilo_placeholder", "assunto_forbidden_value",
    ]


def test_acordao_vazio_e_assunto_vazio_ambos_reasons(tmp_path):
    seletor, parquet, _ = build(tmp_path, [doc("A", assunto="", acordao="")])
    result = seletor.run(parquet)
    assert result.ineligible_log[0]["reasons"] == [
        "acordao_null_or_empty", "assunto_null_or_empty",
    ]


# --------------------------------------------------------------------------- #
# Preservação de colunas / valores / HTML
# --------------------------------------------------------------------------- #

def test_preserva_13_colunas_ordem_e_valores(tmp_path):
    html = '<p class="x">Trata-se de <b>auditoria</b></p>'
    seletor, parquet, _ = build(tmp_path, [
        doc("A", assunto="tema a", acordao=html, COLEGIADO="Plenário", RELATOR="r1",
            SUMARIO="sum", RELATORIO="rel", VOTO="v"),
        doc("B", assunto="tema b", acordao="decisao b"),
    ])
    result = seletor.run(parquet)
    sel = pd.read_parquet(result.parquet_path)
    assert list(sel.columns) == CANONICAL_COLUMNS
    assert len(sel) == 2
    # HTML original preservado byte a byte
    a = sel[sel["source_key"] == "A"].iloc[0]
    assert a["ACORDAO"] == html


def test_nenhuma_coluna_de_elegibilidade_adicionada(tmp_path):
    seletor, parquet, _ = build(tmp_path, [doc("A")])
    result = seletor.run(parquet)
    sel = pd.read_parquet(result.parquet_path)
    assert list(sel.columns) == CANONICAL_COLUMNS
    assert "eligible" not in sel.columns
    assert "reasons" not in sel.columns


# --------------------------------------------------------------------------- #
# Fingerprints
# --------------------------------------------------------------------------- #

def test_fingerprint_canonico_validado_antes_da_selecao(tmp_path):
    """Sidecar com fingerprint divergente → FingerprintMismatchError; nenhum artefato."""
    seletor, parquet, config = build(tmp_path, [doc("A"), doc("B")])
    # Corromper o sidecar
    sidecar = parquet.parent / f"{parquet.stem}_metadata.json"
    sidecar.write_text(json.dumps({"dataset_fingerprint": "0" * 64}), encoding="utf-8")

    with pytest.raises(FingerprintMismatchError):
        seletor.run(parquet)
    exp_dir = Path(config.experimental_dir)
    assert not exp_dir.exists() or not any(exp_dir.glob("*.parquet"))


def test_selection_fingerprint_determinístico(tmp_path):
    """Mesmo canônico + mesma política → mesmo selection_fingerprint em duas execuções."""
    rows = [doc("A"), doc("B", acordao=""), doc("C", assunto="SIGILOSO")]
    s1, p1, _ = build(tmp_path / "a", rows)
    s2, p2, _ = build(tmp_path / "b", rows)
    r1 = s1.run(p1)
    r2 = s2.run(p2)
    assert r1.selection_fingerprint == r2.selection_fingerprint


def test_manifest_registra_ambos_fingerprints_e_contagens(tmp_path):
    seletor, parquet, _ = build(tmp_path, [doc("A"), doc("B", acordao=""), doc("C")])
    result = seletor.run(parquet)
    meta = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert meta["source_parquet"] == parquet.name
    assert len(meta["source_dataset_fingerprint"]) == 64
    assert meta["selection_fingerprint"] == result.selection_fingerprint
    assert meta["config_version"] == "1.0"
    assert meta["eligibility_policy_version"] == "1.0"
    assert meta["n_total"] == 3
    assert meta["n_eligible"] == 2
    assert meta["n_ineligible"] == 1
    assert "eligibility_policy" in meta
    assert "created_at" in meta


# --------------------------------------------------------------------------- #
# ineligible.jsonl / reconciliação
# --------------------------------------------------------------------------- #

def test_ineligible_jsonl_sempre_produzido_mesmo_vazio(tmp_path):
    seletor, parquet, _ = build(tmp_path, [doc("A"), doc("B")])  # ambos elegíveis
    result = seletor.run(parquet)
    assert result.ineligible_log_path.exists()
    linhas = [l for l in result.ineligible_log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert linhas == []


def test_ineligible_jsonl_contem_doc_id_source_key_reasons(tmp_path):
    seletor, parquet, _ = build(tmp_path, [doc("A", acordao="")])
    result = seletor.run(parquet)
    linha = json.loads(result.ineligible_log_path.read_text(encoding="utf-8").splitlines()[0])
    assert linha["source_key"] == "A"
    assert linha["doc_id"].startswith("tcu-")
    assert linha["reasons"] == ["acordao_null_or_empty"]


def test_reconciliacao(tmp_path):
    rows = [doc("A"), doc("B", acordao=""), doc("C", assunto="SIGILOSO"), doc("D")]
    seletor, parquet, _ = build(tmp_path, rows)
    result = seletor.run(parquet)
    assert result.n_eligible + result.n_ineligible == result.n_total == 4


@given(n=st.integers(min_value=1, max_value=25), seed=st.integers(min_value=0, max_value=5))
@settings(max_examples=40, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])
def test_property_reconciliacao(tmp_path_factory, n, seed):
    """
    Feature: construcao-corpus-piloto
    Property: Reconciliação total da seleção experimental
    **Validates: Requirement 10.12**
    """
    tmp_path = tmp_path_factory.mktemp("sel_recon")
    variantes = [
        lambda k: doc(k),
        lambda k: doc(k, acordao=""),
        lambda k: doc(k, assunto="SIGILOSO"),
        lambda k: doc(k, acordao=SIGILO),
        lambda k: doc(k, assunto="  "),
    ]
    rows = [variantes[(i + seed) % len(variantes)](f"K{i}") for i in range(n)]
    seletor, parquet, _ = build(tmp_path, rows)
    result = seletor.run(parquet)
    assert result.n_eligible + result.n_ineligible == result.n_total == n


# --------------------------------------------------------------------------- #
# Imutabilidade do canônico / publicação atômica / não sobrescrita / vazio
# --------------------------------------------------------------------------- #

def test_canonico_nao_modificado(tmp_path):
    seletor, parquet, _ = build(tmp_path, [doc("A"), doc("B", acordao="")])
    antes = parquet.read_bytes()
    seletor.run(parquet)
    assert parquet.read_bytes() == antes


def test_nao_sobrescreve_selecao_existente(tmp_path):
    import time
    seletor, parquet, _ = build(tmp_path, [doc("A")])
    r1 = seletor.run(parquet)
    conteudo1 = r1.parquet_path.read_bytes()
    time.sleep(1.1)
    r2 = seletor.run(parquet)
    assert r2.parquet_path != r1.parquet_path
    assert r1.parquet_path.exists()
    assert r1.parquet_path.read_bytes() == conteudo1


def test_publicacao_produz_tres_artefatos_e_interim_limpo(tmp_path):
    seletor, parquet, config = build(tmp_path, [doc("A"), doc("B", acordao="")])
    result = seletor.run(parquet)
    assert result.parquet_path.exists()
    assert result.manifest_path.exists()
    assert result.ineligible_log_path.exists()
    # interim limpo
    interim = Path(config.staging_dir)
    if interim.exists():
        assert not any(interim.iterdir())


def test_corpus_vazio(tmp_path):
    df_vazio = pd.DataFrame({c: [] for c in CANONICAL_COLUMNS})
    config = make_config(tmp_path)
    parquet = write_canonical(tmp_path, df_vazio)
    seletor = SeletorExperimental(config)
    result = seletor.run(parquet)
    assert result.n_total == 0
    assert result.n_eligible == 0
    assert result.n_ineligible == 0
    sel = pd.read_parquet(result.parquet_path)
    assert len(sel) == 0
    assert list(sel.columns) == CANONICAL_COLUMNS
    # ineligible vazio mas presente
    assert result.ineligible_log_path.exists()


def test_valor_persistido_inalterado_apesar_da_normalizacao(tmp_path):
    """ACORDAO com HTML/espaços é elegível; valor gravado permanece o original."""
    original = "  <p>Decisão   com   espacos</p>  "
    seletor, parquet, _ = build(tmp_path, [doc("A", acordao=original)])
    result = seletor.run(parquet)
    sel = pd.read_parquet(result.parquet_path)
    assert sel["ACORDAO"].iloc[0] == original  # inalterado, não normalizado

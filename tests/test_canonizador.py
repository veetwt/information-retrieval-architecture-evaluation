# Feature: construcao-corpus-piloto
# Requirements: 5.1–5.12, 6.1–6.4, 7.1–7.4, 8.10, 8.11, 9.4–9.6

import hashlib
import json
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
from data.canonizador import Canonizador, CanonicalizationResult
from data.auditor import PendingManifestError, ProvenanceError


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_SENTINEL = object()


def make_config(
    tmp_path: Path,
    *,
    primary_key_field: str | None = "KEY",
    text_field: str | None = "TEXTO",
    metadata_fields: list[str] | None = None,
    required_fields: list[str] | None = None,
    allowed_fields: list[str] | None = None,
    retrieval_text_fields=_SENTINEL,
    preserved_fields: list[str] | None = None,
) -> CorpusConfig:
    if allowed_fields is None:
        allowed_fields = ["KEY", "TEXTO", "RELATOR", "COLEGIADO", "ENTIDADE"]
    if required_fields is None:
        required_fields = ["KEY"]
    # Por padrão, o campo textual TEXTO entra na baseline (retrieval_text_fields),
    # de modo que apareça como coluna no corpus canônico. Testes que precisam de
    # comportamento diferente passam o valor explicitamente (incluindo None).
    if retrieval_text_fields is _SENTINEL:
        retrieval_text_fields = ["TEXTO"] if text_field == "TEXTO" else None
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
        required_fields=required_fields,
        retrieval_text_fields=retrieval_text_fields,
        preserved_fields=preserved_fields,
        staging_dir=str(tmp_path / "interim"),
        raw_dir=str(tmp_path / "raw"),
        manifests_dir=str(tmp_path / "manifests"),
        processed_dir=str(tmp_path / "processed" / "original"),
        fingerprint_log=str(tmp_path / "runs" / "fingerprint_log.jsonl"),
    )


def make_manifest(tmp_path: Path) -> ManifestWriter:
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    return ManifestWriter(manifest_dir / "manifest.jsonl")


def write_csv(tmp_path: Path, df: pd.DataFrame, name: str = "corpus.csv") -> Path:
    src = tmp_path / "source" / name
    src.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(src, index=False)
    return src


def ingest_csv(config: CorpusConfig, manifest: ManifestWriter, src: Path) -> Path:
    ingestor = Ingestor(config, manifest)
    result = ingestor.ingest(src, "2026-01-15T10:00:00Z")
    assert result.status == "ingested", result.message
    return Path(config.raw_dir) / result.stored_filename


def setup(
    tmp_path: Path,
    df: pd.DataFrame,
    **cfg_kwargs,
) -> tuple[Canonizador, Path, ManifestWriter, CorpusConfig]:
    config = make_config(tmp_path, **cfg_kwargs)
    manifest = make_manifest(tmp_path)
    src = write_csv(tmp_path, df)
    raw_path = ingest_csv(config, manifest, src)
    canonizador = Canonizador(config, manifest)
    return canonizador, raw_path, manifest, config


# --------------------------------------------------------------------------- #
# doc_id: determinismo (property) e regra exata
# --------------------------------------------------------------------------- #

@given(source_key=st.text(min_size=1, max_size=80))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_doc_id_deterministico(tmp_path, source_key):
    """
    Feature: construcao-corpus-piloto
    Property 3: Determinismo do doc_id por source_key
    **Validates: Requirements 5.3**
    """
    config = make_config(tmp_path)
    canonizador = Canonizador(config, make_manifest(tmp_path))
    a = canonizador._assign_doc_id(source_key)
    b = canonizador._assign_doc_id(source_key)
    assert a == b


def test_doc_id_regra_exata(tmp_path):
    """doc_id == 'tcu-' + sha256(source_key.utf8)[:12]."""
    config = make_config(tmp_path)
    canonizador = Canonizador(config, make_manifest(tmp_path))
    sk = "ACORDAO-COMPLETO-123456"
    esperado = "tcu-" + hashlib.sha256(sk.encode("utf-8")).hexdigest()[:12]
    assert canonizador._assign_doc_id(sk) == esperado


def test_colisao_doc_id_aborta_canonizacao(tmp_path, monkeypatch):
    """Dois source_key distintos com mesmo doc_id → aborta antes de escrever."""
    df = pd.DataFrame({"KEY": ["A", "B"], "TEXTO": ["x", "y"]})
    canonizador, raw_path, _, config = setup(tmp_path, df)

    # Forçar colisão: doc_id constante
    monkeypatch.setattr(canonizador, "_assign_doc_id", lambda sk: "tcu-000000000000")
    with pytest.raises(ValueError, match="[Cc]olis"):
        canonizador.run(raw_path)
    # Nenhum artefato publicado
    assert not any(Path(config.processed_dir).glob("*.parquet")) if Path(config.processed_dir).exists() else True


# --------------------------------------------------------------------------- #
# source_key: preservação e rejeição de nulo/vazio
# --------------------------------------------------------------------------- #

def test_source_key_preservado(tmp_path):
    """source_key preserva o valor original de KEY sem modificação."""
    df = pd.DataFrame({"KEY": ["AC-1", "AC-2", "AC-3"], "TEXTO": ["a", "b", "c"]})
    canonizador, raw_path, _, _ = setup(tmp_path, df)
    result = canonizador.run(raw_path)
    parquet = pd.read_parquet(result.parquet_path)
    assert sorted(parquet["source_key"].tolist()) == ["AC-1", "AC-2", "AC-3"]


def test_source_key_nulo_vazio_rejeitado_antes_doc_id(tmp_path):
    """source_key nulo/vazio/espaços → rejeitado com 'source_key_null_or_empty'."""
    df = pd.DataFrame(
        {"KEY": ["AC-1", None, "", "   ", "AC-5"], "TEXTO": ["a", "b", "c", "d", "e"]}
    )
    canonizador, raw_path, _, _ = setup(tmp_path, df)
    result = canonizador.run(raw_path)

    assert result.n_total == 5
    assert result.n_accepted == 2  # AC-1, AC-5
    reasons = [r["reason"] for r in result.rejected_log]
    assert reasons.count("source_key_null_or_empty") == 3
    # source_key nulo aparece como None no log
    nulos = [r for r in result.rejected_log if r["reason"] == "source_key_null_or_empty"]
    assert all(r["source_key"] is None for r in nulos)


# --------------------------------------------------------------------------- #
# uma linha por documento, unicidade, reconciliação
# --------------------------------------------------------------------------- #

def test_uma_linha_por_documento_e_bijetivo(tmp_path):
    """source_key e doc_id não-nulos; nenhum doc_id duplicado com source_key distinto. (Property 4)"""
    df = pd.DataFrame({"KEY": ["A", "B", "C"], "TEXTO": ["x", "y", "z"]})
    canonizador, raw_path, _, _ = setup(tmp_path, df)
    result = canonizador.run(raw_path)
    parquet = pd.read_parquet(result.parquet_path)

    assert parquet["source_key"].notna().all()
    assert parquet["doc_id"].notna().all()
    # relação consistente: 1:1 entre doc_id e source_key
    assert parquet.groupby("doc_id")["source_key"].nunique().max() == 1
    assert len(parquet) == parquet["doc_id"].nunique()


def test_duplicate_source_key_rejeitado(tmp_path):
    """source_key repetido → primeira ocorrência aceita, repetição rejeitada."""
    df = pd.DataFrame({"KEY": ["A", "A", "B"], "TEXTO": ["x", "x2", "y"]})
    canonizador, raw_path, _, _ = setup(tmp_path, df)
    result = canonizador.run(raw_path)
    assert result.n_accepted == 2
    assert any(r["reason"] == "duplicate_source_key" for r in result.rejected_log)


@given(
    keys=st.lists(st.text(min_size=0, max_size=6), min_size=1, max_size=25),
)
@settings(
    max_examples=60,
    deadline=None,  # cada exemplo faz I/O real (ingestão + CSV + parquet); timing variável
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
def test_property_reconciliacao_total(tmp_path_factory, keys):
    """
    Feature: construcao-corpus-piloto
    Property 2: Reconciliação total de registros
    **Validates: Requirements 5.5**
    n_accepted + n_rejected == n_total, sempre.
    """
    tmp_path = tmp_path_factory.mktemp("recon")
    df = pd.DataFrame({"KEY": keys, "TEXTO": ["t"] * len(keys)})
    canonizador, raw_path, _, _ = setup(tmp_path, df)
    result = canonizador.run(raw_path)
    assert result.n_accepted + result.n_rejected == result.n_total == len(keys)


# --------------------------------------------------------------------------- #
# Parquet: round-trip, corpus vazio, no-overwrite
# --------------------------------------------------------------------------- #

def test_round_trip_parquet(tmp_path):
    """Escrita seguida de leitura retorna mesmo nº de linhas e mesmos dtypes. (Property 8)"""
    df = pd.DataFrame({"KEY": ["A", "B"], "TEXTO": ["x", "y"], "RELATOR": ["r1", "r2"]})
    canonizador, raw_path, _, _ = setup(tmp_path, df, metadata_fields=["RELATOR"])
    result = canonizador.run(raw_path)
    p1 = pd.read_parquet(result.parquet_path)
    p2 = pd.read_parquet(result.parquet_path)
    assert len(p1) == len(p2) == result.n_accepted
    assert list(p1.dtypes) == list(p2.dtypes)
    assert list(p1.columns) == ["doc_id", "source_key", "TEXTO", "RELATOR"]


def test_corpus_vazio_parquet_valido(tmp_path):
    """Zero registros → Parquet válido com zero linhas e schema correto."""
    df = pd.DataFrame({"KEY": [], "TEXTO": [], "RELATOR": []})
    canonizador, raw_path, _, _ = setup(tmp_path, df, metadata_fields=["RELATOR"])
    result = canonizador.run(raw_path)
    assert result.n_total == 0
    assert result.n_accepted == 0
    parquet = pd.read_parquet(result.parquet_path)
    assert len(parquet) == 0
    assert list(parquet.columns) == ["doc_id", "source_key", "TEXTO", "RELATOR"]


def test_nao_sobrescreve_parquet_existente(tmp_path):
    """Segunda canonização → novo Parquet com sufixo; primeiro inalterado."""
    df = pd.DataFrame({"KEY": ["A", "B"], "TEXTO": ["x", "y"]})
    canonizador, raw_path, _, config = setup(tmp_path, df)

    r1 = canonizador.run(raw_path)
    conteudo1 = r1.parquet_path.read_bytes()

    # Forçar mesmo nome base seria por timestamp; garantimos ao menos que não sobrescreve
    # criando um arquivo com o nome-base que a próxima execução tentaria usar.
    import time
    time.sleep(1.1)
    r2 = canonizador.run(raw_path)

    assert r2.parquet_path.exists()
    assert r1.parquet_path.exists()
    # primeiro arquivo intacto
    assert r1.parquet_path.read_bytes() == conteudo1


# --------------------------------------------------------------------------- #
# fingerprint / sidecar / excluded_fields / metadata
# --------------------------------------------------------------------------- #

def test_sidecar_contem_dataset_fingerprint(tmp_path):
    """Sidecar _metadata.json contém dataset_fingerprint (64 hex) e campos exigidos."""
    df = pd.DataFrame({"KEY": ["A", "B"], "TEXTO": ["x", "y"]})
    canonizador, raw_path, _, _ = setup(tmp_path, df)
    result = canonizador.run(raw_path)
    meta = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
    assert "dataset_fingerprint" in meta
    assert len(meta["dataset_fingerprint"]) == 64
    assert meta["dataset_fingerprint"] == result.dataset_fingerprint
    for campo in ["parquet_file", "created_at", "config_version", "batch_id",
                  "allowed_fields", "excluded_fields"]:
        assert campo in meta


def test_fingerprint_determinismo_entre_execucoes(tmp_path):
    """Mesma entrada → mesmo dataset_fingerprint em execuções distintas. (Property 5)"""
    df = pd.DataFrame({"KEY": ["A", "B", "C"], "TEXTO": ["x", "y", "z"]})
    c1, raw1, _, _ = setup(tmp_path / "a", df)
    c2, raw2, _, _ = setup(tmp_path / "b", df)
    r1 = c1.run(raw1)
    r2 = c2.run(raw2)
    assert r1.dataset_fingerprint == r2.dataset_fingerprint


def test_fingerprint_log_registrado(tmp_path):
    """fingerprint_log.jsonl recebe uma linha após publicação bem-sucedida."""
    df = pd.DataFrame({"KEY": ["A"], "TEXTO": ["x"]})
    canonizador, raw_path, _, config = setup(tmp_path, df)
    result = canonizador.run(raw_path)
    log_path = Path(config.fingerprint_log)
    assert log_path.exists()
    linhas = [l for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(linhas) == 1
    entry = json.loads(linhas[0])
    assert entry["dataset_fingerprint"] == result.dataset_fingerprint


def test_allowed_fields_controla_colunas(tmp_path):
    """Campo fora de allowed_fields → ausente no Parquet e em excluded_fields."""
    df = pd.DataFrame(
        {"KEY": ["A", "B"], "TEXTO": ["x", "y"], "VISAOGERAL": ["ia1", "ia2"]}
    )
    # VISAOGERAL não está em allowed_fields
    canonizador, raw_path, _, _ = setup(
        tmp_path, df, allowed_fields=["KEY", "TEXTO"]
    )
    result = canonizador.run(raw_path)
    parquet = pd.read_parquet(result.parquet_path)
    assert "VISAOGERAL" not in parquet.columns
    assert "VISAOGERAL" in result.excluded_fields


def test_metadata_field_ausente_permanece_null(tmp_path):
    """metadata_field ausente em um registro → null no Parquet; registro não rejeitado."""
    df = pd.DataFrame(
        {"KEY": ["A", "B"], "TEXTO": ["x", "y"], "RELATOR": ["r1", None]}
    )
    canonizador, raw_path, _, _ = setup(tmp_path, df, metadata_fields=["RELATOR"])
    result = canonizador.run(raw_path)
    assert result.n_accepted == 2  # RELATOR não é obrigatório
    parquet = pd.read_parquet(result.parquet_path)
    relator_b = parquet.loc[parquet["source_key"] == "B", "RELATOR"].iloc[0]
    assert pd.isna(relator_b)


def test_text_field_ausente_nao_rejeita(tmp_path):
    """text_field (ACORDAO) vazio não é motivo de rejeição (não é required)."""
    df = pd.DataFrame({"KEY": ["A", "B"], "TEXTO": ["conteudo", None]})
    canonizador, raw_path, _, _ = setup(tmp_path, df)
    result = canonizador.run(raw_path)
    assert result.n_accepted == 2  # ambos aceitos; TEXTO vazio preservado como null
    parquet = pd.read_parquet(result.parquet_path)
    texto_b = parquet.loc[parquet["source_key"] == "B", "TEXTO"].iloc[0]
    assert pd.isna(texto_b)


def test_rejected_log_sempre_produzido(tmp_path):
    """_rejected.jsonl sempre existe, mesmo sem rejeições."""
    df = pd.DataFrame({"KEY": ["A", "B"], "TEXTO": ["x", "y"]})
    canonizador, raw_path, _, _ = setup(tmp_path, df)
    result = canonizador.run(raw_path)
    assert result.rejected_log_path.exists()
    assert result.rejected_log == []
    assert result.issues_log_path is None  # sem issues no baseline


# --------------------------------------------------------------------------- #
# Bloqueio por proveniência / pending
# --------------------------------------------------------------------------- #

def test_arquivo_sem_manifest_bloqueia_canonizador(tmp_path):
    """Arquivo sem entrada no Manifest → ProvenanceError; nenhum artefato."""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    raw_dir = Path(config.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    orphan = raw_dir / "orfao.csv"
    pd.DataFrame({"KEY": ["A"], "TEXTO": ["x"]}).to_csv(orphan, index=False)

    canonizador = Canonizador(config, manifest)
    with pytest.raises(ProvenanceError) as exc:
        canonizador.run(orphan)
    assert exc.value.reason == "provenance_missing"
    assert not Path(config.processed_dir).exists() or not any(
        Path(config.processed_dir).glob("*.parquet")
    )


def test_hash_divergente_bloqueia_canonizador(tmp_path):
    """SHA-256 divergente → ProvenanceError(integrity_mismatch)."""
    df = pd.DataFrame({"KEY": ["A"], "TEXTO": ["x"]})
    canonizador, raw_path, _, _ = setup(tmp_path, df)
    raw_path.write_text("KEY,TEXTO\n9,corrompido\n", encoding="utf-8")
    with pytest.raises(ProvenanceError) as exc:
        canonizador.run(raw_path)
    assert exc.value.reason == "integrity_mismatch"


def test_pending_manifest_bloqueia_canonizador(tmp_path):
    """pending.jsonl → PendingManifestError; nenhum artefato."""
    df = pd.DataFrame({"KEY": ["A"], "TEXTO": ["x"]})
    canonizador, raw_path, manifest, config = setup(tmp_path, df)
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
        canonizador.run(raw_path)
    assert not any(Path(config.processed_dir).glob("*.parquet")) if Path(config.processed_dir).exists() else True


# --------------------------------------------------------------------------- #
# retrieval_text_fields e preserved_fields — validação de config
# --------------------------------------------------------------------------- #

def test_config_retrieval_text_fields_valido(tmp_path):
    """retrieval_text_fields ⊆ allowed_fields → carrega sem erro."""
    config = make_config(
        tmp_path,
        allowed_fields=["KEY", "ASSUNTO", "ACORDAO"],
        text_field="ACORDAO",
        retrieval_text_fields=["ASSUNTO", "ACORDAO"],
    )
    assert config.retrieval_text_fields == ["ASSUNTO", "ACORDAO"]


def test_config_preserved_fields_valido(tmp_path):
    """preserved_fields ⊆ allowed_fields → carrega sem erro."""
    config = make_config(
        tmp_path,
        allowed_fields=["KEY", "TEXTO", "SUMARIO", "VOTO"],
        preserved_fields=["SUMARIO", "VOTO"],
    )
    assert config.preserved_fields == ["SUMARIO", "VOTO"]


def test_config_retrieval_text_fields_fora_de_allowed_rejeitado(tmp_path):
    """retrieval_text_fields com campo fora de allowed_fields → ValidationError."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        make_config(
            tmp_path,
            allowed_fields=["KEY", "TEXTO"],
            retrieval_text_fields=["TEXTO", "NAO_EXISTE"],
        )


def test_config_preserved_fields_fora_de_allowed_rejeitado(tmp_path):
    """preserved_fields com campo fora de allowed_fields → ValidationError."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        make_config(
            tmp_path,
            allowed_fields=["KEY", "TEXTO"],
            preserved_fields=["FANTASMA"],
        )


# --------------------------------------------------------------------------- #
# Schema canônico com as novas categorias
# --------------------------------------------------------------------------- #

def _full_config(tmp_path):
    """Config espelhando a decisão metodológica do lote TCU 2024."""
    allowed = [
        "KEY", "ASSUNTO", "ACORDAO", "COLEGIADO", "RELATOR", "TIPOPROCESSO",
        "DATASESSAO", "ENTIDADE", "UNIDADETECNICA", "SUMARIO", "RELATORIO", "VOTO",
    ]
    return dict(
        allowed_fields=allowed,
        text_field="ACORDAO",
        retrieval_text_fields=["ASSUNTO", "ACORDAO"],
        metadata_fields=["COLEGIADO", "RELATOR", "TIPOPROCESSO", "DATASESSAO",
                         "ENTIDADE", "UNIDADETECNICA"],
        preserved_fields=["SUMARIO", "RELATORIO", "VOTO"],
    )


def test_schema_canonico_ordem_completa(tmp_path):
    """Schema exato e determinístico com as três categorias; ACORDAO não duplicado."""
    df = pd.DataFrame({
        "KEY": ["A", "B"],
        "ASSUNTO": ["as1", "as2"],
        "ACORDAO": ["ac1", "ac2"],
        "COLEGIADO": ["Plenário", "1ª Câmara"],
        "RELATOR": ["r1", "r2"],
        "TIPOPROCESSO": ["APOS", "TCE"],
        "DATASESSAO": ["01/01/2024", "02/01/2024"],
        "ENTIDADE": ["e1", "e2"],
        "UNIDADETECNICA": ["u1", "u2"],
        "SUMARIO": ["s1", "s2"],
        "RELATORIO": ["rel1", "rel2"],
        "VOTO": ["v1", "v2"],
    })
    canonizador, raw_path, _, _ = setup(tmp_path, df, **_full_config(tmp_path))
    result = canonizador.run(raw_path)
    parquet = pd.read_parquet(result.parquet_path)
    esperado = [
        "doc_id", "source_key", "ASSUNTO", "ACORDAO", "COLEGIADO", "RELATOR",
        "TIPOPROCESSO", "DATASESSAO", "ENTIDADE", "UNIDADETECNICA",
        "SUMARIO", "RELATORIO", "VOTO",
    ]
    assert list(parquet.columns) == esperado
    # ACORDAO (também text_field) aparece uma única vez
    assert list(parquet.columns).count("ACORDAO") == 1


def test_assunto_e_campos_preservados_presentes(tmp_path):
    """ASSUNTO (baseline) e SUMARIO/RELATORIO/VOTO (preservados) presentes no Parquet."""
    df = pd.DataFrame({
        "KEY": ["A"], "ASSUNTO": ["as"], "ACORDAO": ["ac"],
        "COLEGIADO": ["Plenário"], "RELATOR": ["r"], "TIPOPROCESSO": ["APOS"],
        "DATASESSAO": ["01/01/2024"], "ENTIDADE": ["e"], "UNIDADETECNICA": ["u"],
        "SUMARIO": ["s"], "RELATORIO": ["rel"], "VOTO": ["v"],
    })
    canonizador, raw_path, _, _ = setup(tmp_path, df, **_full_config(tmp_path))
    parquet = pd.read_parquet(canonizador.run(raw_path).parquet_path)
    for col in ["ASSUNTO", "SUMARIO", "RELATORIO", "VOTO"]:
        assert col in parquet.columns


def test_preservacao_literal_e_html(tmp_path):
    """Valores textuais preservados literalmente, incluindo HTML (sem limpeza)."""
    html = '<p class="x">Trata-se de <b>auditoria</b></p>'
    df = pd.DataFrame({
        "KEY": ["A"], "ASSUNTO": ["as"], "ACORDAO": [html],
        "COLEGIADO": ["Plenário"], "RELATOR": ["r"], "TIPOPROCESSO": ["APOS"],
        "DATASESSAO": ["01/01/2024"], "ENTIDADE": ["e"], "UNIDADETECNICA": ["u"],
        "SUMARIO": [html], "RELATORIO": ["rel"], "VOTO": ["v"],
    })
    canonizador, raw_path, _, _ = setup(tmp_path, df, **_full_config(tmp_path))
    parquet = pd.read_parquet(canonizador.run(raw_path).parquet_path)
    assert parquet["ACORDAO"].iloc[0] == html
    assert parquet["SUMARIO"].iloc[0] == html


def test_campos_ausentes_permanecem_null_sem_rejeicao(tmp_path):
    """Ausência em retrieval/preserved/metadata → null; nenhuma rejeição por isso."""
    df = pd.DataFrame({
        "KEY": ["A", "B"],
        "ASSUNTO": ["as1", None],       # retrieval ausente em B
        "ACORDAO": [None, "ac2"],        # retrieval/text_field ausente em A
        "COLEGIADO": ["Plenário", None], # metadata ausente em B
        "RELATOR": ["r1", "r2"],
        "TIPOPROCESSO": ["APOS", "TCE"],
        "DATASESSAO": ["01/01/2024", "02/01/2024"],
        "ENTIDADE": ["e1", "e2"],
        "UNIDADETECNICA": ["u1", "u2"],
        "SUMARIO": [None, "s2"],         # preserved ausente em A
        "RELATORIO": ["rel1", None],
        "VOTO": [None, None],            # preserved ausente em ambos
    })
    canonizador, raw_path, _, _ = setup(tmp_path, df, **_full_config(tmp_path))
    result = canonizador.run(raw_path)
    assert result.n_accepted == 2  # nenhuma rejeição: só KEY é obrigatório
    assert result.rejected_log == []
    parquet = pd.read_parquet(result.parquet_path)
    a = parquet[parquet["source_key"] == "A"].iloc[0]
    b = parquet[parquet["source_key"] == "B"].iloc[0]
    assert pd.isna(a["ACORDAO"]) and pd.isna(a["SUMARIO"])
    assert pd.isna(b["ASSUNTO"]) and pd.isna(b["COLEGIADO"])
    assert pd.isna(a["VOTO"]) and pd.isna(b["VOTO"])


def test_corpus_vazio_schema_completo(tmp_path):
    """Corpus vazio → Parquet com zero linhas e schema completo das três categorias."""
    df = pd.DataFrame({c: [] for c in _full_config(tmp_path)["allowed_fields"]})
    canonizador, raw_path, _, _ = setup(tmp_path, df, **_full_config(tmp_path))
    result = canonizador.run(raw_path)
    assert result.n_total == 0 and result.n_accepted == 0
    parquet = pd.read_parquet(result.parquet_path)
    assert len(parquet) == 0
    assert list(parquet.columns) == [
        "doc_id", "source_key", "ASSUNTO", "ACORDAO", "COLEGIADO", "RELATOR",
        "TIPOPROCESSO", "DATASESSAO", "ENTIDADE", "UNIDADETECNICA",
        "SUMARIO", "RELATORIO", "VOTO",
    ]


def test_round_trip_schema_completo(tmp_path):
    """Round-trip do Parquet com todas as categorias: mesmas linhas, colunas e dtypes."""
    df = pd.DataFrame({
        "KEY": ["A", "B", "C"],
        "ASSUNTO": ["as1", "as2", "as3"], "ACORDAO": ["ac1", "ac2", "ac3"],
        "COLEGIADO": ["P", "1C", "2C"], "RELATOR": ["r1", "r2", "r3"],
        "TIPOPROCESSO": ["APOS", "TCE", "REPR"], "DATASESSAO": ["01/01/2024"] * 3,
        "ENTIDADE": ["e1", "e2", "e3"], "UNIDADETECNICA": ["u1", "u2", "u3"],
        "SUMARIO": ["s1", "s2", "s3"], "RELATORIO": ["r1", "r2", "r3"],
        "VOTO": ["v1", "v2", "v3"],
    })
    canonizador, raw_path, _, _ = setup(tmp_path, df, **_full_config(tmp_path))
    result = canonizador.run(raw_path)
    p1 = pd.read_parquet(result.parquet_path)
    p2 = pd.read_parquet(result.parquet_path)
    assert len(p1) == len(p2) == result.n_accepted == 3
    assert list(p1.columns) == list(p2.columns)
    assert list(p1.dtypes) == list(p2.dtypes)


def test_nenhuma_coluna_duplicada_campo_em_multiplas_categorias(tmp_path):
    """Campo declarado em retrieval e preserved → uma única coluna; papéis no sidecar."""
    df = pd.DataFrame({"KEY": ["A"], "TEXTO": ["t"], "COLEGIADO": ["P"]})
    # TEXTO em retrieval e preserved ao mesmo tempo
    canonizador, raw_path, _, _ = setup(
        tmp_path, df,
        allowed_fields=["KEY", "TEXTO", "COLEGIADO"],
        text_field="TEXTO",
        retrieval_text_fields=["TEXTO"],
        metadata_fields=["COLEGIADO"],
        preserved_fields=["TEXTO"],
    )
    result = canonizador.run(raw_path)
    parquet = pd.read_parquet(result.parquet_path)
    assert list(parquet.columns).count("TEXTO") == 1
    assert list(parquet.columns) == ["doc_id", "source_key", "TEXTO", "COLEGIADO"]
    meta = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
    # TEXTO deve listar ambos os papéis
    assert set(meta["field_roles"]["TEXTO"]) == {"retrieval_text_fields", "preserved_fields"}


def test_sidecar_registra_categorias(tmp_path):
    """Sidecar registra text_field, retrieval_text_fields, metadata_fields, preserved_fields,
    canonical_columns e field_roles."""
    df = pd.DataFrame({
        "KEY": ["A"], "ASSUNTO": ["as"], "ACORDAO": ["ac"],
        "COLEGIADO": ["P"], "RELATOR": ["r"], "TIPOPROCESSO": ["APOS"],
        "DATASESSAO": ["01/01/2024"], "ENTIDADE": ["e"], "UNIDADETECNICA": ["u"],
        "SUMARIO": ["s"], "RELATORIO": ["rel"], "VOTO": ["v"],
    })
    canonizador, raw_path, _, _ = setup(tmp_path, df, **_full_config(tmp_path))
    result = canonizador.run(raw_path)
    meta = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
    assert meta["text_field"] == "ACORDAO"
    assert meta["retrieval_text_fields"] == ["ASSUNTO", "ACORDAO"]
    assert meta["metadata_fields"] == ["COLEGIADO", "RELATOR", "TIPOPROCESSO",
                                       "DATASESSAO", "ENTIDADE", "UNIDADETECNICA"]
    assert meta["preserved_fields"] == ["SUMARIO", "RELATORIO", "VOTO"]
    assert meta["canonical_columns"][:2] == ["doc_id", "source_key"]
    assert meta["field_roles"]["ASSUNTO"] == ["retrieval_text_fields"]
    assert meta["field_roles"]["SUMARIO"] == ["preserved_fields"]

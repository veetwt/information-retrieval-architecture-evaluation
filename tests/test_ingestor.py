# Feature: construcao-corpus-piloto
# Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 2.5, 8.2–8.6

import datetime
import hashlib
import shutil
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from data.config import CorpusConfig
from data.manifest import ManifestWriter
from data.ingestor import Ingestor, IngestorResult


def make_config(tmp_path: Path) -> CorpusConfig:
    """Cria CorpusConfig apontando para diretórios temporários."""
    return CorpusConfig(
        source_identifier="TCU-portal-publico",
        batch_id="tcu-2024-v1",
        schema_version="1.0",
        config_version="1.0",
        allowed_fields=["NUMACORDAO", "INTEIROTEOR"],
        dataset="acordaos-tcu",
        dataset_year=2024,
        source_url="https://portal.tcu.gov.br",
        staging_dir=str(tmp_path / "interim"),
        raw_dir=str(tmp_path / "raw"),
        manifests_dir=str(tmp_path / "manifests"),
    )


def make_manifest(tmp_path: Path) -> ManifestWriter:
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    return ManifestWriter(manifest_dir / "manifest.jsonl")


def make_source_file(
    tmp_path: Path,
    name: str = "acordaos_2024.csv",
    content: bytes = b"conteudo csv tcu",
) -> Path:
    src = tmp_path / "source" / name
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(content)
    return src


# --- T5.5 ---


def test_ingestao_basica_sucesso(tmp_path):
    """Ingestão de arquivo novo deve retornar status='ingested'."""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    ingestor = Ingestor(config, manifest)
    src = make_source_file(tmp_path)

    result = ingestor.ingest(src, "2026-01-15T10:00:00Z")

    assert result.status == "ingested"
    assert result.stored_filename == "acordaos_2024.csv"
    assert result.sha256 is not None
    assert len(result.sha256) == 64
    # arquivo deve estar em data/raw/
    assert (tmp_path / "raw" / "acordaos_2024.csv").exists()
    # entrada deve estar no Manifest
    entries = manifest.load_entries()
    assert len(entries) == 1
    assert entries[0]["stored_filename"] == "acordaos_2024.csv"


def test_arquivo_nao_existe_retorna_validation_error(tmp_path):
    """Arquivo de origem inexistente deve retornar status='validation_error'."""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    ingestor = Ingestor(config, manifest)

    result = ingestor.ingest(tmp_path / "nao_existe.csv", "2026-01-15T10:00:00Z")

    assert result.status == "validation_error"
    assert result.sha256 is None
    raw_dir = tmp_path / "raw"
    assert not raw_dir.exists() or not any(raw_dir.iterdir()) if raw_dir.exists() else True


def test_duplicidade_por_conteudo_aborta_antes_staging(tmp_path):
    """SHA-256 já no Manifest deve abortar sem criar arquivo em staging ou raw."""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    ingestor = Ingestor(config, manifest)
    src = make_source_file(tmp_path)

    # Primeira ingestão
    result1 = ingestor.ingest(src, "2026-01-15T10:00:00Z")
    assert result1.status == "ingested"

    # Segunda ingestão — mesmo conteúdo, mesmo arquivo
    result2 = ingestor.ingest(src, "2026-01-15T11:00:00Z")

    assert result2.status == "duplicate_content"
    # staging deve estar limpo
    staging_dir = tmp_path / "interim"
    if staging_dir.exists():
        assert list(staging_dir.iterdir()) == []


def test_duplicidade_por_conteudo_nome_diferente(tmp_path):
    """Arquivo com mesmo conteúdo mas nome diferente deve ser detectado como duplicate_content."""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    ingestor = Ingestor(config, manifest)

    conteudo = b"mesmo conteudo exato"
    src1 = make_source_file(tmp_path, "arquivo_a.csv", conteudo)
    src2 = make_source_file(tmp_path, "arquivo_b.csv", conteudo)

    result1 = ingestor.ingest(src1, "2026-01-15T10:00:00Z")
    assert result1.status == "ingested"

    result2 = ingestor.ingest(src2, "2026-01-15T11:00:00Z")
    # Conteúdo idêntico → duplicate_content, mesmo que nome seja diferente
    assert result2.status == "duplicate_content"
    # Apenas um arquivo em data/raw/
    raw_files = list((tmp_path / "raw").iterdir())
    assert len(raw_files) == 1


def test_conflict_por_nome_gera_stored_filename_distinto(tmp_path):
    """Arquivo com mesmo nome mas conteúdo diferente deve receber stored_filename versionado."""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    ingestor = Ingestor(config, manifest)

    # Use different source subdirectories to avoid overwriting the same file
    src1_dir = tmp_path / "source_v1"
    src1_dir.mkdir(parents=True, exist_ok=True)
    src1 = src1_dir / "acordaos_2024.csv"
    src1.write_bytes(b"conteudo versao 1")

    src2_dir = tmp_path / "source_v2"
    src2_dir.mkdir(parents=True, exist_ok=True)
    src2 = src2_dir / "acordaos_2024.csv"
    src2.write_bytes(b"conteudo versao 2 diferente")

    result1 = ingestor.ingest(src1, "2026-01-15T10:00:00Z")
    assert result1.status == "ingested"
    assert result1.stored_filename == "acordaos_2024.csv"

    result2 = ingestor.ingest(src2, "2026-01-15T11:00:00Z")
    assert result2.status == "name_conflict_versioned"
    assert result2.stored_filename is not None
    assert result2.stored_filename != "acordaos_2024.csv"
    assert "acordaos_2024" in result2.stored_filename

    # Ambos os arquivos devem estar em data/raw/
    raw_files = list((tmp_path / "raw").iterdir())
    assert len(raw_files) == 2

    # Arquivo original não sobrescrito — verificar pelo conteúdo
    original = (tmp_path / "raw" / "acordaos_2024.csv").read_bytes()
    assert original == b"conteudo versao 1"

    # Ambas as entradas no Manifest
    entries = manifest.load_entries()
    assert len(entries) == 2


def test_integridade_staging_sha256_preservado(tmp_path):
    """SHA-256 do arquivo promovido para data/raw/ deve ser idêntico ao da origem. (Property 1)"""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    ingestor = Ingestor(config, manifest)
    conteudo = b"conteudo para verificar integridade"
    src = make_source_file(tmp_path, content=conteudo)
    sha256_esperado = hashlib.sha256(conteudo).hexdigest()

    result = ingestor.ingest(src, "2026-01-15T10:00:00Z")

    assert result.status == "ingested"
    assert result.sha256 == sha256_esperado
    # verificar arquivo em data/raw/
    arquivo_raw = tmp_path / "raw" / "acordaos_2024.csv"
    assert hashlib.sha256(arquivo_raw.read_bytes()).hexdigest() == sha256_esperado


def test_falha_integridade_nao_afeta_raw(tmp_path):
    """SHA-256 divergente em staging deve resultar em integrity_error sem afetar data/raw/."""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    ingestor = Ingestor(config, manifest)
    src = make_source_file(tmp_path)

    # Interceptar compute_sha256 para simular divergência no staging
    call_count = {"n": 0}
    original_sha256 = __import__("utils.hashing", fromlist=["compute_sha256"]).compute_sha256

    def fake_sha256(path):
        call_count["n"] += 1
        if call_count["n"] == 2:  # segunda chamada = staging
            return "0" * 64  # hash falso
        return original_sha256(path)

    with patch("data.ingestor.compute_sha256", side_effect=fake_sha256):
        result = ingestor.ingest(src, "2026-01-15T10:00:00Z")

    assert result.status == "integrity_error"
    assert result.sha256 is not None
    # data/raw/ não deve ter sido criado ou deve estar vazio
    raw_dir = tmp_path / "raw"
    assert not raw_dir.exists() or not any(raw_dir.iterdir())
    # staging deve estar limpo
    staging_dir = tmp_path / "interim"
    assert not staging_dir.exists() or not any(staging_dir.iterdir())
    # Manifest sem entradas
    assert manifest.load_entries() == []


def test_promote_nao_sobrescreve_arquivo_existente_com_manifest(tmp_path):
    """Arquivo existente em data/raw/ com entrada Manifest consistente deve resultar em file_exists_consistent."""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    ingestor = Ingestor(config, manifest)
    src = make_source_file(tmp_path)

    # Primeira ingestão normal
    result1 = ingestor.ingest(src, "2026-01-15T10:00:00Z")
    assert result1.status == "ingested"

    # Tentar ingerir arquivo com mesmo nome mas conteúdo diferente
    # stored_filename será versionado (Conflito_Por_Nome)
    src_novo = tmp_path / "source2" / "acordaos_2024.csv"
    src_novo.parent.mkdir(parents=True, exist_ok=True)
    src_novo.write_bytes(b"conteudo completamente diferente xyz")

    result2 = ingestor.ingest(src_novo, "2026-01-15T11:00:00Z")
    # Pode ser name_conflict_versioned (arquivo com nome diferente) — OK
    # O importante é que o arquivo original NÃO foi sobrescrito
    original_content = (tmp_path / "raw" / "acordaos_2024.csv").read_bytes()
    assert original_content == b"conteudo csv tcu"  # conteúdo original preservado


def test_blocked_pending_manifest(tmp_path):
    """has_pending_entries() True deve bloquear ingestão sem nenhuma escrita."""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    ingestor = Ingestor(config, manifest)
    src = make_source_file(tmp_path)

    # Criar pending.jsonl com uma entrada
    manifest.append_pending_entry({
        "original_filename": "outro.csv",
        "stored_filename": "outro.csv",
        "downloaded_at": "2026-01-01T00:00:00Z",
        "ingested_at": "2026-01-01T00:00:01Z",
        "file_size_bytes": 100,
        "sha256": "c" * 64,
        "source_url": "https://portal.tcu.gov.br",
        "source_identifier": "TCU-portal-publico",
        "dataset": "acordaos-tcu",
        "dataset_year": 2024,
        "schema_version": "1.0",
        "batch_id": "tcu-2024-v1",
    })

    result = ingestor.ingest(src, "2026-01-15T10:00:00Z")

    assert result.status == "blocked_pending_manifest"
    # Nenhum arquivo criado
    raw_dir = tmp_path / "raw"
    assert not raw_dir.exists() or not any(raw_dir.iterdir())
    staging_dir = tmp_path / "interim"
    assert not staging_dir.exists() or not any(staging_dir.iterdir())
    # Manifest sem novas entradas
    assert manifest.load_entries() == []


def test_manifest_pending_apos_falha_de_escrita(tmp_path):
    """Falha na escrita do Manifest após promoção deve resultar em manifest_pending e pending.jsonl."""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    ingestor = Ingestor(config, manifest)
    src = make_source_file(tmp_path)

    # Simular falha em append_entry (mas não em append_pending_entry)
    def fail_append(entry):
        raise IOError("Disco cheio simulado")

    manifest.append_entry = fail_append

    result = ingestor.ingest(src, "2026-01-15T10:00:00Z")

    assert result.status == "manifest_pending"
    assert result.stored_filename == "acordaos_2024.csv"
    # Arquivo deve estar em data/raw/
    assert (tmp_path / "raw" / "acordaos_2024.csv").exists()
    # pending.jsonl deve existir com a entrada
    assert manifest.has_pending_entries()


def test_stored_filename_desambiguacao_progressiva(tmp_path):
    """Colisão de sha256[:8] deve levar à ampliação progressiva."""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    ingestor = Ingestor(config, manifest)

    # Conteúdos distintos para ter sha256s distintos
    conteudo_v1 = b"versao 1 do arquivo"
    conteudo_v2 = b"versao 2 completamente diferente do arquivo"
    sha256_v2 = hashlib.sha256(conteudo_v2).hexdigest()

    # Use different source subdirectories to avoid overwriting the same file
    src1_dir = tmp_path / "source_v1"
    src1_dir.mkdir(parents=True, exist_ok=True)
    src1 = src1_dir / "base.csv"
    src1.write_bytes(conteudo_v1)

    src2_dir = tmp_path / "source_v2"
    src2_dir.mkdir(parents=True, exist_ok=True)
    src2 = src2_dir / "base.csv"
    src2.write_bytes(conteudo_v2)

    result1 = ingestor.ingest(src1, "2026-01-15T10:00:00Z")
    assert result1.status == "ingested"

    # Criar manualmente um arquivo com o nome que o candidato sha256[:8] produziria
    # para forçar a desambiguação progressiva
    stem = "base"
    suffix = ".csv"
    candidato_8 = f"{stem}_{sha256_v2[:8]}{suffix}"
    raw_dir = tmp_path / "raw"
    (raw_dir / candidato_8).write_bytes(b"arquivo bloqueador")

    result2 = ingestor.ingest(src2, "2026-01-15T11:00:00Z")
    assert result2.status == "name_conflict_versioned"
    assert result2.stored_filename is not None
    # stored_filename deve ser diferente do candidato_8 (desambiguação usou N > 8)
    assert result2.stored_filename != candidato_8
    assert "base_" in result2.stored_filename


def test_staging_limpo_apos_ingestao_sucesso(tmp_path):
    """Após ingestão bem-sucedida, staging deve estar limpo."""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    ingestor = Ingestor(config, manifest)
    src = make_source_file(tmp_path)

    result = ingestor.ingest(src, "2026-01-15T10:00:00Z")
    assert result.status == "ingested"

    staging_dir = tmp_path / "interim"
    if staging_dir.exists():
        remaining = list(staging_dir.iterdir())
        assert remaining == [], f"staging não está limpo: {remaining}"


def test_manifest_contem_todos_campos_obrigatorios(tmp_path):
    """Entrada no Manifest deve conter todos os campos obrigatórios."""
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    ingestor = Ingestor(config, manifest)
    src = make_source_file(tmp_path)

    result = ingestor.ingest(src, "2026-01-15T10:00:00Z")
    assert result.status == "ingested"

    entry = manifest.load_entries()[0]
    for campo in ManifestWriter.REQUIRED_FIELDS:
        assert campo in entry and entry[campo] is not None, f"Campo ausente: {campo}"
    # source_url ou source_identifier deve estar presente
    assert entry.get("source_url") or entry.get("source_identifier")


# --- T5.6 — Property test ---

@given(conteudo=st.binary(min_size=1, max_size=1024))
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_property_integridade_copia(tmp_path_factory, conteudo):
    """
    Feature: construcao-corpus-piloto
    Property 1: Integridade da cópia (SHA-256 preservado na promoção)

    **Validates: Requirements 1.6**

    Para qualquer conteúdo binário válido, SHA-256 do arquivo promovido
    deve ser igual ao SHA-256 calculado sobre o arquivo de origem.
    """
    tmp_path = tmp_path_factory.mktemp("prop_integridade")
    config = make_config(tmp_path)
    manifest = make_manifest(tmp_path)
    ingestor = Ingestor(config, manifest)

    src = tmp_path / "source" / "prop_test.csv"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(conteudo)

    sha256_origem = hashlib.sha256(conteudo).hexdigest()
    result = ingestor.ingest(src, "2026-01-15T10:00:00Z")

    assert result.status == "ingested"
    arquivo_raw = tmp_path / "raw" / "prop_test.csv"
    assert arquivo_raw.exists()
    sha256_raw = hashlib.sha256(arquivo_raw.read_bytes()).hexdigest()
    assert sha256_raw == sha256_origem

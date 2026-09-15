# Feature: construcao-corpus-piloto
# Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 1.7

import hashlib
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from data.manifest import ManifestWriter

ENTRADA_VALIDA = {
    "original_filename": "acordaos_2024.csv",
    "stored_filename": "acordaos_2024.csv",
    "downloaded_at": "2026-01-15T10:00:00Z",
    "ingested_at": "2026-01-15T14:32:11Z",
    "file_size_bytes": 12345,
    "sha256": "a" * 64,
    "source_url": "https://portal.tcu.gov.br",
    "source_identifier": None,
    "dataset": "acordaos-tcu",
    "dataset_year": 2024,
    "schema_version": "1.0",
    "batch_id": "tcu-2024-v1",
}


def test_manifest_append_e_load(tmp_path):
    """append_entry deve gravar e load_entries deve recuperar a entrada."""
    mw = ManifestWriter(tmp_path / "manifests" / "manifest.jsonl")
    (tmp_path / "manifests").mkdir()
    mw.append_entry(ENTRADA_VALIDA)
    entries = mw.load_entries()
    assert len(entries) == 1
    assert entries[0]["sha256"] == "a" * 64


def test_manifest_load_vazio_sem_arquivo(tmp_path):
    """load_entries deve retornar lista vazia se o arquivo não existir."""
    mw = ManifestWriter(tmp_path / "manifest.jsonl")
    assert mw.load_entries() == []


def test_manifest_rejeita_campo_ausente(tmp_path):
    """append_entry sem campo obrigatório deve levantar ValueError."""
    mw = ManifestWriter(tmp_path / "manifest.jsonl")
    entrada_incompleta = {k: v for k, v in ENTRADA_VALIDA.items() if k != "batch_id"}
    with pytest.raises(ValueError) as exc_info:
        mw.append_entry(entrada_incompleta)
    assert "batch_id" in str(exc_info.value)


def test_manifest_rejeita_sem_source(tmp_path):
    """append_entry sem source_url nem source_identifier deve levantar ValueError."""
    mw = ManifestWriter(tmp_path / "manifest.jsonl")
    entrada = {**ENTRADA_VALIDA, "source_url": None, "source_identifier": None}
    with pytest.raises(ValueError):
        mw.append_entry(entrada)


def test_sha256_exists_retorna_true(tmp_path):
    """sha256_exists deve retornar True e a entrada quando o hash existe."""
    (tmp_path / "manifests").mkdir()
    mw = ManifestWriter(tmp_path / "manifests" / "manifest.jsonl")
    mw.append_entry(ENTRADA_VALIDA)
    found, entry = mw.sha256_exists("a" * 64)
    assert found is True
    assert entry["original_filename"] == "acordaos_2024.csv"


def test_sha256_exists_retorna_false(tmp_path):
    """sha256_exists deve retornar False para hash inexistente."""
    mw = ManifestWriter(tmp_path / "manifest.jsonl")
    found, entry = mw.sha256_exists("b" * 64)
    assert found is False
    assert entry is None


def test_original_filename_exists(tmp_path):
    """original_filename_exists deve detectar nome de arquivo existente."""
    (tmp_path / "manifests").mkdir()
    mw = ManifestWriter(tmp_path / "manifests" / "manifest.jsonl")
    mw.append_entry(ENTRADA_VALIDA)
    found, entry = mw.original_filename_exists("acordaos_2024.csv")
    assert found is True
    found2, _ = mw.original_filename_exists("outro.csv")
    assert found2 is False


def test_validate_provenance_missing(tmp_path):
    """validate_file_provenance deve retornar 'provenance_missing' para arquivo sem entrada."""
    mw = ManifestWriter(tmp_path / "manifest.jsonl")
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    arquivo = raw_dir / "arquivo.csv"
    arquivo.write_bytes(b"conteudo")
    ok, motivo = mw.validate_file_provenance("arquivo.csv", raw_dir)
    assert ok is False
    assert motivo == "provenance_missing"


def test_validate_provenance_file_not_found(tmp_path):
    """validate_file_provenance deve retornar 'file_not_found' se arquivo físico não existe."""
    (tmp_path / "manifests").mkdir()
    mw = ManifestWriter(tmp_path / "manifests" / "manifest.jsonl")
    entrada = {**ENTRADA_VALIDA, "stored_filename": "ausente.csv"}
    mw.append_entry(entrada)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    ok, motivo = mw.validate_file_provenance("ausente.csv", raw_dir)
    assert ok is False
    assert motivo == "file_not_found"


def test_validate_provenance_integrity_mismatch(tmp_path):
    """validate_file_provenance deve retornar 'integrity_mismatch' quando SHA-256 diverge."""
    (tmp_path / "manifests").mkdir()
    mw = ManifestWriter(tmp_path / "manifests" / "manifest.jsonl")
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    arquivo = raw_dir / "acordaos_2024.csv"
    arquivo.write_bytes(b"conteudo real")
    # registrar com hash errado
    entrada = {**ENTRADA_VALIDA, "sha256": "b" * 64}
    mw.append_entry(entrada)
    ok, motivo = mw.validate_file_provenance("acordaos_2024.csv", raw_dir)
    assert ok is False
    assert motivo == "integrity_mismatch"


def test_validate_provenance_ok(tmp_path):
    """validate_file_provenance deve retornar (True, '') quando hash e entrada batem."""
    (tmp_path / "manifests").mkdir()
    mw = ManifestWriter(tmp_path / "manifests" / "manifest.jsonl")
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    conteudo = b"conteudo do acordao"
    arquivo = raw_dir / "acordaos_2024.csv"
    arquivo.write_bytes(conteudo)
    sha256_real = hashlib.sha256(conteudo).hexdigest()
    entrada = {**ENTRADA_VALIDA, "sha256": sha256_real}
    mw.append_entry(entrada)
    ok, motivo = mw.validate_file_provenance("acordaos_2024.csv", raw_dir)
    assert ok is True
    assert motivo == ""


def test_has_pending_entries_false_sem_arquivo(tmp_path):
    """has_pending_entries deve retornar False quando pending.jsonl não existe."""
    mw = ManifestWriter(tmp_path / "manifest.jsonl")
    assert mw.has_pending_entries() is False


def test_has_pending_entries_true_com_entrada(tmp_path):
    """has_pending_entries deve retornar True quando pending.jsonl tem pelo menos uma linha."""
    mw = ManifestWriter(tmp_path / "manifest.jsonl")
    mw.append_pending_entry(ENTRADA_VALIDA)
    assert mw.has_pending_entries() is True


def test_pending_entry_mesmo_schema(tmp_path):
    """append_pending_entry deve gravar entrada legível em pending.jsonl."""
    mw = ManifestWriter(tmp_path / "manifest.jsonl")
    mw.append_pending_entry(ENTRADA_VALIDA)
    pending_path = tmp_path / "pending.jsonl"
    assert pending_path.exists()
    linha = json.loads(pending_path.read_text(encoding="utf-8").strip())
    assert linha["batch_id"] == "tcu-2024-v1"


def test_manifest_multiplas_entradas(tmp_path):
    """load_entries deve retornar todas as entradas em ordem de inserção."""
    (tmp_path / "manifests").mkdir()
    mw = ManifestWriter(tmp_path / "manifests" / "manifest.jsonl")
    entrada2 = {**ENTRADA_VALIDA, "stored_filename": "outro.csv", "sha256": "b" * 64,
                "original_filename": "outro.csv"}
    mw.append_entry(ENTRADA_VALIDA)
    mw.append_entry(entrada2)
    entries = mw.load_entries()
    assert len(entries) == 2
    assert entries[1]["stored_filename"] == "outro.csv"

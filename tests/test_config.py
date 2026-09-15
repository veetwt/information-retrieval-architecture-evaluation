# Feature: construcao-corpus-piloto
# Requirements: 7.1, 7.5, 9.1, 9.2, 9.3

import sys
import textwrap
from pathlib import Path
import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from data.config import CorpusConfig

CAMPOS_OBRIGATORIOS = {
    "source_identifier": "TCU-portal-publico",
    "batch_id": "tcu-acordaos-2024-v1",
    "schema_version": "1.0",
    "config_version": "1.0",
    "allowed_fields": ["NUMACORDAO", "INTEIROTEOR", "ANOACORDAO"],
    "dataset": "acordaos-tcu",
    "dataset_year": 2024,
}


def test_config_valida_campos_obrigatorios():
    """Config com todos os campos obrigatórios deve ser carregado sem erro."""
    cfg = CorpusConfig(**CAMPOS_OBRIGATORIOS)
    assert cfg.batch_id == "tcu-acordaos-2024-v1"
    assert cfg.dataset_year == 2024


def test_config_rejeita_campo_ausente():
    """Omitir campo obrigatório deve levantar ValidationError."""
    dados = {k: v for k, v in CAMPOS_OBRIGATORIOS.items() if k != "batch_id"}
    with pytest.raises(ValidationError) as exc_info:
        CorpusConfig(**dados)
    assert "batch_id" in str(exc_info.value)


def test_config_defaults_caminhos():
    """Campos de caminhos devem ter os valores padrão definidos no design."""
    cfg = CorpusConfig(**CAMPOS_OBRIGATORIOS)
    assert cfg.raw_dir == "data/raw"
    assert cfg.staging_dir == "data/interim"
    assert cfg.manifests_dir == "data/manifests"
    assert cfg.processed_dir == "data/processed/original"


def test_config_rejeita_metadata_fields_fora_de_allowed_fields():
    """metadata_fields com campo não em allowed_fields deve levantar ValidationError."""
    dados = {**CAMPOS_OBRIGATORIOS, "metadata_fields": ["CAMPO_INEXISTENTE"]}
    with pytest.raises(ValidationError) as exc_info:
        CorpusConfig(**dados)
    assert "metadata_fields" in str(exc_info.value).lower() or "allowed_fields" in str(exc_info.value).lower()


def test_config_rejeita_required_fields_fora_de_allowed_fields():
    """required_fields com campo não em allowed_fields deve levantar ValidationError."""
    dados = {**CAMPOS_OBRIGATORIOS, "required_fields": ["CAMPO_INEXISTENTE"]}
    with pytest.raises(ValidationError):
        CorpusConfig(**dados)


def test_config_rejeita_primary_key_field_fora_de_allowed_fields():
    """primary_key_field não em allowed_fields deve levantar ValidationError."""
    dados = {**CAMPOS_OBRIGATORIOS, "primary_key_field": "CAMPO_INEXISTENTE"}
    with pytest.raises(ValidationError):
        CorpusConfig(**dados)


def test_config_aceita_primary_key_field_em_allowed_fields():
    """primary_key_field em allowed_fields deve ser aceito."""
    dados = {**CAMPOS_OBRIGATORIOS, "primary_key_field": "NUMACORDAO"}
    cfg = CorpusConfig(**dados)
    assert cfg.primary_key_field == "NUMACORDAO"


def test_config_aceita_metadata_fields_subconjunto():
    """metadata_fields subconjunto de allowed_fields deve ser aceito."""
    dados = {**CAMPOS_OBRIGATORIOS, "metadata_fields": ["ANOACORDAO"]}
    cfg = CorpusConfig(**dados)
    assert cfg.metadata_fields == ["ANOACORDAO"]


def test_config_load_yaml(tmp_path):
    """load() com arquivo .yaml deve carregar corretamente."""
    yaml_content = textwrap.dedent("""
        source_identifier: TCU-portal-publico
        batch_id: tcu-2024-v1
        schema_version: "1.0"
        config_version: "1.0"
        allowed_fields:
          - NUMACORDAO
          - INTEIROTEOR
        dataset: acordaos-tcu
        dataset_year: 2024
    """)
    f = tmp_path / "config.yaml"
    f.write_text(yaml_content, encoding="utf-8")
    cfg = CorpusConfig.load(f)
    assert cfg.batch_id == "tcu-2024-v1"
    assert "NUMACORDAO" in cfg.allowed_fields


def test_config_load_toml(tmp_path):
    """load() com arquivo .toml deve carregar corretamente."""
    toml_content = textwrap.dedent("""
        source_identifier = "TCU-portal-publico"
        batch_id = "tcu-2024-v1"
        schema_version = "1.0"
        config_version = "1.0"
        allowed_fields = ["NUMACORDAO", "INTEIROTEOR"]
        dataset = "acordaos-tcu"
        dataset_year = 2024
    """)
    f = tmp_path / "config.toml"
    f.write_bytes(toml_content.encode("utf-8"))
    cfg = CorpusConfig.load(f)
    assert cfg.batch_id == "tcu-2024-v1"


def test_config_load_formato_invalido(tmp_path):
    """load() com sufixo desconhecido deve levantar ValueError."""
    f = tmp_path / "config.json"
    f.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Formato não suportado"):
        CorpusConfig.load(f)


def test_config_source_version_independentes():
    """config_version e schema_version são independentes (sem sincronização automática)."""
    dados = {**CAMPOS_OBRIGATORIOS, "config_version": "2.0", "schema_version": "1.0"}
    cfg = CorpusConfig(**dados)
    assert cfg.config_version == "2.0"
    assert cfg.schema_version == "1.0"

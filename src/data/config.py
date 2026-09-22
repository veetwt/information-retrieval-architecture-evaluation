"""Modelo de configuração do pipeline de construção do corpus piloto.

CorpusConfig é um modelo Pydantic v2 que valida e carrega o Config_File.
Centraliza todos os parâmetros de execução do pipeline, garantindo que
erros de configuração sejam detectados antes de qualquer operação de I/O.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator


class CorpusConfig(BaseModel):
    """Configuração central do pipeline de construção do corpus piloto."""

    # --- Campos obrigatórios ---
    source_identifier: str
    """Identificador da fonte oficial (ex: 'TCU-portal-publico')."""

    batch_id: str
    """Identificador único do lote (ex: 'tcu-acordaos-2024-v1')."""

    schema_version: str
    """Versão do schema do Manifest (ex: '1.0')."""

    config_version: str
    """Versão desta instância de configuração (ex: '1.0').
    Conceitualmente separado de schema_version."""

    allowed_fields: list[str]
    """Campos do dataset original elegíveis para inclusão no Corpus_Canonico."""

    dataset: str
    """Nome do dataset (ex: 'acordaos-tcu')."""

    dataset_year: int
    """Ano ao qual o lote se refere (ex: 2024)."""

    # --- Campos opcionais ---
    source_url: str | None = None
    """URL da fonte oficial."""

    primary_key_field: str | None = None
    """Nome da coluna que funciona como identificador primário no dataset."""

    text_field: str | None = None
    """Nome da coluna que contém o texto completo do documento."""

    metadata_fields: list[str] | None = None
    """Subconjunto de allowed_fields com campos estruturados (metadados)."""

    required_fields: list[str] | None = None
    """Campos obrigatórios para elegibilidade de um registro na canonização."""

    retrieval_text_fields: list[str] | None = None
    """Subconjunto de allowed_fields: baseline textual dos experimentos de recuperação.
    Preservados como colunas independentes no corpus canônico; o Canonizador não os
    concatena. Default None mantém compatibilidade com configurações anteriores."""

    preserved_fields: list[str] | None = None
    """Subconjunto de allowed_fields: campos documentais preservados no corpus canônico,
    fora da baseline principal. Default None mantém compatibilidade."""

    # --- Caminhos (com defaults do design) ---
    staging_dir: str = "data/interim"
    raw_dir: str = "data/raw"
    manifests_dir: str = "data/manifests"
    processed_dir: str = "data/processed/original"
    reports_dir: str = "reports/corpus"
    fingerprint_log: str = "runs/artifacts/fingerprint_log.jsonl"

    @model_validator(mode="after")
    def _validate_field_subsets(self) -> "CorpusConfig":
        """Valida restrições cross-field entre os campos configurados."""
        allowed = set(self.allowed_fields)

        if self.metadata_fields is not None:
            invalidos = [f for f in self.metadata_fields if f not in allowed]
            if invalidos:
                raise ValueError(
                    f"metadata_fields contém campos fora de allowed_fields: {invalidos}"
                )

        if self.required_fields is not None:
            invalidos = [f for f in self.required_fields if f not in allowed]
            if invalidos:
                raise ValueError(
                    f"required_fields contém campos fora de allowed_fields: {invalidos}"
                )

        if self.primary_key_field is not None and self.primary_key_field not in allowed:
            raise ValueError(
                f"primary_key_field '{self.primary_key_field}' não está em allowed_fields"
            )

        if self.text_field is not None and self.text_field not in allowed:
            raise ValueError(
                f"text_field '{self.text_field}' não está em allowed_fields"
            )

        if self.retrieval_text_fields is not None:
            invalidos = [f for f in self.retrieval_text_fields if f not in allowed]
            if invalidos:
                raise ValueError(
                    f"retrieval_text_fields contém campos fora de allowed_fields: {invalidos}"
                )

        if self.preserved_fields is not None:
            invalidos = [f for f in self.preserved_fields if f not in allowed]
            if invalidos:
                raise ValueError(
                    f"preserved_fields contém campos fora de allowed_fields: {invalidos}"
                )

        return self

    @classmethod
    def from_yaml(cls, path: Path) -> "CorpusConfig":
        """Carrega e valida o Config_File a partir de um arquivo YAML.

        Lança ValueError com mensagem descritiva se o arquivo for inválido.
        """
        try:
            with open(path, encoding="utf-8") as f:
                data: Any = yaml.safe_load(f)
        except OSError as exc:
            raise ValueError(f"Não foi possível abrir o arquivo YAML '{path}': {exc}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"Arquivo YAML inválido '{path}': {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"O arquivo YAML '{path}' deve conter um mapeamento no nível raiz.")

        return cls.model_validate(data)

    @classmethod
    def from_toml(cls, path: Path) -> "CorpusConfig":
        """Carrega e valida o Config_File a partir de um arquivo TOML.

        Usa tomllib da stdlib (Python ≥ 3.11).
        Lança ValueError se o arquivo for inválido.
        """
        try:
            with open(path, "rb") as f:
                data: Any = tomllib.load(f)
        except OSError as exc:
            raise ValueError(f"Não foi possível abrir o arquivo TOML '{path}': {exc}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"Arquivo TOML inválido '{path}': {exc}") from exc

        return cls.model_validate(data)

    @classmethod
    def load(cls, path: Path) -> "CorpusConfig":
        """Detecta o formato pelo sufixo e delega para from_yaml ou from_toml.

        - .yaml / .yml  → from_yaml
        - .toml         → from_toml
        - outros        → ValueError("Formato não suportado: ...")
        """
        suffix = path.suffix.lower()
        if suffix in (".yaml", ".yml"):
            return cls.from_yaml(path)
        if suffix == ".toml":
            return cls.from_toml(path)
        raise ValueError(f"Formato não suportado: '{path.suffix}'. Use .yaml, .yml ou .toml.")

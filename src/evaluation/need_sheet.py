"""Modelo e validação da Ficha de Invariantes de uma necessidade de informação.

Contexto (spec `protocolo-experimental`, Requirement 5): cada necessidade de
informação do núcleo comparativo possui uma **ficha de invariantes**, criada
ANTES da execução dos recuperadores, que documenta a necessidade e suas três
formulações (direta, parafraseada, prolixa). A ficha NÃO é o gold/reference e
NÃO é fornecida aos recuperadores como filtro ou informação privilegiada.

Este módulo oferece:
- ``NeedSheet``: modelo Pydantic v2 que valida a ESTRUTURA da ficha (não o seu
  conteúdo semântico).
- ``NeedSheet.from_yaml`` / ``to_yaml``: carga e serialização YAML, no mesmo
  estilo de ``CorpusConfig`` (um arquivo por necessidade).

Fronteiras deliberadas (decisões metodológicas registradas nas specs):
- As condições obrigatórias são DESCRITIVAS e apenas ANOTADAS como relativas a
  metadados ou a conteúdo textual. NÃO são filtros executáveis e NÃO devem ser
  transformadas em consulta estruturada pronta.
- A equivalência semântica das três formulações NÃO é decidida aqui. O Pydantic
  verifica apenas que a revisão foi REGISTRADA; o julgamento de equivalência
  exige revisão humana do conteúdo (Requirement 5).
- Nem toda necessidade tem condição documental explícita: uma necessidade
  baseada em metadados pode ser, por exemplo, uma contagem agrupada por
  colegiado. Portanto ``mandatory_conditions`` pode ser vazia.

Estados do ciclo de vida (``equivalence_validation.status``):
- ``draft``: ficha em elaboração; formulações podem estar incompletas.
- ``validated``: exige os campos preenchidos (ver ``_validate_validated_sheet``):
  as três formulações não vazias e a revisão de equivalência registrada
  (justificativa + ao menos um revisor).
"""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


# Os seis campos de metadados permitidos nas anotações das condições. Espelham
# `metadata_fields` do Config_File (configs/acordaos_tcu_2024.yaml) e a seleção
# experimental congelada. Mantidos aqui como constante da camada de avaliação
# para validar anotações sem acoplar a ficha ao pipeline de corpus; se os
# metadados selecionados mudarem no Config_File, esta lista deve acompanhar.
PERMITTED_METADATA_FIELDS: tuple[str, ...] = (
    "COLEGIADO",
    "RELATOR",
    "TIPOPROCESSO",
    "DATASESSAO",
    "ENTIDADE",
    "UNIDADETECNICA",
)

# Padrão de identificador das fichas DEFINITIVAS do conjunto experimental:
# NI- seguido de exatamente três dígitos (NI-001, NI-002, ...). Os casos piloto
# NI-01/NI-02/NI-03 permanecem apenas em docs/experimento/ e NÃO são fichas
# definitivas; por isso não precisam satisfazer este padrão.
NEED_ID_PATTERN = r"^NI-[0-9]{3}$"
_NEED_ID_RE = re.compile(NEED_ID_PATTERN)

# selection_fingerprint: SHA-256 hexadecimal de 64 caracteres (minúsculos), igual
# ao registrado no manifesto da Selecao_Experimental. A validação estrutural
# verifica apenas presença e formato; a conferência contra o manifesto/corpus é
# uma validação SEPARADA (ver verify_selection_fingerprint), para não recalcular
# o fingerprint a cada leitura de ficha.
SELECTION_FINGERPRINT_PATTERN = r"^[0-9a-f]{64}$"
_FINGERPRINT_RE = re.compile(SELECTION_FINGERPRINT_PATTERN)


class NeedNature(str, Enum):
    """Natureza da necessidade (Requirement 5; categorias operacionais)."""

    METADATA = "metadata"
    TEXTUAL = "textual"
    MIXED = "mixed"


class ConditionRelatesTo(str, Enum):
    """Anotação da origem da condição obrigatória (para fins de anotação)."""

    METADATA = "metadata"
    TEXTUAL = "textual"


class ValidationStatus(str, Enum):
    """Estado do ciclo de vida da ficha."""

    DRAFT = "draft"
    VALIDATED = "validated"


class Scope(BaseModel):
    """Escopo documental e temporal da necessidade.

    ``selection_fingerprint`` vincula a ficha inequivocamente à Selecao_Experimental
    congelada (21.631 documentos), pelo mesmo valor registrado no manifesto da
    seleção. A validação aqui é apenas de **formato** (SHA-256 de 64 hex); a
    conferência de que o valor corresponde ao manifesto/corpus é separada
    (``verify_selection_fingerprint``), para não recalcular o fingerprint em toda
    leitura de ficha.
    """

    model_config = {"extra": "forbid"}

    corpus: str
    """Identificação do corpus/seleção (ex.: batch_id da seleção congelada)."""

    temporal: str
    """Escopo temporal (ex.: '2024')."""

    selection_fingerprint: str
    """SHA-256 (64 hex) da Selecao_Experimental congelada, como no manifesto."""

    @field_validator("selection_fingerprint")
    @classmethod
    def _validate_fingerprint_format(cls, v: str) -> str:
        if not _FINGERPRINT_RE.match(v):
            raise ValueError(
                "scope.selection_fingerprint deve ser um SHA-256 hexadecimal de "
                "64 caracteres minúsculos (ver manifesto da seleção)."
            )
        return v


class MandatoryCondition(BaseModel):
    """Condição obrigatória DESCRITIVA que delimita documentos pertinentes.

    É uma anotação, não um filtro executável. ``relates_to`` indica se a condição
    se apoia em metadados ou no conteúdo textual. Quando ``relates_to == metadata``,
    ``fields`` PODE listar os campos de metadados envolvidos, restritos aos seis
    permitidos; a lista é opcional (a condição continua sendo descritiva).
    """

    model_config = {"extra": "forbid"}

    description: str
    """Descrição em linguagem natural da condição obrigatória."""

    relates_to: ConditionRelatesTo
    """Anotação: a condição se relaciona a 'metadata' ou a 'textual'."""

    fields: list[str] = Field(default_factory=list)
    """Campos de metadados citados (opcional). Só válido se relates_to == metadata
    e restrito a PERMITTED_METADATA_FIELDS."""

    @model_validator(mode="after")
    def _validate_fields(self) -> "MandatoryCondition":
        if self.fields:
            if self.relates_to != ConditionRelatesTo.METADATA:
                raise ValueError(
                    "mandatory_condition.fields só é permitido quando "
                    "relates_to == 'metadata'."
                )
            invalidos = [f for f in self.fields if f not in PERMITTED_METADATA_FIELDS]
            if invalidos:
                raise ValueError(
                    f"mandatory_condition.fields contém campos não permitidos: "
                    f"{invalidos}. Permitidos: {list(PERMITTED_METADATA_FIELDS)}."
                )
        return self


class Formulations(BaseModel):
    """As três condições de formulação (Requirement 5).

    Em ficha ``draft``, podem estar vazias/incompletas. A exigência de
    preenchimento é aplicada no nível da ficha quando ``status == validated``.
    """

    model_config = {"extra": "forbid"}

    direct: str = ""
    """Formulação direta (referência)."""

    paraphrase: str = ""
    """Formulação parafraseada (extensão semelhante à direta)."""

    verbose: str = ""
    """Formulação prolixa (mais extensa, sem novos fatos nem pistas da resposta)."""


class EquivalenceReviewer(BaseModel):
    """Registro de uma revisão de equivalência (rastreabilidade)."""

    model_config = {"extra": "forbid"}

    id: str
    """Identificador do revisor."""

    decision: str
    """Decisão registrada do revisor (ex.: 'equivalent', 'not_equivalent')."""


class EquivalenceValidation(BaseModel):
    """Estado e registro da validação de equivalência das formulações.

    O Pydantic NÃO julga equivalência semântica; apenas registra o estado e a
    revisão. O conteúdo da justificativa e das decisões é responsabilidade da
    revisão humana (Requirement 5).
    """

    model_config = {"extra": "forbid"}

    status: ValidationStatus = ValidationStatus.DRAFT
    """Estado do ciclo de vida: 'draft' ou 'validated'."""

    rationale: str = ""
    """Justificativa do julgamento de equivalência (preenchida na validação)."""

    reviewers: list[EquivalenceReviewer] = Field(default_factory=list)
    """Revisores que registraram decisão (≥ 1 exigido para 'validated')."""


class NeedSheet(BaseModel):
    """Ficha de Invariantes de uma necessidade de informação.

    Valida a ESTRUTURA (campos, tipos, enumerações, anotações de metadados) e as
    exigências de ciclo de vida. Não decide equivalência semântica nem gera
    filtros executáveis.
    """

    model_config = {"extra": "forbid"}

    schema_version: str
    """Versão do schema da ficha (ex.: '1.0')."""

    need_id: str
    """Identificador único e estável da necessidade (ex.: 'NI-001')."""

    description: str
    """Descrição da necessidade de informação em linguagem natural."""

    nature: NeedNature
    """Natureza: metadata, textual ou mixed."""

    scope: Scope
    """Escopo documental e temporal."""

    mandatory_conditions: list[MandatoryCondition] = Field(default_factory=list)
    """Condições obrigatórias descritivas (pode ser vazia; ver docstring do módulo)."""

    requested_facts: list[str] = Field(default_factory=list)
    """Informações/fatos solicitados pela necessidade."""

    operations: list[str] = Field(default_factory=list)
    """Operações necessárias, quando aplicáveis (ex.: identify, count, compare, aggregate)."""

    formulations: Formulations
    """As três condições de formulação."""

    equivalence_validation: EquivalenceValidation = Field(
        default_factory=EquivalenceValidation
    )
    """Estado e registro da validação de equivalência."""

    @field_validator("need_id")
    @classmethod
    def _validate_need_id_format(cls, v: str) -> str:
        if not _NEED_ID_RE.match(v):
            raise ValueError(
                f"need_id '{v}' não segue o padrão '{NEED_ID_PATTERN}' "
                "(ex.: NI-001). Os pilotos NI-01/02/03 permanecem apenas em docs/."
            )
        return v

    @model_validator(mode="after")
    def _validate_lifecycle(self) -> "NeedSheet":
        """Aplica exigências de ciclo de vida sem julgar equivalência semântica."""
        if self.equivalence_validation.status == ValidationStatus.VALIDATED:
            self._validate_validated_sheet()
        return self

    def _validate_validated_sheet(self) -> None:
        """Exigências adicionais para uma ficha com status 'validated'.

        - As três formulações devem estar preenchidas (não vazias/só-espaços).
        - requested_facts não pode ser vazio (a necessidade pede algo).
        - A revisão de equivalência deve estar registrada: justificativa não vazia
          e ao menos um revisor. (O Pydantic não avalia o mérito da equivalência.)
        """
        faltando = [
            nome
            for nome, valor in (
                ("direct", self.formulations.direct),
                ("paraphrase", self.formulations.paraphrase),
                ("verbose", self.formulations.verbose),
            )
            if not valor.strip()
        ]
        if faltando:
            raise ValueError(
                "ficha 'validated' exige as três formulações preenchidas; "
                f"ausentes/vazias: {faltando}."
            )

        if not any(f.strip() for f in self.requested_facts):
            raise ValueError(
                "ficha 'validated' exige ao menos um item em requested_facts."
            )

        ev = self.equivalence_validation
        if not ev.rationale.strip():
            raise ValueError(
                "ficha 'validated' exige equivalence_validation.rationale preenchido."
            )
        if not ev.reviewers:
            raise ValueError(
                "ficha 'validated' exige ao menos um revisor em "
                "equivalence_validation.reviewers."
            )

    # ------------------------------------------------------------------ #
    # Carga e serialização YAML (um arquivo por necessidade)
    # ------------------------------------------------------------------ #

    @classmethod
    def from_yaml(cls, path: Path) -> "NeedSheet":
        """Carrega e valida uma ficha a partir de um arquivo YAML.

        Lança ValueError com mensagem descritiva se o arquivo não puder ser lido
        ou não contiver um mapeamento no nível raiz. Erros de estrutura são
        reportados como pydantic.ValidationError.
        """
        try:
            with open(path, encoding="utf-8") as f:
                data: Any = yaml.safe_load(f)
        except OSError as exc:
            raise ValueError(
                f"Não foi possível abrir a ficha YAML '{path}': {exc}"
            ) from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"Ficha YAML inválida '{path}': {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(
                f"A ficha YAML '{path}' deve conter um mapeamento no nível raiz."
            )
        return cls.model_validate(data)

    def to_yaml(self) -> str:
        """Serializa a ficha para YAML legível (ordem de campos preservada)."""
        data = self.model_dump(mode="json")
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


# --------------------------------------------------------------------------- #
# Validação SEPARADA: conferência ficha × manifesto da seleção
# --------------------------------------------------------------------------- #


def verify_selection_fingerprint(sheet: NeedSheet, selection_manifest_path: Path) -> bool:
    """Confere se o ``scope.selection_fingerprint`` da ficha bate com o manifesto.

    Esta é uma validação **separada** da validação estrutural do ``NeedSheet``:
    - NÃO é executada em toda leitura de ficha (``from_yaml`` apenas valida formato);
    - NÃO recalcula o fingerprint do Parquet — apenas lê o valor já registrado no
      manifesto da seleção (campo ``selection_fingerprint``) e compara.

    Destina-se a ser chamada ao montar/validar o conjunto experimental, não a cada
    acesso individual a uma ficha. Lança ValueError se o manifesto não puder ser
    lido ou não contiver ``selection_fingerprint``.
    """
    try:
        manifest = json.loads(selection_manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(
            f"Não foi possível ler o manifesto da seleção '{selection_manifest_path}': {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Manifesto da seleção inválido '{selection_manifest_path}': {exc}"
        ) from exc

    expected = manifest.get("selection_fingerprint")
    if not expected:
        raise ValueError(
            "Manifesto da seleção não contém 'selection_fingerprint'; "
            "conferência impossível."
        )
    return sheet.scope.selection_fingerprint == expected

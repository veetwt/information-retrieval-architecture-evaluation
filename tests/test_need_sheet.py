# Feature: protocolo-experimental — Ficha de Invariantes (Requirement 5)
# Valida o modelo estrutural NeedSheet: identificador/natureza, campos
# obrigatórios, três formulações, ciclo de vida draft/validated, restrição dos
# seis campos de metadados e preservação da estrutura. Não julga equivalência
# semântica (isso é revisão humana registrada à parte).

import copy
import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from evaluation.need_sheet import (  # noqa: E402
    NeedSheet,
    NeedNature,
    AnswerCardinality,
    ValidationStatus,
    PERMITTED_METADATA_FIELDS,
    verify_selection_fingerprint,
)

TEMPLATE_PATH = (
    Path(__file__).parent.parent
    / "evaluation" / "questions" / "needs" / "_need_sheet.template.yaml"
)

# Fingerprint (64 hex) de exemplo para os testes — não precisa ser o real para
# validar FORMATO; a conferência contra manifesto é testada à parte.
FP = "ec125709322854d164e8f4aeaffb0351ef92e0adfede4d92b17b955b5ea1bc5c"


def draft_sheet_dict() -> dict:
    """Ficha mínima válida em elaboração (draft), com formulações incompletas."""
    return {
        "schema_version": "1.0",
        "need_id": "NI-001",
        "description": "necessidade de exemplo",
        "nature": "metadata",
        "scope": {
            "corpus": "tcu-acordaos-completo-2024-v1",
            "temporal": "2024",
            "selection_fingerprint": FP,
        },
        "mandatory_conditions": [],
        "requested_facts": [],
        "operations": [],
        "formulations": {"direct": "", "paraphrase": "", "verbose": ""},
        "equivalence_validation": {"status": "draft", "rationale": "", "reviewers": []},
    }


def validated_sheet_dict() -> dict:
    """Ficha mínima válida já validada (validated)."""
    d = draft_sheet_dict()
    d["requested_facts"] = ["quantidade de acórdãos", "relator"]
    d["operations"] = ["count", "identify"]
    d["formulations"] = {
        "direct": "formulação direta",
        "paraphrase": "formulação parafraseada",
        "verbose": "formulação mais extensa com explicações adicionais",
    }
    d["equivalence_validation"] = {
        "status": "validated",
        "rationale": "as três pedem os mesmos fatos sob as mesmas condições",
        "reviewers": [{"id": "rev1", "decision": "equivalent"}],
    }
    return d


# --------------------------------------------------------------------------- #
# Estrutura básica e identificador/natureza
# --------------------------------------------------------------------------- #

def test_draft_valido():
    sheet = NeedSheet.model_validate(draft_sheet_dict())
    assert sheet.need_id == "NI-001"
    assert sheet.nature == NeedNature.METADATA
    assert sheet.equivalence_validation.status == ValidationStatus.DRAFT


def test_validated_valido():
    sheet = NeedSheet.model_validate(validated_sheet_dict())
    assert sheet.equivalence_validation.status == ValidationStatus.VALIDATED


@pytest.mark.parametrize("nature", ["metadata", "textual", "mixed"])
def test_naturezas_validas(nature):
    d = draft_sheet_dict()
    d["nature"] = nature
    assert NeedSheet.model_validate(d).nature.value == nature


def test_natureza_invalida_rejeitada():
    d = draft_sheet_dict()
    d["nature"] = "estruturada"
    with pytest.raises(ValidationError):
        NeedSheet.model_validate(d)


def test_need_id_vazio_rejeitado():
    d = draft_sheet_dict()
    d["need_id"] = "   "
    with pytest.raises(ValidationError):
        NeedSheet.model_validate(d)


@pytest.mark.parametrize("nid", ["NI-001", "NI-002", "NI-999", "NI-000"])
def test_need_id_formato_valido(nid):
    d = draft_sheet_dict()
    d["need_id"] = nid
    assert NeedSheet.model_validate(d).need_id == nid


@pytest.mark.parametrize("nid", ["NI-01", "NI-0001", "NI-1", "ni-001", "NI001", "X-001", "NI-00a"])
def test_need_id_formato_invalido(nid):
    # Inclui o padrão dos pilotos (NI-01), que NÃO é id de ficha definitiva.
    d = draft_sheet_dict()
    d["need_id"] = nid
    with pytest.raises(ValidationError):
        NeedSheet.model_validate(d)


def test_campo_obrigatorio_ausente_rejeitado():
    d = draft_sheet_dict()
    del d["scope"]
    with pytest.raises(ValidationError):
        NeedSheet.model_validate(d)


def test_tres_formulacoes_presentes_no_schema():
    # O objeto formulations sempre carrega as três chaves (mesmo vazias em draft).
    sheet = NeedSheet.model_validate(draft_sheet_dict())
    assert hasattr(sheet.formulations, "direct")
    assert hasattr(sheet.formulations, "paraphrase")
    assert hasattr(sheet.formulations, "verbose")


def test_campo_extra_rejeitado():
    d = draft_sheet_dict()
    d["campo_desconhecido"] = "x"
    with pytest.raises(ValidationError):
        NeedSheet.model_validate(d)


# --------------------------------------------------------------------------- #
# Ciclo de vida draft vs validated
# --------------------------------------------------------------------------- #

def test_validated_exige_tres_formulacoes():
    d = validated_sheet_dict()
    d["formulations"]["verbose"] = "   "  # só espaços
    with pytest.raises(ValidationError) as exc:
        NeedSheet.model_validate(d)
    assert "formula" in str(exc.value).lower()


def test_validated_exige_requested_facts():
    d = validated_sheet_dict()
    d["requested_facts"] = []
    with pytest.raises(ValidationError) as exc:
        NeedSheet.model_validate(d)
    assert "requested_facts" in str(exc.value)


def test_validated_exige_rationale():
    d = validated_sheet_dict()
    d["equivalence_validation"]["rationale"] = ""
    with pytest.raises(ValidationError) as exc:
        NeedSheet.model_validate(d)
    assert "rationale" in str(exc.value)


def test_validated_exige_revisor():
    d = validated_sheet_dict()
    d["equivalence_validation"]["reviewers"] = []
    with pytest.raises(ValidationError) as exc:
        NeedSheet.model_validate(d)
    assert "revisor" in str(exc.value).lower() or "reviewers" in str(exc.value)


def test_draft_tolera_formulacoes_incompletas():
    # Em draft, formulações vazias são aceitas (sem erro).
    sheet = NeedSheet.model_validate(draft_sheet_dict())
    assert sheet.formulations.direct == ""


# --------------------------------------------------------------------------- #
# Condições obrigatórias e campos de metadados permitidos
# --------------------------------------------------------------------------- #

def test_mandatory_conditions_pode_ser_vazia():
    # Necessidade por metadados sem condição documental explícita (ex.: contagem).
    d = draft_sheet_dict()
    d["mandatory_conditions"] = []
    assert NeedSheet.model_validate(d).mandatory_conditions == []


def test_condicao_metadata_com_campo_permitido():
    d = draft_sheet_dict()
    d["mandatory_conditions"] = [
        {"description": "restrita ao Plenário", "relates_to": "metadata",
         "fields": ["COLEGIADO"]}
    ]
    sheet = NeedSheet.model_validate(d)
    assert sheet.mandatory_conditions[0].fields == ["COLEGIADO"]


def test_condicao_metadata_com_campo_nao_permitido_rejeitada():
    d = draft_sheet_dict()
    d["mandatory_conditions"] = [
        {"description": "campo inválido", "relates_to": "metadata",
         "fields": ["NUMACORDAO"]}
    ]
    with pytest.raises(ValidationError) as exc:
        NeedSheet.model_validate(d)
    assert "NUMACORDAO" in str(exc.value)


def test_todos_os_seis_campos_permitidos():
    d = draft_sheet_dict()
    d["mandatory_conditions"] = [
        {"description": "usa todos os seis", "relates_to": "metadata",
         "fields": list(PERMITTED_METADATA_FIELDS)}
    ]
    sheet = NeedSheet.model_validate(d)
    assert sheet.mandatory_conditions[0].fields == list(PERMITTED_METADATA_FIELDS)


def test_condicao_textual_nao_aceita_fields():
    d = draft_sheet_dict()
    d["mandatory_conditions"] = [
        {"description": "ancorada no texto", "relates_to": "textual",
         "fields": ["COLEGIADO"]}
    ]
    with pytest.raises(ValidationError) as exc:
        NeedSheet.model_validate(d)
    assert "metadata" in str(exc.value).lower()


def test_condicao_textual_sem_fields_valida():
    d = draft_sheet_dict()
    d["mandatory_conditions"] = [
        {"description": "ancorada no texto", "relates_to": "textual"}
    ]
    sheet = NeedSheet.model_validate(d)
    assert sheet.mandatory_conditions[0].fields == []


# --------------------------------------------------------------------------- #
# Critério de relevância (campos opcionais previstos no protocolo, §8.E)
# --------------------------------------------------------------------------- #

def test_campos_relevancia_sao_opcionais():
    # Ficha draft sem os novos campos continua válida (retrocompatibilidade).
    sheet = NeedSheet.model_validate(draft_sheet_dict())
    assert sheet.answer_cardinality is None
    assert sheet.required_textual_evidence == []
    assert sheet.partial_relevance_rule == ""


@pytest.mark.parametrize("card", ["single", "enumeration", "multidocument"])
def test_answer_cardinality_valida(card):
    d = draft_sheet_dict()
    d["answer_cardinality"] = card
    assert NeedSheet.model_validate(d).answer_cardinality.value == card


def test_answer_cardinality_invalida_rejeitada():
    d = draft_sheet_dict()
    d["answer_cardinality"] = "unica"
    with pytest.raises(ValidationError):
        NeedSheet.model_validate(d)


def test_required_textual_evidence_lista():
    d = draft_sheet_dict()
    d["required_textual_evidence"] = ["conteúdo trata de X", "e também de Y"]
    sheet = NeedSheet.model_validate(d)
    assert len(sheet.required_textual_evidence) == 2


def test_partial_relevance_rule_exige_cardinalidade_multi():
    # single (ou ausente) + partial_relevance_rule preenchido => incoerente.
    d = draft_sheet_dict()
    d["answer_cardinality"] = "single"
    d["partial_relevance_rule"] = "qualquer doc do tema conta"
    with pytest.raises(ValidationError) as exc:
        NeedSheet.model_validate(d)
    assert "partial_relevance_rule" in str(exc.value)


def test_partial_relevance_rule_sem_cardinalidade_rejeitada():
    d = draft_sheet_dict()
    d["partial_relevance_rule"] = "contribui com parte da resposta"
    with pytest.raises(ValidationError):
        NeedSheet.model_validate(d)


@pytest.mark.parametrize("card", ["enumeration", "multidocument"])
def test_partial_relevance_rule_valida_em_multidocumento(card):
    d = draft_sheet_dict()
    d["answer_cardinality"] = card
    d["partial_relevance_rule"] = "relevante se cobre a parte que lhe cabe"
    sheet = NeedSheet.model_validate(d)
    assert sheet.partial_relevance_rule.startswith("relevante")


def test_campos_relevancia_round_trip_yaml(tmp_path):
    d = draft_sheet_dict()
    d["answer_cardinality"] = "multidocument"
    d["required_textual_evidence"] = ["tema de pedágio"]
    d["partial_relevance_rule"] = "contribui com parte"
    p = tmp_path / "NI-003.yaml"
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    sheet = NeedSheet.from_yaml(p)
    reloaded = yaml.safe_load(sheet.to_yaml())
    assert reloaded["answer_cardinality"] == "multidocument"
    assert reloaded["required_textual_evidence"] == ["tema de pedágio"]
    assert reloaded["partial_relevance_rule"] == "contribui com parte"


# --------------------------------------------------------------------------- #
# Carga/serialização YAML e o template do projeto
# --------------------------------------------------------------------------- #

def test_from_yaml_round_trip(tmp_path):
    d = validated_sheet_dict()
    p = tmp_path / "NI-001.yaml"
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    sheet = NeedSheet.from_yaml(p)
    assert sheet.need_id == "NI-001"
    # to_yaml deve ser recarregável e preservar o conteúdo essencial.
    reloaded = yaml.safe_load(sheet.to_yaml())
    assert reloaded["need_id"] == "NI-001"
    assert reloaded["nature"] == "metadata"


def test_from_yaml_nao_mapeamento_rejeitado(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("- apenas\n- uma\n- lista\n", encoding="utf-8")
    with pytest.raises(ValueError):
        NeedSheet.from_yaml(p)


def test_template_existe_e_e_draft_valido():
    # O template do projeto deve existir e carregar como ficha draft válida.
    assert TEMPLATE_PATH.exists(), f"template ausente em {TEMPLATE_PATH}"
    sheet = NeedSheet.from_yaml(TEMPLATE_PATH)
    assert sheet.equivalence_validation.status == ValidationStatus.DRAFT
    # O template usa NI-000 como placeholder reservado (não é necessidade real).
    assert sheet.need_id == "NI-000"
    # O template já referencia a seleção congelada por fingerprint (formato válido).
    assert len(sheet.scope.selection_fingerprint) == 64


# --------------------------------------------------------------------------- #
# Vínculo com o corpus congelado: formato do fingerprint + conferência separada
# --------------------------------------------------------------------------- #

def test_scope_exige_selection_fingerprint():
    d = draft_sheet_dict()
    del d["scope"]["selection_fingerprint"]
    with pytest.raises(ValidationError):
        NeedSheet.model_validate(d)


@pytest.mark.parametrize("bad", [
    "ABC",                    # curto
    "G" * 64,                 # caractere não-hex
    FP.upper(),               # maiúsculas não permitidas
    FP + "0",                 # 65 chars
    FP[:-1],                  # 63 chars
])
def test_selection_fingerprint_formato_invalido(bad):
    d = draft_sheet_dict()
    d["scope"]["selection_fingerprint"] = bad
    with pytest.raises(ValidationError):
        NeedSheet.model_validate(d)


def test_verify_selection_fingerprint_confere_com_manifesto(tmp_path):
    sheet = NeedSheet.model_validate(draft_sheet_dict())
    manifest = tmp_path / "sel_manifest.json"
    manifest.write_text(
        '{"selection_fingerprint": "%s"}' % FP, encoding="utf-8"
    )
    assert verify_selection_fingerprint(sheet, manifest) is True


def test_verify_selection_fingerprint_detecta_divergencia(tmp_path):
    sheet = NeedSheet.model_validate(draft_sheet_dict())
    manifest = tmp_path / "sel_manifest.json"
    manifest.write_text('{"selection_fingerprint": "%s"}' % ("a" * 64), encoding="utf-8")
    assert verify_selection_fingerprint(sheet, manifest) is False


def test_verify_selection_fingerprint_manifesto_sem_campo(tmp_path):
    sheet = NeedSheet.model_validate(draft_sheet_dict())
    manifest = tmp_path / "sel_manifest.json"
    manifest.write_text('{"outro": 1}', encoding="utf-8")
    with pytest.raises(ValueError):
        verify_selection_fingerprint(sheet, manifest)

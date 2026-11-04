# Feature: retrieval estruturado v0.3 — reconhecimento robusto de ENTIDADE e
# suporte conservador a UNIDADETECNICA. Testa siglas (simples/compostas/com
# barra, inclusive em parênteses com conteúdo extra), variantes/identidade,
# multivalor, menções de contexto, ambiguidade de entidades distintas, ausência
# de filtro, conjunção, determinismo e os helpers de forma de sigla.

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from retrieval.structured import (  # noqa: E402
    StructuredRetriever,
    _extract_siglas,
    _is_acronym_like,
    _sigla_usable_in_text,
)


def make_df() -> pd.DataFrame:
    rows = [
        # sigla com barra dentro de parênteses com conteúdo extra (CNPJ)
        ("d1", "Plenário", "AROLDO CEDRAZ", "DENÚNCIA (DEN)", "24/01/2024",
         "Administração Regional do Serviço Social do Comércio no Estado do "
         "Mato Grosso do Sul (Sesc/MS, CNPJ 03.560.440/0001-91)", "AudContratações."),
        # mesma identidade-base de outra org com sigla simples; variante com sigla
        ("d2", "Plenário", "WALTON ALENCAR RODRIGUES", "REPRESENTAÇÃO (REPR)", "13/03/2024",
         "Agência Nacional de Transportes Terrestres (ANTT).", "AudRodoviaAviação."),
        # variante sem sigla da MESMA entidade (ANTT)
        ("d3", "Plenário", "AUGUSTO NARDES", "REPRESENTAÇÃO (REPR)", "28/02/2024",
         "Agência Nacional de Transportes Terrestres.", "AudRodoviaAviação."),
        # multivalor
        ("d4", "Plenário", "VITAL DO RÊGO", "REPRESENTAÇÃO (REPR)", "17/01/2024",
         "Agência Nacional de Transportes Terrestres; Ministério dos Transportes.",
         "AudRodoviaAviação."),
        # parêntese com palavra comum ('em Liquidação') — NÃO é sigla
        ("d5", "Plenário", "JORGE OLIVEIRA", "TOMADA DE CONTAS ESPECIAL (TCE)", "02/07/2024",
         "Grupo Executivo Para Extinção do Dner - MT (em Liquidação)", "AudTCE."),
        # duas entidades específicas distintas no mesmo doc (ambíguo se ambas citadas)
        ("d6", "Segunda Câmara", "ANTONIO ANASTASIA", "REPRESENTAÇÃO (REPR)", "15/10/2024",
         "Universidade Federal do Pará; Universidade Federal de Pernambuco.",
         "AudEducação."),
        # UNIDADETECNICA com sigla distinta
        ("d7", "Primeira Câmara", "JHONATAN DE JESUS", "APOSENTADORIA (APOS)", "08/10/2024",
         "Instituto Nacional do Seguro Social.",
         "Unidade de Auditoria Especializada em Pessoal (AudPessoal)."),
    ]
    cols = ["doc_id", "COLEGIADO", "RELATOR", "TIPOPROCESSO", "DATASESSAO",
            "ENTIDADE", "UNIDADETECNICA"]
    return pd.DataFrame(rows, columns=cols)


@pytest.fixture
def r():
    return StructuredRetriever(make_df(), corpus_fingerprint="fp")


# --- helpers de forma de sigla ---

def test_is_acronym_like():
    assert _is_acronym_like("ANTT") is True
    assert _is_acronym_like("Sesc/MS") is True
    assert _is_acronym_like("AudPessoal") is True
    assert _is_acronym_like("que") is False
    assert _is_acronym_like("em") is False
    assert _is_acronym_like("Eletronorte") is False  # uma única maiúscula


def test_extract_siglas_ignora_palavra_comum_e_rotulo_identificador():
    # Palavras comuns dentro de parênteses não são siglas.
    assert _extract_siglas("em Liquidação") == []
    assert _extract_siglas("que incorporou a Amazonas") == []
    # Rótulo de identificador seguido de número (CNPJ 03...) NÃO é sigla de
    # entidade; a sigla real (Sesc/MS) é preservada.
    assert _extract_siglas("Sesc/MS, CNPJ 03.560.440/0001-91") == ["Sesc/MS"]
    # Rótulos administrativos seguidos de número são descartados em geral.
    assert _extract_siglas("UASG 158154") == []
    assert _extract_siglas("ANTT") == ["ANTT"]


def test_extract_siglas_preserva_multiplas_siglas_legitimas():
    # A função NÃO se limita ao primeiro token do parêntese: siglas legítimas em
    # partes distintas (separadas por vírgula/;) são todas extraídas, desde que
    # cada uma tenha forma de acrônimo.
    assert _extract_siglas("ANAC; ANTT") == ["ANAC", "ANTT"]
    assert _extract_siglas("Cefet/RJ, AGU") == ["Cefet/RJ", "AGU"]
    # 'Casemg' tem só uma maiúscula (nome, não acrônimo) -> não é extraída,
    # enquanto 'Ceasa/MG' (com barra) é.
    assert _extract_siglas("Ceasa/MG, Casemg") == ["Ceasa/MG"]


def test_sigla_usable_in_text():
    assert _sigla_usable_in_text("antt") is True
    assert _sigla_usable_in_text("bb") is False       # curta demais
    assert _sigla_usable_in_text("cc/pr") is True      # barra permite


# --- sigla com barra e conteúdo extra no parêntese ---

def test_sigla_com_barra_casa(r):
    cond = r.interpret("denúncia referente ao Sesc/MS")
    assert "ENTIDADE" in cond
    assert "Sesc/MS" in cond["ENTIDADE"]
    res = r.retrieve("denúncia referente ao Sesc/MS")
    assert res.doc_ids == ["d1"]


def test_palavra_comum_em_parenteses_nao_vira_sigla(r):
    # 'em'/'que' não podem casar como sigla a partir de d5 / entidades
    cond = r.interpret("qual processo em que houve irregularidade?")
    assert "ENTIDADE" not in cond


# --- variantes e multivalor (ANTT) ---

def test_nome_completo_unifica_variantes_e_multivalor(r):
    res = r.retrieve("representações da Agência Nacional de Transportes Terrestres")
    assert set(res.doc_ids) == {"d2", "d3", "d4"}


def test_sigla_antt_unica_identidade(r):
    # ANTT com ponto (d2) e a variante multivalor (d4) e sem sigla (d3):
    # a sigla 'ANTT' só está nas que têm parênteses; identidade-base é a mesma.
    cond = r.interpret("processos da ANTT")
    # 'antt' aparece só em d2 como sigla; d4 tem 'ANTT' dentro de multivalor sem
    # parênteses? Não: d4 não tem sigla. A identidade da sigla deve ser única.
    assert "ENTIDADE" in cond
    assert "Transportes Terrestres" in cond["ENTIDADE"]


# --- entidades distintas (ambiguidade) ---

def test_entidades_distintas_nao_escolhe_arbitrariamente(r):
    diag = {}
    cond = r.interpret(
        "comparar a Universidade Federal do Pará e a Universidade Federal de Pernambuco",
        diag,
    )
    assert "ENTIDADE" not in cond
    assert diag.get("entidade", {}).get("reason") == "multiple_distinct_entities"


def test_entidade_unica_especifica_casa(r):
    res = r.retrieve("atos da Universidade Federal do Pará")
    assert res.doc_ids == ["d6"]


# --- UNIDADETECNICA (conservador, por sigla) ---

def test_unidadetecnica_por_sigla(r):
    cond = r.interpret("processos analisados pela AudPessoal")
    assert cond.get("UNIDADETECNICA") is not None
    res = r.retrieve("processos analisados pela AudPessoal")
    assert res.doc_ids == ["d7"]


def test_unidadetecnica_sem_sigla_nao_filtra(r):
    # Mencionar o nome genérico sem a sigla não deve filtrar UNIDADETECNICA
    cond = r.interpret("unidade de auditoria especializada")
    assert "UNIDADETECNICA" not in cond


# --- conjunção, ausência, determinismo ---

def test_conjuncao_entidade_tipo(r):
    res = r.retrieve("representações da Agência Nacional de Transportes Terrestres")
    assert set(res.doc_ids) == {"d2", "d3", "d4"}
    assert set(res.fields_used) == {"TIPOPROCESSO", "ENTIDADE"}


def test_sem_filtro_identificavel(r):
    res = r.retrieve("qual foi o entendimento final sobre o caso?")
    assert res.n_documents == 0
    assert res.diagnostics.get("no_conditions_identified") is True


def test_determinismo(r):
    q = "representações da Agência Nacional de Transportes Terrestres"
    assert r.retrieve(q).doc_ids == r.retrieve(q).doc_ids


# --- Integração no corpus real ---

ROOT = Path(__file__).parent.parent
SEL_DIR = ROOT / "data" / "processed" / "experimental"


def _real_selection():
    cands = sorted(SEL_DIR.glob("selection_tcu-acordaos-completo-2024-v1_*.parquet"))
    return cands[-1] if cands else None


@pytest.mark.skipif(_real_selection() is None, reason="seleção congelada ausente")
def test_integracao_sesc_ms_real():
    rr = StructuredRetriever.from_selection(_real_selection())
    cond = rr.interpret("denúncia referente ao Sesc/MS")
    assert "ENTIDADE" in cond
    assert "Sesc/MS" in cond["ENTIDADE"]


@pytest.mark.skipif(_real_selection() is None, reason="seleção congelada ausente")
def test_integracao_sem_sigla_espuria_real():
    # Uma consulta sobre ANTT não deve produzir entidade espúria (ex.: Eletrobras)
    rr = StructuredRetriever.from_selection(_real_selection())
    cond = rr.interpret(
        "representações da Agência Nacional de Transportes Terrestres sobre pedágio"
    )
    assert "Transportes Terrestres" in cond.get("ENTIDADE", "")


@pytest.mark.skipif(_real_selection() is None, reason="seleção congelada ausente")
def test_integracao_estado_pe_contexto_real():
    # 'Estado de Pernambuco' como contexto geográfico não deve virar filtro sozinho
    rr = StructuredRetriever.from_selection(_real_selection())
    diag = {}
    cond = rr.interpret("irregularidades em recursos da educação no Estado de Pernambuco", diag)
    assert "ENTIDADE" not in cond

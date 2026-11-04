# Feature: retrieval estruturado — interpretação genérica de ENTIDADE (v0.2).
# Testa reconhecimento de siglas/nomes, equivalência de variantes e multivalor,
# prevenção de falsos positivos de contexto (órgão julgador / menções genéricas),
# tratamento de ambiguidade, ausência de condições e determinismo.

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from retrieval.structured import StructuredRetriever  # noqa: E402


def make_df() -> pd.DataFrame:
    """Corpus sintético com variantes e multivalor de ENTIDADE."""
    rows = [
        # d1: entidade com sigla entre parênteses
        ("d1", "Plenário", "AROLDO CEDRAZ", "REPRESENTAÇÃO (REPR)", "06/11/2024",
         "Agência Nacional de Transportes Terrestres (ANTT).", "AudRodoviaAviação."),
        # d2: mesma entidade, variante sem sigla, com ponto
        ("d2", "Plenário", "WALTON ALENCAR RODRIGUES", "REPRESENTAÇÃO (REPR)", "13/03/2024",
         "Agência Nacional de Transportes Terrestres.", "AudRodoviaAviação."),
        # d3: multivalor — ANTT + Ministério dos Transportes
        ("d3", "Plenário", "AUGUSTO NARDES", "REPRESENTAÇÃO (REPR)", "28/02/2024",
         "Agência Nacional de Transportes Terrestres; Ministério dos Transportes.",
         "AudRodoviaAviação."),
        # d4: entidade diferente (contém 'Tribunal de Contas da União' como alvo real)
        ("d4", "Plenário", "VITAL DO RÊGO", "ADMINISTRATIVO (ADM)", "17/01/2024",
         "Tribunal de Contas da União", "AudPessoal."),
        # d5: entidade genérica "Estado de Pernambuco"
        ("d5", "Plenário", "VITAL DO RÊGO", "DENÚNCIA (DEN)", "17/01/2024",
         "Estado de Pernambuco.", "AudPessoal."),
        # d6: entidade específica de educação em PE
        ("d6", "Segunda Câmara", "ANTONIO ANASTASIA", "APOSENTADORIA (APOS)", "15/10/2024",
         "Secretaria de Estado da Educação de Pernambuco.", "AudPessoal."),
    ]
    cols = ["doc_id", "COLEGIADO", "RELATOR", "TIPOPROCESSO", "DATASESSAO",
            "ENTIDADE", "UNIDADETECNICA"]
    return pd.DataFrame(rows, columns=cols)


@pytest.fixture
def r():
    return StructuredRetriever(make_df(), corpus_fingerprint="fp")


# --- Reconhecimento de nome completo e variantes/multivalor ---

def test_nome_completo_casa_todas_as_variantes(r):
    res = r.retrieve("representações da Agência Nacional de Transportes Terrestres")
    # d1 (com sigla), d2 (sem sigla), d3 (multivalor) devem casar
    assert set(res.doc_ids) == {"d1", "d2", "d3"}
    assert "ENTIDADE" in res.fields_used


def test_multivalor_componente_casa(r):
    # Mencionar 'Ministério dos Transportes' deve casar o componente em d3
    res = r.retrieve("processos do Ministério dos Transportes")
    assert "d3" in res.doc_ids


# --- Sigla inequívoca entre parênteses ---

def test_sigla_inequivoca_casa(r):
    # 'ANTT' aparece como sigla inequívoca de um único componente
    cond = r.interpret("representações da ANTT")
    assert "ENTIDADE" in cond
    assert "Transportes Terrestres" in cond["ENTIDADE"]


def test_filtro_captura_variantes_mesmo_citando_sigla(r):
    # Mesmo que a condição identificada venha com '(ANTT)', o filtro deve capturar
    # as variantes com e sem sigla (d1 com '(ANTT)', d2 sem, d3 multivalor).
    res = r.retrieve("representações da Agência Nacional de Transportes Terrestres (ANTT)")
    assert set(res.doc_ids) == {"d1", "d2", "d3"}


# --- Falsos positivos de contexto ---

def test_context_tokens_derivados_do_corpus(r):
    # A guarda de especificidade depende de tokens de contexto derivados por
    # document-frequency. Em corpus sintético pequeno o conjunto existe (pode ser
    # vazio); o comportamento estatístico é validado na integração (corpus real).
    assert hasattr(r, "_context_tokens")
    assert isinstance(r._context_tokens, set)


def test_is_specific_usa_tokens_de_contexto():
    # Força um conjunto de tokens de contexto e verifica a regra de especificidade,
    # de forma determinística e independente do tamanho do corpus.
    rr = StructuredRetriever(make_df(), corpus_fingerprint="fp")
    rr._context_tokens = {"estado", "contas", "uniao", "tribunal", "secretaria"}
    # só tokens de contexto -> não específico
    assert rr._is_specific("tribunal de contas da uniao") is False
    assert rr._is_specific("estado de") is False
    # contém token distintivo -> específico
    assert rr._is_specific("agencia nacional de transportes terrestres") is True


# --- Ambiguidade, ausência e determinismo ---

def test_sem_entidade_identificavel(r):
    diag = {}
    cond = r.interpret("qual foi a decisão sobre o mérito?", diag)
    assert "ENTIDADE" not in cond


def test_determinismo(r):
    q = "representações da Agência Nacional de Transportes Terrestres"
    assert r.retrieve(q).doc_ids == r.retrieve(q).doc_ids


def test_diagnostico_presente_no_resultado(r):
    res = r.retrieve("qual acórdão do Tribunal de Contas da União tratou do tema X?")
    assert "interpretation_notes" in res.diagnostics


# --- Integração: guarda estatística de contexto no corpus real ---

ROOT = Path(__file__).parent.parent
SEL_DIR = ROOT / "data" / "processed" / "experimental"


def _real_selection():
    cands = sorted(SEL_DIR.glob("selection_tcu-acordaos-completo-2024-v1_*.parquet"))
    return cands[-1] if cands else None


@pytest.mark.skipif(_real_selection() is None, reason="seleção congelada ausente")
def test_integracao_tcu_julgador_nao_vira_filtro():
    rr = StructuredRetriever.from_selection(_real_selection())
    diag = {}
    cond = rr.interpret(
        "qual acórdão do Tribunal de Contas da União tratou do tema de merenda?", diag
    )
    # No corpus real, 'tribunal/contas/uniao' são tokens de contexto frequentes;
    # a menção ao órgão julgador NÃO deve impor filtro de ENTIDADE.
    assert "ENTIDADE" not in cond


@pytest.mark.skipif(_real_selection() is None, reason="seleção congelada ausente")
def test_integracao_antt_especifica_vira_filtro():
    rr = StructuredRetriever.from_selection(_real_selection())
    cond = rr.interpret(
        "representações da Agência Nacional de Transportes Terrestres", {}
    )
    assert "ENTIDADE" in cond
    assert "Transportes Terrestres" in cond["ENTIDADE"]

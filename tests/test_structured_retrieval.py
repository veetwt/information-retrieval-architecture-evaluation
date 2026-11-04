# Feature: retrieval — protótipo da arquitetura estruturada + interface comum.
# Testa interpretação genérica de condições de metadados e semântica de
# recuperação por filtros (sem score inventado, determinística). Inclui um
# teste de integração opcional sobre a seleção congelada real.

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from retrieval.base import RetrievalResult, RetrievedDocument, Retriever  # noqa: E402
from retrieval.structured import StructuredRetriever  # noqa: E402


def make_df() -> pd.DataFrame:
    """Corpus sintético pequeno com os seis campos de metadados."""
    rows = [
        # doc_id, COLEGIADO, RELATOR, TIPOPROCESSO, DATASESSAO, ENTIDADE, UNIDADETECNICA
        ("d1", "Plenário", "AROLDO CEDRAZ", "DENÚNCIA (DEN)", "24/01/2024",
         "Administração Regional do Sesc no MS.", "AudContratações."),
        ("d2", "Plenário", "WALTON ALENCAR RODRIGUES", "REPRESENTAÇÃO (REPR)", "06/11/2024",
         "Agência Nacional de Transportes Terrestres.", "AudRodoviaAviação."),
        ("d3", "Primeira Câmara", "JHONATAN DE JESUS", "APOSENTADORIA (APOS)", "08/10/2024",
         "Universidade Federal do Pará.", "AudPessoal."),
        ("d4", "Segunda Câmara", "ANTONIO ANASTASIA", "REPRESENTAÇÃO (REPR)", "19/03/2024",
         "Agência Nacional de Transportes Terrestres.", "AudRodoviaAviação."),
        ("d5", "Plenário", "AROLDO CEDRAZ", "DENÚNCIA (DEN)", "24/01/2024",
         "Outra Entidade Qualquer.", "AudContratações."),
    ]
    cols = ["doc_id", "COLEGIADO", "RELATOR", "TIPOPROCESSO", "DATASESSAO",
            "ENTIDADE", "UNIDADETECNICA"]
    return pd.DataFrame(rows, columns=cols)


@pytest.fixture
def retriever():
    return StructuredRetriever(make_df(), corpus_fingerprint="fp-teste")


# --------------------------------------------------------------------------- #
# Interface comum
# --------------------------------------------------------------------------- #

def test_structured_cumpre_protocolo(retriever):
    assert isinstance(retriever, Retriever)
    assert retriever.architecture_name == "structured"


def test_result_tipos(retriever):
    res = retriever.retrieve("representação do Plenário")
    assert isinstance(res, RetrievalResult)
    assert all(isinstance(d, RetrievedDocument) for d in res.documents)
    assert res.doc_ids == sorted(res.doc_ids)  # ordem determinística


# --------------------------------------------------------------------------- #
# Interpretação de condições
# --------------------------------------------------------------------------- #

def test_interpreta_colegiado_plenario(retriever):
    c = retriever.interpret("acórdãos do Plenário")
    assert c.get("COLEGIADO") == "Plenário"


def test_interpreta_primeira_camara(retriever):
    assert retriever.interpret("na Primeira Câmara")["COLEGIADO"] == "Primeira Câmara"
    assert retriever.interpret("na 1ª Câmara")["COLEGIADO"] == "Primeira Câmara"


def test_interpreta_tipoprocesso_por_nome(retriever):
    assert retriever.interpret("uma representação qualquer")["TIPOPROCESSO"] == "REPRESENTAÇÃO (REPR)"
    assert retriever.interpret("trata-se de denúncia")["TIPOPROCESSO"] == "DENÚNCIA (DEN)"


def test_interpreta_relator_inequivoco(retriever):
    c = retriever.interpret("sob relatoria de Aroldo Cedraz")
    assert c.get("RELATOR") == "AROLDO CEDRAZ"


def test_interpreta_data_numerica_e_extenso(retriever):
    assert retriever.interpret("sessão de 24/01/2024")["DATASESSAO"] == "24/01/2024"
    assert retriever.interpret("em 24 de janeiro de 2024")["DATASESSAO"] == "24/01/2024"


def test_sem_condicoes_identificadas(retriever):
    res = retriever.retrieve("qual o entendimento jurisprudencial sobre o tema X?")
    assert res.diagnostics.get("no_conditions_identified") is True
    assert res.n_documents == 0  # não inventa filtros nem documentos


# --------------------------------------------------------------------------- #
# Semântica de recuperação
# --------------------------------------------------------------------------- #

def test_conjuncao_de_condicoes(retriever):
    # Plenário + Denúncia + Aroldo Cedraz + 24/01/2024 => d1 e d5
    res = retriever.retrieve("denúncia do Plenário sob relatoria de Aroldo Cedraz em 24/01/2024")
    assert set(res.doc_ids) == {"d1", "d5"}


def test_score_nunca_inventado(retriever):
    res = retriever.retrieve("representação do Plenário")
    assert all(d.score is None for d in res.documents)


def test_rank_sequencial_e_determinístico(retriever):
    res = retriever.retrieve("representação")  # d2 e d4
    ranks = [d.rank for d in res.documents]
    assert ranks == list(range(1, len(ranks) + 1))
    # reexecução dá a mesma ordem
    res2 = retriever.retrieve("representação")
    assert res.doc_ids == res2.doc_ids


def test_entidade_conservadora_casa_quando_literal(retriever):
    res = retriever.retrieve(
        "representações relativas à Agência Nacional de Transportes Terrestres"
    )
    assert set(res.doc_ids) == {"d2", "d4"}
    assert "ENTIDADE" in res.fields_used


def test_fields_used_reflete_condicoes(retriever):
    res = retriever.retrieve("aposentadoria na Primeira Câmara")
    assert set(res.fields_used) == {"TIPOPROCESSO", "COLEGIADO"}
    assert res.doc_ids == ["d3"]


# --------------------------------------------------------------------------- #
# Integração: seleção congelada real (se presente)
# --------------------------------------------------------------------------- #

ROOT = Path(__file__).parent.parent
SEL_DIR = ROOT / "data" / "processed" / "experimental"


def _real_selection():
    cands = sorted(SEL_DIR.glob("selection_tcu-acordaos-completo-2024-v1_*.parquet"))
    return cands[-1] if cands else None


@pytest.mark.skipif(_real_selection() is None, reason="seleção congelada ausente")
def test_integracao_selecao_real():
    sel = _real_selection()
    r = StructuredRetriever.from_selection(sel)
    res = r.retrieve("representações do Plenário")
    # universo congelado esperado
    assert res.diagnostics["n_corpus"] == 21631
    # deve identificar condições e retornar um conjunto não vazio, determinístico
    assert res.diagnostics["identified_conditions"].get("COLEGIADO") == "Plenário"
    assert res.diagnostics["identified_conditions"].get("TIPOPROCESSO") == "REPRESENTAÇÃO (REPR)"
    assert res.n_documents > 0
    assert res.doc_ids == sorted(res.doc_ids)

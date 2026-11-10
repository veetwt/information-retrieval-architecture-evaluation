# Testes do gerador de pools (SEM rótulos de relevância). Usa recuperadores STUB
# determinísticos e fichas sintéticas; não acessa índice real nem rede.

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from retrieval.base import RetrievalResult, RetrievedDocument  # noqa: E402
from evaluation.need_sheet import (  # noqa: E402
    EquivalenceValidation,
    Formulations,
    MandatoryCondition,
    NeedSheet,
    Scope,
)
from evaluation.pool_generator import PoolGenerator, validate_official  # noqa: E402

FP = "ec125709322854d164e8f4aeaffb0351ef92e0adfede4d92b17b955b5ea1bc5c"


# --------------------------------------------------------------------------- #
# Stubs de recuperadores (programáveis por query)
# --------------------------------------------------------------------------- #

class StubStructured:
    VERSION = "0.3.0"
    architecture_name = "structured"

    def __init__(self, by_query, conditions_by_query=None):
        # by_query: dict query -> lista de doc_ids (conjunto, sem ranking)
        self._by_query = by_query
        self._cond = conditions_by_query or {}

    def retrieve(self, query):
        docs = [RetrievedDocument(doc_id=d, rank=i + 1, score=None)
                for i, d in enumerate(self._by_query.get(query, []))]
        return RetrievalResult(
            query=query, architecture="structured", documents=docs,
            fields_used=[], diagnostics={"identified_conditions": self._cond.get(query, {})},
        )


class StubRanked:
    def __init__(self, name, version, by_query, path_by_query=None):
        self.architecture_name = name
        self.VERSION = version
        self._by_query = by_query           # query -> [(doc_id, score), ...]
        self._path = path_by_query or {}

    def retrieve(self, query):
        docs = [RetrievedDocument(doc_id=d, rank=i + 1, score=s)
                for i, (d, s) in enumerate(self._by_query.get(query, []))]
        diag = {}
        if query in self._path:
            diag["path"] = self._path[query]
        return RetrievalResult(
            query=query, architecture=self.architecture_name, documents=docs,
            fields_used=["ASSUNTO", "ACORDAO"], diagnostics=diag,
        )


class StubIndex:
    def __init__(self, meta):
        self.meta = meta


class StubHybridContainer:
    """Objeto 'hybrid-like' que o PoolGenerator consome via composição."""
    VERSION = "0.2.0"

    def __init__(self, structured, vector, hybrid, meta):
        self._structured = structured
        self._vector = vector
        self._hybrid_impl = hybrid
        self._vector._index = StubIndex(meta)

    def retrieve(self, query):
        return self._hybrid_impl.retrieve(query)


def make_sheet(need_id, direct, paraphrase, verbose, status="draft", conditions=None):
    return NeedSheet(
        schema_version="1.0",
        need_id=need_id,
        description="necessidade sintética de teste",
        nature="metadata",
        scope=Scope(corpus="tcu-acordaos-completo-2024-v1", temporal="2024",
                    selection_fingerprint=FP),
        mandatory_conditions=conditions or [],
        requested_facts=["fato"],
        operations=["identify"],
        formulations=Formulations(direct=direct, paraphrase=paraphrase, verbose=verbose),
        equivalence_validation=EquivalenceValidation(status=status),
    )


def build_generator(structured, vector, hybrid, df, T=100, T_cond=100, D=50):
    meta = {"model_name": "stub", "embedding_dim": 8, "n_docs_indexed": len(df),
            "n_chunks": len(df), "is_partial_index": False, "selection_fingerprint": FP}
    container = StubHybridContainer(structured, vector, hybrid, meta)
    return PoolGenerator(
        container, selection_df=df, selection_fingerprint=FP, index_meta=meta,
        D=D, T=T, T_cond=T_cond, k_cuts=(5, 10, 50),
    )


def make_df(doc_ids, **cols):
    base = {"doc_id": list(doc_ids)}
    base.update(cols)
    return pd.DataFrame(base)


# --------------------------------------------------------------------------- #
# Testes
# --------------------------------------------------------------------------- #

def test_j0_e_dedup_basico(tmp_path):
    # 3 formulações com conjuntos estruturados pequenos (censo) e rankings.
    qd, qp, qv = "direta", "parafrase", "prolixa"
    structured = StubStructured({qd: ["d1", "d2"], qp: ["d2", "d3"], qv: ["d1"]})
    vector = StubRanked("vector", "0.2.0", {qd: [("d1", .9), ("d4", .5)],
                                            qp: [("d3", .8)], qv: [("d5", .7)]})
    hybrid = StubRanked("hybrid", "0.2.0",
                        {qd: [("d1", .9)], qp: [("d3", .8)], qv: [("d5", .7)]},
                        path_by_query={qd: "C", qp: "C", qv: "A"})
    df = make_df(["d1", "d2", "d3", "d4", "d5", "d6"])
    gen = build_generator(structured, vector, hybrid, df)
    sheet = make_sheet("NI-001", qd, qp, qv)
    raw, cand = gen.generate_need(sheet, run_seed=1)
    ids = sorted(c["doc_id"] for c in cand)
    # união de tudo: d1..d5 (d6 não aparece em nada)
    assert ids == ["d1", "d2", "d3", "d4", "d5"]
    # dedup: cada doc_id uma vez
    assert len(ids) == len(set(ids))
    # 3 linhas raw (uma por formulação)
    assert len(raw) == 3


def test_conjuntos_estruturados_diferentes_por_formulacao(tmp_path):
    qd, qp, qv = "a", "b", "c"
    structured = StubStructured({qd: ["d1"], qp: ["d2"], qv: ["d3"]})
    vector = StubRanked("vector", "0.2.0", {qd: [], qp: [], qv: []})
    hybrid = StubRanked("hybrid", "0.2.0", {qd: [], qp: [], qv: []})
    df = make_df(["d1", "d2", "d3"])
    gen = build_generator(structured, vector, hybrid, df)
    sheet = make_sheet("NI-002", qd, qp, qv)
    raw, cand = gen.generate_need(sheet, run_seed=1)
    # cada formulação contribui com um doc estruturado distinto
    assert sorted(c["doc_id"] for c in cand) == ["d1", "d2", "d3"]
    # per_formulation registra in_structured_set corretamente por formulação
    by_doc = {c["doc_id"]: json.loads(c["per_formulation"]) for c in cand}
    assert by_doc["d1"]["direct"]["in_structured_set"] is True
    assert by_doc["d1"]["paraphrase"]["in_structured_set"] is False


def test_estratificacao_conjunto_grande(tmp_path):
    # conjunto estruturado > T em uma formulação -> estrato I (∩J0) + amostra R.
    big = [f"s{i}" for i in range(300)]
    qd = "q"
    # vetor coloca s0..s9 no J0 (top-D); estrutura devolve os 300.
    structured = StubStructured({qd: big})
    vector = StubRanked("vector", "0.2.0", {qd: [(f"s{i}", 1.0 - i * 0.001) for i in range(10)]})
    hybrid = StubRanked("hybrid", "0.2.0", {qd: [(f"s{i}", 1.0 - i * 0.001) for i in range(10)]},
                        path_by_query={qd: "C"})
    df = make_df(big)
    gen = build_generator(structured, vector, hybrid, df, T=100)
    sheet = make_sheet("NI-003", qd, "", "")
    raw, cand = gen.generate_need(sheet, run_seed=5)
    # estrato I = interseção com J0 (os 10 do vetor); restante amostrado
    summary = json.loads(raw[0]["struct_stratum"])
    assert summary["N"] == 300
    assert summary["n_I"] == 10
    assert summary["n_R"] == 290
    assert summary["s_R"] > 0 and summary["s_R"] <= 290
    # candidatos = J0(10) + amostra(s_R); todos distintos
    judged = {c["doc_id"] for c in cand}
    assert len(judged) == 10 + summary["s_R"]


def test_estrutura_completa_preservada_no_raw(tmp_path):
    big = [f"s{i}" for i in range(300)]
    qd = "q"
    structured = StubStructured({qd: big})
    vector = StubRanked("vector", "0.2.0", {qd: []})
    hybrid = StubRanked("hybrid", "0.2.0", {qd: []})
    df = make_df(big)
    gen = build_generator(structured, vector, hybrid, df, T=100)
    sheet = make_sheet("NI-004", qd, "", "")
    raw, cand = gen.generate_need(sheet, run_seed=1)
    # o conjunto estruturado COMPLETO (300) é preservado no raw, mesmo que só
    # parte vá a julgamento.
    full = json.loads(raw[0]["structured_set"])
    assert len(full) == 300
    assert raw[0]["structured_set_size"] == 300


def test_reprodutibilidade_mesma_seed(tmp_path):
    big = [f"s{i}" for i in range(300)]
    qd = "q"
    structured = StubStructured({qd: big})
    vector = StubRanked("vector", "0.2.0", {qd: []})
    hybrid = StubRanked("hybrid", "0.2.0", {qd: []})
    df = make_df(big)
    g1 = build_generator(structured, vector, hybrid, df, T=100)
    g2 = build_generator(structured, vector, hybrid, df, T=100)
    s = make_sheet("NI-005", qd, "", "")
    _, c1 = g1.generate_need(s, run_seed=99)
    _, c2 = g2.generate_need(s, run_seed=99)
    assert sorted(x["doc_id"] for x in c1) == sorted(x["doc_id"] for x in c2)


def test_amostra_muda_com_seed(tmp_path):
    big = [f"s{i}" for i in range(300)]
    qd = "q"
    structured = StubStructured({qd: big})
    vector = StubRanked("vector", "0.2.0", {qd: []})
    hybrid = StubRanked("hybrid", "0.2.0", {qd: []})
    df = make_df(big)
    g = build_generator(structured, vector, hybrid, df, T=100)
    s = make_sheet("NI-006", qd, "", "")
    _, c1 = g.generate_need(s, run_seed=1)
    _, c2 = g.generate_need(s, run_seed=2)
    assert sorted(x["doc_id"] for x in c1) != sorted(x["doc_id"] for x in c2)


def test_complemento_so_metadados_verificaveis(tmp_path):
    # condição de metadados com fields -> gera complemento; textual -> não.
    qd = "q"
    structured = StubStructured({qd: []})
    vector = StubRanked("vector", "0.2.0", {qd: []})
    hybrid = StubRanked("hybrid", "0.2.0", {qd: []})
    df = make_df(["d1", "d2", "d3"],
                 COLEGIADO=["Plenário", "Primeira Câmara", "Plenário"])
    gen = build_generator(structured, vector, hybrid, df)
    conds = [MandatoryCondition(description="restrita ao colegiado Plenario",
                                relates_to="metadata", fields=["COLEGIADO"])]
    sheet = make_sheet("NI-007", qd, "", "", conditions=conds)
    raw, cand = gen.generate_need(sheet, run_seed=1)
    ids = {c["doc_id"] for c in cand}
    # "plenario" casa d1 e d3 (normalização sem acento)
    assert ids == {"d1", "d3"}
    assert all(json.loads(c["per_formulation"]) is not None for c in cand)


def test_sem_rotulos_de_relevancia(tmp_path):
    qd = "q"
    structured = StubStructured({qd: ["d1"]})
    vector = StubRanked("vector", "0.2.0", {qd: [("d1", .9)]})
    hybrid = StubRanked("hybrid", "0.2.0", {qd: [("d1", .9)]})
    df = make_df(["d1"])
    gen = build_generator(structured, vector, hybrid, df)
    sheet = make_sheet("NI-008", qd, "", "")
    raw, cand = gen.generate_need(sheet, run_seed=1)
    # nenhuma coluna de relevância nos candidatos
    for c in cand:
        assert "label" not in c and "relevance" not in c and "relevant" not in c


def test_run_grava_artefatos_e_unicidade(tmp_path):
    qd = "q"
    structured = StubStructured({qd: ["d1", "d2"]})
    vector = StubRanked("vector", "0.2.0", {qd: [("d1", .9)]})
    hybrid = StubRanked("hybrid", "0.2.0", {qd: [("d1", .9)]})
    df = make_df(["d1", "d2"])
    gen = build_generator(structured, vector, hybrid, df)
    sheet = make_sheet("NI-009", qd, "", "")
    out = tmp_path / "run1"
    manifest = gen.run([sheet], out, run_id="run1", run_seed=1, status="exploratory")
    assert (out / "pool_manifest.json").exists()
    assert (out / "retrieval_raw.parquet").exists()
    assert (out / "pool_candidates.parquet").exists()
    assert manifest["status"] == "exploratory"
    cand = pd.read_parquet(out / "pool_candidates.parquet")
    keys = list(zip(cand["run_id"], cand["need_id"], cand["doc_id"]))
    assert len(keys) == len(set(keys))


def test_validate_official_rejeita_draft(tmp_path):
    qd = "q"
    structured = StubStructured({qd: ["d1"]})
    vector = StubRanked("vector", "0.2.0", {qd: [("d1", .9)]})
    hybrid = StubRanked("hybrid", "0.2.0", {qd: [("d1", .9)]})
    df = make_df(["d1"])
    gen = build_generator(structured, vector, hybrid, df)
    sheet = make_sheet("NI-010", qd, "", "", status="draft")
    out = tmp_path / "run2"
    manifest = gen.run([sheet], out, run_id="run2", run_seed=1)
    check = validate_official(manifest, [sheet])
    assert check.ok is False
    assert any("draft" in r for r in check.reasons)

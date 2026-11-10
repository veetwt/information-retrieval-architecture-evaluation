# Feature: Alternativa B — seleção reduzida para julgamento humano.
# Cobre: dedup por (need_id, doc_id), corte top-5, universo estrito ANTT+REPR
# (NI-003), inclusão de referências (ausente vs já presente), integridade do
# manifesto, aplicação RÍGIDA do teto e preservação de D=50 no registro.
# Usa recuperadores FALSOS (não carrega modelo nem índice reais).

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from retrieval.base import RetrievalResult, RetrievedDocument  # noqa: E402
from evaluation.need_sheet import NeedSheet  # noqa: E402
from evaluation.judgment_selection import (  # noqa: E402
    JudgmentCapExceeded,
    JudgmentSelector,
    strict_antt_representation_universe,
    validate_judgment_manifest,
    JUDGMENT_CAP,
    JUDGMENT_TOPK,
    RECORD_DEPTH,
)

FP = "ec125709322854d164e8f4aeaffb0351ef92e0adfede4d92b17b955b5ea1bc5c"


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #

class _FakeIndex:
    def __init__(self, meta):
        self.meta = meta


class _FakeVector:
    VERSION = "fake-vec"

    def __init__(self, meta, responses):
        self._index = _FakeIndex(meta)
        self._responses = responses  # query -> list[doc_id] (ranked)

    def retrieve(self, query):
        ids = self._responses.get(query, [])
        docs = [RetrievedDocument(doc_id=d, rank=i + 1, score=1.0 - i * 0.01)
                for i, d in enumerate(ids)]
        return RetrievalResult(query=query, architecture="vector", documents=docs)


class _FakeHybrid:
    VERSION = "fake-hyb"

    def __init__(self, meta, responses, structured=None):
        self._vector = _FakeVector(meta, {})
        self._vector._index = _FakeIndex(meta)
        self._structured = structured or _FakeStructured()
        self._responses = responses

    def retrieve(self, query):
        ids = self._responses.get(query, [])
        docs = [RetrievedDocument(doc_id=d, rank=i + 1, score=0.9 - i * 0.01)
                for i, d in enumerate(ids)]
        return RetrievalResult(query=query, architecture="hybrid", documents=docs,
                               diagnostics={"path": "B"})


class _FakeStructured:
    VERSION = "fake-str"

    def __init__(self, responses=None, n_corpus=100):
        self._responses = responses or {}  # query -> list[doc_id]
        self._n_corpus = n_corpus

    def retrieve(self, query):
        ids = self._responses.get(query, [])
        docs = [RetrievedDocument(doc_id=d, rank=i + 1, score=None)
                for i, d in enumerate(ids)]
        diag = {
            "architecture_version": self.VERSION,
            "identified_conditions": {"TIPOPROCESSO": "X"} if ids else {},
            "n_corpus": self._n_corpus,
            "n_matched": len(ids),
        }
        if not ids:
            diag["no_conditions_identified"] = True
        return RetrievalResult(query=query, architecture="structured",
                               documents=docs, diagnostics=diag)


def _meta(partial=False):
    return {
        "model_name": "fake-model", "embedding_dim": 384,
        "n_docs_indexed": 100, "n_chunks": 100,
        "is_partial_index": partial, "selection_fingerprint": FP,
    }


def _df_with(docs):
    """DataFrame mínimo com os campos usados pelo universo estrito."""
    rows = []
    for d in docs:
        rows.append({"doc_id": d["doc_id"],
                     "ENTIDADE": d.get("ENTIDADE", ""),
                     "TIPOPROCESSO": d.get("TIPOPROCESSO", "")})
    return pd.DataFrame(rows)


def _sheet(need_id, nature="metadata"):
    data = {
        "schema_version": "1.0", "need_id": need_id,
        "description": "x", "nature": nature,
        "scope": {"corpus": "c", "temporal": "2024", "selection_fingerprint": FP},
        "mandatory_conditions": [], "requested_facts": ["f"],
        "operations": ["identify"],
        "formulations": {"direct": f"{need_id} D", "paraphrase": f"{need_id} P",
                         "verbose": f"{need_id} V"},
        "equivalence_validation": {
            "status": "validated", "rationale": "ok",
            "reviewers": [{"id": "Vitoria Novaes da Costa", "decision": "equivalent"}],
        },
    }
    return NeedSheet.model_validate(data)


def _build_selector(vec_resp, hyb_resp, df, references=None, cap=JUDGMENT_CAP,
                    str_resp=None, n_corpus=100):
    meta = _meta()
    structured = _FakeStructured(str_resp or {}, n_corpus=n_corpus)
    hybrid = _FakeHybrid(meta, hyb_resp, structured=structured)
    hybrid._vector = _FakeVector(meta, vec_resp)
    sel = JudgmentSelector(
        hybrid, selection_df=df, selection_fingerprint=FP, index_meta=meta,
        references=references if references is not None else {}, cap=cap,
    )
    return sel


# --------------------------------------------------------------------------- #
# Universo estrito ANTT + REPR
# --------------------------------------------------------------------------- #

def test_strict_universe_matches_antt_and_repr_only():
    df = _df_with([
        {"doc_id": "a", "ENTIDADE": "Agência Nacional de Transportes Terrestres (ANTT)", "TIPOPROCESSO": "REPRESENTAÇÃO (REPR)"},
        {"doc_id": "b", "ENTIDADE": "ANTT", "TIPOPROCESSO": "Representação (REPR)"},
        {"doc_id": "c", "ENTIDADE": "ANTT", "TIPOPROCESSO": "DENÚNCIA (DEN)"},        # tipo errado
        {"doc_id": "d", "ENTIDADE": "Outra Entidade", "TIPOPROCESSO": "REPR"},         # entidade errada
        {"doc_id": "e", "ENTIDADE": "ANTT; Ministério", "TIPOPROCESSO": "representacao"},  # multivalor
    ])
    uni = strict_antt_representation_universe(df)
    assert uni == ["a", "b", "e"]


def test_strict_universe_is_not_broad_heuristic():
    # Documento que apenas menciona "transportes" não entra (precisa terrestres/antt).
    df = _df_with([
        {"doc_id": "x", "ENTIDADE": "Agência de Transportes Aquaviários", "TIPOPROCESSO": "Representação"},
    ])
    assert strict_antt_representation_universe(df) == []


# --------------------------------------------------------------------------- #
# Top-5 + deduplicação
# --------------------------------------------------------------------------- #

def test_top5_cut_and_dedup_across_formulations_and_architectures():
    # vetorial retorna 7 docs; apenas top-5 contam. Híbrida repete alguns.
    vec = {
        "NI-001 D": ["v1", "v2", "v3", "v4", "v5", "v6", "v7"],
        "NI-001 P": ["v1", "v2", "v3", "v4", "v5"],
        "NI-001 V": ["v1", "v2", "v3", "v4", "v5"],
    }
    hyb = {
        "NI-001 D": ["v1", "h1", "h2", "h3", "h4"],
        "NI-001 P": ["v1", "h1", "h2", "h3", "h4"],
        "NI-001 V": ["v1", "h1", "h2", "h3", "h4"],
    }
    df = _df_with([{"doc_id": f"v{i}"} for i in range(1, 8)] + [{"doc_id": f"h{i}"} for i in range(1, 5)])
    sel = _build_selector(vec, hyb, df)
    origins, _ = sel.select_need(_sheet("NI-001"))
    # v6, v7 fora (além do top-5). Únicos: v1..v5 + h1..h4 = 9
    assert set(origins) == {"v1", "v2", "v3", "v4", "v5", "h1", "h2", "h3", "h4"}
    assert "v6" not in origins and "v7" not in origins
    # v1 veio de vetorial E híbrida
    assert origins["v1"].top5_vector and origins["v1"].top5_hybrid
    # registra formulações
    assert set(origins["v1"].vector_formulations) == {"direct", "paraphrase", "verbose"}


def test_structured_set_recorded_without_entering_judgment_cut():
    # A estruturada devolve um conjunto grande; ele é REGISTRADO mas NÃO entra
    # no conjunto de julgamento (só top-5 vetorial/híbrida + estrito + ref).
    vec = {"NI-001 D": ["a"], "NI-001 P": [], "NI-001 V": []}
    hyb = {"NI-001 D": [], "NI-001 P": [], "NI-001 V": []}
    str_resp = {"NI-001 D": [f"s{i}" for i in range(60)]}  # 60/100 -> amplo
    df = _df_with([{"doc_id": "a"}] + [{"doc_id": f"s{i}"} for i in range(60)])
    sel = _build_selector(vec, hyb, df, str_resp=str_resp, n_corpus=100)
    origins, records = sel.select_need(_sheet("NI-001"))
    # julgamento: apenas "a" (top-5 vetorial); nenhum s* entra
    assert set(origins) == {"a"}
    rec = next(r for r in records if r["formulation"] == "direct")
    sset = json.loads(rec["structured_set"])
    assert len(sset) == 60 and rec["structured_set_size"] == 60
    assert rec["structured_overly_broad"] is True
    assert rec["structured_no_conditions"] is False


def test_structured_no_conditions_flag_recorded():
    vec = {"NI-001 D": ["a"], "NI-001 P": [], "NI-001 V": []}
    hyb = {"NI-001 D": [], "NI-001 P": [], "NI-001 V": []}
    df = _df_with([{"doc_id": "a"}])
    sel = _build_selector(vec, hyb, df, str_resp={})  # estruturada vazia
    _, records = sel.select_need(_sheet("NI-001"))
    rec = next(r for r in records if r["formulation"] == "direct")
    assert rec["structured_set_size"] == 0
    assert rec["structured_no_conditions"] is True
    assert rec["structured_overly_broad"] is False


def test_record_preserves_full_depth_not_only_top5():
    # Mesmo com corte top-5, o registro deve guardar a lista completa (até D).
    vec = {"NI-001 D": [f"v{i}" for i in range(1, 9)], "NI-001 P": [], "NI-001 V": []}
    hyb = {"NI-001 D": [], "NI-001 P": [], "NI-001 V": []}
    df = _df_with([{"doc_id": f"v{i}"} for i in range(1, 9)])
    sel = _build_selector(vec, hyb, df)
    _, records = sel.select_need(_sheet("NI-001"))
    rec_direct = next(r for r in records if r["formulation"] == "direct")
    full = json.loads(rec_direct["vector_full_topD"])
    top5 = json.loads(rec_direct["vector_top5"])
    assert len(full) == 8 and len(top5) == 5
    assert rec_direct["record_depth"] == RECORD_DEPTH and rec_direct["judgment_topk"] == JUDGMENT_TOPK


# --------------------------------------------------------------------------- #
# Universo estrito dentro da NI-003 + sobreposição
# --------------------------------------------------------------------------- #

def test_ni003_includes_strict_universe_and_marks_overlap():
    # u1 aparece no top-5 vetorial E no universo estrito (sobreposição).
    vec = {"NI-003 D": ["u1", "r1", "r2"], "NI-003 P": [], "NI-003 V": []}
    hyb = {"NI-003 D": [], "NI-003 P": [], "NI-003 V": []}
    df = _df_with([
        {"doc_id": "u1", "ENTIDADE": "ANTT", "TIPOPROCESSO": "Representação (REPR)"},
        {"doc_id": "u2", "ENTIDADE": "ANTT", "TIPOPROCESSO": "Representação (REPR)"},
        {"doc_id": "r1"}, {"doc_id": "r2"},
    ])
    sel = _build_selector(vec, hyb, df)
    origins, _ = sel.select_need(_sheet("NI-003", nature="mixed"))
    assert "u2" in origins and origins["u2"].strict_universe
    assert origins["u1"].strict_universe and origins["u1"].top5_vector  # sobreposição


def test_strict_universe_only_applies_to_ni003():
    vec = {"NI-001 D": [], "NI-001 P": [], "NI-001 V": []}
    hyb = {"NI-001 D": [], "NI-001 P": [], "NI-001 V": []}
    df = _df_with([{"doc_id": "u1", "ENTIDADE": "ANTT", "TIPOPROCESSO": "Representação"}])
    sel = _build_selector(vec, hyb, df)
    origins, _ = sel.select_need(_sheet("NI-001"))
    assert origins == {}  # NI-001 não puxa o universo estrito


# --------------------------------------------------------------------------- #
# Referências confirmadas
# --------------------------------------------------------------------------- #

def test_reference_added_when_absent():
    vec = {"NI-001 D": ["x1"], "NI-001 P": [], "NI-001 V": []}
    hyb = {"NI-001 D": [], "NI-001 P": [], "NI-001 V": []}
    df = _df_with([{"doc_id": "x1"}, {"doc_id": "ref1"}])
    sel = _build_selector(vec, hyb, df, references={"NI-001": ("ref1",)})
    origins, _ = sel.select_need(_sheet("NI-001"))
    assert "ref1" in origins and origins["ref1"].reference
    assert origins["ref1"].sources() == ["reference"]


def test_reference_only_annotates_when_already_present():
    vec = {"NI-001 D": ["ref1"], "NI-001 P": [], "NI-001 V": []}
    hyb = {"NI-001 D": [], "NI-001 P": [], "NI-001 V": []}
    df = _df_with([{"doc_id": "ref1"}])
    sel = _build_selector(vec, hyb, df, references={"NI-001": ("ref1",)})
    origins, _ = sel.select_need(_sheet("NI-001"))
    # já presente por top-5 vetorial; referência apenas anotada, sem duplicar
    assert origins["ref1"].top5_vector and origins["ref1"].reference
    assert set(origins["ref1"].sources()) == {"top5_vector", "reference"}


def test_reference_outside_selection_is_not_invented():
    vec = {"NI-001 D": ["x1"], "NI-001 P": [], "NI-001 V": []}
    hyb = {"NI-001 D": [], "NI-001 P": [], "NI-001 V": []}
    df = _df_with([{"doc_id": "x1"}])  # ref fora da seleção
    sel = _build_selector(vec, hyb, df, references={"NI-001": ("ghost",)})
    origins, records = sel.select_need(_sheet("NI-001"))
    assert "ghost" not in origins
    assert any(r["formulation"] == "__reference_warning__" for r in records)


# --------------------------------------------------------------------------- #
# Manifesto, unicidade e teto
# --------------------------------------------------------------------------- #

def test_run_writes_artifacts_and_manifest(tmp_path):
    vec = {"NI-001 D": ["a", "b"], "NI-001 P": [], "NI-001 V": []}
    hyb = {"NI-001 D": ["b", "c"], "NI-001 P": [], "NI-001 V": []}
    df = _df_with([{"doc_id": "a"}, {"doc_id": "b"}, {"doc_id": "c"}])
    sel = _build_selector(vec, hyb, df)
    manifest = sel.run([_sheet("NI-001")], tmp_path, run_id="r1")
    assert (tmp_path / "judgment_manifest.json").exists()
    assert (tmp_path / "judgment_candidates.parquet").exists()
    assert (tmp_path / "retrieval_record.parquet").exists()
    assert manifest["counts"]["n_judgments"] == 3  # a, b, c
    assert manifest["overlaps"]["vector_and_hybrid"] == 1  # b
    assert manifest["params"]["judgment_topk"] == JUDGMENT_TOPK
    assert manifest["params"]["record_depth_D"] == RECORD_DEPTH


def test_cap_enforced_and_nothing_written(tmp_path):
    # 6 docs no top-5 vetorial (cap=5) -> excede; deve abortar sem gravar.
    vec = {"NI-001 D": ["d1", "d2", "d3", "d4", "d5"], "NI-001 P": ["d6"], "NI-001 V": []}
    hyb = {"NI-001 D": [], "NI-001 P": [], "NI-001 V": []}
    df = _df_with([{"doc_id": f"d{i}"} for i in range(1, 7)])
    sel = _build_selector(vec, hyb, df, cap=5)
    with pytest.raises(JudgmentCapExceeded) as exc:
        sel.run([_sheet("NI-001")], tmp_path, run_id="r1")
    assert exc.value.required == 6 and exc.value.cap == 5
    # nada gravado
    assert not (tmp_path / "judgment_manifest.json").exists()
    assert not (tmp_path / "judgment_candidates.parquet").exists()


def test_cap_boundary_exact_is_allowed(tmp_path):
    vec = {"NI-001 D": ["d1", "d2", "d3", "d4", "d5"], "NI-001 P": [], "NI-001 V": []}
    hyb = {"NI-001 D": [], "NI-001 P": [], "NI-001 V": []}
    df = _df_with([{"doc_id": f"d{i}"} for i in range(1, 6)])
    sel = _build_selector(vec, hyb, df, cap=5)
    manifest = sel.run([_sheet("NI-001")], tmp_path, run_id="r1")
    assert manifest["counts"]["n_judgments"] == 5


def test_validate_manifest_ok_and_detects_problems(tmp_path):
    vec = {"NI-001 D": ["a"], "NI-001 P": [], "NI-001 V": []}
    hyb = {"NI-001 D": [], "NI-001 P": [], "NI-001 V": []}
    df = _df_with([{"doc_id": "a"}])
    sel = _build_selector(vec, hyb, df)
    sheets = [_sheet("NI-001")]
    manifest = sel.run(sheets, tmp_path, run_id="r1")
    assert validate_judgment_manifest(manifest, sheets).ok

    # fingerprint ausente -> inválido
    bad = dict(manifest)
    bad["selection_fingerprint"] = ""
    assert not validate_judgment_manifest(bad, sheets).ok

    # total acima do cap -> inválido
    bad2 = json.loads(json.dumps(manifest))
    bad2["counts"]["n_judgments"] = 999
    chk = validate_judgment_manifest(bad2, sheets)
    assert not chk.ok and any("excede" in r for r in chk.reasons)


def test_not_selected_docs_are_absent_never_irrelevant(tmp_path):
    # Documentos fora do conjunto simplesmente não aparecem (desconhecidos).
    vec = {"NI-001 D": ["a"], "NI-001 P": [], "NI-001 V": []}
    hyb = {"NI-001 D": [], "NI-001 P": [], "NI-001 V": []}
    df = _df_with([{"doc_id": "a"}, {"doc_id": "z_nao_recuperado"}])
    sel = _build_selector(vec, hyb, df)
    manifest = sel.run([_sheet("NI-001")], tmp_path, run_id="r1")
    cand = pd.read_parquet(tmp_path / "judgment_candidates.parquet")
    assert "z_nao_recuperado" not in set(cand["doc_id"])
    # nenhuma coluna de relevância é criada
    assert not any(c in cand.columns for c in ("label", "relevance", "relevant"))

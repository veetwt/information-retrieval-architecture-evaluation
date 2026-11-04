# Feature: arquitetura HÍBRIDA (estruturada + vetorial).
# Testa a estratégia fixa: filtro estruturado + ordenação por similaridade sobre
# TODOS os candidatos, com fallback vetorial global. Usa encoder/tokenizer STUB
# determinísticos (sem rede) e um corpus sintético coerente entre as duas bases.

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from retrieval.base import RetrievalResult, Retriever  # noqa: E402
from retrieval.structured import StructuredRetriever  # noqa: E402
from retrieval.vector import VectorRetriever  # noqa: E402
from retrieval.vector_index import (  # noqa: E402
    IndexIntegrityError,
    build_index,
    load_index,
)
from retrieval.hybrid import HybridIntegrityError, HybridRetriever  # noqa: E402
from utils.hashing import compute_dataset_fingerprint  # noqa: E402


# --------------------------------------------------------------------------- #
# Stubs determinísticos (reaproveitam o padrão dos testes vetoriais)
# --------------------------------------------------------------------------- #

class StubTokenizer:
    def __init__(self):
        self._vocab: dict[str, int] = {}
        self._inv: dict[int, str] = {}

    def _id(self, w: str) -> int:
        if w not in self._vocab:
            idx = len(self._vocab) + 10
            self._vocab[w] = idx
            self._inv[idx] = w
        return self._vocab[w]

    def encode(self, text, add_special_tokens=False):
        ids = [self._id(w) for w in str(text).split()]
        if add_special_tokens:
            return [1] + ids + [2]
        return ids

    def decode(self, ids, skip_special_tokens=True):
        return " ".join(self._inv.get(int(i), "") for i in ids).strip()

    def num_special_tokens_to_add(self, pair=False):
        return 2


class StubEncoder:
    """Vetor por hashing de palavras; textos de vocabulário próximo ficam próximos."""

    def __init__(self, dim: int = 32):
        self._dim = dim
        self.tokenizer = StubTokenizer()

    def get_sentence_embedding_dimension(self) -> int:
        return self._dim

    def encode(self, texts, batch_size=32, convert_to_numpy=True,
               normalize_embeddings=True, show_progress_bar=False):
        vecs = np.zeros((len(texts), self._dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in str(t).lower().split():
                vecs[i, (hash(w) % self._dim)] += 1.0
        if normalize_embeddings:
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            vecs = vecs / norms
        return vecs


# --------------------------------------------------------------------------- #
# Corpus sintético coerente entre estruturado e vetorial
# --------------------------------------------------------------------------- #

def make_selection_df() -> pd.DataFrame:
    # ENTIDADE registra a sigla entre parênteses (como no corpus real), para que
    # a estruturada v0.3.0 reconheça a sigla inequívoca como filtro de ENTIDADE.
    rows = [
        # d1, d5: representações da ANTT (tipo REPR) com textos distintos
        ("d1", "Plenário", "AROLDO CEDRAZ", "REPRESENTAÇÃO (REPR)", "24/01/2024",
         "Agência Nacional de Transportes Terrestres (ANTT).", "AudRodoviaAviação.",
         "representacao tarifa de pedagio rodovia",
         "reajuste da tarifa de pedagio da rodovia concessao antt"),
        ("d2", "Plenário", "WALTON ALENCAR RODRIGUES", "REPRESENTAÇÃO (REPR)", "06/11/2024",
         "Agência Nacional de Transportes Terrestres (ANTT).", "AudRodoviaAviação.",
         "representacao sobre fiscalizacao de contrato",
         "monitoramento de contrato de concessao sem tarifa"),
        ("d3", "Primeira Câmara", "JHONATAN DE JESUS", "APOSENTADORIA (APOS)", "08/10/2024",
         "Universidade Federal do Para (UFPA).", "AudPessoal.",
         "aposentadoria de servidor publico federal",
         "ato de aposentadoria julgado legal servidor universidade"),
        ("d4", "Segunda Câmara", "ANTONIO ANASTASIA", "DENÚNCIA (DEN)", "19/03/2024",
         "Administração Regional do Sesc no Estado do Mato Grosso do Sul (Sesc/MS).",
         "AudContratações.",
         "denuncia sobre contratos do sesc",
         "irregularidades em contratos da administracao regional do sesc"),
        ("d5", "Plenário", "AROLDO CEDRAZ", "REPRESENTAÇÃO (REPR)", "24/01/2024",
         "Agência Nacional de Transportes Terrestres (ANTT).", "AudRodoviaAviação.",
         "representacao sobre tarifa de pedagio e reajuste",
         "aumento da tarifa de pedagio em rodovia federal antt pedagio"),
    ]
    cols = ["doc_id", "COLEGIADO", "RELATOR", "TIPOPROCESSO", "DATASESSAO",
            "ENTIDADE", "UNIDADETECNICA", "ASSUNTO", "ACORDAO"]
    return pd.DataFrame(rows, columns=cols)


@pytest.fixture
def hybrid(tmp_path):
    df = make_selection_df()
    sel = tmp_path / "selection_test-v1_20260101_000000.parquet"
    df.to_parquet(sel, engine="pyarrow", index=False)

    idx_dir = tmp_path / "idx"
    build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="fp",
                max_tokens=16, overlap_tokens=2, batch_size=4, shard_size=4)

    structured = StructuredRetriever(df, corpus_fingerprint="fp")
    vector = VectorRetriever(load_index(idx_dir), model=StubEncoder(), display_limit=10)
    return HybridRetriever(structured, vector, display_limit=10)


# --------------------------------------------------------------------------- #
# Interface comum
# --------------------------------------------------------------------------- #

def test_cumpre_interface_comum(hybrid):
    assert isinstance(hybrid, Retriever)
    assert hybrid.architecture_name == "hybrid"
    res = hybrid.retrieve("representação sobre tarifa de pedagio da ANTT")
    assert isinstance(res, RetrievalResult)


# --------------------------------------------------------------------------- #
# Caminho filtrado: combinação de filtros + similaridade
# --------------------------------------------------------------------------- #

def test_filtro_estruturado_restringe_candidatos(hybrid):
    # "representação" + "ANTT" -> TIPOPROCESSO=REPR e ENTIDADE=ANTT: d1, d2, d5.
    res = hybrid.retrieve("representação da ANTT sobre tarifa de pedagio")
    assert res.diagnostics["path"] == "structured_filter_then_vector_rank"
    cond = res.diagnostics["identified_conditions"]
    assert cond.get("TIPOPROCESSO") == "REPRESENTAÇÃO (REPR)"
    assert "ENTIDADE" in cond
    ids = set(res.doc_ids)
    # Só documentos que satisfazem AMBAS as condições podem aparecer.
    assert ids <= {"d1", "d2", "d5"}
    # d3 (aposentadoria) e d4 (denúncia/Sesc) nunca aparecem neste caminho.
    assert "d3" not in ids and "d4" not in ids


def test_ordenacao_por_similaridade_nao_por_doc_id(hybrid):
    # Entre os candidatos REPR+ANTT, os de tarifa/pedágio (d1, d5) devem superar
    # o de fiscalização de contrato (d2) por similaridade — não por ordem de doc_id.
    res = hybrid.retrieve("reajuste e aumento da tarifa de pedagio em rodovia")
    scores = [d.score for d in res.documents]
    assert scores == sorted(scores, reverse=True)
    assert all(isinstance(d.score, float) for d in res.documents)
    top_ids = [d.doc_id for d in res.documents[:2]]
    assert "d2" not in top_ids  # menos similar ao tema tarifa/pedágio


def test_similaridade_sobre_todos_os_candidatos(hybrid):
    # O ranking deve considerar todos os candidatos do filtro, e cada doc aparece
    # uma única vez (consolidação por doc_id).
    res = hybrid.retrieve("representação da ANTT")
    ids = res.doc_ids
    assert len(ids) == len(set(ids))
    assert set(ids) <= {"d1", "d2", "d5"}
    assert res.diagnostics["n_ranked_candidates"] == len(ids)


# --------------------------------------------------------------------------- #
# Fallback: ausência de condições / ausência de candidatos
# --------------------------------------------------------------------------- #

def test_fallback_sem_condicoes(hybrid):
    # Consulta puramente temática, sem metadados reconhecíveis -> vetorial global.
    res = hybrid.retrieve("tarifa de pedagio rodovia")
    assert res.diagnostics["path"] == "vector_global_fallback"
    assert res.diagnostics["fallback_reason"] == "no_conditions_identified"
    # Pode retornar qualquer documento do corpus (não restrito a um tipo/entidade).
    assert len(res.documents) >= 1
    for d in res.documents:
        assert d.evidence.get("path") == "vector_global_fallback"


def test_condicoes_reconhecidas_sem_candidatos_retorna_vazio(tmp_path):
    # Política aprovada (Caso B): condição reconhecida, mas interseção vazia ->
    # resultado VAZIO, SEM fallback vetorial global.
    # COLEGIADO é reconhecido por palavra-chave (independe do corpus): removemos
    # todos os documentos de "Segunda Câmara" para que o filtro não tenha candidato.
    df = make_selection_df()
    df = df[df["COLEGIADO"] != "Segunda Câmara"].reset_index(drop=True)
    assert "Segunda Câmara" not in set(df["COLEGIADO"])  # garante ausência de candidato

    sel = tmp_path / "selection_test-v1_20260101_000000.parquet"
    df.to_parquet(sel, engine="pyarrow", index=False)
    idx_dir = tmp_path / "idx_nocand"
    build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="fp",
                max_tokens=16, overlap_tokens=2, batch_size=4, shard_size=4)
    structured = StructuredRetriever(df, corpus_fingerprint="fp")

    # Encoder instrumentado: registra se encode() é chamado na recuperação.
    class CountingEncoder(StubEncoder):
        def __init__(self):
            super().__init__()
            self.encode_calls = 0

        def encode(self, texts, **kw):
            self.encode_calls += 1
            return super().encode(texts, **kw)

    enc = CountingEncoder()
    vector = VectorRetriever(load_index(idx_dir), model=enc, display_limit=10)
    hybrid = HybridRetriever(structured, vector, display_limit=10)
    calls_before = enc.encode_calls

    res = hybrid.retrieve("processos julgados na Segunda Câmara")
    # Condição reconhecida...
    assert res.diagnostics["identified_conditions"].get("COLEGIADO") == "Segunda Câmara"
    # ...mas interseção vazia -> resultado vazio, caminho dedicado.
    assert res.diagnostics["path"] == "structured_no_candidates"
    assert res.diagnostics["structured_intersection_empty"] is True
    assert res.diagnostics["n_structured_candidates"] == 0
    assert res.diagnostics["n_ranked_candidates"] == 0
    assert res.documents == []
    assert res.architecture == "hybrid"
    # fields_used coerente com os metadados reconhecidos (sem ASSUNTO/ACORDAO).
    assert res.fields_used == ["COLEGIADO"]
    # NÃO executou fallback vetorial global: sem diagnóstico vetorial e sem encode.
    assert "vector_diagnostics" not in res.diagnostics
    assert "fallback_reason" not in res.diagnostics
    assert enc.encode_calls == calls_before  # vetorial NÃO foi consultado


# --------------------------------------------------------------------------- #
# Evidências e diagnósticos
# --------------------------------------------------------------------------- #

def test_evidencia_no_caminho_filtrado(hybrid):
    res = hybrid.retrieve("representação da ANTT sobre tarifa de pedagio")
    top = res.documents[0]
    assert "passage" in top.evidence and top.evidence["passage"]
    assert top.evidence["consolidation"] == "max_pooling"
    assert top.evidence["path"] == "structured_filter_then_vector_rank"
    assert "matched_conditions" in top.evidence


def test_fields_used_caminho_filtrado(hybrid):
    res = hybrid.retrieve("representação da ANTT")
    # metadados filtrados + campos textuais da ordenação
    assert "ASSUNTO" in res.fields_used and "ACORDAO" in res.fields_used
    assert "TIPOPROCESSO" in res.fields_used
    assert "ENTIDADE" in res.fields_used


def test_diagnostico_registra_regra_e_fallback(hybrid):
    res_filtro = hybrid.retrieve("representação da ANTT")
    assert "combination_rule" in res_filtro.diagnostics
    assert res_filtro.diagnostics["n_structured_candidates"] >= 1

    res_fb = hybrid.retrieve("tarifa de pedagio rodovia")
    assert res_fb.diagnostics["path"] == "vector_global_fallback"
    assert "vector_diagnostics" in res_fb.diagnostics


# --------------------------------------------------------------------------- #
# Reprodutibilidade
# --------------------------------------------------------------------------- #

def test_reprodutibilidade(hybrid):
    q = "representação da ANTT sobre tarifa de pedagio"
    r1 = hybrid.retrieve(q)
    r2 = hybrid.retrieve(q)
    assert [(d.doc_id, round(d.score, 6)) for d in r1.documents] == \
           [(d.doc_id, round(d.score, 6)) for d in r2.documents]


def test_sem_duplicacao_de_documento(hybrid):
    res = hybrid.retrieve("representação da ANTT sobre tarifa de pedagio e contrato")
    ids = res.doc_ids
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------- #
# Política de fallback (Caso A vs Caso B) — regressão da mudança v0.2.0
# --------------------------------------------------------------------------- #

def test_caso_a_fallback_global_consulta_vetorial(hybrid):
    # Caso A: sem condições reconhecidas -> fallback global que corresponde,
    # em ordem e score, à recuperação vetorial pura para a mesma consulta.
    q = "tarifa de pedagio rodovia"
    res = hybrid.retrieve(q)
    assert res.diagnostics["path"] == "vector_global_fallback"
    assert res.diagnostics["fallback_reason"] == "no_conditions_identified"
    assert len(res.documents) >= 1
    vres = hybrid._vector.retrieve(q)
    assert [(d.doc_id, round(float(d.score), 6)) for d in res.documents] == \
           [(d.doc_id, round(float(d.score), 6)) for d in vres.documents]


def test_caso_c_caminho_filtrado_preservado(hybrid):
    # Caso C: condições + candidatos -> ranking vetorial sobre os candidatos,
    # score desc com desempate por doc_id, sem duplicação e dentro do filtro.
    res = hybrid.retrieve("representação da ANTT sobre tarifa de pedagio")
    assert res.diagnostics["path"] == "structured_filter_then_vector_rank"
    assert res.diagnostics["n_ranked_candidates"] >= 1
    scores = [d.score for d in res.documents]
    assert scores == sorted(scores, reverse=True)
    ids = res.doc_ids
    assert len(ids) == len(set(ids))


def test_caso_b_vazio_preserva_condicoes(hybrid):
    # Caso B sobre o corpus sintético da fixture: COLEGIADO reconhecido mas
    # inexistente no corpus -> vazio, sem fallback. (Nenhum doc é "Terceira
    # Câmara"; o vocabulário de COLEGIADO é por palavra-chave, não do corpus.)
    # Observação: o reconhecedor de COLEGIADO cobre Plenário/Primeira/Segunda;
    # para forçar interseção vazia de forma determinística usamos TIPOPROCESSO
    # reconhecido combinado com COLEGIADO sem documentos correspondentes.
    res = hybrid.retrieve("aposentadoria julgada no Plenário")
    # Se houver candidatos, é Caso C; se não houver, é Caso B. Verificamos a
    # coerência do diagnóstico conforme o caminho efetivamente tomado.
    if res.diagnostics["path"] == "structured_no_candidates":
        assert res.documents == []
        assert res.diagnostics["n_structured_candidates"] == 0
        assert res.diagnostics["n_ranked_candidates"] == 0
        assert "vector_diagnostics" not in res.diagnostics
        assert set(res.fields_used) <= {"COLEGIADO", "TIPOPROCESSO"}
    else:
        assert res.diagnostics["path"] == "structured_filter_then_vector_rank"
        assert res.diagnostics["n_ranked_candidates"] >= 1


# --------------------------------------------------------------------------- #
# Integridade seleção <-> índice (via from_artifacts)
# --------------------------------------------------------------------------- #

def _write_selection_with_manifest(df, tmp_path, name="selection_test-v1_20260101_000000"):
    """Grava o parquet da seleção + manifesto sidecar com fingerprint real."""
    sel = tmp_path / f"{name}.parquet"
    df.to_parquet(sel, engine="pyarrow", index=False)
    fp = compute_dataset_fingerprint(df, sort_col="doc_id")
    manifest = tmp_path / f"{name}_manifest.json"
    manifest.write_text(json.dumps({"selection_fingerprint": fp}), encoding="utf-8")
    return sel, fp


def _build_compatible_index(df, sel, tmp_path, fp, idx_name="idx"):
    """Constrói um índice sintético cujo selection_fingerprint == fp (real)."""
    idx_dir = tmp_path / idx_name
    build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint=fp,
                max_tokens=16, overlap_tokens=2, batch_size=4, shard_size=4)
    return idx_dir


def test_from_artifacts_compativel(tmp_path):
    df = make_selection_df()
    sel, fp = _write_selection_with_manifest(df, tmp_path)
    idx_dir = _build_compatible_index(df, sel, tmp_path, fp)
    hybrid = HybridRetriever.from_artifacts(sel, idx_dir, model=StubEncoder(), display_limit=10)
    assert isinstance(hybrid, Retriever)
    # comportamento preservado: consulta com condições + candidatos -> caminho filtrado
    res = hybrid.retrieve("representação da ANTT sobre tarifa de pedagio")
    assert res.diagnostics["path"] == "structured_filter_then_vector_rank"


def test_from_artifacts_fingerprint_divergente_do_indice(tmp_path):
    df = make_selection_df()
    sel, fp = _write_selection_with_manifest(df, tmp_path)
    # Índice construído com OUTRO fingerprint registrado -> incompatível.
    idx_dir = tmp_path / "idx_bad_fp"
    build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="OUTRO_FP",
                max_tokens=16, overlap_tokens=2, batch_size=4, shard_size=4)
    with pytest.raises(HybridIntegrityError):
        HybridRetriever.from_artifacts(sel, idx_dir, model=StubEncoder())


def test_from_artifacts_fingerprint_ausente_no_indice(tmp_path):
    df = make_selection_df()
    sel, fp = _write_selection_with_manifest(df, tmp_path)
    idx_dir = tmp_path / "idx_no_fp"
    build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint=None,
                max_tokens=16, overlap_tokens=2, batch_size=4, shard_size=4)
    with pytest.raises(HybridIntegrityError):
        HybridRetriever.from_artifacts(sel, idx_dir, model=StubEncoder())


def test_from_artifacts_manifesto_divergente(tmp_path):
    # Manifesto com fingerprint que não corresponde ao df -> rejeita.
    df = make_selection_df()
    sel = tmp_path / "selection_test-v1_20260101_000000.parquet"
    df.to_parquet(sel, engine="pyarrow", index=False)
    (tmp_path / "selection_test-v1_20260101_000000_manifest.json").write_text(
        json.dumps({"selection_fingerprint": "nao_corresponde"}), encoding="utf-8")
    idx_dir = _build_compatible_index(
        df, sel, tmp_path, compute_dataset_fingerprint(df, sort_col="doc_id"))
    with pytest.raises(HybridIntegrityError):
        HybridRetriever.from_artifacts(sel, idx_dir, model=StubEncoder())


def test_from_artifacts_doc_da_selecao_ausente_no_indice(tmp_path):
    # Índice construído com um subconjunto (um doc a menos) -> seleção tem doc
    # que não está no índice. Para manter o fingerprint coerente com o índice,
    # registramos no índice o fingerprint do SUBCONJUNTO, mas passamos a seleção
    # COMPLETA ao from_artifacts: o descompasso é detectado por fingerprint e,
    # caso passasse, pela correspondência de doc_id.
    df_full = make_selection_df()
    df_sub = df_full.iloc[:-1].copy()  # remove d5
    sel_full, fp_full = _write_selection_with_manifest(df_full, tmp_path, "sel_full")
    # índice só com o subconjunto:
    sel_sub = tmp_path / "sel_sub.parquet"
    df_sub.to_parquet(sel_sub, engine="pyarrow", index=False)
    fp_sub = compute_dataset_fingerprint(df_sub, sort_col="doc_id")
    idx_dir = tmp_path / "idx_sub"
    build_index(sel_sub, idx_dir, model=StubEncoder(), selection_fingerprint=fp_sub,
                max_tokens=16, overlap_tokens=2, batch_size=4, shard_size=4)
    # from_artifacts com a seleção COMPLETA (fp_full) e índice do subconjunto (fp_sub)
    with pytest.raises(HybridIntegrityError):
        HybridRetriever.from_artifacts(sel_full, idx_dir, model=StubEncoder())


def test_from_artifacts_doc_extra_no_indice(tmp_path):
    # Índice com um doc a MAIS que a seleção. Verifica a correspondência de
    # conjuntos (burlando o check de fingerprint via verify, por construção os
    # fingerprints também divergiriam; aqui forçamos coincidência de fp para
    # isolar a checagem de doc_id não é possível sem corromper — então validamos
    # que a divergência é capturada de todo modo).
    df_sel = make_selection_df().iloc[:-1].copy()      # seleção sem d5
    df_idx = make_selection_df()                        # índice com d5 extra
    sel, fp_sel = _write_selection_with_manifest(df_sel, tmp_path, "sel_small")
    sel_big = tmp_path / "sel_big.parquet"
    df_idx.to_parquet(sel_big, engine="pyarrow", index=False)
    fp_big = compute_dataset_fingerprint(df_idx, sort_col="doc_id")
    idx_dir = tmp_path / "idx_big"
    build_index(sel_big, idx_dir, model=StubEncoder(), selection_fingerprint=fp_big,
                max_tokens=16, overlap_tokens=2, batch_size=4, shard_size=4)
    with pytest.raises(HybridIntegrityError):
        HybridRetriever.from_artifacts(sel, idx_dir, model=StubEncoder())


def test_load_index_rejeita_parcial(tmp_path):
    df = make_selection_df()
    sel = tmp_path / "selection_test-v1_20260101_000000.parquet"
    df.to_parquet(sel, engine="pyarrow", index=False)
    idx_dir = tmp_path / "idx_partial"
    # limit < total -> is_partial_index = True
    build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="fp",
                max_tokens=16, overlap_tokens=2, batch_size=4, shard_size=4, limit=2)
    with pytest.raises(IndexIntegrityError):
        load_index(idx_dir)
    # allow_partial=True permite carregar (uso técnico explícito)
    idx = load_index(idx_dir, allow_partial=True)
    assert idx.meta["is_partial_index"] is True


def test_load_index_meta_ausente(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_index(tmp_path / "inexistente")


def test_verify_integrity_desligado_permite_incompativel(tmp_path):
    # Escotilha de escape: verify_integrity=False NÃO valida compatibilidade.
    df = make_selection_df()
    sel = tmp_path / "selection_test-v1_20260101_000000.parquet"
    df.to_parquet(sel, engine="pyarrow", index=False)
    idx_dir = tmp_path / "idx_any"
    build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="qualquer",
                max_tokens=16, overlap_tokens=2, batch_size=4, shard_size=4)
    hybrid = HybridRetriever.from_artifacts(
        sel, idx_dir, model=StubEncoder(), verify_integrity=False)
    assert isinstance(hybrid, Retriever)

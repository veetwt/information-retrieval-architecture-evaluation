# Feature: arquitetura vetorial — preparação textual, índice e VectorRetriever.
# Usa um ENCODER STUB e um TOKENIZER STUB determinísticos (sem baixar modelo)
# para testar o pipeline: chunking por tokens, vínculo chunk->doc_id,
# construção/carregamento do índice, construção RETOMÁVEL por shards, ordenação
# por similaridade, consolidação por documento (sem duplicação), interface comum
# e reprodutibilidade.

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from retrieval.base import RetrievalResult, Retriever  # noqa: E402
from retrieval.text_prep import (  # noqa: E402
    build_document_text,
    chunk_text,
    chunk_text_by_tokens,
    clean_html,
    document_to_chunks,
    document_to_chunks_by_tokens,
)
from retrieval.vector_index import (  # noqa: E402
    SHARDS_DIR,
    STATE_FILE,
    build_index,
    load_index,
)
from retrieval.vector import VectorRetriever  # noqa: E402


# --------------------------------------------------------------------------- #
# Stubs determinísticos (sem rede)
# --------------------------------------------------------------------------- #

class StubTokenizer:
    """Tokenizer determinístico baseado em palavras.

    Cada palavra vira um id (um vocabulário crescente, estável no processo);
    decode junta as palavras de volta. `num_special_tokens_to_add` devolve 2,
    como o tokenizer real (reserva para [CLS]/[SEP]). É suficiente para exercitar
    o chunking por tokens de forma determinística, sem baixar modelo.
    """

    def __init__(self):
        self._vocab: dict[str, int] = {}
        self._inv: dict[int, str] = {}

    def _id(self, w: str) -> int:
        if w not in self._vocab:
            idx = len(self._vocab) + 10  # evita colidir com ids especiais baixos
            self._vocab[w] = idx
            self._inv[idx] = w
        return self._vocab[w]

    def encode(self, text, add_special_tokens=False):
        ids = [self._id(w) for w in str(text).split()]
        if add_special_tokens:
            # Simula [CLS]/[SEP]: 2 ids especiais (1 e 2) envolvendo o conteúdo.
            return [1] + ids + [2]
        return ids

    def decode(self, ids, skip_special_tokens=True):
        return " ".join(self._inv.get(int(i), "") for i in ids).strip()

    def num_special_tokens_to_add(self, pair=False):
        return 2


class StubEncoder:
    """Encoder determinístico, sem rede. Mapeia texto -> vetor por hashing de
    palavras. Textos com vocabulário semelhante ficam próximos (cosseno alto).
    Expõe `.tokenizer` para o chunking por tokens do índice."""

    def __init__(self, dim: int = 24):
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


# PYTHONHASHSEED pode variar entre processos; dentro de um processo de teste o
# hash de str é estável, o que basta para os asserts determinísticos aqui.


def make_selection(tmp_path: Path) -> Path:
    df = pd.DataFrame({
        "doc_id": ["d1", "d2", "d3"],
        "ASSUNTO": [
            "representacao sobre tarifa de pedagio rodovia",
            "aposentadoria de servidor publico federal",
            "denuncia sobre merenda escolar em pernambuco",
        ],
        "ACORDAO": [
            "<p>acordam reajuste da tarifa de pedagio da rodovia concessao</p>",
            "<p>acordam julgar legal o ato de aposentadoria do servidor</p>",
            "<p>acordam sobre falta de merenda escolar e contratos de professores</p>",
        ],
    })
    p = tmp_path / "selection_test-v1_20260101_000000.parquet"
    df.to_parquet(p, engine="pyarrow", index=False)
    return p


# --------------------------------------------------------------------------- #
# Preparação textual
# --------------------------------------------------------------------------- #

def test_clean_html_remove_tags_preserva_conteudo():
    raw = "<p>ACÓRDÃO Nº 2639/2024 - TCU - Plenário</p>"
    assert clean_html(raw) == "ACÓRDÃO Nº 2639/2024 - TCU - Plenário"


def test_clean_html_preserva_numeros_e_datas():
    raw = "<b>Processo 019.104/2024-3</b> sessão 05/03/2024"
    out = clean_html(raw)
    assert "019.104/2024-3" in out and "05/03/2024" in out


def test_clean_html_vazio_e_nulo():
    assert clean_html(None) == ""
    assert clean_html("") == ""


def test_build_document_text_combina_assunto_acordao():
    t = build_document_text("ASSUNTO X", "<p>CORPO Y</p>")
    assert t == "ASSUNTO X CORPO Y"


def test_chunk_text_curto_um_chunk():
    assert chunk_text("uma frase curta", chunk_words=100, overlap_words=20) == ["uma frase curta"]


def test_chunk_text_longo_com_overlap_e_progresso():
    words = [f"w{i}" for i in range(250)]
    text = " ".join(words)
    chunks = chunk_text(text, chunk_words=100, overlap_words=20)
    # passo = 80 -> chunks começam em 0, 80, 160; o de 160 cobre até o fim (249),
    # então o laço encerra: 3 chunks, sem perda de palavras.
    assert len(chunks) == 3
    assert chunks[0].split()[0] == "w0"
    assert chunks[1].split()[0] == "w80"   # overlap preservado
    assert chunks[2].split()[0] == "w160"
    assert chunks[2].split()[-1] == "w249"  # último chunk vai até o fim
    # nenhuma palavra perdida: a união cobre todas
    cobertas = set()
    for c in chunks:
        cobertas.update(c.split())
    assert cobertas == set(words)


def test_chunk_text_parametros_invalidos():
    with pytest.raises(ValueError):
        chunk_text("x", chunk_words=0)
    with pytest.raises(ValueError):
        chunk_text("x", chunk_words=10, overlap_words=10)


def test_document_to_chunks_vincula_doc_id_e_ordem():
    chunks = document_to_chunks("docX", "a b c", "<p>d e f</p>", chunk_words=2, overlap_words=0)
    assert all(c.doc_id == "docX" for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_document_to_chunks_sem_texto():
    assert document_to_chunks("d", None, None) == []


# --------------------------------------------------------------------------- #
# Chunking por TOKENS (Tarefa 2): garante respeito à janela do modelo
# --------------------------------------------------------------------------- #

def test_chunk_por_tokens_respeita_janela():
    tok = StubTokenizer()
    # 300 palavras-token; max_tokens=10 -> budget util = 10 - 2 = 8
    words = [f"t{i}" for i in range(300)]
    text = " ".join(words)
    pieces = chunk_text_by_tokens(text, tok, max_tokens=10, overlap_tokens=2)
    # cada peça, re-tokenizada + especiais, cabe na janela
    for p in pieces:
        eff = len(tok.encode(p)) + tok.num_special_tokens_to_add()
        assert eff <= 10
    # progresso e cobertura: a 1a peça começa em t0 e a união cobre todas
    assert pieces[0].split()[0] == "t0"
    cobertas = set()
    for p in pieces:
        cobertas.update(p.split())
    assert cobertas == set(words)


def test_chunk_por_tokens_texto_curto_uma_peca():
    tok = StubTokenizer()
    pieces = chunk_text_by_tokens("a b c", tok, max_tokens=10, overlap_tokens=2)
    assert pieces == ["a b c"]


def test_chunk_por_tokens_vazio():
    tok = StubTokenizer()
    assert chunk_text_by_tokens("", tok, max_tokens=10, overlap_tokens=2) == []


def test_chunk_por_tokens_parametros_invalidos():
    tok = StubTokenizer()
    with pytest.raises(ValueError):
        chunk_text_by_tokens("x y z", tok, max_tokens=2, overlap_tokens=0)  # sem budget
    with pytest.raises(ValueError):
        chunk_text_by_tokens("x y z", tok, max_tokens=10, overlap_tokens=8)  # overlap>=budget


def test_document_to_chunks_by_tokens_vincula_doc_id():
    tok = StubTokenizer()
    chunks = document_to_chunks_by_tokens(
        "docY", "a b c d e f", "<p>g h i j k l</p>", tok, max_tokens=10, overlap_tokens=1
    )
    assert all(c.doc_id == "docY" for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


# --------------------------------------------------------------------------- #
# Índice: construção, metadados, carregamento, vínculo chunk->doc_id
# --------------------------------------------------------------------------- #

def test_build_and_load_index(tmp_path):
    sel = make_selection(tmp_path)
    idx_dir = tmp_path / "idx"
    meta = build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="fp123",
                       max_tokens=16, overlap_tokens=2, batch_size=2, shard_size=3)
    assert meta["n_docs_indexed"] == 3
    assert meta["is_partial_index"] is False
    assert meta["selection_fingerprint"] == "fp123"
    assert meta["chunking"] == "by_tokens"
    assert (idx_dir / "embeddings.npy").exists()
    assert (idx_dir / "chunks.parquet").exists()
    assert (idx_dir / "index_meta.json").exists()

    index = load_index(idx_dir)
    assert index.n_chunks == meta["n_chunks"]
    assert index.dim == 24
    # todo chunk referencia um doc_id da seleção
    assert set(index.chunk_doc_ids) <= {"d1", "d2", "d3"}


def test_build_index_nao_recomputa_sem_overwrite(tmp_path):
    sel = make_selection(tmp_path)
    idx_dir = tmp_path / "idx"
    build_index(sel, idx_dir, model=StubEncoder(), batch_size=2)
    emb_mtime = (idx_dir / "embeddings.npy").stat().st_mtime_ns
    # segunda chamada sem overwrite retorna meta sem reescrever
    build_index(sel, idx_dir, model=StubEncoder(), batch_size=2)
    assert (idx_dir / "embeddings.npy").stat().st_mtime_ns == emb_mtime


def test_build_index_parcial_limit(tmp_path):
    sel = make_selection(tmp_path)
    idx_dir = tmp_path / "idxp"
    meta = build_index(sel, idx_dir, model=StubEncoder(), limit=2, batch_size=2)
    assert meta["n_docs_indexed"] == 2
    assert meta["is_partial_index"] is True


# --------------------------------------------------------------------------- #
# Construção RETOMÁVEL por shards (Tarefa 1)
# --------------------------------------------------------------------------- #

def test_shards_e_estado_sao_criados(tmp_path):
    sel = make_selection(tmp_path)
    idx_dir = tmp_path / "idx"
    meta = build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="fp",
                       max_tokens=16, overlap_tokens=2, batch_size=2, shard_size=2)
    # chunks.parquet existe e o estado registra todos os shards concluídos
    assert (idx_dir / "chunks.parquet").exists()
    state = json.loads((idx_dir / STATE_FILE).read_text(encoding="utf-8"))
    n_chunks = meta["n_chunks"]
    expected_shards = (n_chunks + 1) // 2  # shard_size=2
    assert state["n_shards"] == expected_shards
    assert len(state["completed_shards"]) == expected_shards
    assert (idx_dir / SHARDS_DIR).is_dir()


def test_retomada_pula_shards_concluidos(tmp_path):
    # Simula interrupção: prepara chunks + 1 shard, remove embeddings/meta e
    # verifica que a retomada reaproveita o shard já existente e conclui.
    sel = make_selection(tmp_path)
    idx_dir = tmp_path / "idx"

    # 1a construção completa (com stub) para ter chunks + shards no disco.
    build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="fp",
                max_tokens=16, overlap_tokens=2, batch_size=2, shard_size=2)

    # Simula interrupção APÓS consolidar: apaga os artefatos finais, mantém
    # chunks.parquet, build_state.json e os shards.
    (idx_dir / "embeddings.npy").unlink()
    (idx_dir / "index_meta.json").unlink()

    # Conta um encoder que registra quantos textos re-codificou.
    class CountingEncoder(StubEncoder):
        def __init__(self):
            super().__init__()
            self.encoded = 0

        def encode(self, texts, **kw):
            self.encoded += len(texts)
            return super().encode(texts, **kw)

    enc = CountingEncoder()
    meta = build_index(sel, idx_dir, model=enc, selection_fingerprint="fp",
                       max_tokens=16, overlap_tokens=2, batch_size=2, shard_size=2)
    # Todos os shards já estavam concluídos -> nenhum chunk recodificado.
    assert enc.encoded == 0
    assert (idx_dir / "embeddings.npy").exists()
    assert meta["n_chunks"] > 0


def test_retomada_refaz_shard_incompleto(tmp_path):
    sel = make_selection(tmp_path)
    idx_dir = tmp_path / "idx"
    build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="fp",
                max_tokens=16, overlap_tokens=2, batch_size=2, shard_size=2)

    # Corrompe um shard (remove de completed + apaga o arquivo) e os finais.
    state_path = idx_dir / STATE_FILE
    state = json.loads(state_path.read_text(encoding="utf-8"))
    corrupt_start = state["completed_shards"][0]
    state["completed_shards"] = [s for s in state["completed_shards"] if s != corrupt_start]
    state_path.write_text(json.dumps(state), encoding="utf-8")
    shard_file = idx_dir / SHARDS_DIR / f"emb_{corrupt_start:08d}.npy"
    shard_file.unlink()
    (idx_dir / "embeddings.npy").unlink()
    (idx_dir / "index_meta.json").unlink()

    meta = build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="fp",
                       max_tokens=16, overlap_tokens=2, batch_size=2, shard_size=2)
    assert shard_file.exists()  # refeito
    assert (idx_dir / "embeddings.npy").exists()
    assert meta["n_chunks"] > 0


def test_retomada_incompativel_e_rejeitada(tmp_path):
    sel = make_selection(tmp_path)
    idx_dir = tmp_path / "idx"
    build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="fp",
                max_tokens=16, overlap_tokens=2, batch_size=2, shard_size=2)
    (idx_dir / "embeddings.npy").unlink()
    (idx_dir / "index_meta.json").unlink()

    # Mudar o fingerprint da seleção torna o estado salvo incompatível.
    with pytest.raises(ValueError):
        build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="OUTRO",
                    max_tokens=16, overlap_tokens=2, batch_size=2, shard_size=2)


def test_consolidacao_equivale_aos_shards(tmp_path):
    # O embeddings.npy consolidado deve ser a concatenação dos shards na ordem.
    sel = make_selection(tmp_path)
    idx_dir = tmp_path / "idx"
    meta = build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="fp",
                       max_tokens=16, overlap_tokens=2, batch_size=2, shard_size=2)
    emb = np.load(idx_dir / "embeddings.npy")
    shard_dir = idx_dir / SHARDS_DIR
    parts = [np.load(p) for p in sorted(shard_dir.glob("emb_*.npy"))]
    concat = np.concatenate(parts, axis=0)
    assert emb.shape == concat.shape == (meta["n_chunks"], 24)
    assert np.allclose(emb, concat)


def test_overwrite_reconstroi_limpo(tmp_path):
    sel = make_selection(tmp_path)
    idx_dir = tmp_path / "idx"
    build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="fp",
                max_tokens=16, overlap_tokens=2, batch_size=2, shard_size=2)
    meta = build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="fp2",
                       max_tokens=16, overlap_tokens=2, batch_size=2, shard_size=2,
                       overwrite=True)
    assert meta["selection_fingerprint"] == "fp2"
    assert (idx_dir / "embeddings.npy").exists()


# --------------------------------------------------------------------------- #
# VectorRetriever: interface, ordenação, consolidação, reprodutibilidade
# --------------------------------------------------------------------------- #

@pytest.fixture
def retriever(tmp_path):
    sel = make_selection(tmp_path)
    idx_dir = tmp_path / "idx"
    build_index(sel, idx_dir, model=StubEncoder(), selection_fingerprint="fp",
                max_tokens=16, overlap_tokens=2, batch_size=2, shard_size=3)
    return VectorRetriever.from_index_dir(idx_dir, model=StubEncoder(), display_limit=10)


def test_cumpre_interface_comum(retriever):
    assert isinstance(retriever, Retriever)
    assert retriever.architecture_name == "vector"
    res = retriever.retrieve("tarifa de pedagio rodovia")
    assert isinstance(res, RetrievalResult)


def test_score_e_ordenacao_desc(retriever):
    res = retriever.retrieve("tarifa de pedagio rodovia concessao")
    scores = [d.score for d in res.documents]
    assert scores == sorted(scores, reverse=True)
    assert all(isinstance(d.score, float) for d in res.documents)
    # o doc de pedágio deve ser o mais similar
    assert res.documents[0].doc_id == "d1"


def test_sem_duplicacao_de_documento(retriever):
    res = retriever.retrieve("acordam reajuste tarifa pedagio servidor merenda")
    ids = res.doc_ids
    assert len(ids) == len(set(ids))  # cada doc_id aparece uma única vez


def test_evidencia_contem_passagem(retriever):
    res = retriever.retrieve("merenda escolar pernambuco")
    top = res.documents[0]
    assert top.doc_id == "d3"
    assert "passage" in top.evidence and top.evidence["passage"]
    assert top.evidence["consolidation"] == "max_pooling"


def test_reprodutibilidade(retriever):
    q = "tarifa de pedagio"
    r1 = retriever.retrieve(q)
    r2 = retriever.retrieve(q)
    assert [(d.doc_id, round(d.score, 6)) for d in r1.documents] == \
           [(d.doc_id, round(d.score, 6)) for d in r2.documents]


def test_fields_used_apenas_assunto_acordao(retriever):
    res = retriever.retrieve("qualquer coisa")
    assert set(res.fields_used) == {"ASSUNTO", "ACORDAO"}


def test_diagnostico_reporta_chunking_por_tokens(retriever):
    res = retriever.retrieve("tarifa pedagio")
    assert res.diagnostics["chunking"] == "by_tokens"
    assert res.diagnostics["max_tokens"] == 16


def test_display_limit_provisorio(tmp_path):
    sel = make_selection(tmp_path)
    idx_dir = tmp_path / "idx"
    build_index(sel, idx_dir, model=StubEncoder(), batch_size=2, shard_size=2)
    r = VectorRetriever.from_index_dir(idx_dir, model=StubEncoder(), display_limit=1)
    res = r.retrieve("tarifa pedagio")
    assert len(res.documents) == 1
    assert res.diagnostics["display_limit_provisional"] == 1

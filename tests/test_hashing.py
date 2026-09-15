# Feature: construcao-corpus-piloto
# Requirements: 1.2, 2.3, 8.5, 9.4, 9.5

import hashlib
import math
import sys
from pathlib import Path
import pandas as pd
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from utils.hashing import compute_sha256, compute_dataset_fingerprint


# --- T1.3: testes de compute_sha256 ---

def test_sha256_equivalente_hashlib(tmp_path):
    """Property 1 relacionada: hash calculado deve ser idêntico ao hashlib."""
    conteudo = b"acordao tcu teste 12345"
    f = tmp_path / "teste.bin"
    f.write_bytes(conteudo)
    esperado = hashlib.sha256(conteudo).hexdigest()
    assert compute_sha256(f) == esperado

def test_sha256_arquivo_grande_chunks(tmp_path):
    """Arquivo maior que 8 MB deve ser lido corretamente por chunks."""
    conteudo = b"x" * (9 * 1024 * 1024)  # 9 MB
    f = tmp_path / "grande.bin"
    f.write_bytes(conteudo)
    esperado = hashlib.sha256(conteudo).hexdigest()
    assert compute_sha256(f) == esperado

def test_sha256_arquivo_inexistente_levanta_ioerror(tmp_path):
    """IOError deve ser levantado para caminho inválido."""
    with pytest.raises(IOError):
        compute_sha256(tmp_path / "nao_existe.bin")

def test_sha256_retorna_64_chars(tmp_path):
    """Retorno deve ser string hexadecimal de exatamente 64 caracteres."""
    f = tmp_path / "a.bin"
    f.write_bytes(b"qualquer coisa")
    resultado = compute_sha256(f)
    assert isinstance(resultado, str)
    assert len(resultado) == 64
    assert all(c in "0123456789abcdef" for c in resultado)


# --- T1.4: testes de compute_dataset_fingerprint ---

def test_fingerprint_determinístico_mesma_entrada():
    """Duas chamadas com o mesmo DataFrame devem retornar o mesmo fingerprint."""
    df = pd.DataFrame({"doc_id": ["a", "b"], "texto": ["foo", "bar"]})
    assert compute_dataset_fingerprint(df) == compute_dataset_fingerprint(df)

def test_fingerprint_muda_quando_schema_muda():
    """Property 5: fingerprint deve mudar quando o schema lógico muda."""
    df1 = pd.DataFrame({"doc_id": ["a"], "texto": ["foo"]})
    df2 = pd.DataFrame({"doc_id": ["a"], "texto": ["foo"], "extra": ["x"]})
    assert compute_dataset_fingerprint(df1) != compute_dataset_fingerprint(df2)

def test_fingerprint_muda_quando_conteudo_muda():
    """Fingerprint deve mudar quando o conteúdo dos dados muda."""
    df1 = pd.DataFrame({"doc_id": ["a"], "texto": ["foo"]})
    df2 = pd.DataFrame({"doc_id": ["a"], "texto": ["bar"]})
    assert compute_dataset_fingerprint(df1) != compute_dataset_fingerprint(df2)

def test_fingerprint_independente_de_ordem_de_linhas():
    """Fingerprint deve ser independente da ordem de inserção das linhas."""
    df1 = pd.DataFrame({"doc_id": ["a", "b"], "texto": ["foo", "bar"]})
    df2 = pd.DataFrame({"doc_id": ["b", "a"], "texto": ["bar", "foo"]})
    assert compute_dataset_fingerprint(df1) == compute_dataset_fingerprint(df2)

def test_fingerprint_retorna_64_chars():
    """Retorno deve ser string hexadecimal de 64 caracteres."""
    df = pd.DataFrame({"doc_id": ["a"], "texto": ["foo"]})
    resultado = compute_dataset_fingerprint(df)
    assert isinstance(resultado, str)
    assert len(resultado) == 64
    assert all(c in "0123456789abcdef" for c in resultado)

def test_fingerprint_lida_com_null():
    """Null deve ser serializado como literal 'null'."""
    df1 = pd.DataFrame({"doc_id": ["a"], "texto": [None]})
    df2 = pd.DataFrame({"doc_id": ["a"], "texto": [None]})
    assert compute_dataset_fingerprint(df1) == compute_dataset_fingerprint(df2)

@given(
    dados=st.lists(
        st.fixed_dictionaries({"doc_id": st.text(min_size=1, max_size=20)}),
        min_size=1,
        max_size=20,
    )
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property_dataset_fingerprint_determinístico(dados):
    """
    Feature: construcao-corpus-piloto
    Property 5: Determinismo do dataset_fingerprint incluindo schema
    Para qualquer DataFrame, duas chamadas retornam o mesmo fingerprint.
    """
    df = pd.DataFrame(dados)
    assert compute_dataset_fingerprint(df) == compute_dataset_fingerprint(df)

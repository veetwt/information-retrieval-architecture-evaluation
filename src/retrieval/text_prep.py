"""Preparação textual reproduzível para a arquitetura vetorial.

Responsável por transformar os campos ASSUNTO e ACORDAO de um acórdão em
passagens (chunks) prontas para embedding, de forma determinística e sem
descartar informação silenciosamente.

Decisões (ver justificativa na entrega da etapa):
- Usa EXCLUSIVAMENTE ASSUNTO e ACORDAO (nunca SUMARIO/RELATORIO/VOTO).
- ACORDAO é 100% HTML no corpus; remove-se a marcação preservando o TEXTO,
  inclusive números de acórdão, datas, artigos de lei e pontuação juridicamente
  relevante (não se removem dígitos, barras, pontos ou hífens do conteúdo).
- Como o modelo de embedding tem janela curta (128 tokens) e a maioria dos
  documentos excede isso, o texto é dividido em CHUNKS por janelas de palavras
  com sobreposição. Cada chunk mantém o vínculo com o doc_id e um índice de
  ordem, para rastreabilidade e consolidação posterior por documento.

Dois modos de chunking, ambos determinísticos:

1) Por TOKENS do tokenizer real (modo de produção, recomendado). É o único que
   garante, por construção, que nenhum chunk exceda a janela do modelo (128
   tokens): fatia a sequência de tokens em janelas de `max_tokens` com
   sobreposição e decodifica cada janela de volta para texto. Foi verificado que
   o chunking por palavras (abaixo) produzia chunks com ~227 tokens em média
   (94,8% acima de 128), causando TRUNCAMENTO SILENCIOSO — por isso o pipeline
   real usa o chunking por tokens.

2) Por PALAVRAS (modo leve, sem tokenizer). Usado em testes determinísticos com
   encoder-stub (sem rede). NÃO garante o limite de tokens e por isso não deve
   ser usado para construir o índice real.

Parâmetros padrão de chunking por tokens (registrados no índice):
- MAX_TOKENS: 128 (janela do modelo, incluindo tokens especiais [CLS]/[SEP]).
- OVERLAP_TOKENS: 16 tokens de sobreposição, para não cortar evidência na
  fronteira; equivale a ~12,5% da janela.

Parâmetros padrão de chunking por palavras (modo de teste):
- CHUNK_WORDS: ~100 palavras por chunk.
- CHUNK_OVERLAP_WORDS: ~20 palavras de sobreposição.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

CHUNK_WORDS = 100
CHUNK_OVERLAP_WORDS = 20

MAX_TOKENS = 128
OVERLAP_TOKENS = 16

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Chunk:
    """Uma passagem derivada de um acórdão.

    - doc_id: identificador do documento de origem (unidade de avaliação).
    - chunk_index: ordem da passagem dentro do documento (0-based).
    - text: texto limpo da passagem (usado para embedding e como evidência).
    """

    doc_id: str
    chunk_index: int
    text: str


def clean_html(value: object) -> str:
    """Remove marcação HTML e normaliza espaços, preservando o conteúdo textual.

    Não altera caixa, não remove acentos, dígitos, datas, números de acórdão nem
    pontuação do conteúdo — apenas retira as tags e colapsa espaços em branco.
    Valores nulos/NaN viram string vazia.
    """
    if value is None:
        return ""
    s = str(value)
    if s.lower() == "nan":
        return ""
    s = _TAG_RE.sub(" ", s)
    # entidades HTML comuns que possam restar
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return _WS_RE.sub(" ", s).strip()


def build_document_text(assunto: object, acordao: object) -> str:
    """Combina ASSUNTO e ACORDAO (nesta ordem) em um único texto limpo.

    A ordem ASSUNTO → ACORDAO coloca o resumo temático antes do inteiro teor,
    favorecendo que a primeira passagem carregue o tema principal.
    """
    a = clean_html(assunto)
    b = clean_html(acordao)
    return (a + " " + b).strip() if a or b else ""


def chunk_text(
    text: str,
    chunk_words: int = CHUNK_WORDS,
    overlap_words: int = CHUNK_OVERLAP_WORDS,
) -> list[str]:
    """Divide o texto em janelas de palavras com sobreposição (determinístico).

    - Retorna [] para texto vazio.
    - Se o texto couber em um único chunk, retorna uma lista de um elemento.
    - A sobreposição evita cortar evidência na fronteira; o passo é
      (chunk_words - overlap_words). Garante progresso mesmo com parâmetros
      degenerados.
    """
    if chunk_words <= 0:
        raise ValueError("chunk_words deve ser > 0")
    if overlap_words < 0 or overlap_words >= chunk_words:
        raise ValueError("overlap_words deve estar em [0, chunk_words)")

    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_words:
        return [" ".join(words)]

    step = chunk_words - overlap_words
    chunks: list[str] = []
    start = 0
    n = len(words)
    while start < n:
        window = words[start:start + chunk_words]
        chunks.append(" ".join(window))
        if start + chunk_words >= n:
            break
        start += step
    return chunks


@runtime_checkable
class Tokenizer(Protocol):
    """Interface mínima do tokenizer usada pelo chunking por tokens.

    Compatível com os tokenizers do Hugging Face (``model.tokenizer``):
    - ``encode(text, add_special_tokens=False) -> list[int]``
    - ``decode(ids, skip_special_tokens=True) -> str``
    - ``num_special_tokens_to_add(pair=False) -> int``
    """

    def encode(self, text: str, add_special_tokens: bool = ...) -> list[int]:
        ...

    def decode(self, ids: list[int], skip_special_tokens: bool = ...) -> str:
        ...

    def num_special_tokens_to_add(self, pair: bool = ...) -> int:
        ...


# Margem de segurança (em tokens) descontada do orçamento por janela. O texto de
# cada chunk é DECODIFICADO dos ids e, na codificação do modelo, é RE-TOKENIZADO;
# essa ida-e-volta (decode → re-encode) não preserva exatamente a contagem de
# tokens (fronteiras de subpalavra/espaço podem deslocar em ±1). A margem evita
# que a re-tokenização ultrapasse a janela do modelo por 1 token.
ROUNDTRIP_SAFETY_TOKENS = 4


def chunk_text_by_tokens(
    text: str,
    tokenizer: "Tokenizer",
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[str]:
    """Divide o texto em janelas de TOKENS com sobreposição (determinístico).

    Garante que cada passagem, ao ser re-tokenizada pelo modelo com os tokens
    especiais, caiba em `max_tokens` — eliminando o truncamento silencioso.

    O orçamento útil por janela é
    ``max_tokens - num_special_tokens_to_add - ROUNDTRIP_SAFETY_TOKENS``
    (reserva para [CLS]/[SEP] e para a variação da ida-e-volta decode→re-encode).
    O passo é ``budget - overlap_tokens``.

    Como salvaguarda final e verificável, cada peça decodificada é
    RE-TOKENIZADA (com tokens especiais) e, se ainda exceder ``max_tokens``, tem
    os ids finais descartados de forma determinística até caber. Assim, nenhum
    chunk persistido pode ser truncado silenciosamente pelo modelo.

    - Retorna [] para texto vazio.
    - Se o texto couber em uma janela, retorna uma lista de um elemento.
    - O texto de cada chunk é obtido decodificando os ids da janela, de forma
      que o chunk persistido corresponda ao que será embutido.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens deve ser > 0")

    try:
        special = int(tokenizer.num_special_tokens_to_add(pair=False))
    except TypeError:  # pragma: no cover - tokenizers sem o kwarg
        special = int(tokenizer.num_special_tokens_to_add())
    budget = max_tokens - special - ROUNDTRIP_SAFETY_TOKENS
    if budget <= 0:
        raise ValueError(
            f"max_tokens={max_tokens} insuficiente para {special} tokens "
            f"especiais + margem de segurança {ROUNDTRIP_SAFETY_TOKENS}"
        )
    if overlap_tokens < 0 or overlap_tokens >= budget:
        raise ValueError(
            "overlap_tokens deve estar em [0, max_tokens - especiais - margem)"
        )

    ids = tokenizer.encode(text, add_special_tokens=False)
    if not ids:
        return []

    def _fit(window_ids: list[int]) -> str:
        """Decodifica e garante, por re-tokenização, que cabe em max_tokens."""
        w = list(window_ids)
        while w:
            piece = tokenizer.decode(w, skip_special_tokens=True).strip()
            n_eff = len(tokenizer.encode(piece, add_special_tokens=True))
            if n_eff <= max_tokens:
                return piece
            # Ainda grande após a ida-e-volta: remove o último id e tenta de novo.
            w = w[:-1]
        return ""

    if len(ids) <= budget:
        return [_fit(ids)]

    step = budget - overlap_tokens
    pieces: list[str] = []
    start = 0
    n = len(ids)
    while start < n:
        window = ids[start:start + budget]
        piece = _fit(window)
        if piece:
            pieces.append(piece)
        if start + budget >= n:
            break
        start += step
    return pieces


def document_to_chunks(
    doc_id: str,
    assunto: object,
    acordao: object,
    chunk_words: int = CHUNK_WORDS,
    overlap_words: int = CHUNK_OVERLAP_WORDS,
) -> list[Chunk]:
    """Pipeline (modo de teste, por palavras): combina campos, limpa e divide.

    Um documento sem texto (após limpeza) não gera chunks. Caso contrário, gera
    ao menos um Chunk. Cada Chunk preserva o doc_id e o índice de ordem.

    NÃO garante o limite de tokens do modelo; para o índice real use
    ``document_to_chunks_by_tokens``.
    """
    text = build_document_text(assunto, acordao)
    pieces = chunk_text(text, chunk_words, overlap_words)
    return [Chunk(doc_id=doc_id, chunk_index=i, text=p) for i, p in enumerate(pieces)]


def document_to_chunks_by_tokens(
    doc_id: str,
    assunto: object,
    acordao: object,
    tokenizer: "Tokenizer",
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[Chunk]:
    """Pipeline de produção: combina campos, limpa e divide por TOKENS reais.

    Garante que cada chunk caiba na janela do modelo. Um documento sem texto
    (após limpeza) não gera chunks.
    """
    text = build_document_text(assunto, acordao)
    pieces = chunk_text_by_tokens(text, tokenizer, max_tokens, overlap_tokens)
    return [Chunk(doc_id=doc_id, chunk_index=i, text=p) for i, p in enumerate(pieces)]

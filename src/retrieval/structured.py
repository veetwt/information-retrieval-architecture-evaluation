"""Protótipo da arquitetura de recuperação ESTRUTURADA (baseada em metadados).

A recuperação estruturada NÃO é BM25 nem busca lexical sobre o texto: ela
interpreta, a partir do TEXTO da consulta, possíveis condições sobre os seis
campos de metadados auditados e recupera os documentos da Selecao_Experimental
que satisfazem a conjunção dessas condições.

Campos de metadados usados: COLEGIADO, RELATOR, TIPOPROCESSO, DATASESSAO,
ENTIDADE, UNIDADETECNICA.

Estratégia GENÉRICA de interpretação (sem regra por pergunta; sem acesso à ficha):
- COLEGIADO: detecta menções a "plenário", "primeira/1ª câmara", "segunda/2ª câmara".
- TIPOPROCESSO: mapa derivado automaticamente dos valores distintos do corpus
  (nome e sigla de cada valor "NOME (SIGLA)"); casa o tipo citado no texto.
- RELATOR: casa o nome de um relator (entre os valores distintos do corpus) citado
  no texto, com correspondência por nome completo ou sobrenome inequívoco.
- DATASESSAO: detecta datas "dd/mm/aaaa" e "d de <mês> de aaaa".
- ENTIDADE: interpretação genérica derivada do corpus (ver _build_entidade_index e
  _match_entidade): casa por componentes (split por ';'), normaliza caixa/acentos/
  espaços/pontuação, reconhece siglas INEQUÍVOCAS entre parênteses e exige
  ESPECIFICIDADE do nome (não ser composto só por tokens de contexto genéricos
  como "estado de"/"municipio de"). Menções pouco específicas ou ao órgão julgador
  (ex.: "Tribunal de Contas da União" como contexto) NÃO viram filtro: são
  registradas no diagnóstico. Nenhuma lista é específica das perguntas.
- UNIDADETECNICA: interpretação CONSERVADORA, apenas por SIGLA inequívoca
  (ex.: 'AudPessoal'). O casamento por nome NÃO é habilitado porque o prefixo das
  unidades ("Unidade de Auditoria Especializada em ...") é muito repetitivo e
  geraria falsos positivos. Siglas ambíguas são apenas registradas no diagnóstico.

Semântica de recuperação:
- O resultado é o CONJUNTO de documentos que satisfazem a conjunção das condições
  identificadas. Como não há pontuação de relevância natural em filtros, `score`
  é None (nunca inventado) e a ordem é determinística por `doc_id`.
- Se NENHUMA condição for identificada, o resultado é vazio e o diagnóstico
  registra `no_conditions_identified=True` — não se inventam filtros.

Determinismo: a mesma consulta sobre o mesmo corpus produz sempre o mesmo
resultado (ordenação estável por doc_id).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

try:
    from retrieval.base import RetrievalResult, RetrievedDocument
except ImportError:  # pragma: no cover
    from .base import RetrievalResult, RetrievedDocument


METADATA_FIELDS = (
    "COLEGIADO", "RELATOR", "TIPOPROCESSO", "DATASESSAO", "ENTIDADE", "UNIDADETECNICA",
)

# Separador de componentes em ENTIDADE multivalorada (observado na auditoria).
ENTIDADE_SEPARATOR = ";"

# Comprimento mínimo (normalizado) de um nome de entidade para ser considerado
# específico o bastante para virar filtro. Evita casar fragmentos curtos.
ENTIDADE_MIN_LEN = 12

# Um token é tratado como "de contexto" (genérico) quando aparece em uma fração
# de componentes distintos de ENTIDADE maior ou igual a este limiar. Derivado do
# corpus (document frequency), reproduzível e independente de perguntas. Em
# corpora grandes, captura palavras administrativas/estruturais frequentes
# (ex.: "estado", "municipio", "secretaria"). Uma menção composta apenas por
# tokens de contexto não é específica o bastante para impor um filtro.
CONTEXT_TOKEN_DF_RATIO = 0.02

# A guarda estatística de tokens de contexto só é ativada quando há componentes
# distintos suficientes para que a frequência seja significativa. Abaixo disso
# (ex.: corpora sintéticos de teste), o conjunto de tokens de contexto é vazio e
# a interpretação se apoia apenas em comprimento/especificidade estrutural.
CONTEXT_TOKEN_MIN_COMPONENTS = 200

# Denominações da instituição EMISSORA do corpus (a corte que profere os acórdãos).
# Como a coleção é, por definição, composta por acórdãos do TCU, nomear o próprio
# TCU na pergunta refere-se ao ÓRGÃO JULGADOR e não a uma entidade jurisdicionada
# alvo; portanto não deve virar filtro de ENTIDADE. É um fato do DATASET (não uma
# lista por pergunta). Comparação feita sobre a forma normalizada.
ISSUING_INSTITUTION_TERMS = (
    "tribunal de contas da uniao",
    "tcu",
)

_MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _norm(s: str) -> str:
    """Normaliza para casamento: minúsculas, sem acento, espaços colapsados.

    Converte os indicadores ordinais 'ª'/'º' em 'a'/'o' antes de remover acentos,
    para que '1ª' vire '1a' (e não um caractere residual).
    """
    s = str(s).replace("ª", "a").replace("º", "o").replace("°", "o")
    return " ".join(_strip_accents(s).lower().split())


def _strip_paren(s: str) -> str:
    """Remove trechos entre parênteses (ex.: a sigla '(ANTT)') e normaliza espaços.

    Usado para casar variantes da mesma entidade com e sem a sigla entre parênteses.
    """
    return " ".join(re.sub(r"\([^)]*\)", " ", s).split())


# Formato de uma sigla: letras/dígitos, podendo conter barra, ponto ou hífen
# internos (ex.: 'ANTT', 'Sesc/MS', 'CC/PR', 'Cefet/RJ'). Usado para extrair
# siglas de dentro de parênteses, inclusive quando seguidas de outro conteúdo
# (ex.: '(Sesc/MS, CNPJ ...)').
_SIGLA_TOKEN_RE = re.compile(r"^[A-Za-zºª]+(?:[/.\-][A-Za-z0-9ºª]+)*$")


def _is_acronym_like(token: str) -> bool:
    """Verdadeiro se o token (na CAIXA ORIGINAL) tem forma de sigla/acrônimo.

    Critérios genéricos (independentes de lista):
    - contém '/' (ex.: 'Sesc/MS', 'CC/PR'); ou
    - é todo em maiúsculas (ex.: 'ANTT', 'AGU', 'ANS'); ou
    - tem ao menos 2 letras maiúsculas (ex.: 'AudPessoal', 'AudTCE').

    Rejeita palavras comuns minúsculas ('que', 'em', 'de') e nomes próprios com uma
    única inicial maiúscula ('Eletronorte'), que não são siglas discriminantes.
    """
    letras = [c for c in token if c.isalpha()]
    if not letras:
        return False
    if "/" in token:
        return True
    uppers = sum(1 for c in letras if c.isupper())
    if uppers == len(letras):  # todo maiúsculo
        return True
    return uppers >= 2


def _extract_siglas(paren_content: str) -> list[str]:
    """Extrai tokens com cara de sigla de dentro de um parêntese (caixa original).

    Separa o conteúdo por vírgula/ponto-e-vírgula e, para cada parte, considera o
    primeiro 'token' (até o primeiro espaço) — assim, múltiplas siglas legítimas em
    partes distintas são todas extraídas. Aceita o token se tiver forma de sigla
    (_SIGLA_TOKEN_RE), comprimento plausível E aparência de acrônimo
    (_is_acronym_like, avaliado na caixa ORIGINAL), E não for um rótulo de
    identificador seguido de número (ex.: 'CNPJ 03.560.440/...', 'UASG 158154'),
    que é rótulo administrativo, não sigla de entidade.

    Exemplos:
    - '(Sesc/MS, CNPJ 03.560.440/0001-91)' -> ['Sesc/MS']  (CNPJ+número descartado)
    - '(Ceasa/MG) e ... (Casemg)' -> ambas as siglas são preservadas
    - '(que incorporou ...)' e '(em Liquidação)' -> []  (palavras comuns)
    """
    siglas: list[str] = []
    for parte in re.split(r"[,;]", paren_content):
        parte = parte.strip()
        if not parte:
            continue
        toks = parte.split()
        token = toks[0].strip().strip(".")
        # Rótulo de identificador seguido de número (ex.: 'CNPJ 03.560.440/...',
        # 'UASG 158154') NÃO é sigla de entidade: é um rótulo administrativo que
        # precede um valor de inscrição. Regra genérica (não há lista de rótulos):
        # se o token-candidato é imediatamente seguido, na mesma parte, por um
        # token que começa com dígito, descarta-se o candidato.
        seguido_de_numero = len(toks) >= 2 and toks[1][:1].isdigit()
        if (
            2 <= len(token) <= 12
            and _SIGLA_TOKEN_RE.match(token)
            and _is_acronym_like(token)
            and not seguido_de_numero
        ):
            siglas.append(token)
    return siglas


def _sigla_usable_in_text(sigla_norm: str) -> bool:
    """Se uma sigla (já normalizada) pode ser casada com segurança em texto livre.

    Siglas muito curtas (< 3 caracteres) são propensas a colisão com partículas da
    língua; só são aceitas se contiverem '/'. Reduz falsos positivos no casamento
    sobre a consulta em linguagem natural.
    """
    return ("/" in sigla_norm) or (len(sigla_norm) >= 3)


def _base_identity(component: str) -> str:
    """Identidade normalizada de um componente: sem parênteses, sem ponto final.

    Dois componentes que diferem apenas por caixa, acentos, pontuação ou pela sigla
    entre parênteses reduzem-se à mesma identidade (ex.: '... (CNPQ)' e '... (CNPq)').
    """
    return _strip_paren(_norm(component)).rstrip(". ")


def _stem(token: str) -> str:
    """Radical conservador de uma palavra (pt-br) para casar singular/plural.

    Remove acento (via _norm no chamador) e sufixos flexionais comuns. Usado só
    para o nome de TIPOPROCESSO (ex.: 'representacao'/'representacoes' -> 'represent').
    Não é um stemmer linguístico completo; é uma heurística determinística.
    """
    t = token
    for suf in ("coes", "cao", "oes", "aos", "ais", "res", "es", "as", "os", "a", "o", "s"):
        if len(t) - len(suf) >= 5 and t.endswith(suf):
            return t[: -len(suf)]
    return t


class StructuredRetriever:
    """Recuperação estruturada por interpretação de condições de metadados."""

    architecture_name = "structured"
    VERSION = "0.3.0"

    def __init__(
        self,
        df: pd.DataFrame,
        corpus_fingerprint: str | None = None,
        issuing_institution_terms: tuple[str, ...] = ISSUING_INSTITUTION_TERMS,
    ) -> None:
        """Inicializa com o DataFrame da seleção congelada (somente leitura).

        `corpus_fingerprint` é registrado nos diagnósticos para reprodutibilidade.
        `issuing_institution_terms` lista denominações normalizadas da corte emissora
        do corpus (fato do dataset), para que nomeá-la não vire filtro de ENTIDADE.
        """
        self._df = df
        self._fingerprint = corpus_fingerprint
        self._issuing_terms = {_norm(t) for t in issuing_institution_terms}
        # Vocabulários derivados do próprio corpus (genéricos, não por pergunta).
        self._colegiados = self._distinct("COLEGIADO")
        self._relatores = self._distinct("RELATOR")
        self._tipo_map = self._build_tipo_map()
        self._build_entidade_index()
        self._build_unidade_index()

    # ------------------------------------------------------------------ #
    # Construção de vocabulários a partir do corpus
    # ------------------------------------------------------------------ #

    def _distinct(self, col: str) -> list[str]:
        s = self._df[col].dropna().astype(str).str.strip()
        s = s[s != ""]
        return sorted(s.unique().tolist())

    def _build_tipo_map(self) -> list[dict]:
        """Lista de entradas de TIPOPROCESSO derivadas do corpus (genérica).

        Para cada valor "NOME (SIGLA)" registra:
        - canonical: o valor canônico;
        - name_stem: radical da primeira palavra do nome (casa singular/plural);
        - name_norm: nome normalizado completo (para casamento por substring);
        - sigla: sigla normalizada (casada como palavra inteira, quando existir).
        """
        entradas: list[dict] = []
        for val in self._distinct("TIPOPROCESSO"):
            m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", val)
            nome = m.group(1) if m else val
            sigla = m.group(2) if m else ""
            nome_norm = _norm(nome)
            primeira = nome_norm.split()[0] if nome_norm.split() else nome_norm
            entradas.append({
                "canonical": val,
                "name_stem": _stem(primeira),
                "name_norm": nome_norm,
                "sigla": _norm(sigla),
            })
        return entradas

    def _build_entidade_index(self) -> None:
        """Índices de ENTIDADE derivados do corpus (genéricos).

        Constrói:
        - self._ent_components: componentes distintos (após split por ';' e remoção
          de ponto final), com forma normalizada, para casamento por substring;
        - self._ent_sigla_unamb: mapa sigla_normalizada -> componente, SOMENTE para
          siglas inequívocas (entre parênteses) que apontam para um único componente;
        - self._context_tokens: conjunto dos tokens mais frequentes entre componentes
          distintos (tokens "de contexto" genéricos), para rejeitar menções pouco
          específicas.

        Nenhuma lista é específica das perguntas de desenvolvimento; tudo vem dos
        valores reais do campo ENTIDADE.
        """
        from collections import Counter

        componentes: set[str] = set()
        for val in self._df["ENTIDADE"].dropna().astype(str):
            for part in val.split(ENTIDADE_SEPARATOR):
                part = part.strip().rstrip(".").strip()
                if part:
                    componentes.add(part)

        # Lista de componentes com forma normalizada (para busca por substring).
        self._ent_components = [
            {"text": c, "norm": _norm(c).rstrip(". ")} for c in sorted(componentes)
        ]

        # Siglas entre parênteses -> componentes. Extrai o token de sigla mesmo
        # quando há conteúdo extra no parêntese (ex.: '(Sesc/MS, CNPJ ...)').
        sigla_to_comps: dict[str, set[str]] = {}
        for c in componentes:
            for m in re.finditer(r"\(([^)]+)\)", c):
                for s in _extract_siglas(m.group(1)):
                    sigla_to_comps.setdefault(_norm(s), set()).add(c)

        # Uma sigla é utilizável quando TODOS os seus componentes compartilham a
        # mesma IDENTIDADE (nome-base sem parênteses). Isso unifica variantes da
        # mesma entidade (ex.: 'CNPQ'/'CNPq') e descarta siglas genuinamente
        # ambíguas (que apontam para entidades diferentes). O valor guardado é o
        # nome-base (identidade) a ser usado como filtro.
        self._ent_sigla_unamb: dict[str, str] = {}
        self._ent_sigla_ambiguous: set[str] = set()
        for s, comps_s in sigla_to_comps.items():
            identidades = {_base_identity(c) for c in comps_s}
            if len(identidades) == 1:
                # representante: o componente mais curto (nome-base mais limpo)
                repr_comp = min(comps_s, key=lambda c: len(c))
                self._ent_sigla_unamb[s] = repr_comp
            else:
                self._ent_sigla_ambiguous.add(s)

        # Tokens de contexto: por document frequency entre componentes distintos.
        # Um token (>=4 chars) é "de contexto" se aparece em >= CONTEXT_TOKEN_DF_RATIO
        # dos componentes distintos. Reproduzível e derivado do corpus.
        tok = Counter()
        for c in componentes:
            for t in set(_norm(c).split()):
                if len(t) >= 4:
                    tok[t] += 1
        n_comp = len(componentes)
        if n_comp >= CONTEXT_TOKEN_MIN_COMPONENTS:
            limiar = CONTEXT_TOKEN_DF_RATIO * n_comp
            self._context_tokens = {t for t, c in tok.items() if c >= limiar}
        else:
            # Corpus pequeno: frequência não é significativa; não aplicar a guarda.
            self._context_tokens = set()

    def _build_unidade_index(self) -> None:
        """Índice de siglas de UNIDADETECNICA derivado do corpus (genérico).

        As unidades técnicas têm nomes com prefixo muito repetitivo ("Unidade de
        Auditoria Especializada em ...") e siglas distintivas entre parênteses
        (ex.: 'AudPessoal', 'AudTCE'). Por isso, a interpretação de UNIDADETECNICA é
        CONSERVADORA: apenas por SIGLA inequívoca (identidade única). O casamento
        por nome não é habilitado, por alto risco de falso positivo no prefixo
        genérico (ver docstring do módulo).
        """
        componentes: set[str] = set()
        for val in self._df["UNIDADETECNICA"].dropna().astype(str):
            for part in val.split(ENTIDADE_SEPARATOR):
                part = part.strip().rstrip(".").strip()
                if part:
                    componentes.add(part)

        sigla_to_comps: dict[str, set[str]] = {}
        for c in componentes:
            for m in re.finditer(r"\(([^)]+)\)", c):
                for s in _extract_siglas(m.group(1)):
                    sigla_to_comps.setdefault(_norm(s), set()).add(c)

        self._uni_sigla_unamb: dict[str, str] = {}
        self._uni_sigla_ambiguous: set[str] = set()
        for s, comps_s in sigla_to_comps.items():
            identidades = {_base_identity(c) for c in comps_s}
            if len(identidades) == 1:
                self._uni_sigla_unamb[s] = min(comps_s, key=lambda c: len(c))
            else:
                self._uni_sigla_ambiguous.add(s)

    # ------------------------------------------------------------------ #
    # Interpretação da consulta (genérica)
    # ------------------------------------------------------------------ #

    def interpret(self, query: str, diag: dict | None = None) -> dict:
        """Extrai condições de metadados do texto. Não acessa ficha/gold.

        `diag`, quando fornecido, recebe anotações de diagnóstico (ex.: menções de
        entidade descartadas por ambiguidade/contexto), sem afetar as condições.
        """
        qn = _norm(query)
        conditions: dict[str, object] = {}

        # COLEGIADO
        if "plenario" in qn:
            conditions["COLEGIADO"] = "Plenário"
        elif ("primeira camara" in qn) or ("1a camara" in qn) or ("1 camara" in qn):
            conditions["COLEGIADO"] = "Primeira Câmara"
        elif ("segunda camara" in qn) or ("2a camara" in qn) or ("2 camara" in qn):
            conditions["COLEGIADO"] = "Segunda Câmara"

        # TIPOPROCESSO: casa pela sigla (palavra inteira), pelo nome completo
        # (substring) ou pelo radical da primeira palavra do nome (singular/plural
        # e flexões). Em empate, prefere o nome mais específico (mais longo).
        q_stems = {_stem(tok) for tok in qn.split()}
        melhor = None  # (especificidade, canonical)
        for e in self._tipo_map:
            casou = False
            espec = 0
            if e["sigla"] and re.search(rf"\b{re.escape(e['sigla'])}\b", qn):
                casou = True
                espec = max(espec, len(e["sigla"]))
            if e["name_norm"] and e["name_norm"] in qn:
                casou = True
                espec = max(espec, len(e["name_norm"]))
            if len(e["name_stem"]) >= 5 and e["name_stem"] in q_stems:
                casou = True
                espec = max(espec, len(e["name_stem"]))
            if casou:
                cand = (espec, e["canonical"])
                if melhor is None or cand[0] > melhor[0]:
                    melhor = cand
        if melhor is not None:
            conditions["TIPOPROCESSO"] = melhor[1]

        # RELATOR: casa nome completo ou sobrenome inequívoco
        rel = self._match_relator(qn)
        if rel is not None:
            conditions["RELATOR"] = rel

        # DATASESSAO
        data = self._match_data(query, qn)
        if data is not None:
            conditions["DATASESSAO"] = data

        # ENTIDADE (genérico, com guarda de especificidade/ambiguidade)
        ent, ent_diag = self._match_entidade(query)
        if ent is not None:
            conditions["ENTIDADE"] = ent
        if diag is not None and ent_diag:
            diag["entidade"] = ent_diag

        # UNIDADETECNICA (conservador: só por sigla inequívoca)
        uni, uni_diag = self._match_unidade(query)
        if uni is not None:
            conditions["UNIDADETECNICA"] = uni
        if diag is not None and uni_diag:
            diag["unidadetecnica"] = uni_diag

        return conditions

    def _match_relator(self, qn: str) -> str | None:
        """Casa um relator citado no texto (nome completo ou sobrenome único)."""
        achados = []
        for rel in self._relatores:
            reln = _norm(rel)
            if reln in qn:
                achados.append(rel)
                continue
            # sobrenome (último token) se for inequívoco entre os relatores
            sobrenome = reln.split()[-1]
            if len(sobrenome) >= 4 and re.search(rf"\b{re.escape(sobrenome)}\b", qn):
                achados.append(rel)
        achados = sorted(set(achados))
        # só aceita se identificou exatamente um relator (evita ambiguidade)
        return achados[0] if len(achados) == 1 else None

    def _match_data(self, query: str, qn: str) -> str | None:
        """Detecta data no formato dd/mm/aaaa ou 'd de <mês> de aaaa'."""
        m = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", query)
        if m:
            return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
        m = re.search(r"\b(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})\b", qn)
        if m:
            dia = int(m.group(1)); mes = _MESES.get(m.group(2)); ano = m.group(3)
            if mes:
                return f"{dia:02d}/{mes:02d}/{ano}"
        return None

    def _is_issuing_institution(self, norm_comp: str) -> bool:
        """Verdadeiro se o componente é (essencialmente) a corte emissora do corpus.

        Nomear o órgão julgador (o TCU, autor de todos os acórdãos) não é um filtro
        de ENTIDADE discriminante nesta coleção. Fato do dataset, não lista por
        pergunta.
        """
        base = norm_comp.rstrip(". ")
        return any(base == term or term == base for term in self._issuing_terms)

    def _is_specific(self, norm_comp: str) -> bool:
        """Um componente de entidade é 'específico' se não for composto apenas por
        tokens de contexto genéricos (ex.: 'estado de', 'municipio de') e não for a
        própria corte emissora do corpus.

        Exige ao menos um token com >= 4 caracteres que NÃO esteja no conjunto de
        tokens de contexto derivado do corpus. Caso contrário, é considerado pouco
        específico (serve de contexto, não de filtro).
        """
        if self._is_issuing_institution(norm_comp):
            return False
        tokens = [t for t in norm_comp.split() if len(t) >= 4]
        if not tokens:
            return False
        return any(t not in self._context_tokens for t in tokens)

    def _match_entidade(self, query: str) -> tuple[str | None, dict]:
        """Casamento genérico de ENTIDADE com guarda de especificidade/ambiguidade.

        Procedimento (derivado do corpus, sem lista por pergunta):
        1. Siglas inequívocas entre parênteses: se uma sigla que aponta para um
           único componente aparece como palavra inteira na consulta, é um forte
           indício e casa esse componente.
        2. Nomes de componentes: casa por substring normalizada (tratando acento,
           caixa, espaços, pontuação e componentes multivalorados separados por
           ';'), exigindo comprimento mínimo e ESPECIFICIDADE (não ser só tokens
           de contexto). Em empate, vence o componente mais longo (mais específico).
        3. Guarda de ambiguidade: candidatos encontrados porém NÃO específicos são
           registrados no diagnóstico e NÃO viram filtro (ex.: menção ao órgão
           julgador 'Tribunal de Contas da União' como contexto, ou 'Estado de ...'
           genérico).

        Retorna (valor_componente | None, diagnóstico).
        """
        # _norm preserva '/', então a mesma forma normalizada serve para siglas
        # simples e com barra.
        qn = _norm(query)
        diag: dict = {}

        # 1) Sigla cuja identidade é única (inclui siglas com barra, ex.: 'Sesc/MS').
        # Casa a sigla como token delimitado (fronteira que não parte em '/').
        sigla_hits: dict[str, str] = {}  # sigla -> componente representante
        for sigla, comp in self._ent_sigla_unamb.items():
            if not _sigla_usable_in_text(sigla):
                continue
            if re.search(rf"(?<![\w/]){re.escape(sigla)}(?![\w/])", qn):
                if self._is_specific(_base_identity(comp)):
                    sigla_hits[sigla] = comp
        if sigla_hits:
            # preferir a sigla mais longa/específica citada (ex.: 'sesc/ms' > 'sesc')
            sigla_sel = max(sigla_hits, key=len)
            diag["matched_by"] = "sigla"
            diag["sigla"] = sigla_sel
            if len(sigla_hits) > 1:
                diag["other_sigla_hits"] = sorted(k for k in sigla_hits if k != sigla_sel)
            return sigla_hits[sigla_sel], diag

        # Registrar siglas ambíguas citadas (não viram filtro, mas ficam no diag).
        amb_siglas = [
            s for s in self._ent_sigla_ambiguous
            if re.search(rf"(?<![\w/]){re.escape(s)}(?![\w/])", qn)
        ]
        if amb_siglas:
            diag["ambiguous_siglas"] = sorted(amb_siglas)[:5]

        # 2) Nome de componente por substring, agrupando por IDENTIDADE.
        especificos: dict[str, str] = {}  # identidade -> texto do componente
        contexto: list[str] = []
        for comp in self._ent_components:
            base = comp["norm"]
            if len(base) < ENTIDADE_MIN_LEN:
                continue
            if base in qn:
                if self._is_specific(base) and not self._is_bare_admin_head(base):
                    ident = _base_identity(comp["text"])
                    # manter o componente mais curto por identidade (nome-base limpo)
                    if ident not in especificos or len(comp["text"]) < len(especificos[ident]):
                        especificos[ident] = comp["text"]
                else:
                    contexto.append(comp["text"])

        if len(especificos) == 1:
            (_, texto), = especificos.items()
            diag["matched_by"] = "name"
            return texto, diag

        if len(especificos) > 1:
            # Múltiplas entidades DISTINTAS: não escolher arbitrariamente.
            diag["reason"] = "multiple_distinct_entities"
            diag["distinct_candidates"] = sorted(especificos.values())[:5]
            return None, diag

        if contexto:
            # Houve menção, mas apenas pouco específica (contexto/órgão julgador/
            # cabeçalho administrativo genérico como 'Estado de X').
            diag["context_only_candidates"] = sorted(set(contexto))[:5]
            diag["reason"] = "mention_too_generic_for_filter"
        return None, diag

    def _is_bare_admin_head(self, norm_comp: str) -> bool:
        """Componente é um 'cabeçalho administrativo nu' do tipo 'estado de X' /
        'municipio de X' / 'prefeitura municipal de X', em que a primeira palavra é
        um token de contexto genérico (derivado do corpus).

        Tais menções aparecem com frequência como CONTEXTO geográfico/administrativo
        do assunto, não como a entidade jurisdicionada alvo. De forma conservadora,
        não as tratamos como filtro automático; a ambiguidade é registrada.

        Observação: isto NÃO proíbe nomes geográficos — apenas evita impor um filtro
        quando a menção é um cabeçalho genérico. Uma entidade específica cujo nome
        começa por termo administrativo mas contém outros termos distintivos ainda
        é tratada pela via normal (ver _is_specific). O teste aqui é restrito: só
        dispara quando o componente é CURTO (poucos tokens) e inicia por contexto.
        """
        tokens = norm_comp.split()
        if not tokens:
            return False
        if tokens[0] not in self._context_tokens:
            return False
        # curto: cabeçalho + no máximo um qualificador (ex.: 'estado de pernambuco')
        tokens_sig = [t for t in tokens if len(t) >= 4]
        return len(tokens_sig) <= 2

    def _match_unidade(self, query: str) -> tuple[str | None, dict]:
        """Casamento CONSERVADOR de UNIDADETECNICA: apenas por sigla inequívoca.

        O casamento por nome não é usado (prefixo genérico muito repetitivo →
        alto risco de falso positivo). Siglas (ex.: 'AudPessoal') são distintivas;
        aceitas quando apontam para uma única identidade. Siglas ambíguas ou apenas
        o nome genérico são registrados no diagnóstico, sem impor filtro.
        """
        qn = _norm(query)
        diag: dict = {}
        hits: dict[str, str] = {}
        for sigla, comp in self._uni_sigla_unamb.items():
            if not _sigla_usable_in_text(sigla):
                continue
            if re.search(rf"(?<![\w/]){re.escape(sigla)}(?![\w/])", qn):
                hits[sigla] = comp
        if hits:
            sigla_sel = max(hits, key=len)
            diag["matched_by"] = "sigla"
            diag["sigla"] = sigla_sel
            return hits[sigla_sel], diag
        amb = [
            s for s in self._uni_sigla_ambiguous
            if re.search(rf"(?<![\w/]){re.escape(s)}(?![\w/])", qn)
        ]
        if amb:
            diag["ambiguous_siglas"] = sorted(amb)[:5]
        return None, diag

    # ------------------------------------------------------------------ #
    # Recuperação
    # ------------------------------------------------------------------ #

    def retrieve(self, query: str) -> RetrievalResult:
        """Recupera o conjunto de documentos que satisfazem as condições."""
        interp_diag: dict = {}
        conditions = self.interpret(query, diag=interp_diag)
        diagnostics: dict = {
            "architecture_version": self.VERSION,
            "identified_conditions": dict(conditions),
            "interpretation_notes": interp_diag,
            "corpus_fingerprint": self._fingerprint,
            "n_corpus": int(len(self._df)),
        }

        if not conditions:
            diagnostics["no_conditions_identified"] = True
            return RetrievalResult(
                query=query,
                architecture=self.architecture_name,
                documents=[],
                fields_used=[],
                diagnostics=diagnostics,
            )

        mask = pd.Series(True, index=self._df.index)
        for campo, valor in conditions.items():
            col = self._df[campo].astype(str).str.strip()
            if campo in ("ENTIDADE", "UNIDADETECNICA"):
                # Campos multivalorados com variantes com/sem sigla entre parênteses.
                # Para capturar todas as variantes da MESMA identidade, o filtro usa
                # o NOME-BASE (sem o parêntese de sigla) como substring.
                base = _strip_paren(_norm(valor)).rstrip(". ")
                mask &= col.map(lambda x, b=base: b in _norm(x))
            else:
                mask &= (col == valor)

        sub = self._df[mask]
        doc_ids = sorted(sub["doc_id"].astype(str).tolist())  # ordem determinística

        documents = [
            RetrievedDocument(
                doc_id=did,
                rank=i + 1,
                score=None,  # filtros não têm score natural; não inventar
                evidence={"matched_conditions": dict(conditions)},
            )
            for i, did in enumerate(doc_ids)
        ]
        diagnostics["n_matched"] = len(documents)
        return RetrievalResult(
            query=query,
            architecture=self.architecture_name,
            documents=documents,
            fields_used=list(conditions.keys()),
            diagnostics=diagnostics,
        )

    # ------------------------------------------------------------------ #
    # Construção a partir da seleção congelada
    # ------------------------------------------------------------------ #

    @classmethod
    def from_selection(
        cls, parquet_path: Path, fingerprint: str | None = None
    ) -> "StructuredRetriever":
        """Carrega a seleção congelada (somente leitura) e constrói o retriever."""
        df = pd.read_parquet(parquet_path, engine="pyarrow")
        return cls(df, corpus_fingerprint=fingerprint)

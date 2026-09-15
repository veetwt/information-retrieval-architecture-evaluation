"""Utilitários de hashing para o pipeline de construção do corpus piloto.

Funções puras e sem estado para cálculo de hash de arquivos e DataFrames.
Usadas pelo Ingestor (integridade) e pelo Canonizador (fingerprint de
reprodutibilidade).
"""

import datetime
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

# Tamanho de chunk para leitura de arquivos grandes (8 MB)
CHUNK_SIZE = 8 * 1024 * 1024


def compute_sha256(path: Path) -> str:
    """Calcula SHA-256 do conteúdo binário completo do arquivo.

    Lê em chunks de 8 MB para suportar arquivos grandes.
    Retorna string hexadecimal de 64 caracteres.
    Lança IOError se o arquivo não puder ser lido.
    """
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                h.update(chunk)
    except OSError as exc:
        raise IOError(f"Não foi possível ler o arquivo '{path}': {exc}") from exc
    return h.hexdigest()


def _serialize_value(v) -> str:
    """Serialização canônica de um valor individual para o fingerprint."""
    # bool deve ser verificado ANTES de int (bool é subclasse de int no Python)
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    # pd.NA, pd.NaT e similares
    try:
        if pd.isna(v):
            return "null"
    except (TypeError, ValueError):
        pass
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, int):
        return str(int(v))
    if isinstance(v, float):
        if math.isnan(v):
            return "NaN"
        if math.isinf(v):
            return "Infinity"
        return repr(v)
    if isinstance(v, pd.Timestamp):
        # Converter para UTC, remover tzinfo e formatar com precisão de segundos
        ts = v
        if ts.tzinfo is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)
        return ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(v, datetime.datetime):
        if v.tzinfo is not None:
            import calendar
            epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
            ts_utc = v.astimezone(datetime.timezone.utc)
            v = ts_utc.replace(tzinfo=None)
        return v.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(v, datetime.date):
        return v.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(v)


def compute_dataset_fingerprint(df: pd.DataFrame, sort_col: str = "doc_id") -> str:
    """Calcula fingerprint determinístico do DataFrame incluindo schema e conteúdo.

    Algoritmo:
      1. Schema: lista ordenada de (coluna, dtype_str) → serializar como JSON
      2. Conteúdo: ordenar DataFrame por sort_col, depois pelas demais colunas
         em ordem alfabética (ordenação secundária determinística)
      3. Serializar cada linha com representação canônica dos valores
      4. SHA-256 da concatenação: schema_json + '\\n' + linha_1 + '\\n' + ... + linha_N

    Independente de: compressão do Parquet, row groups, timestamps internos,
    ordem física do arquivo, metadados específicos do writer.
    Retorna string hexadecimal de 64 caracteres.
    """
    # 1. Schema: lista ordenada de (coluna, dtype_str)
    schema = sorted([(col, str(df[col].dtype)) for col in df.columns])
    schema_json = json.dumps(schema, ensure_ascii=False)

    # 2. Ordenar por sort_col, depois pelas demais colunas em ordem alfabética
    cols = list(df.columns)
    sort_keys = []
    if sort_col in cols:
        sort_keys.append(sort_col)
    # demais colunas em ordem alfabética
    sort_keys += sorted(c for c in cols if c != sort_col)

    if sort_keys:
        df_sorted = df.sort_values(by=sort_keys, kind="mergesort", na_position="first")
    else:
        df_sorted = df

    # 3. Serializar cada linha
    linhas = []
    for row in df_sorted.itertuples(index=False, name=None):
        row_dict = {
            col: _serialize_value(val)
            for col, val in zip(cols, row)
        }
        linha_json = json.dumps(row_dict, sort_keys=True, ensure_ascii=False)
        linhas.append(linha_json)

    # 4. SHA-256 da concatenação
    conteudo = schema_json + "\n" + "\n".join(linhas)
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()

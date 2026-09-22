"""Auditor — cálculo de métricas de qualidade do corpus bruto.

Responsabilidades:
- Verificar bloqueio por pending.jsonl (PendingManifestError) antes de qualquer análise.
- Validar proveniência e integridade do arquivo em data/raw/ (ProvenanceError).
- Calcular análises estruturais (sempre presentes) e condicionais (quando os campos
  correspondentes estiverem configurados no Config_File e presentes no dataset).
- Persistir os 5 relatórios obrigatórios em reports/corpus/.

O Auditor nunca modifica data/raw/. Análises não executadas são explicitamente marcadas
com FieldAnalysisStatus (NOT_CONFIGURED / FIELD_MISSING); nunca representadas por 0.

Suporte a campos CSV grandes:
    O CSV bruto do TCU contém campos textuais muito extensos (ex: INTEIROTEOR, VOTO).
    O parser padrão do módulo csv da stdlib possui um limite de tamanho de campo
    (csv.field_size_limit) que pode ser menor que campos reais do dataset, causando
    `_csv.Error: field larger than field limit`. O pandas usa seu próprio parser, mas
    para robustez o Auditor eleva o limite de forma segura e reversível durante a
    leitura (ver _read_csv). O limite é elevado para um valor grande derivado de
    sys.maxsize com fallback progressivo, evitando OverflowError em plataformas de 64
    bits onde sys.maxsize excede o limite de C long.
"""

from __future__ import annotations

import csv
import datetime
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import ClassVar

import pandas as pd

try:
    from data.config import CorpusConfig
    from data.manifest import ManifestWriter
except ImportError:
    from .config import CorpusConfig
    from .manifest import ManifestWriter


class PendingManifestError(Exception):
    """Levantada quando pending.jsonl contém entradas não consolidadas.

    Bloqueia a auditoria: nenhuma análise é executada e nenhum relatório é produzido.
    A resolução é manual e auditável pelo pesquisador.
    """


class ProvenanceError(Exception):
    """Levantada quando a proveniência/integridade do arquivo é inválida.

    O motivo ("provenance_missing" ou "integrity_mismatch") fica disponível no
    atributo `reason`. Nenhum relatório é produzido quando levantada.
    """

    def __init__(self, reason: str, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason)


class FieldAnalysisStatus(str, Enum):
    """Status discriminado de uma análise condicional."""

    NOT_CONFIGURED = "not_configured"  # campo não existe no Config_File
    FIELD_MISSING = "field_missing"    # campo configurado mas não encontrado no dataset
    OK = "ok"                          # análise executada com sucesso


@dataclass
class ConditionalAnalysis:
    """Resultado de uma análise condicional, com status explícito.

    `result` é None sempre que `status != OK`. Nunca usar 0 para representar
    análise não executada (0 significa zero ocorrências encontradas).
    """

    status: FieldAnalysisStatus
    result: dict | list | int | None = None  # None quando status != OK


@dataclass
class AuditResult:
    """Resultado consolidado da auditoria de um corpus bruto."""

    # --- Análises estruturais (sempre presentes) ---
    n_rows: int
    n_cols: int
    column_names: list[str]
    column_types: dict[str, str]
    missing_counts: dict[str, int]
    coverage_pct: dict[str, float]           # valores em [0.00, 100.00]
    unique_counts: dict[str, int]
    audit_timestamp: str                      # ISO 8601 UTC
    auditor_version: str
    source_file: str

    # --- Análises condicionais com status discriminado ---
    duplicates_analysis: ConditionalAnalysis
    text_length_analysis: ConditionalAnalysis
    docs_without_text: ConditionalAnalysis
    metadata_coverage: ConditionalAnalysis

    # --- Registro separado de inconsistências de configuração ---
    config_inconsistencies: list[str] = field(default_factory=list)


class Auditor:
    """Cálculo e persistência de métricas de qualidade do corpus bruto."""

    VERSION: ClassVar[str] = "1.0.0"

    # Nomes dos 5 relatórios obrigatórios.
    REPORT_FILENAMES: ClassVar[dict[str, str]] = {
        "raw_summary": "raw_summary.json",
        "column_profile": "column_profile.csv",
        "text_length_profile": "text_length_profile.csv",
        "sample_records": "sample_records.csv",
        "audit_report": "audit_report.md",
    }

    SAMPLE_SEED: ClassVar[int] = 42
    SAMPLE_SIZE: ClassVar[int] = 20

    def __init__(self, config: CorpusConfig, manifest: ManifestWriter) -> None:
        """Inicializa com a configuração do pipeline e o ManifestWriter."""
        self._config = config
        self._manifest = manifest

    # ------------------------------------------------------------------ #
    # Leitura segura de CSV grande
    # ------------------------------------------------------------------ #

    @staticmethod
    def _raise_csv_field_size_limit() -> int:
        """Eleva csv.field_size_limit ao maior valor aceito pela plataforma.

        Campos textuais do corpus TCU (ex: INTEIROTEOR, VOTO) podem exceder o
        limite padrão do módulo csv. sys.maxsize pode exceder o limite de C long
        em algumas plataformas, causando OverflowError; por isso reduzimos
        progressivamente (fator 10) até um valor aceito.

        Retorna o limite anterior para permitir restauração posterior.
        """
        previous = csv.field_size_limit()
        novo_limite = sys.maxsize
        while True:
            try:
                csv.field_size_limit(novo_limite)
                break
            except OverflowError:
                novo_limite = int(novo_limite // 10)
                if novo_limite <= previous:
                    # Não conseguimos ampliar além do valor atual; manter o anterior.
                    csv.field_size_limit(previous)
                    break
        return previous

    @staticmethod
    def _detect_delimiter(corpus_path: Path) -> str:
        """Detecta o delimitador do CSV a partir da primeira linha (cabeçalho).

        Datasets públicos do TCU usam '|' como separador; outros usam ','.
        Usa csv.Sniffer sobre o cabeçalho, restringindo aos delimitadores
        plausíveis. Em caso de falha de detecção, retorna ',' (padrão do CSV).
        Não modifica o arquivo; apenas lê o início para inspeção.
        """
        try:
            with open(corpus_path, encoding="utf-8", errors="replace", newline="") as f:
                amostra = f.readline()
            if not amostra:
                return ","
            dialect = csv.Sniffer().sniff(amostra, delimiters="|,;\t")
            return dialect.delimiter
        except (csv.Error, OSError):
            return ","

    def _read_csv(self, corpus_path: Path) -> pd.DataFrame:
        """Lê o CSV para um DataFrame com suporte a campos grandes.

        Eleva csv.field_size_limit de forma reversível durante a leitura e o
        restaura ao final (mesmo em caso de exceção). Usa o engine "python" do
        pandas, que respeita csv.field_size_limit, garantindo leitura de campos
        textuais extensos sem truncamento nem erro.

        O delimitador é detectado automaticamente (csv.Sniffer), pois o dataset
        do TCU usa '|' enquanto outros usam ','. Aspas duplas embutidas ("")
        dentro de campos entre aspas são tratadas pela convenção padrão do CSV.

        Lê todas as colunas como string (dtype=str) para preservar os valores
        originais sem inferência ou coerção de tipo, alinhado à política do
        pipeline de nunca inferir ou normalizar valores. Valores ausentes são
        mantidos como pd.NA (sem conversão para NaN de ponto flutuante).
        """
        delimiter = self._detect_delimiter(corpus_path)
        limite_anterior = self._raise_csv_field_size_limit()
        try:
            df = pd.read_csv(
                corpus_path,
                sep=delimiter,
                dtype=str,
                keep_default_na=True,
                na_values=[],
                engine="python",
            )
        finally:
            csv.field_size_limit(limite_anterior)
        return df

    # ------------------------------------------------------------------ #
    # Execução da auditoria
    # ------------------------------------------------------------------ #

    def run(self, corpus_path: Path) -> AuditResult:
        """Executa a auditoria completa sobre o arquivo em data/raw/.

        Ordem obrigatória de verificações:
        1. has_pending_entries() → PendingManifestError se True (nenhuma análise).
        2. Existência/legibilidade do arquivo → FileNotFoundError.
        3. validate_file_provenance() → ProvenanceError (provenance_missing /
           integrity_mismatch) antes de qualquer leitura do dataset.
        4. Análises estruturais (sempre) + condicionais (quando configuradas e
           presentes no dataset).
        """
        # 1. Bloqueio por pending.jsonl
        if self._manifest.has_pending_entries():
            raise PendingManifestError(
                "pending.jsonl contém entradas não consolidadas no Manifest. "
                "Nenhuma auditoria será executada até resolução manual."
            )

        # 2. Existência do arquivo
        if not corpus_path.exists() or not corpus_path.is_file():
            raise FileNotFoundError(
                f"Corpus não encontrado ou ilegível: '{corpus_path}'"
            )

        # 3. Proveniência e integridade
        stored_filename = corpus_path.name
        raw_dir = corpus_path.parent
        valido, motivo = self._manifest.validate_file_provenance(stored_filename, raw_dir)
        if not valido:
            if motivo == "integrity_mismatch":
                raise ProvenanceError(
                    "integrity_mismatch",
                    f"SHA-256 atual de '{stored_filename}' diverge do registrado no Manifest.",
                )
            # provenance_missing ou file_not_found → tratados como provenância ausente
            raise ProvenanceError(
                "provenance_missing",
                f"Arquivo '{stored_filename}' não possui entrada válida no Manifest "
                f"(motivo: {motivo}).",
            )

        # 4. Leitura do dataset (com suporte a campos grandes)
        df = self._read_csv(corpus_path)

        columns = list(df.columns)
        n_rows = int(len(df))
        n_cols = int(len(columns))

        column_types = {col: str(df[col].dtype) for col in columns}
        missing_counts = self._compute_missing_counts(df)
        coverage_pct = self._compute_coverage_pct(df, missing_counts, n_rows)
        unique_counts = {col: int(df[col].nunique(dropna=True)) for col in columns}

        config_inconsistencies: list[str] = []

        duplicates_analysis = self._analyze_duplicates(df, config_inconsistencies)
        text_length_analysis = self._analyze_text_length(df, config_inconsistencies)
        docs_without_text = self._analyze_docs_without_text(df, config_inconsistencies)
        metadata_coverage = self._analyze_metadata_coverage(df, n_rows, config_inconsistencies)

        return AuditResult(
            n_rows=n_rows,
            n_cols=n_cols,
            column_names=columns,
            column_types=column_types,
            missing_counts=missing_counts,
            coverage_pct=coverage_pct,
            unique_counts=unique_counts,
            audit_timestamp=self._now_iso(),
            auditor_version=self.VERSION,
            source_file=stored_filename,
            duplicates_analysis=duplicates_analysis,
            text_length_analysis=text_length_analysis,
            docs_without_text=docs_without_text,
            metadata_coverage=metadata_coverage,
            config_inconsistencies=config_inconsistencies,
        )

    # ------------------------------------------------------------------ #
    # Análises estruturais
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_blank_series(series: pd.Series) -> pd.Series:
        """Retorna máscara booleana de valores "ausentes" para cobertura.

        Um valor é considerado ausente quando é nulo (pd.NA/None/NaN) OU quando,
        tratado como texto, contém apenas espaços em branco (inclui "", " ",
        "\\t", "\\n" e combinações). Alinhado à Property 9.
        """
        is_null = series.isna()
        # Converter para string apenas os não nulos; nulos permanecem marcados.
        stripped = series.astype("string").str.strip()
        is_empty = stripped.eq("")
        return is_null | is_empty.fillna(True)

    def _compute_missing_counts(self, df: pd.DataFrame) -> dict[str, int]:
        """Contagem de valores ausentes por coluna (nulo ou apenas espaços)."""
        return {
            col: int(self._is_blank_series(df[col]).sum())
            for col in df.columns
        }

    def _compute_coverage_pct(
        self, df: pd.DataFrame, missing_counts: dict[str, int], n_rows: int
    ) -> dict[str, float]:
        """Percentual de cobertura por coluna, em [0.00, 100.00], 2 casas.

        cobertura = presentes / total * 100. Se n_rows == 0, cobertura = 0.00
        (não há registros presentes).
        """
        coverage: dict[str, float] = {}
        for col in df.columns:
            if n_rows == 0:
                coverage[col] = 0.00
                continue
            presentes = n_rows - missing_counts[col]
            pct = round(presentes / n_rows * 100.0, 2)
            # Salvaguarda numérica para o intervalo [0.00, 100.00]
            pct = max(0.00, min(100.00, pct))
            coverage[col] = pct
        return coverage

    # ------------------------------------------------------------------ #
    # Análises condicionais
    # ------------------------------------------------------------------ #

    def _analyze_duplicates(
        self, df: pd.DataFrame, config_inconsistencies: list[str]
    ) -> ConditionalAnalysis:
        """Número de registros duplicados por primary_key_field (N-1 por grupo).

        Contabiliza como duplicatas N-1 registros de cada grupo de N registros
        com identificador idêntico. Valores nulos do identificador não são
        contabilizados como grupo de duplicatas.
        """
        pk = self._config.primary_key_field
        if pk is None:
            return ConditionalAnalysis(status=FieldAnalysisStatus.NOT_CONFIGURED)
        if pk not in df.columns:
            config_inconsistencies.append(
                f"primary_key_field '{pk}' configurado mas ausente no dataset"
            )
            return ConditionalAnalysis(status=FieldAnalysisStatus.FIELD_MISSING)

        serie = df[pk]
        nao_nulos = serie[~serie.isna()]
        # Total de duplicatas = total de registros não nulos - número de grupos distintos.
        n_grupos = int(nao_nulos.nunique(dropna=True))
        n_duplicatas = int(len(nao_nulos) - n_grupos)
        return ConditionalAnalysis(status=FieldAnalysisStatus.OK, result=n_duplicatas)

    def _analyze_text_length(
        self, df: pd.DataFrame, config_inconsistencies: list[str]
    ) -> ConditionalAnalysis:
        """Distribuição do tamanho (nº de caracteres) do campo de texto completo.

        Métricas: min, max, mean (2 casas), median (2 casas), p25, p75.
        O comprimento é medido sobre o valor textual; valores nulos são
        excluídos do cálculo de distribuição.
        """
        tf = self._config.text_field
        if tf is None:
            return ConditionalAnalysis(status=FieldAnalysisStatus.NOT_CONFIGURED)
        if tf not in df.columns:
            config_inconsistencies.append(
                f"text_field '{tf}' configurado mas ausente no dataset"
            )
            return ConditionalAnalysis(status=FieldAnalysisStatus.FIELD_MISSING)

        serie = df[tf]
        comprimentos = serie.dropna().astype("string").str.len().dropna()

        if len(comprimentos) == 0:
            resultado = {
                "count": 0,
                "min": None,
                "max": None,
                "mean": None,
                "median": None,
                "p25": None,
                "p75": None,
            }
            return ConditionalAnalysis(status=FieldAnalysisStatus.OK, result=resultado)

        resultado = {
            "count": int(len(comprimentos)),
            "min": int(comprimentos.min()),
            "max": int(comprimentos.max()),
            "mean": round(float(comprimentos.mean()), 2),
            "median": round(float(comprimentos.median()), 2),
            "p25": round(float(comprimentos.quantile(0.25)), 2),
            "p75": round(float(comprimentos.quantile(0.75)), 2),
        }
        return ConditionalAnalysis(status=FieldAnalysisStatus.OK, result=resultado)

    def _analyze_docs_without_text(
        self, df: pd.DataFrame, config_inconsistencies: list[str]
    ) -> ConditionalAnalysis:
        """Contagem e lista de Documentos_Sem_Texto (nulo, vazio ou só espaços).

        Retorna dict com 'count' e 'row_indices' (índices de linha, base 0)
        dos documentos sem texto. Depende de text_field configurado.
        """
        tf = self._config.text_field
        if tf is None:
            return ConditionalAnalysis(status=FieldAnalysisStatus.NOT_CONFIGURED)
        if tf not in df.columns:
            config_inconsistencies.append(
                f"text_field '{tf}' configurado mas ausente no dataset"
            )
            return ConditionalAnalysis(status=FieldAnalysisStatus.FIELD_MISSING)

        blank_mask = self._is_blank_series(df[tf])
        indices = [int(i) for i in df.index[blank_mask].tolist()]
        resultado = {
            "count": int(len(indices)),
            "row_indices": indices,
        }
        return ConditionalAnalysis(status=FieldAnalysisStatus.OK, result=resultado)

    def _analyze_metadata_coverage(
        self, df: pd.DataFrame, n_rows: int, config_inconsistencies: list[str]
    ) -> ConditionalAnalysis:
        """Cobertura (% preenchido) de cada campo declarado em metadata_fields.

        Preenchido = não nulo, não vazio e não composto apenas por espaços.
        Campos configurados mas ausentes no dataset são registrados em
        config_inconsistencies e omitidos do resultado; os presentes são
        analisados normalmente.
        """
        mf = self._config.metadata_fields
        if not mf:  # None ou lista vazia
            return ConditionalAnalysis(status=FieldAnalysisStatus.NOT_CONFIGURED)

        presentes = [c for c in mf if c in df.columns]
        ausentes = [c for c in mf if c not in df.columns]
        for c in ausentes:
            config_inconsistencies.append(
                f"metadata_field '{c}' configurado mas ausente no dataset"
            )

        if not presentes:
            # Todos os campos configurados estão ausentes no dataset.
            return ConditionalAnalysis(status=FieldAnalysisStatus.FIELD_MISSING)

        cobertura: dict[str, float] = {}
        for col in presentes:
            if n_rows == 0:
                cobertura[col] = 0.00
                continue
            ausentes_col = int(self._is_blank_series(df[col]).sum())
            pct = round((n_rows - ausentes_col) / n_rows * 100.0, 2)
            pct = max(0.00, min(100.00, pct))
            cobertura[col] = pct

        resultado = {"coverage_pct": cobertura, "omitted_fields": ausentes}
        return ConditionalAnalysis(status=FieldAnalysisStatus.OK, result=resultado)

    # ------------------------------------------------------------------ #
    # Persistência dos relatórios
    # ------------------------------------------------------------------ #

    def save_reports(self, result: AuditResult, reports_dir: Path) -> dict[str, Path]:
        """Salva os 5 relatórios obrigatórios em reports_dir.

        - Todos os 5 arquivos são sempre produzidos.
        - Análises NOT_CONFIGURED / FIELD_MISSING são indicadas explicitamente;
          nunca representadas por 0.
        - sample_records.csv: amostra determinística (seed=42) de até 20 registros,
          relida do próprio arquivo auditado no momento da persistência.
        - Sufixo YYYYMMDDTHHMMSSZ quando o nome já existir (nenhuma sobrescrita).
        - Cria o diretório se não existir.
        - Lança OSError se a escrita falhar.
        """
        try:
            reports_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OSError(
                f"Falha ao criar diretório de relatórios '{reports_dir}': {exc}"
            ) from exc

        paths = {
            key: self._resolve_report_path(reports_dir, filename)
            for key, filename in self.REPORT_FILENAMES.items()
        }

        try:
            self._write_raw_summary(result, paths["raw_summary"])
            self._write_column_profile(result, paths["column_profile"])
            self._write_text_length_profile(result, paths["text_length_profile"])
            self._write_sample_records(result, paths["sample_records"])
            self._write_audit_report(result, paths["audit_report"])
        except OSError as exc:
            raise OSError(
                f"Falha ao gravar relatório de auditoria em '{reports_dir}': {exc}"
            ) from exc

        return paths

    def _resolve_report_path(self, reports_dir: Path, filename: str) -> Path:
        """Resolve o caminho do relatório, evitando sobrescrita com sufixo de timestamp."""
        candidato = reports_dir / filename
        if not candidato.exists():
            return candidato
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        timestamp = self._now_compact()
        return reports_dir / f"{stem}_{timestamp}{suffix}"

    # ---- Escritores individuais ----

    def _write_raw_summary(self, result: AuditResult, path: Path) -> None:
        """raw_summary.json — totais gerais e status das análises condicionais."""
        summary = {
            "n_rows": result.n_rows,
            "n_cols": result.n_cols,
            "column_names": result.column_names,
            "audit_timestamp": result.audit_timestamp,
            "auditor_version": result.auditor_version,
            "source_file": result.source_file,
            "duplicates_analysis": self._conditional_to_json(result.duplicates_analysis),
            "text_length_analysis": self._conditional_to_json(result.text_length_analysis),
            "docs_without_text": self._conditional_to_json(result.docs_without_text),
            "metadata_coverage": self._conditional_to_json(result.metadata_coverage),
            "config_inconsistencies": result.config_inconsistencies,
        }
        path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _conditional_to_json(analysis: ConditionalAnalysis) -> dict:
        """Serializa uma análise condicional com status explícito.

        `result` só aparece quando status == OK. Para NOT_CONFIGURED / FIELD_MISSING,
        result é null (nunca 0).
        """
        return {
            "status": analysis.status.value,
            "result": analysis.result if analysis.status == FieldAnalysisStatus.OK else None,
        }

    def _write_column_profile(self, result: AuditResult, path: Path) -> None:
        """column_profile.csv — por coluna: nome, tipo, ausentes, cobertura%, únicos."""
        linhas = [
            {
                "column": col,
                "dtype": result.column_types.get(col, ""),
                "missing_count": result.missing_counts.get(col, 0),
                "coverage_pct": result.coverage_pct.get(col, 0.00),
                "unique_count": result.unique_counts.get(col, 0),
            }
            for col in result.column_names
        ]
        df = pd.DataFrame(
            linhas,
            columns=["column", "dtype", "missing_count", "coverage_pct", "unique_count"],
        )
        df.to_csv(path, index=False)

    def _write_text_length_profile(self, result: AuditResult, path: Path) -> None:
        """text_length_profile.csv — distribuição de tamanho do texto ou status explícito."""
        analysis = result.text_length_analysis
        if analysis.status != FieldAnalysisStatus.OK:
            df = pd.DataFrame(
                [
                    {
                        "status": analysis.status.value,
                        "count": None,
                        "min": None,
                        "max": None,
                        "mean": None,
                        "median": None,
                        "p25": None,
                        "p75": None,
                    }
                ]
            )
        else:
            r = analysis.result or {}
            df = pd.DataFrame(
                [
                    {
                        "status": FieldAnalysisStatus.OK.value,
                        "count": r.get("count"),
                        "min": r.get("min"),
                        "max": r.get("max"),
                        "mean": r.get("mean"),
                        "median": r.get("median"),
                        "p25": r.get("p25"),
                        "p75": r.get("p75"),
                    }
                ]
            )
        df.to_csv(path, index=False)

    def _write_sample_records(self, result: AuditResult, path: Path) -> None:
        """sample_records.csv — amostra determinística (seed=42) de até 20 registros.

        A amostra é relida diretamente do arquivo auditado (não é armazenada em
        AuditResult). Se o dataset estiver vazio, grava apenas o header (zero linhas).
        """
        # Reconstruir o caminho do arquivo auditado a partir da config.
        raw_dir = Path(self._config.raw_dir)
        corpus_path = raw_dir / result.source_file

        try:
            df = self._read_csv(corpus_path)
        except (OSError, FileNotFoundError):
            # Fallback defensivo: header vazio com as colunas conhecidas.
            df = pd.DataFrame(columns=result.column_names)

        if len(df) == 0:
            # Header apenas, zero linhas de dados.
            pd.DataFrame(columns=list(df.columns)).to_csv(path, index=False)
            return

        n = min(self.SAMPLE_SIZE, len(df))
        amostra = df.sample(n=n, random_state=self.SAMPLE_SEED)
        amostra.to_csv(path, index=False)

    def _write_audit_report(self, result: AuditResult, path: Path) -> None:
        """audit_report.md — relatório narrativo consolidado."""
        linhas: list[str] = []
        linhas.append("# Relatório de Auditoria do Corpus")
        linhas.append("")
        linhas.append(f"- **Arquivo auditado:** `{result.source_file}`")
        linhas.append(f"- **Timestamp (UTC):** {result.audit_timestamp}")
        linhas.append(f"- **Versão do Auditor:** {result.auditor_version}")
        linhas.append("")
        linhas.append("## Visão geral")
        linhas.append("")
        linhas.append(f"- Total de linhas: **{result.n_rows}**")
        linhas.append(f"- Total de colunas: **{result.n_cols}**")
        linhas.append("")
        linhas.append("## Perfil por coluna")
        linhas.append("")
        linhas.append("| Coluna | Tipo | Ausentes | Cobertura % | Únicos |")
        linhas.append("|---|---|---|---|---|")
        for col in result.column_names:
            linhas.append(
                f"| {col} | {result.column_types.get(col, '')} "
                f"| {result.missing_counts.get(col, 0)} "
                f"| {result.coverage_pct.get(col, 0.00):.2f} "
                f"| {result.unique_counts.get(col, 0)} |"
            )
        linhas.append("")
        linhas.append("## Análises condicionais")
        linhas.append("")
        linhas.append(self._duplicates_md(result.duplicates_analysis))
        linhas.append("")
        linhas.append(self._text_length_md(result.text_length_analysis))
        linhas.append("")
        linhas.append(self._docs_without_text_md(result.docs_without_text))
        linhas.append("")
        linhas.append(self._metadata_coverage_md(result.metadata_coverage))
        linhas.append("")
        if result.config_inconsistencies:
            linhas.append("## Inconsistências de configuração")
            linhas.append("")
            for item in result.config_inconsistencies:
                linhas.append(f"- {item}")
            linhas.append("")

        path.write_text("\n".join(linhas), encoding="utf-8")

    # ---- Fragmentos narrativos ----

    @staticmethod
    def _status_frase(status: FieldAnalysisStatus) -> str:
        if status == FieldAnalysisStatus.NOT_CONFIGURED:
            return "Análise não executada: campo não configurado no Config_File."
        if status == FieldAnalysisStatus.FIELD_MISSING:
            return "Análise não executada: campo configurado mas ausente no dataset."
        return ""

    def _duplicates_md(self, analysis: ConditionalAnalysis) -> str:
        titulo = "### Duplicatas por identificador primário"
        if analysis.status != FieldAnalysisStatus.OK:
            return f"{titulo}\n\n{self._status_frase(analysis.status)}"
        return f"{titulo}\n\n- Registros duplicados (N-1 por grupo): **{analysis.result}**"

    def _text_length_md(self, analysis: ConditionalAnalysis) -> str:
        titulo = "### Distribuição do tamanho do texto"
        if analysis.status != FieldAnalysisStatus.OK:
            return f"{titulo}\n\n{self._status_frase(analysis.status)}"
        r = analysis.result or {}
        return (
            f"{titulo}\n\n"
            f"- Contagem: {r.get('count')}\n"
            f"- Mínimo: {r.get('min')}\n"
            f"- Máximo: {r.get('max')}\n"
            f"- Média: {r.get('mean')}\n"
            f"- Mediana: {r.get('median')}\n"
            f"- P25: {r.get('p25')}\n"
            f"- P75: {r.get('p75')}"
        )

    def _docs_without_text_md(self, analysis: ConditionalAnalysis) -> str:
        titulo = "### Documentos sem texto"
        if analysis.status != FieldAnalysisStatus.OK:
            return f"{titulo}\n\n{self._status_frase(analysis.status)}"
        r = analysis.result or {}
        return f"{titulo}\n\n- Total de documentos sem texto: **{r.get('count')}**"

    def _metadata_coverage_md(self, analysis: ConditionalAnalysis) -> str:
        titulo = "### Cobertura de campos de metadados"
        if analysis.status != FieldAnalysisStatus.OK:
            return f"{titulo}\n\n{self._status_frase(analysis.status)}"
        r = analysis.result or {}
        cobertura = r.get("coverage_pct", {})
        partes = [titulo, ""]
        partes.append("| Campo | Cobertura % |")
        partes.append("|---|---|")
        for campo, pct in cobertura.items():
            partes.append(f"| {campo} | {pct:.2f} |")
        omitidos = r.get("omitted_fields") or []
        if omitidos:
            partes.append("")
            partes.append(f"Campos omitidos (ausentes no dataset): {', '.join(omitidos)}")
        return "\n".join(partes)

    # ------------------------------------------------------------------ #
    # Utilitários de tempo
    # ------------------------------------------------------------------ #

    @staticmethod
    def _now_iso() -> str:
        """Timestamp atual em ISO 8601 UTC com precisão de segundos."""
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _now_compact() -> str:
        """Timestamp compacto YYYYMMDDTHHMMSSZ para sufixo anti-sobrescrita."""
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

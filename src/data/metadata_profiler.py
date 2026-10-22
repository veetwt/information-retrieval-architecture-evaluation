"""MetadataProfiler — auditoria exploratória (somente leitura) dos metadados
da Selecao_Experimental.

Objetivo
--------
Transformar a análise exploratória temporária dos seis campos de metadados em
uma evidência documentada e reproduzível para o TCC, sem modificar o corpus.

O que este módulo faz:
- Lê o Parquet da Selecao_Experimental em modo SOMENTE LEITURA.
- Verifica, quando o manifesto está disponível, se o ``selection_fingerprint``
  recalculado sobre o DataFrame reproduz o valor registrado na seleção (usando a
  mesma função de fingerprint do SeletorExperimental), garantindo que o perfil se
  refere exatamente à seleção congelada.
- Perfila cada campo declarado em ``metadata_fields`` no Config_File, distinguindo
  explicitamente valores brutos, nulos, vazios/só-espaços e normalizados.
- Sinaliza campos multivalorados (separador ``;``) e o outlier de RELATOR,
  sem alterar, inferir ou excluir qualquer registro.
- Renderiza um relatório Markdown determinístico para ``reports/corpus/``.

O que este módulo NÃO faz (fronteiras de escopo):
- Não modifica o Parquet, o CSV, os manifestos ou os critérios de elegibilidade.
- Não escolhe campos, filtros nem estratégia de normalização para uso experimental.
  A normalização aqui é apenas DIAGNÓSTICA, para dimensionar inconsistências de
  formatação; nunca é persistida no corpus.
- Não implementa nenhuma arquitetura de recuperação.

Convenções reaproveitadas do pipeline existente:
- "Ausente" = nulo (None/NaN/pd.NA) OU texto que, após strip, fica vazio
  (mesma semântica de ``Auditor._is_blank_series``).
- Cobertura em [0.00, 100.00], arredondada a 2 casas.
- ``compute_dataset_fingerprint`` (src/utils/hashing.py) para o fingerprint.
"""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

try:
    from utils.hashing import compute_dataset_fingerprint
except ImportError:  # pragma: no cover - alternância de contexto de import
    from ..utils.hashing import compute_dataset_fingerprint


# Separador de múltiplos valores observado em ENTIDADE/UNIDADETECNICA.
MULTIVALUE_SEPARATOR = ";"

# Limite de frequência para sinalizar um valor como "raro" (outlier) em campos
# de baixa cardinalidade como RELATOR. É um limiar DIAGNÓSTICO de inspeção, não
# um parâmetro experimental: apenas destaca valores que merecem verificação
# manual. O corpus nunca é alterado por causa dele.
RARE_VALUE_MAX_COUNT = 1

# Quantidade de valores mais frequentes exibidos como exemplos por campo.
TOP_VALUES_LIMIT = 15

# Teto de valores raros EXIBIDOS por campo no relatório. Em campos de alta
# cardinalidade (ex.: ENTIDADE) os singletons chegam às centenas; listar todos
# seria ruído. O total é sempre informado; apenas a exibição é limitada.
RARE_VALUES_DISPLAY_LIMIT = 20


@dataclass
class FieldProfile:
    """Perfil diagnóstico de um único campo de metadado.

    As contagens distinguem explicitamente, para total rastreabilidade:
    - ``null_count``: valores nulos (None/NaN/pd.NA).
    - ``empty_count``: não nulos que ficam vazios após strip (vazio ou só-espaços).
    - ``missing_count``: null_count + empty_count (critério de "ausente").
    - ``distinct_raw``: distintos sobre o valor ORIGINAL (sem qualquer strip) dos
      presentes; variações de espaço nas bordas/caixa/ponto contam como distintas.
    - ``distinct_normalized``: distintos após normalização diagnóstica (strip +
      colapso de espaços + remoção de ponto final + casefold).
    """

    name: str
    dtype: str
    n_total: int
    null_count: int
    empty_count: int
    distinct_raw: int
    distinct_normalized: int
    coverage_pct: float
    leading_trailing_ws_count: int
    trailing_dot_count: int
    multivalue_count: int
    top_values: list[tuple[str, int]]
    rare_values: list[tuple[str, int]]      # amostra limitada para exibição
    rare_values_total: int                   # total de valores raros (sem corte)

    @property
    def missing_count(self) -> int:
        return self.null_count + self.empty_count

    @property
    def missing_pct(self) -> float:
        if self.n_total == 0:
            return 0.00
        return round(self.missing_count / self.n_total * 100.0, 2)


@dataclass
class MetadataAuditResult:
    """Resultado consolidado da auditoria de metadados da seleção."""

    source_parquet: str
    n_documents: int
    metadata_fields: list[str]
    profiles: list[FieldProfile]
    audit_timestamp: str
    profiler_version: str
    fingerprint_recomputed: str
    fingerprint_expected: str | None
    fingerprint_matches: bool | None
    config_version: str | None
    eligibility_policy_version: str | None
    config_inconsistencies: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Funções puras de perfil (testáveis isoladamente)
# --------------------------------------------------------------------------- #

_WS_RE = re.compile(r"\s+")


def normalize_for_diagnostic(value: str) -> str:
    """Normalização APENAS diagnóstica de um valor textual.

    Passos: strip → colapso de espaços internos → remoção de ponto final →
    casefold. Usada exclusivamente para DIMENSIONAR inconsistências de
    formatação (quantos distintos colapsam). O valor normalizado nunca é
    persistido no corpus nem usado como filtro experimental.
    """
    collapsed = _WS_RE.sub(" ", value.strip())
    collapsed = collapsed.rstrip(".")
    return collapsed.casefold()


def profile_field(
    series: pd.Series,
    name: str,
    n_total: int,
    *,
    multivalue_separator: str = MULTIVALUE_SEPARATOR,
    rare_value_max_count: int = RARE_VALUE_MAX_COUNT,
    top_values_limit: int = TOP_VALUES_LIMIT,
    rare_values_display_limit: int = RARE_VALUES_DISPLAY_LIMIT,
) -> FieldProfile:
    """Calcula o perfil diagnóstico de um campo a partir de sua Series.

    Nunca modifica a Series de entrada. Distingue nulo, vazio/só-espaços, bruto
    e normalizado. Não altera nem remove registros do corpus.
    """
    dtype = str(series.dtype)
    null_count = int(series.isna().sum())

    nonnull = series.dropna()
    nonnull_str = nonnull.astype(str)
    stripped = nonnull_str.str.strip()

    empty_count = int((stripped == "").sum())

    # "Presentes" = não nulos e não vazios/só-espaços.
    present_mask = stripped != ""
    # BRUTO = valor ORIGINAL (sem strip) dos presentes. Variações de espaço nas
    # bordas contam como distintas — é justamente o ruído que queremos medir.
    raw_present = nonnull_str[present_mask]
    # Versão só com strip, usada apenas para ponto final e separador (não para
    # contar distintos brutos).
    stripped_present = stripped[present_mask]

    distinct_raw = int(raw_present.nunique())

    normalized = stripped_present.map(normalize_for_diagnostic)
    distinct_normalized = int(normalized.nunique())

    # Espaço inicial/final no valor ORIGINAL (não nulo).
    leading_trailing_ws_count = int((nonnull_str != nonnull_str.str.strip()).sum())
    # Ponto final no valor (após strip), entre os presentes.
    trailing_dot_count = int(stripped_present.str.endswith(".").sum())
    # Valores multivalorados (contêm o separador declarado).
    multivalue_count = int(
        stripped_present.str.contains(re.escape(multivalue_separator)).sum()
    )

    # Frequências e exemplos sobre o valor BRUTO (original) dos presentes.
    counts = raw_present.value_counts()
    top_values = [(str(v), int(c)) for v, c in counts.head(top_values_limit).items()]
    all_rare = [
        (str(v), int(c))
        for v, c in counts.items()
        if int(c) <= rare_value_max_count
    ]
    rare_values_total = len(all_rare)
    rare_values = all_rare[:rare_values_display_limit]

    present = n_total - (null_count + empty_count)
    coverage_pct = 0.00 if n_total == 0 else round(present / n_total * 100.0, 2)
    coverage_pct = max(0.00, min(100.00, coverage_pct))

    return FieldProfile(
        name=name,
        dtype=dtype,
        n_total=n_total,
        null_count=null_count,
        empty_count=empty_count,
        distinct_raw=distinct_raw,
        distinct_normalized=distinct_normalized,
        coverage_pct=coverage_pct,
        leading_trailing_ws_count=leading_trailing_ws_count,
        trailing_dot_count=trailing_dot_count,
        multivalue_count=multivalue_count,
        top_values=top_values,
        rare_values=rare_values,
        rare_values_total=rare_values_total,
    )


# --------------------------------------------------------------------------- #
# Profiler (orquestra leitura, verificação de fingerprint e perfis)
# --------------------------------------------------------------------------- #


class MetadataProfiler:
    """Auditoria exploratória, somente leitura, dos metadados da seleção."""

    VERSION = "1.0.0"
    REPORT_FILENAME = "metadata_selection_profile.md"

    def __init__(self, metadata_fields: list[str]) -> None:
        """Inicializa com a lista de campos de metadados a perfilar.

        ``metadata_fields`` deve vir do Config_File (não é embutida no código),
        preservando a rastreabilidade da decisão de quais campos existem.
        """
        self._metadata_fields = list(metadata_fields)

    def _find_manifest(self, parquet_path: Path) -> Path | None:
        """Localiza o manifesto sidecar da seleção, se existir."""
        candidate = parquet_path.parent / f"{parquet_path.stem}_manifest.json"
        return candidate if candidate.exists() else None

    def run(self, selection_parquet_path: Path) -> MetadataAuditResult:
        """Executa a auditoria de metadados sobre o Parquet da seleção.

        Somente leitura: não escreve nada no corpus. A escrita do relatório é
        responsabilidade de ``save_report``.
        """
        if not selection_parquet_path.exists():
            raise FileNotFoundError(
                f"Parquet da seleção não encontrado: '{selection_parquet_path}'"
            )

        df = pd.read_parquet(selection_parquet_path, engine="pyarrow")
        n_total = int(len(df))

        # Fingerprint: recalcula e, se houver manifesto, compara ao registrado.
        fingerprint_recomputed = compute_dataset_fingerprint(df, sort_col="doc_id")
        fingerprint_expected: str | None = None
        config_version: str | None = None
        eligibility_policy_version: str | None = None

        manifest_path = self._find_manifest(selection_parquet_path)
        if manifest_path is not None:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            fingerprint_expected = manifest.get("selection_fingerprint")
            config_version = manifest.get("config_version")
            eligibility_policy_version = manifest.get("eligibility_policy_version")

        fingerprint_matches: bool | None
        if fingerprint_expected is None:
            fingerprint_matches = None
        else:
            fingerprint_matches = fingerprint_recomputed == fingerprint_expected

        config_inconsistencies: list[str] = []
        profiles: list[FieldProfile] = []
        for name in self._metadata_fields:
            if name not in df.columns:
                config_inconsistencies.append(
                    f"metadata_field '{name}' declarado no Config_File mas ausente na seleção"
                )
                continue
            profiles.append(profile_field(df[name], name, n_total))

        return MetadataAuditResult(
            source_parquet=selection_parquet_path.name,
            n_documents=n_total,
            metadata_fields=list(self._metadata_fields),
            profiles=profiles,
            audit_timestamp=self._now_iso(),
            profiler_version=self.VERSION,
            fingerprint_recomputed=fingerprint_recomputed,
            fingerprint_expected=fingerprint_expected,
            fingerprint_matches=fingerprint_matches,
            config_version=config_version,
            eligibility_policy_version=eligibility_policy_version,
            config_inconsistencies=config_inconsistencies,
        )

    # ------------------------------------------------------------------ #
    # Persistência do relatório
    # ------------------------------------------------------------------ #

    def save_report(self, result: MetadataAuditResult, reports_dir: Path) -> Path:
        """Grava o relatório Markdown em ``reports_dir`` sem sobrescrever.

        Se o nome padrão já existir, adiciona sufixo de timestamp (mesma política
        anti-sobrescrita do Auditor/Seletor). Cria o diretório se necessário.
        """
        reports_dir.mkdir(parents=True, exist_ok=True)
        path = self._resolve_no_overwrite(reports_dir, self.REPORT_FILENAME)
        path.write_text(self.render_markdown(result), encoding="utf-8")
        return path

    def _resolve_no_overwrite(self, reports_dir: Path, filename: str) -> Path:
        candidate = reports_dir / filename
        if not candidate.exists():
            return candidate
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        return reports_dir / f"{stem}_{self._now_compact()}{suffix}"

    # ------------------------------------------------------------------ #
    # Renderização Markdown (determinística)
    # ------------------------------------------------------------------ #

    def render_markdown(self, result: MetadataAuditResult) -> str:
        """Renderiza o relatório Markdown a partir do resultado."""
        lines: list[str] = []
        lines.append("# Auditoria de Metadados — Selecao_Experimental")
        lines.append("")
        lines.append(
            "> Auditoria exploratória **somente leitura** dos campos de metadados "
            "da seleção experimental. Nenhum registro foi alterado, inferido ou "
            "excluído. A normalização aplicada é **apenas diagnóstica** e não é "
            "persistida no corpus nem adotada como estratégia experimental."
        )
        lines.append("")

        # --- Proveniência e reprodutibilidade ---
        lines.append("## Proveniência e reprodutibilidade")
        lines.append("")
        lines.append(f"- **Arquivo de origem:** `{result.source_parquet}`")
        lines.append(f"- **Documentos analisados:** {result.n_documents}")
        lines.append(f"- **Timestamp (UTC):** {result.audit_timestamp}")
        lines.append(f"- **Versão do MetadataProfiler:** {result.profiler_version}")
        if result.config_version is not None:
            lines.append(f"- **config_version (manifesto):** {result.config_version}")
        if result.eligibility_policy_version is not None:
            lines.append(
                f"- **eligibility_policy_version (manifesto):** "
                f"{result.eligibility_policy_version}"
            )
        lines.append(
            f"- **selection_fingerprint (recalculado):** `{result.fingerprint_recomputed}`"
        )
        if result.fingerprint_expected is not None:
            lines.append(
                f"- **selection_fingerprint (manifesto):** "
                f"`{result.fingerprint_expected}`"
            )
            status = "SIM" if result.fingerprint_matches else "NÃO"
            lines.append(f"- **Fingerprint confere com o manifesto:** **{status}**")
        else:
            lines.append(
                "- **Fingerprint do manifesto:** não disponível "
                "(manifesto ausente); verificação de identidade não realizada."
            )
        lines.append("")

        # --- Critérios de contagem ---
        lines.append("## Critérios de contagem e transformações diagnósticas")
        lines.append("")
        lines.append(
            "- **Nulo:** valor ausente no Parquet (None/NaN/pd.NA)."
        )
        lines.append(
            "- **Vazio/só-espaços:** valor não nulo que, após `strip()`, fica vazio."
        )
        lines.append(
            "- **Ausente (cobertura):** nulo **ou** vazio/só-espaços. "
            "Cobertura = presentes / total × 100, em [0,00; 100,00]."
        )
        lines.append(
            "- **Distintos (brutos):** valores únicos sobre o texto **original** "
            "dos presentes, **sem nenhum strip** — variações de espaço nas bordas, "
            "caixa e ponto final contam como valores distintos."
        )
        lines.append(
            "- **Distintos (normalizados):** após normalização diagnóstica — "
            "`strip` + colapso de espaços internos + remoção de ponto final + "
            "`casefold`. Serve só para medir inconsistência de formatação."
        )
        lines.append(
            f"- **Multivalorado:** valor que contém o separador `"
            f"{MULTIVALUE_SEPARATOR}` (vários itens numa mesma célula)."
        )
        lines.append(
            f"- **Valor raro (outlier):** valor cuja frequência é ≤ "
            f"{RARE_VALUE_MAX_COUNT}; sinalizado para inspeção, sem qualquer alteração."
        )
        lines.append("")

        if result.config_inconsistencies:
            lines.append("## Inconsistências de configuração")
            lines.append("")
            for item in result.config_inconsistencies:
                lines.append(f"- {item}")
            lines.append("")

        # --- Tabela consolidada ---
        lines.append("## Tabela consolidada dos campos")
        lines.append("")
        lines.append(
            "| Campo | Tipo | Nulos | Vazios/ws | Ausentes | Cobertura % | "
            "Distintos (brutos) | Distintos (norm.) | Multivalor (`;`) | Espaço ini/fim |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for p in result.profiles:
            lines.append(
                f"| {p.name} | {p.dtype} | {p.null_count} | {p.empty_count} "
                f"| {p.missing_count} ({p.missing_pct:.2f}%) | {p.coverage_pct:.2f} "
                f"| {p.distinct_raw} | {p.distinct_normalized} "
                f"| {p.multivalue_count} | {p.leading_trailing_ws_count} |"
            )
        lines.append("")

        # --- Detalhe por campo ---
        lines.append("## Detalhe por campo")
        lines.append("")
        for p in result.profiles:
            lines.append(f"### {p.name}")
            lines.append("")
            lines.append(f"- Tipo armazenado: `{p.dtype}`")
            lines.append(
                f"- Nulos: {p.null_count} | Vazios/só-espaços: {p.empty_count} "
                f"| Ausentes (total): {p.missing_count} ({p.missing_pct:.2f}%)"
            )
            lines.append(f"- Cobertura: {p.coverage_pct:.2f}%")
            lines.append(
                f"- Distintos (brutos): {p.distinct_raw} | "
                f"Distintos (normalizados): {p.distinct_normalized}"
            )
            lines.append(
                f"- Valores com ponto final: {p.trailing_dot_count} | "
                f"Valores com espaço inicial/final: {p.leading_trailing_ws_count} | "
                f"Valores multivalorados (`{MULTIVALUE_SEPARATOR}`): {p.multivalue_count}"
            )
            lines.append("")
            lines.append("Valores mais frequentes:")
            lines.append("")
            lines.append("| Frequência | Valor |")
            lines.append("|---|---|")
            for value, count in p.top_values:
                disp = value if len(value) <= 100 else value[:100] + "…"
                disp = disp.replace("|", "\\|")
                lines.append(f"| {count} | {disp} |")
            if p.distinct_raw > len(p.top_values):
                lines.append(
                    f"| … | ({p.distinct_raw} valores distintos no total) |"
                )
            lines.append("")
            if p.rare_values_total:
                lines.append(
                    f"Valores raros (frequência ≤ {RARE_VALUE_MAX_COUNT}): "
                    f"**{p.rare_values_total}** no total — sinalizados para inspeção, "
                    "**sem qualquer alteração**."
                )
                if p.rare_values_total > len(p.rare_values):
                    lines.append(
                        f"Exibindo os primeiros {len(p.rare_values)} "
                        f"(de {p.rare_values_total}):"
                    )
                lines.append("")
                for value, count in p.rare_values:
                    disp = value if len(value) <= 100 else value[:100] + "…"
                    disp = disp.replace("|", "\\|")
                    lines.append(f"- `{disp}` → {count}")
                lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(
            "_Relatório gerado por `MetadataProfiler`. Diagnóstico exploratório; "
            "não define, por si, quais campos ou normalizações serão usados nas "
            "arquiteturas de recuperação._"
        )
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Auxiliares de tempo
    # ------------------------------------------------------------------ #

    @staticmethod
    def _now_iso() -> str:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _now_compact() -> str:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")

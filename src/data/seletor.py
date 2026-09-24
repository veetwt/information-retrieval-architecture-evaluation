"""SeletorExperimental — derivação da Selecao_Experimental a partir do Corpus_Canonico.

Responsabilidades (Design 3.7, 4.8–4.12, decisão 6.11; Requirement 10):
- Ler o Corpus_Canonico (Parquet) e seu sidecar em modo SOMENTE LEITURA.
- Validar que o dataset_fingerprint atual do Parquet bate com o do sidecar de origem.
- Aplicar a Politica_Elegibilidade_Experimental declarada no Config_File.
- Preservar exatamente as mesmas colunas, ordem e valores do canônico nos elegíveis;
  nenhuma coluna de elegibilidade é adicionada.
- Registrar não elegíveis (doc_id, source_key, reasons) em ordem determinística.
- Reconciliação: n_eligible + n_ineligible == n_total.
- Calcular selection_fingerprint próprio e registrar o source_dataset_fingerprint.
- Publicar atomicamente os 3 artefatos em data/processed/experimental/.

Nunca modifica ou sobrescreve o Corpus_Canonico. Não faz chunking, concatenação de
campos, embeddings nem recuperação. A normalização de HTML/espaços é usada apenas para a
decisão de elegibilidade, em memória; o valor persistido é o original do canônico.
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

try:
    from utils.hashing import compute_dataset_fingerprint
except ImportError:
    from ..utils.hashing import compute_dataset_fingerprint

try:
    from data.config import CorpusConfig
except ImportError:
    from .config import CorpusConfig


# Ordem canônica dos reasons de não-elegibilidade (decisão 6.11 / Data Models 4.12).
REASON_ORDER = [
    "acordao_null_or_empty",
    "acordao_sigilo_placeholder",
    "assunto_null_or_empty",
    "assunto_forbidden_value",
]

_TAG_RE = re.compile(r"<[^>]+>")


class FingerprintMismatchError(Exception):
    """Levantada quando o dataset_fingerprint do Parquet diverge do sidecar de origem."""


@dataclass
class SelectionResult:
    """Resultado da seleção experimental."""

    parquet_path: Path
    manifest_path: Path
    ineligible_log_path: Path       # sempre produzido, mesmo vazio
    n_total: int
    n_eligible: int
    n_ineligible: int
    ineligible_log: list[dict]      # [{doc_id, source_key, reasons: [...]}] — em memória
    selection_fingerprint: str
    source_dataset_fingerprint: str
    source_parquet: str


class SeletorExperimental:
    """Produz a Selecao_Experimental a partir do Corpus_Canonico, sem modificá-lo."""

    def __init__(self, config: CorpusConfig) -> None:
        """Inicializa com a configuração do pipeline (inclui experimental_eligibility)."""
        self._config = config

    # ------------------------------------------------------------------ #
    # Normalização de elegibilidade (somente em memória)
    # ------------------------------------------------------------------ #

    def _normalize_for_eligibility(self, value) -> str:
        """Normaliza um valor APENAS para a decisão de elegibilidade (Design 4.9).

        1. nulo (None/NaN) → "".
        2. remove HTML: <[^>]+> → espaço.
        3. colapsa espaços: " ".join(split()).
        Sem alteração de caixa nem remoção de acentos. Não altera o valor persistido.
        """
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass
        texto = _TAG_RE.sub(" ", str(value))
        return " ".join(texto.split())

    # ------------------------------------------------------------------ #
    # Avaliação de elegibilidade
    # ------------------------------------------------------------------ #

    def _evaluate_document(self, row) -> list[str]:
        """Retorna a lista determinística de reasons de não-elegibilidade (vazia = elegível).

        Aplica a política declarada em experimental_eligibility:
        - required_text_fields ACORDAO/ASSUNTO: não podem ser vazios após normalização.
        - sigilo_placeholder (ACORDAO): valor normalizado começando com/igual a algum
          padrão declarado (também normalizado) → não elegível.
        - forbidden_exact_values (ASSUNTO): valor original exatamente igual a um valor
          proibido (comparação literal, sem normalização) → não elegível.
        A ordem dos reasons segue REASON_ORDER.
        """
        ee = self._config.experimental_eligibility
        required = set(ee.required_text_fields)
        forbidden = ee.forbidden_exact_values or {}
        sigilo = ee.sigilo_placeholder

        reasons: set[str] = set()

        # ACORDAO — required + placeholder de sigilo
        acordao_val = row.get("ACORDAO")
        acordao_norm = self._normalize_for_eligibility(acordao_val)
        if "ACORDAO" in required and acordao_norm == "":
            reasons.add("acordao_null_or_empty")
        else:
            # Só avalia placeholder de sigilo se ACORDAO não está vazio.
            if sigilo is not None and sigilo.field == "ACORDAO" and acordao_norm:
                for pat in sigilo.patterns:
                    pat_norm = self._normalize_for_eligibility(pat)
                    if not pat_norm:
                        continue
                    if sigilo.match == "prefix" and acordao_norm.startswith(pat_norm):
                        reasons.add("acordao_sigilo_placeholder")
                        break
                    if sigilo.match == "exact" and acordao_norm == pat_norm:
                        reasons.add("acordao_sigilo_placeholder")
                        break

        # ASSUNTO — required + valor exato proibido
        assunto_val = row.get("ASSUNTO")
        assunto_norm = self._normalize_for_eligibility(assunto_val)
        if "ASSUNTO" in required and assunto_norm == "":
            reasons.add("assunto_null_or_empty")
        # Valor exato proibido: comparação literal sobre o valor original (sem normalização).
        for proibido in forbidden.get("ASSUNTO", []):
            if assunto_val is not None and str(assunto_val) == proibido:
                reasons.add("assunto_forbidden_value")
                break

        # Ordenar segundo REASON_ORDER (determinístico).
        return [r for r in REASON_ORDER if r in reasons]

    # ------------------------------------------------------------------ #
    # Execução
    # ------------------------------------------------------------------ #

    def run(self, canonical_parquet_path: Path) -> SelectionResult:
        """Executa a seleção experimental conforme o Design 3.7 / Requirement 10."""
        if self._config.experimental_eligibility is None:
            raise ValueError(
                "experimental_eligibility não declarado no Config_File; "
                "seleção experimental indisponível."
            )

        if not canonical_parquet_path.exists():
            raise FileNotFoundError(
                f"Corpus canônico não encontrado: '{canonical_parquet_path}'"
            )

        # 1. Localizar e ler o sidecar de origem.
        sidecar_path = (
            canonical_parquet_path.parent / f"{canonical_parquet_path.stem}_metadata.json"
        )
        if not sidecar_path.exists():
            raise FileNotFoundError(
                f"Sidecar do corpus canônico não encontrado: '{sidecar_path}'"
            )
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        source_dataset_fingerprint = sidecar.get("dataset_fingerprint")
        if not source_dataset_fingerprint:
            raise ValueError(
                "Sidecar de origem sem dataset_fingerprint; seleção bloqueada."
            )

        # 2. Ler o Parquet canônico (somente leitura).
        df = pd.read_parquet(canonical_parquet_path, engine="pyarrow")
        n_total = int(len(df))
        colunas_canonicas = list(df.columns)

        # 3. Validar fingerprint: recalcular sobre o DataFrame lido e comparar ao sidecar.
        fingerprint_atual = compute_dataset_fingerprint(df, sort_col="doc_id")
        if fingerprint_atual != source_dataset_fingerprint:
            raise FingerprintMismatchError(
                f"dataset_fingerprint atual ({fingerprint_atual}) diverge do sidecar de "
                f"origem ({source_dataset_fingerprint}). Seleção abortada; nenhum artefato."
            )

        # 5–7. Avaliar elegibilidade por documento.
        ineligible_log: list[dict] = []
        elegivel_mask = []
        for _, row in df.iterrows():
            reasons = self._evaluate_document(row)
            if reasons:
                ineligible_log.append({
                    "doc_id": row.get("doc_id"),
                    "source_key": row.get("source_key"),
                    "reasons": reasons,
                })
                elegivel_mask.append(False)
            else:
                elegivel_mask.append(True)

        mask_series = pd.Series(elegivel_mask, index=df.index, dtype=bool)
        df_eligible = df[mask_series].reset_index(drop=True)  # mesmas colunas/ordem/valores

        n_eligible = int(len(df_eligible))
        n_ineligible = len(ineligible_log)

        # 8. Reconciliação.
        assert n_eligible + n_ineligible == n_total, (
            f"Reconciliação falhou: {n_eligible} + {n_ineligible} != {n_total}"
        )

        # 9. selection_fingerprint sobre o subconjunto elegível.
        selection_fingerprint = compute_dataset_fingerprint(df_eligible, sort_col="doc_id")

        # 10. Produzir artefatos em área temporária e publicar atomicamente.
        timestamp = self._now_compact()
        batch_id = self._config.batch_id
        interim_root = Path(self._config.staging_dir)
        sel_dir = interim_root / f"selection_{timestamp}"
        sel_dir.mkdir(parents=True, exist_ok=True)

        stem = f"selection_{batch_id}_{timestamp}"
        parquet_tmp = sel_dir / f"{stem}.parquet"
        manifest_tmp = sel_dir / f"{stem}_manifest.json"
        ineligible_tmp = sel_dir / f"{stem}_ineligible.jsonl"

        try:
            df_eligible.to_parquet(parquet_tmp, engine="pyarrow", index=False)

            manifest = {
                "source_parquet": canonical_parquet_path.name,
                "source_dataset_fingerprint": source_dataset_fingerprint,
                "selection_fingerprint": selection_fingerprint,
                "config_version": self._config.config_version,
                "eligibility_policy_version": (
                    self._config.experimental_eligibility.eligibility_policy_version
                ),
                "n_total": n_total,
                "n_eligible": n_eligible,
                "n_ineligible": n_ineligible,
                "eligibility_policy": self._policy_dict(),
                "created_at": self._now_iso(),
            }
            manifest_tmp.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            with open(ineligible_tmp, "w", encoding="utf-8") as f:
                for entry in ineligible_log:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            # Validar legibilidade dos artefatos obrigatórios.
            df_check = pd.read_parquet(parquet_tmp, engine="pyarrow")
            if len(df_check) != n_eligible or list(df_check.columns) != colunas_canonicas:
                raise OSError("Parquet experimental ilegível ou inconsistente após escrita.")
            json.loads(manifest_tmp.read_text(encoding="utf-8"))
            ineligible_tmp.read_text(encoding="utf-8")
        except Exception:
            shutil.rmtree(sel_dir, ignore_errors=True)
            raise

        # 11. Publicação atômica em data/processed/experimental/.
        experimental_dir = Path(self._config.experimental_dir)
        experimental_dir.mkdir(parents=True, exist_ok=True)

        final_parquet = self._resolve_no_overwrite(experimental_dir, f"{stem}.parquet")
        final_stem = final_parquet.stem
        final_manifest = experimental_dir / f"{final_stem}_manifest.json"
        final_ineligible = experimental_dir / f"{final_stem}_ineligible.jsonl"

        shutil.move(str(parquet_tmp), str(final_parquet))
        shutil.move(str(manifest_tmp), str(final_manifest))
        shutil.move(str(ineligible_tmp), str(final_ineligible))
        shutil.rmtree(sel_dir, ignore_errors=True)

        return SelectionResult(
            parquet_path=final_parquet,
            manifest_path=final_manifest,
            ineligible_log_path=final_ineligible,
            n_total=n_total,
            n_eligible=n_eligible,
            n_ineligible=n_ineligible,
            ineligible_log=ineligible_log,
            selection_fingerprint=selection_fingerprint,
            source_dataset_fingerprint=source_dataset_fingerprint,
            source_parquet=canonical_parquet_path.name,
        )

    # ------------------------------------------------------------------ #
    # Auxiliares
    # ------------------------------------------------------------------ #

    def _policy_dict(self) -> dict:
        """Serializa a política aplicada para o manifesto."""
        ee = self._config.experimental_eligibility
        sig = None
        if ee.sigilo_placeholder is not None:
            sig = {
                "field": ee.sigilo_placeholder.field,
                "match": ee.sigilo_placeholder.match,
                "patterns": list(ee.sigilo_placeholder.patterns),
            }
        return {
            "required_text_fields": list(ee.required_text_fields),
            "forbidden_exact_values": {k: list(v) for k, v in ee.forbidden_exact_values.items()},
            "sigilo_placeholder": sig,
        }

    def _resolve_no_overwrite(self, base_dir: Path, filename: str) -> Path:
        """Evita sobrescrita do Parquet com sufixo de timestamp."""
        candidato = base_dir / filename
        if not candidato.exists():
            return candidato
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        return base_dir / f"{stem}_{self._now_compact()}{suffix}"

    @staticmethod
    def _now_iso() -> str:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _now_compact() -> str:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")

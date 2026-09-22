"""Canonizador — transformação do CSV bruto em Parquet canônico.

Responsabilidades (conforme Design 3.6 e Requirements 5, 6, 7, 9):
- Ler somente dados brutos com proveniência validada; bloquear se pending.jsonl.
- Validar proveniência/integridade antes de qualquer leitura de dados.
- Preservar a KEY original como source_key, sem modificação.
- Rejeitar source_key nula/vazia (antes de gerar doc_id).
- Derivar doc_id determinístico: 'tcu-' + sha256(source_key.utf-8)[:12].
- Verificar unicidade de doc_id explicitamente (aborta antes de escrever se colisão).
- Aplicar política de elegibilidade (primary_key_field + required_fields).
- Filtrar por allowed_fields; registrar excluded_fields no sidecar.
- Produzir Parquet + sidecar (com dataset_fingerprint) + rejected.jsonl (+ issues.jsonl)
  em área temporária, validar legibilidade e publicar atomicamente em
  data/processed/original/.
- Nunca infere, normaliza, limpa HTML ou preenche valores. Toda política é explícita.
- data/raw/ permanece inalterado; nenhum registro desaparece sem rastreabilidade.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

try:
    from utils.hashing import compute_dataset_fingerprint
except ImportError:
    from ..utils.hashing import compute_dataset_fingerprint

try:
    from data.config import CorpusConfig
    from data.manifest import ManifestWriter
    from data.auditor import PendingManifestError, ProvenanceError
except ImportError:
    from .config import CorpusConfig
    from .manifest import ManifestWriter
    from .auditor import PendingManifestError, ProvenanceError


@dataclass
class CanonicalizationResult:
    """Resultado da canonização de um corpus bruto."""

    parquet_path: Path
    sidecar_path: Path
    rejected_log_path: Path        # {parquet_stem}_rejected.jsonl — sempre produzido
    issues_log_path: Path | None   # {parquet_stem}_issues.jsonl — None se sem problemas
    n_accepted: int
    n_rejected: int
    n_total: int
    rejected_log: list[dict]       # [{source_key, row_index, reason}] — em memória
    issues_log: list[dict]         # [{source_key, field, issue_type, original_value}]
    dataset_fingerprint: str
    excluded_fields: list[str]


class Canonizador:
    """Transformação do CSV bruto em Parquet canônico com rastreabilidade total."""

    DOC_ID_PREFIX = "tcu-"
    DOC_ID_HASH_LEN = 12

    def __init__(self, config: CorpusConfig, manifest: ManifestWriter) -> None:
        """Inicializa com a configuração do pipeline e o ManifestWriter."""
        self._config = config
        self._manifest = manifest

    # ------------------------------------------------------------------ #
    # Leitura segura de CSV grande (mesma abordagem do Auditor)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _raise_csv_field_size_limit() -> int:
        """Eleva csv.field_size_limit ao maior valor aceito pela plataforma.

        Retorna o limite anterior para restauração posterior.
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
                    csv.field_size_limit(previous)
                    break
        return previous

    @staticmethod
    def _detect_delimiter(corpus_path: Path) -> str:
        """Detecta o delimitador do CSV a partir do cabeçalho (', | ; \\t')."""
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
        """Lê o CSV bruto para DataFrame, preservando valores como string.

        dtype=str evita inferência/coerção; delimitador detectado automaticamente;
        field_size_limit elevado de forma reversível para campos textuais grandes.
        Não modifica o arquivo bruto.
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
    # doc_id
    # ------------------------------------------------------------------ #

    def _assign_doc_id(self, source_key: str) -> str:
        """Deriva doc_id a partir de source_key.

        doc_id = 'tcu-' + sha256(source_key.encode('utf-8'))[:12].
        Determinístico por source_key; não modifica source_key.
        """
        h = hashlib.sha256(source_key.encode("utf-8")).hexdigest()
        return f"{self.DOC_ID_PREFIX}{h[:self.DOC_ID_HASH_LEN]}"

    def _validate_doc_id_uniqueness(self, df: pd.DataFrame) -> None:
        """Verifica que não há dois source_key distintos com o mesmo doc_id.

        Opera sobre o DataFrame já com colunas 'source_key' e 'doc_id'.
        Lança ValueError descritivo (com pares conflitantes) se colisão detectada,
        antes de qualquer escrita de artefato.
        """
        # Para cada doc_id, contar quantos source_key distintos mapeiam para ele.
        agrupado = df.groupby("doc_id")["source_key"].nunique()
        colisoes = agrupado[agrupado > 1]
        if len(colisoes) > 0:
            exemplos = []
            for did in list(colisoes.index)[:5]:
                keys = sorted(df.loc[df["doc_id"] == did, "source_key"].unique().tolist())
                exemplos.append(f"{did} <- {keys}")
            raise ValueError(
                "Colisão de doc_id detectada (source_key distintos com mesmo doc_id): "
                + "; ".join(exemplos)
            )

    # ------------------------------------------------------------------ #
    # Elegibilidade
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_blank(value) -> bool:
        """True se valor é nulo, vazio ou composto apenas por espaços."""
        if value is None:
            return True
        try:
            if pd.isna(value):
                return True
        except (TypeError, ValueError):
            pass
        return str(value).strip() == ""

    def _apply_eligibility(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[dict]]:
        """Aplica a política de elegibilidade sobre registros com source_key válido.

        Pré-condição: registros com source_key nulo/vazio já foram removidos em run().
        - Campos obrigatórios = primary_key_field + required_fields:
            rejeita registros com valor nulo/vazio; motivo em rejected_log
            (reason='required_field_missing:<campo>').
        - source_key duplicado: rejeita ocorrências repetidas com
            reason='duplicate_source_key' (mantém a primeira ocorrência).
        - Campos não obrigatórios: política padrão do baseline — preservar valor
            original, sem inferência/normalização. (Sem regras de "malformado"
            declaradas no Config_File, nenhum issue é gerado nesta etapa.)

        Não rejeita por text_field ausente (ACORDAO): text_field não é obrigatório
        para elegibilidade salvo se declarado em required_fields.

        Retorna (df_aceitos, lista_rejeitados_com_motivo).
        """
        rejected: list[dict] = []

        # Conjunto de campos obrigatórios (dedup, preservando presença).
        obrigatorios: list[str] = []
        pk = self._config.primary_key_field
        if pk:
            obrigatorios.append(pk)
        for campo in (self._config.required_fields or []):
            if campo not in obrigatorios:
                obrigatorios.append(campo)

        aceitos_idx: list = []
        vistos_source_key: set[str] = set()

        for idx, row in df.iterrows():
            source_key = row["source_key"]

            # Rejeição por campo obrigatório ausente/malformado.
            motivo = None
            for campo in obrigatorios:
                if campo not in df.columns or self._is_blank(row.get(campo)):
                    motivo = f"required_field_missing:{campo}"
                    break

            if motivo is not None:
                rejected.append({
                    "source_key": source_key,
                    "row_index": int(row["__row_index__"]),
                    "reason": motivo,
                })
                continue

            # Rejeição por source_key duplicado (mantém a primeira ocorrência).
            if source_key in vistos_source_key:
                rejected.append({
                    "source_key": source_key,
                    "row_index": int(row["__row_index__"]),
                    "reason": "duplicate_source_key",
                })
                continue

            vistos_source_key.add(source_key)
            aceitos_idx.append(idx)

        df_aceitos = df.loc[aceitos_idx].copy()
        return df_aceitos, rejected

    # ------------------------------------------------------------------ #
    # Schema de colunas de campos originais
    # ------------------------------------------------------------------ #

    def _build_field_schema(self) -> tuple[list[str], dict[str, list[str]]]:
        """Determina a ordem determinística das colunas de campos originais e seus papéis.

        Ordem (Design 4.3): concatenação de
          retrieval_text_fields → metadata_fields → preserved_fields,
        preservando a ordem declarada em cada lista e removendo repetições na primeira
        ocorrência (a primeira categoria em que o campo aparece fixa sua posição). Um campo
        declarado em mais de uma categoria ocupa uma única coluna, mas todos os seus papéis
        são registrados em field_roles.

        text_field NÃO adiciona coluna por si só (é o campo de referência da auditoria);
        só aparece se também estiver declarado em uma das três categorias de coluna.

        Retorna (colunas_ordenadas, field_roles).
        """
        categorias = [
            ("retrieval_text_fields", self._config.retrieval_text_fields or []),
            ("metadata_fields", self._config.metadata_fields or []),
            ("preserved_fields", self._config.preserved_fields or []),
        ]

        colunas: list[str] = []
        field_roles: dict[str, list[str]] = {}
        for categoria, campos in categorias:
            for campo in campos:
                if campo not in field_roles:
                    field_roles[campo] = []
                    colunas.append(campo)  # primeira ocorrência fixa a posição
                if categoria not in field_roles[campo]:
                    field_roles[campo].append(categoria)

        return colunas, field_roles

    # ------------------------------------------------------------------ #
    # Persistência de artefatos
    # ------------------------------------------------------------------ #

    def _write_sidecar(
        self,
        parquet_path: Path,
        excluded_fields: list[str],
        dataset_fingerprint: str,
        canonical_columns: list[str],
        field_roles: dict[str, list[str]],
    ) -> Path:
        """Escreve '{parquet_stem}_metadata.json'.

        Inclui as categorias declaradas (text_field, retrieval_text_fields,
        metadata_fields, preserved_fields), a ordem determinística das colunas
        (canonical_columns) e o papel de cada campo incluído (field_roles).
        dataset_fingerprint é obrigatório — sua ausência impede a publicação.
        """
        if not dataset_fingerprint:
            raise ValueError(
                "dataset_fingerprint ausente — publicação do Corpus_Canonico bloqueada."
            )
        sidecar_path = parquet_path.parent / f"{parquet_path.stem}_metadata.json"
        conteudo = {
            "parquet_file": parquet_path.name,
            "created_at": self._now_iso(),
            "config_version": self._config.config_version,
            "batch_id": self._config.batch_id,
            "allowed_fields": list(self._config.allowed_fields),
            "excluded_fields": list(excluded_fields),
            "text_field": self._config.text_field,
            "retrieval_text_fields": list(self._config.retrieval_text_fields or []),
            "metadata_fields": list(self._config.metadata_fields or []),
            "preserved_fields": list(self._config.preserved_fields or []),
            "canonical_columns": list(canonical_columns),
            "field_roles": field_roles,
            "dataset_fingerprint": dataset_fingerprint,
        }
        sidecar_path.write_text(
            json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return sidecar_path

    def _write_rejected_log(self, stem_path: Path, rejected: list[dict]) -> Path:
        """Persiste '{stem}_rejected.jsonl'. Sempre produzido, mesmo vazio."""
        path = stem_path.parent / f"{stem_path.stem}_rejected.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for entry in rejected:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return path

    def _write_issues_log(self, stem_path: Path, issues: list[dict]) -> Path | None:
        """Persiste '{stem}_issues.jsonl' somente se issues não estiver vazio."""
        if not issues:
            return None
        path = stem_path.parent / f"{stem_path.stem}_issues.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for entry in issues:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return path

    def _append_fingerprint_log(self, result: CanonicalizationResult) -> None:
        """Acrescenta uma linha ao fingerprint_log.jsonl (histórico auxiliar).

        Falha aqui emite aviso mas não invalida o corpus já publicado.
        """
        entry = {
            "timestamp": self._now_iso(),
            "parquet_file": str(result.parquet_path),
            "dataset_fingerprint": result.dataset_fingerprint,
            "config_version": self._config.config_version,
            "batch_id": self._config.batch_id,
            "n_accepted": result.n_accepted,
            "n_rejected": result.n_rejected,
        }
        try:
            log_path = Path(self._config.fingerprint_log)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            print(
                f"AVISO: falha ao registrar em fingerprint_log.jsonl "
                f"('{self._config.fingerprint_log}': {exc}). O corpus publicado permanece "
                f"válido; o dataset_fingerprint está garantido no sidecar.",
                file=sys.stderr,
            )

    # ------------------------------------------------------------------ #
    # Execução
    # ------------------------------------------------------------------ #

    def run(self, corpus_path: Path) -> CanonicalizationResult:
        """Executa a canonização completa conforme o fluxo do Design."""
        # 1. Proveniência e integridade
        stored_filename = corpus_path.name
        raw_dir = corpus_path.parent
        valido, motivo = self._manifest.validate_file_provenance(stored_filename, raw_dir)
        if not valido:
            if motivo == "integrity_mismatch":
                raise ProvenanceError(
                    "integrity_mismatch",
                    f"SHA-256 atual de '{stored_filename}' diverge do registrado no Manifest.",
                )
            raise ProvenanceError(
                "provenance_missing",
                f"Arquivo '{stored_filename}' sem entrada válida no Manifest (motivo: {motivo}).",
            )

        # 1a. Bloqueio por pending.jsonl
        if self._manifest.has_pending_entries():
            raise PendingManifestError(
                "pending.jsonl contém entradas não consolidadas. Canonização bloqueada "
                "até resolução manual; nenhum artefato produzido."
            )

        # 2. Validar primary_key_field e text_field existem como colunas
        pk = self._config.primary_key_field
        tf = self._config.text_field
        if not pk:
            raise ValueError("primary_key_field não declarado no Config_File.")
        if not tf:
            raise ValueError("text_field não declarado no Config_File.")

        df = self._read_csv(corpus_path)
        n_total = int(len(df))

        if pk not in df.columns:
            raise ValueError(
                f"Erro de configuração: primary_key_field '{pk}' ausente nas colunas do dataset."
            )
        if tf not in df.columns:
            raise ValueError(
                f"Erro de configuração: text_field '{tf}' ausente nas colunas do dataset."
            )

        # 4. Aplicar allowed_fields → excluded_fields
        allowed = list(self._config.allowed_fields)
        excluded_fields = [c for c in df.columns if c not in allowed]

        # Índice de linha original (base 0) para rastreabilidade nos logs.
        df = df.reset_index(drop=True)
        df["__row_index__"] = range(n_total)

        # 5–6. Extrair source_key (valor original de pk, sem modificação);
        #      rejeitar source_key nulo/vazio antes de gerar doc_id.
        rejected: list[dict] = []
        source_key_series = df[pk]

        # dtype=bool explícito: garante indexação booleana correta mesmo com 0 linhas
        # (uma máscara vazia sem dtype bool descartaria as colunas em df[mask]).
        blank_mask = source_key_series.map(self._is_blank).astype(bool)
        for _, row in df[blank_mask].iterrows():
            rejected.append({
                "source_key": None,
                "row_index": int(row["__row_index__"]),
                "reason": "source_key_null_or_empty",
            })

        df_validos = df[~blank_mask].copy()
        df_validos["source_key"] = df_validos[pk].astype(str)

        # 7. Derivar doc_id apenas para registros com source_key válido.
        df_validos["doc_id"] = df_validos["source_key"].map(self._assign_doc_id)

        # 8. Verificar unicidade de doc_id antes de qualquer escrita.
        self._validate_doc_id_uniqueness(df_validos)

        # 8b. Política de elegibilidade.
        df_aceitos, rejected_eleg = self._apply_eligibility(df_validos)
        rejected.extend(rejected_eleg)

        # Montar o DataFrame canônico com o schema determinístico do Design 4.3:
        #   doc_id, source_key,
        #   <retrieval_text_fields>, <metadata_fields>, <preserved_fields>
        # na ordem declarada, removendo repetições na primeira ocorrência (um campo
        # declarado em mais de uma categoria ocupa uma única coluna).
        field_columns, field_roles = self._build_field_schema()
        colunas_canonicas = ["doc_id", "source_key"] + field_columns

        # Garantir presença de todas as colunas do schema (campo ausente no dataset → NA).
        for col in colunas_canonicas:
            if col not in df_aceitos.columns:
                df_aceitos[col] = pd.NA
        df_canonico = df_aceitos[colunas_canonicas].reset_index(drop=True)

        n_accepted = int(len(df_canonico))
        n_rejected = len(rejected)
        # Reconciliação total (Property 2).
        assert n_accepted + n_rejected == n_total, (
            f"Reconciliação falhou: {n_accepted} + {n_rejected} != {n_total}"
        )

        issues: list[dict] = []  # baseline sem regras de "malformado" declaradas

        # 8c. dataset_fingerprint sobre o DataFrame aceito.
        dataset_fingerprint = compute_dataset_fingerprint(df_canonico, sort_col="doc_id")

        # 9. Produzir artefatos em área temporária.
        timestamp = self._now_compact()
        interim_root = Path(self._config.staging_dir)
        canon_dir = interim_root / f"canon_{timestamp}"
        canon_dir.mkdir(parents=True, exist_ok=True)

        parquet_name = f"corpus_{self._config.batch_id}_{timestamp}.parquet"
        parquet_tmp = canon_dir / parquet_name

        try:
            df_canonico.to_parquet(parquet_tmp, engine="pyarrow", index=False)
            sidecar_tmp = self._write_sidecar(
                parquet_tmp,
                excluded_fields,
                dataset_fingerprint,
                colunas_canonicas,
                field_roles,
            )
            rejected_tmp = self._write_rejected_log(parquet_tmp, rejected)
            issues_tmp = self._write_issues_log(parquet_tmp, issues)

            # 10. Validar legibilidade dos artefatos obrigatórios.
            df_check = pd.read_parquet(parquet_tmp, engine="pyarrow")
            if len(df_check) != n_accepted:
                raise OSError("Parquet ilegível ou inconsistente após escrita.")
            json.loads(sidecar_tmp.read_text(encoding="utf-8"))
            rejected_tmp.read_text(encoding="utf-8")
        except Exception:
            # Descartar diretório temporário; nada é publicado.
            shutil.rmtree(canon_dir, ignore_errors=True)
            raise

        # 11. Publicação atômica em data/processed/original/.
        processed_dir = Path(self._config.processed_dir)
        processed_dir.mkdir(parents=True, exist_ok=True)

        final_parquet = self._resolve_no_overwrite(processed_dir, parquet_name)
        final_stem = final_parquet.stem  # pode ganhar sufixo de timestamp

        # Recalcular nomes de destino a partir do stem final (mantém consistência).
        final_sidecar = processed_dir / f"{final_stem}_metadata.json"
        final_rejected = processed_dir / f"{final_stem}_rejected.jsonl"
        final_issues = processed_dir / f"{final_stem}_issues.jsonl" if issues_tmp else None

        shutil.move(str(parquet_tmp), str(final_parquet))
        shutil.move(str(sidecar_tmp), str(final_sidecar))
        shutil.move(str(rejected_tmp), str(final_rejected))
        if issues_tmp is not None and final_issues is not None:
            shutil.move(str(issues_tmp), str(final_issues))

        # Limpar diretório temporário remanescente.
        shutil.rmtree(canon_dir, ignore_errors=True)

        result = CanonicalizationResult(
            parquet_path=final_parquet,
            sidecar_path=final_sidecar,
            rejected_log_path=final_rejected,
            issues_log_path=final_issues,
            n_accepted=n_accepted,
            n_rejected=n_rejected,
            n_total=n_total,
            rejected_log=rejected,
            issues_log=issues,
            dataset_fingerprint=dataset_fingerprint,
            excluded_fields=excluded_fields,
        )

        # 12. Registrar no fingerprint_log (falha = aviso, não invalida corpus).
        self._append_fingerprint_log(result)

        return result

    def _resolve_no_overwrite(self, processed_dir: Path, parquet_name: str) -> Path:
        """Resolve o caminho do Parquet evitando sobrescrita com sufixo de timestamp."""
        candidato = processed_dir / parquet_name
        if not candidato.exists():
            return candidato
        stem = Path(parquet_name).stem
        suffix = Path(parquet_name).suffix
        return processed_dir / f"{stem}_{self._now_compact()}{suffix}"

    # ------------------------------------------------------------------ #
    # Utilitários de tempo
    # ------------------------------------------------------------------ #

    @staticmethod
    def _now_iso() -> str:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _now_compact() -> str:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")

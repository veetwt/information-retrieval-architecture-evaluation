"""Ingestor — incorporação controlada de arquivos ao corpus bruto.

Responsabilidades:
- Receber arquivo local fornecido pelo pesquisador
- Validar existência e legibilidade
- Calcular SHA-256 e verificar duplicidades
- Copiar para área de staging (data/interim/)
- Verificar integridade SHA-256 da cópia
- Verificar fisicamente o destino em data/raw/ antes de promover
- Promover o arquivo validado para data/raw/
- Registrar proveniência no Manifest
- Bloquear quando pending.jsonl contiver entradas não resolvidas
"""

from __future__ import annotations

import datetime
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

try:
    from utils.hashing import compute_sha256
except ImportError:
    from ..utils.hashing import compute_sha256

try:
    from data.config import CorpusConfig
    from data.manifest import ManifestWriter
except ImportError:
    from .config import CorpusConfig
    from .manifest import ManifestWriter


@dataclass
class IngestorResult:
    """Resultado de uma operação de ingestão."""

    status: Literal[
        "ingested",
        "duplicate_content",
        "name_conflict_versioned",
        "integrity_error",
        "validation_error",
        "file_exists_consistent",
        "inconsistency_orphan_file",
        "manifest_pending",
        "blocked_pending_manifest",
    ]
    """Status da operação:
    - ingested: ingestão concluída com sucesso
    - duplicate_content: SHA-256 já existe no Manifest; nenhuma cópia feita
    - name_conflict_versioned: Conflito_Por_Nome; arquivo incorporado com stored_filename versionado
    - integrity_error: SHA-256 staging ≠ SHA-256 origem; staging descartado
    - validation_error: arquivo de origem não existe ou não é legível
    - file_exists_consistent: destino físico já existe em data/raw/ com entrada Manifest consistente
    - inconsistency_orphan_file: destino físico existe em data/raw/ sem entrada Manifest
    - manifest_pending: arquivo promovido com sucesso, mas escrita no Manifest falhou
    - blocked_pending_manifest: pending.jsonl contém entradas não resolvidas
    """

    stored_filename: str | None
    """Nome usado em data/raw/ (None se não houve promoção)."""

    sha256: str | None
    """SHA-256 do arquivo de origem (None se cálculo falhou)."""

    message: str
    """Mensagem descritiva do resultado."""


class Ingestor:
    """Fluxo completo de ingestão: validação, hashing, staging, verificação física e promoção."""

    def __init__(self, config: CorpusConfig, manifest: ManifestWriter) -> None:
        """Inicializa com a configuração e o ManifestWriter.

        Não faz I/O; apenas guarda as referências.
        """
        self._config = config
        self._manifest = manifest

    def _copy_to_staging(self, source: Path, staging_name: str) -> Path:
        """Copia arquivo de origem para data/interim/staging_name.

        Cria o diretório staging se não existir.
        Retorna o Path do arquivo em staging.
        """
        staging_dir = Path(self._config.staging_dir)
        staging_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, staging_dir / staging_name)
        return staging_dir / staging_name

    def _cleanup_staging(self, staging_path: Path) -> None:
        """Remove arquivo de staging sem lançar exceção se não existir."""
        staging_path.unlink(missing_ok=True)

    def _resolve_stored_filename(self, original_filename: str, sha256: str) -> str:
        """Determina stored_filename seguro contra colisões.

        Sem Conflito_Por_Nome: retorna original_filename.
        Com Conflito_Por_Nome (original_filename já no Manifest com hash diferente):
          - Gera candidato: '{stem}_{sha256[:N]}{suffix}', N começa em 8
          - Verifica colisão no Manifest (stored_filename) E fisicamente em raw_dir
          - Se houver colisão: aumenta N progressivamente: 10, 12, ..., 64
          - Se nenhuma extensão eliminar a colisão: lança ValueError descritivo
        Em nenhuma situação um arquivo existente em data/raw/ é sobrescrito.
        """
        found, entry = self._manifest.original_filename_exists(original_filename)

        # Sem Conflito_Por_Nome
        if not found:
            return original_filename

        # Entrada existe: verificar se é Duplicidade_Por_Conteudo ou Conflito_Por_Nome
        # Se o sha256 é o mesmo, é Duplicidade_Por_Conteudo — o chamador abortará antes.
        # Por segurança, retornar original_filename.
        if entry is not None and entry.get("sha256") == sha256:
            return original_filename

        # Conflito_Por_Nome real: mesmo nome, hash diferente
        stem = Path(original_filename).stem
        suffix = Path(original_filename).suffix
        raw_dir = Path(self._config.raw_dir)

        # Coletar todos os stored_filenames já no Manifest
        manifest_stored = {e.get("stored_filename") for e in self._manifest.load_entries()}

        # Tentar desambiguação progressiva
        for n in [8, 10, 12, 14, 16, 20, 24, 32, 48, 64]:
            candidato = f"{stem}_{sha256[:n]}{suffix}"

            # Verificar colisão no Manifest
            if candidato in manifest_stored:
                continue

            # Verificar colisão física em raw_dir
            if (raw_dir / candidato).exists():
                continue

            return candidato

        raise ValueError(
            f"Não foi possível gerar stored_filename único para '{original_filename}' "
            f"após desambiguação progressiva"
        )

    def _promote_to_raw(self, staging_path: Path, stored_filename: str) -> Path:
        """Move arquivo de staging para data/raw/stored_filename.

        Antes de mover:
          1. Verifica se o caminho físico final já existe em data/raw/
          2. Se existir E entrada Manifest consistente → levanta FileExistsError("file_exists_consistent")
          3. Se existir E sem entrada Manifest → levanta FileExistsError("inconsistency_orphan_file")
          4. Se não existir → mover com shutil.move

        Em nenhuma situação um arquivo existente em data/raw/ é sobrescrito.
        Retorna Path do arquivo promovido em caso de sucesso.
        """
        raw_dir = Path(self._config.raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)
        destino = raw_dir / stored_filename

        if destino.exists():
            # Verificar proveniência para determinar o tipo de conflito
            valido, motivo = self._manifest.validate_file_provenance(stored_filename, raw_dir)
            if valido:
                raise FileExistsError("file_exists_consistent")
            elif motivo == "provenance_missing":
                raise FileExistsError("inconsistency_orphan_file")
            else:
                # integrity_mismatch ou outro — arquivo existe sem proveniência confiável
                raise FileExistsError("inconsistency_orphan_file")

        shutil.move(str(staging_path), str(destino))
        return destino

    def ingest(
        self,
        source_path: Path,
        downloaded_at: str,  # ISO 8601 UTC, informado pelo pesquisador
    ) -> IngestorResult:
        """Executa o fluxo completo de ingestão conforme o Design.

        Passos:
        0. Verificar pending.jsonl
        1. Validar existência e legibilidade
        2. Calcular SHA-256 da origem
        3. Verificar Duplicidade_Por_Conteudo
        4. Verificar Conflito_Por_Nome e resolver stored_filename
        5-8. Staging e verificação de integridade
        9. Promover para data/raw/
        10. Registrar no Manifest
        """
        # Passo 0 — Verificar pending.jsonl
        if self._manifest.has_pending_entries():
            return IngestorResult(
                status="blocked_pending_manifest",
                stored_filename=None,
                sha256=None,
                message=(
                    "pending.jsonl contém entradas não resolvidas. "
                    "Resolva manualmente antes de continuar."
                ),
            )

        # Passo 1 — Validar existência e legibilidade
        if not source_path.exists():
            return IngestorResult(
                status="validation_error",
                stored_filename=None,
                sha256=None,
                message=f"Arquivo não encontrado: '{source_path}'",
            )
        if not source_path.is_file():
            return IngestorResult(
                status="validation_error",
                stored_filename=None,
                sha256=None,
                message=f"Caminho não é um arquivo: '{source_path}'",
            )

        # Passo 2 — Calcular SHA-256 da origem
        try:
            sha256_origem = compute_sha256(source_path)
        except IOError as exc:
            return IngestorResult(
                status="validation_error",
                stored_filename=None,
                sha256=None,
                message=f"Falha ao calcular SHA-256 da origem: {exc}",
            )

        # Passo 3 — Verificar Duplicidade_Por_Conteudo
        found, existing = self._manifest.sha256_exists(sha256_origem)
        if found:
            return IngestorResult(
                status="duplicate_content",
                stored_filename=None,
                sha256=sha256_origem,
                message=(
                    f"Conteúdo já ingerido. Entrada existente: "
                    f"original_filename='{existing['original_filename']}', "
                    f"ingested_at='{existing['ingested_at']}'"
                ),
            )

        # Passo 4 — Verificar Conflito_Por_Nome e determinar stored_filename
        original_filename = source_path.name
        nome_conflito = False
        try:
            stored_filename = self._resolve_stored_filename(original_filename, sha256_origem)
        except ValueError as exc:
            return IngestorResult(
                status="validation_error",
                stored_filename=None,
                sha256=sha256_origem,
                message=str(exc),
            )
        if stored_filename != original_filename:
            nome_conflito = True

        # Passos 5–8 — Staging e verificação de integridade
        staging_name = stored_filename
        staging_path = None
        try:
            staging_path = self._copy_to_staging(source_path, staging_name)
            sha256_staging = compute_sha256(staging_path)
            if sha256_staging != sha256_origem:
                self._cleanup_staging(staging_path)
                return IngestorResult(
                    status="integrity_error",
                    stored_filename=None,
                    sha256=sha256_origem,
                    message="Falha de integridade: SHA-256 da cópia em staging diverge da origem.",
                )
        except IOError as exc:
            if staging_path is not None:
                self._cleanup_staging(staging_path)
            return IngestorResult(
                status="integrity_error",
                stored_filename=None,
                sha256=sha256_origem,
                message=f"Erro de I/O durante staging: {exc}",
            )

        # Passo 9 — Promover para data/raw/
        try:
            raw_path = self._promote_to_raw(staging_path, stored_filename)
        except FileExistsError as exc:
            self._cleanup_staging(staging_path)
            motivo = str(exc)
            if motivo == "file_exists_consistent":
                return IngestorResult(
                    status="file_exists_consistent",
                    stored_filename=stored_filename,
                    sha256=sha256_origem,
                    message=(
                        f"Arquivo '{stored_filename}' já existe em data/raw/ "
                        f"com proveniência consistente."
                    ),
                )
            else:  # inconsistency_orphan_file
                return IngestorResult(
                    status="inconsistency_orphan_file",
                    stored_filename=stored_filename,
                    sha256=sha256_origem,
                    message=(
                        f"Arquivo '{stored_filename}' já existe em data/raw/ "
                        f"sem entrada válida no Manifest."
                    ),
                )

        # Passo 10 — Registrar no Manifest
        file_size = raw_path.stat().st_size
        entry = {
            "original_filename": original_filename,
            "stored_filename": stored_filename,
            "downloaded_at": downloaded_at,
            "ingested_at": datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "file_size_bytes": file_size,
            "sha256": sha256_origem,
            "source_url": self._config.source_url,
            "source_identifier": self._config.source_identifier,
            "dataset": self._config.dataset,
            "dataset_year": self._config.dataset_year,
            "schema_version": self._config.schema_version,
            "batch_id": self._config.batch_id,
        }

        try:
            self._manifest.append_entry(entry)
        except Exception as exc:
            # Arquivo está em data/raw/ mas Manifest falhou — gravar em pending.jsonl
            try:
                self._manifest.append_pending_entry(entry)
            except IOError:
                pass  # Não pode fazer mais nada; arquivo retido em data/raw/
            return IngestorResult(
                status="manifest_pending",
                stored_filename=stored_filename,
                sha256=sha256_origem,
                message=(
                    f"Arquivo promovido para data/raw/ mas registro no Manifest falhou. "
                    f"Entrada em pending.jsonl. stored_filename='{stored_filename}'"
                ),
            )

        # Status final
        final_status = "name_conflict_versioned" if nome_conflito else "ingested"
        return IngestorResult(
            status=final_status,
            stored_filename=stored_filename,
            sha256=sha256_origem,
            message=f"Arquivo '{stored_filename}' ingerido com sucesso em data/raw/.",
        )

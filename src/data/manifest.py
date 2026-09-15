"""ManifestWriter — leitura, escrita e verificação de proveniência do Manifest.

O Manifest é um arquivo JSON Lines (manifest.jsonl) que registra metadados
de proveniência de cada arquivo bruto incorporado ao corpus. É append-only
e permite leitura programática sem carregamento completo do arquivo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import ClassVar

# Importar compute_sha256 do módulo de utilidades (não re-implementar)
# O sys.path é resolvido por quem invoca o módulo; aqui usamos import relativo
# quando disponível ou absoluto via sys.path conforme a convenção do projeto.
try:
    from utils.hashing import compute_sha256
except ImportError:
    # Fallback para importação relativa quando usado dentro do pacote src
    from ..utils.hashing import compute_sha256


class ManifestWriter:
    """Leitura e escrita do arquivo manifest.jsonl.

    Verifica duplicidade por conteúdo e por nome antes da ingestão,
    registra entradas de proveniência após promoção bem-sucedida, e
    valida a proveniência de arquivos em data/raw/ antes de seu
    processamento pelo Auditor e pelo Canonizador.
    """

    REQUIRED_FIELDS: ClassVar[list[str]] = [
        "original_filename",
        "stored_filename",
        "downloaded_at",
        "ingested_at",
        "file_size_bytes",
        "sha256",
        "dataset",
        "dataset_year",
        "schema_version",
        "batch_id",
        # Nota: source_url ou source_identifier — pelo menos um deve estar presente.
        # Verificado em append_entry separadamente.
    ]

    PENDING_FILENAME: ClassVar[str] = "pending.jsonl"
    """Arquivo no mesmo diretório que manifest.jsonl para entradas pendentes."""

    def __init__(self, manifest_path: Path) -> None:
        """Inicializa com o caminho do manifest.jsonl.

        Não cria o arquivo; a criação ocorre no primeiro append_entry.
        """
        self._manifest_path = manifest_path

    @property
    def _pending_path(self) -> Path:
        """Caminho do pending.jsonl, no mesmo diretório que manifest.jsonl."""
        return self._manifest_path.parent / self.PENDING_FILENAME

    def load_entries(self) -> list[dict]:
        """Carrega todas as entradas do manifest.jsonl em memória.

        Retorna lista de dicts. Retorna lista vazia se o arquivo não existir.
        """
        if not self._manifest_path.exists():
            return []

        entries = []
        with open(self._manifest_path, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    entries.append(json.loads(linha))
        return entries

    def sha256_exists(self, sha256: str) -> tuple[bool, dict | None]:
        """Verifica se o sha256 já existe em alguma entrada.

        Retorna (True, entry) se encontrado, (False, None) caso contrário.
        """
        for entry in self.load_entries():
            if entry.get("sha256") == sha256:
                return True, entry
        return False, None

    def original_filename_exists(self, original_filename: str) -> tuple[bool, dict | None]:
        """Verifica se o original_filename já consta em alguma entrada.

        Retorna (True, entry) se encontrado, (False, None) caso contrário.
        """
        for entry in self.load_entries():
            if entry.get("original_filename") == original_filename:
                return True, entry
        return False, None

    def append_entry(self, entry: dict) -> None:
        """Valida campos obrigatórios e escreve uma linha JSON no manifest.jsonl.

        Verificações:
        - Todos os campos de REQUIRED_FIELDS devem estar presentes.
        - Pelo menos um de source_url ou source_identifier deve ser não-None
          e não-string-vazia.

        Lança ValueError se campo obrigatório ausente ou inválido.
        """
        # Verificar campos obrigatórios
        for campo in self.REQUIRED_FIELDS:
            if campo not in entry or entry[campo] is None:
                raise ValueError(
                    f"Campo obrigatório ausente ou inválido: {campo}"
                )

        # Verificar que pelo menos um de source_url ou source_identifier está presente
        source_url = entry.get("source_url")
        source_identifier = entry.get("source_identifier")
        source_url_ok = source_url is not None and source_url != ""
        source_identifier_ok = source_identifier is not None and source_identifier != ""
        if not source_url_ok and not source_identifier_ok:
            raise ValueError(
                "Campo obrigatório ausente ou inválido: "
                "pelo menos um de 'source_url' ou 'source_identifier' deve estar presente"
            )

        # Garantir que o diretório existe
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)

        # Escrever em modo append
        with open(self._manifest_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def append_pending_entry(self, entry: dict) -> None:
        """Grava entry em pending.jsonl quando append_entry falhar após promoção.

        Mesmo diretório que manifest.jsonl. Modo append; um objeto JSON por linha.
        Lança IOError se pending.jsonl também falhar.
        """
        try:
            self._pending_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._pending_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            raise IOError(
                f"Falha ao gravar entrada em pending.jsonl '{self._pending_path}': {exc}"
            ) from exc

    def has_pending_entries(self) -> bool:
        """Retorna True se pending.jsonl existir e contiver pelo menos uma linha.

        Indica que existe(m) arquivo(s) em data/raw/ cuja proveniência não está
        consolidada no manifest.jsonl principal.
        """
        if not self._pending_path.exists():
            return False

        with open(self._pending_path, encoding="utf-8") as f:
            for linha in f:
                if linha.strip():
                    return True
        return False

    def validate_file_provenance(
        self, stored_filename: str, raw_dir: Path
    ) -> tuple[bool, str]:
        """Verifica se um arquivo em data/raw/ possui proveniência válida no Manifest.

        Condições para proveniência válida:
          1. Existe uma entrada no Manifest com stored_filename == stored_filename.
          2. O SHA-256 atual do arquivo em raw_dir/stored_filename é idêntico
             ao sha256 registrado nessa entrada.

        Retorna (True, "") se válido.
        Retorna (False, motivo) nos casos:
          - entrada ausente no Manifest: "provenance_missing"
          - SHA-256 divergente: "integrity_mismatch"
          - arquivo físico não encontrado em raw_dir: "file_not_found"
        Lança IOError se não for possível calcular o hash do arquivo.
        """
        # Buscar entrada no Manifest
        entry = None
        for e in self.load_entries():
            if e.get("stored_filename") == stored_filename:
                entry = e
                break

        if entry is None:
            return False, "provenance_missing"

        # Verificar existência física
        arquivo_path = raw_dir / stored_filename
        if not arquivo_path.exists():
            return False, "file_not_found"

        # Calcular SHA-256 atual (pode levantar IOError)
        sha256_atual = compute_sha256(arquivo_path)

        # Comparar com o registrado
        if sha256_atual != entry.get("sha256"):
            return False, "integrity_mismatch"

        return True, ""

"""Módulos de dados do pipeline de construção do corpus piloto."""

from .config import CorpusConfig
from .manifest import ManifestWriter
from .ingestor import Ingestor, IngestorResult
from .auditor import (
    Auditor,
    AuditResult,
    ConditionalAnalysis,
    FieldAnalysisStatus,
    PendingManifestError,
    ProvenanceError,
)
from .canonizador import Canonizador, CanonicalizationResult
from .seletor import SeletorExperimental, SelectionResult, FingerprintMismatchError

__all__ = [
    "CorpusConfig",
    "ManifestWriter",
    "Ingestor",
    "IngestorResult",
    "Auditor",
    "AuditResult",
    "ConditionalAnalysis",
    "FieldAnalysisStatus",
    "PendingManifestError",
    "ProvenanceError",
    "Canonizador",
    "CanonicalizationResult",
    "SeletorExperimental",
    "SelectionResult",
    "FingerprintMismatchError",
]

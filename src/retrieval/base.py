"""Interface comum de recuperação para as arquiteturas do experimento.

Esta camada define o contrato que as três arquiteturas (estruturada, vetorial,
híbrida) deverão cumprir para receber a MESMA consulta textual e devolver
resultados num formato homogêneo, auditável e reproduzível.

Princípios (ver spec protocolo-experimental e steering metodologia):
- A entrada é apenas o TEXTO da consulta (uma formulação em linguagem natural).
- A interface NÃO conhece a ficha de invariantes (NeedSheet): nada de need_id,
  nature, mandatory_conditions, requested_facts, respostas candidatas ou gold.
- O resultado registra o suficiente para reproduzir a execução: a consulta, a
  arquitetura, os documentos (doc_id), a ordem (rank), score quando aplicável,
  evidências/campos usados e metadados de reprodutibilidade.
- Nem toda arquitetura tem score natural (a estruturada, por filtros, não tem):
  nesse caso `score` é None e NÃO deve ser inventado.

Esta camada não executa nenhuma arquitetura por si; apenas define os tipos e o
protocolo. As implementações concretas ficam em módulos próprios (ex.:
`structured.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RetrievedDocument:
    """Um documento recuperado para uma consulta.

    `rank` é a posição (1-based) na ordem retornada pela arquitetura.
    `score` é a pontuação quando a arquitetura a produz; None quando não há
    pontuação natural (ex.: recuperação por filtros estruturados) — nunca
    inventar um valor.
    `evidence` descreve, de forma auditável, por que o documento foi retornado
    (ex.: os campos/condições que ele satisfez).
    """

    doc_id: str
    rank: int
    score: float | None = None
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalResult:
    """Resultado completo de uma execução de recuperação, auditável.

    Campos:
    - query: o texto exato submetido.
    - architecture: identificador da arquitetura (ex.: "structured").
    - documents: lista ordenada de RetrievedDocument (rank crescente).
    - fields_used: campos do corpus efetivamente usados na recuperação.
    - diagnostics: informações para reproduzir/entender a execução (ex.: condições
      identificadas, se houve interpretação vazia, versão, fingerprint do corpus).
    """

    query: str
    architecture: str
    documents: list[RetrievedDocument]
    fields_used: list[str] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)

    @property
    def n_documents(self) -> int:
        return len(self.documents)

    @property
    def doc_ids(self) -> list[str]:
        return [d.doc_id for d in self.documents]


@runtime_checkable
class Retriever(Protocol):
    """Protocolo comum das arquiteturas de recuperação.

    Uma implementação recebe o TEXTO de uma formulação e devolve um
    RetrievalResult. Não recebe a ficha nem o gold.
    """

    architecture_name: str

    def retrieve(self, query: str) -> RetrievalResult:
        """Executa a recuperação para a consulta textual informada."""
        ...

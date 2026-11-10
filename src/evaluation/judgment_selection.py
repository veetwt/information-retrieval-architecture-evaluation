"""Seleção reduzida para JULGAMENTO HUMANO (Alternativa B).

Etapa SEPARADA do gerador de pools (`pool_generator.py`): preserva a recuperação
sobre os 21.631 acórdãos e a profundidade D=50, mas deriva uma lista
determinística de até 67 pares `(need_id, doc_id)` para avaliação humana,
conforme a adaptação metodológica aprovada e documentada em
`docs/experimento/proposta_operacional_avaliacao_e_gold.md` §12.

Composição do conjunto de julgamento (recorte aprovado):
1. União dos **top-5** das arquiteturas vetorial e híbrida, nas três formulações
   de cada necessidade, deduplicada por `(need_id, doc_id)`;
2. Universo **estrito** da NI-003: documentos que satisfazem
   `ENTIDADE = ANTT` (variantes/multivalor) **E** `TIPOPROCESSO = Representação`.
   Este universo é calculado AQUI, de forma independente, e **não** reutiliza a
   heurística ampla de `pool_generator._condition_complement`;
3. Documentos de **referência confirmados** de NI-001 e NI-002, incluídos apenas
   se ausentes no conjunto de julgamento da respectiva necessidade.

Princípios:
- NÃO modifica os recuperadores, o corpus, os índices nem as fichas.
- NÃO atribui rótulos de relevância e NÃO constrói gold.
- A recuperação completa (top-D=50) é preservada no registro; o top-5 é apenas o
  corte de JULGAMENTO (distinto da profundidade de recuperação).
- Documentos fora do conjunto de julgamento permanecem com relevância
  DESCONHECIDA — nunca automaticamente irrelevantes.
- Teto RÍGIDO de 67 julgamentos: se o conjunto obrigatório ultrapassar o teto, a
  preparação é INTERROMPIDA com a contagem; nenhum documento é descartado
  silenciosamente para caber.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    from evaluation.need_sheet import NeedSheet
    from retrieval.hybrid import HybridRetriever
except ImportError:  # pragma: no cover
    from .need_sheet import NeedSheet
    from ..retrieval.hybrid import HybridRetriever


SELECTION_VERSION = "0.1.0"

# Corte de JULGAMENTO humano (distinto de D=50, a profundidade de recuperação).
JUDGMENT_TOPK = 5
# Profundidade de recuperação preservada no registro completo (não é o corte).
RECORD_DEPTH = 50
# Teto RÍGIDO de julgamentos humanos distintos aprovado (Alternativa B §12.2).
JUDGMENT_CAP = 67

# Limiar DIAGNÓSTICO (não experimental) para sinalizar um conjunto estruturado
# como "excessivamente amplo": fração do corpus a partir da qual o conjunto é
# grande o bastante para indicar interpretação pouco restritiva. Apenas descreve;
# não altera o conjunto nem impõe ranking.
BROAD_SET_RATIO = 0.5

FORMULATIONS = ("direct", "paraphrase", "verbose")

# Documentos de referência CONFIRMADOS (conferência factual concluída em tarefas
# anteriores; registrados nos comentários das fichas, não em campo estruturado).
# São passados explicitamente para manter a seleção auditável sem alterar as
# fichas validadas. Chave: need_id -> lista de doc_ids de referência.
DEFAULT_REFERENCES: dict[str, tuple[str, ...]] = {
    "NI-001": ("tcu-b8b9f99c805c",),  # ACORDAO-COMPLETO-2641518 (denúncia Sesc/MS)
    "NI-002": ("tcu-5567c745c20f",),  # Acórdão 16/2024 - Plenário
}

# Need_id cujo universo estrito é incluído integralmente (ANTT + Representação).
STRICT_UNIVERSE_NEED = "NI-003"

MANIFEST_FILE = "judgment_manifest.json"
JUDGMENT_FILE = "judgment_candidates.parquet"
RECORD_FILE = "retrieval_record.parquet"


class JudgmentCapExceeded(Exception):
    """Levantada quando o conjunto obrigatório ultrapassa o teto aprovado."""

    def __init__(self, required: int, cap: int, breakdown: dict):
        self.required = required
        self.cap = cap
        self.breakdown = breakdown
        super().__init__(
            f"Conjunto obrigatório de julgamento ({required}) excede o teto "
            f"aprovado ({cap}). Nenhum documento foi descartado. "
            f"Composição: {breakdown}"
        )


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: object) -> str:
    s = "" if s is None else str(s)
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", s).strip().lower()


def strict_antt_representation_universe(df: pd.DataFrame) -> list[str]:
    """doc_ids que satisfazem ESTRITAMENTE ENTIDADE=ANTT E TIPOPROCESSO=REPR.

    Critério independente e explícito (NÃO é a heurística ampla de substring do
    complemento por condições):
    - ENTIDADE: contém a denominação da Agência Nacional de Transportes
      Terrestres ("transportes terrestres") OU a sigla isolada "antt"
      (considerando variantes e valores múltiplos no mesmo campo);
    - TIPOPROCESSO: é Representação — contém "representacao" ou a sigla "repr".
    """
    ent = df["ENTIDADE"].astype(str).map(_norm)
    tp = df["TIPOPROCESSO"].astype(str).map(_norm)
    antt_mask = ent.str.contains("transportes terrestres") | ent.str.contains(r"\bantt\b")
    repr_mask = tp.str.contains("representacao") | tp.str.contains(r"\brepr\b")
    sel = df[antt_mask & repr_mask]
    return sorted(str(d) for d in sel["doc_id"].tolist())


@dataclass
class PairOrigin:
    """Origens de inclusão de um par (need_id, doc_id) no conjunto de julgamento."""

    top5_vector: bool = False
    top5_hybrid: bool = False
    strict_universe: bool = False     # universo estrito ANTT+REPR (NI-003)
    reference: bool = False           # documento de referência confirmado
    # formulações em que o doc apareceu no top-5 de cada arquitetura
    vector_formulations: list[str] = field(default_factory=list)
    hybrid_formulations: list[str] = field(default_factory=list)

    def sources(self) -> list[str]:
        out = []
        if self.top5_vector:
            out.append("top5_vector")
        if self.top5_hybrid:
            out.append("top5_hybrid")
        if self.strict_universe:
            out.append("strict_universe_ni003")
        if self.reference:
            out.append("reference")
        return out


class JudgmentSelector:
    """Deriva o conjunto reduzido de julgamento humano (Alternativa B)."""

    def __init__(
        self,
        hybrid: HybridRetriever,
        *,
        selection_df: pd.DataFrame,
        selection_fingerprint: str,
        index_meta: dict,
        references: dict[str, tuple[str, ...]] | None = None,
        topk: int = JUDGMENT_TOPK,
        record_depth: int = RECORD_DEPTH,
        cap: int = JUDGMENT_CAP,
    ) -> None:
        self._hybrid = hybrid
        self._structured = hybrid._structured
        self._vector = hybrid._vector
        self._df = selection_df
        self._fingerprint = selection_fingerprint
        self._index_meta = index_meta
        self._references = dict(DEFAULT_REFERENCES if references is None else references)
        self.topk = topk
        self.record_depth = record_depth
        self.cap = cap
        self._corpus_ids = set(str(d) for d in selection_df["doc_id"].tolist())

    @classmethod
    def from_artifacts(
        cls,
        selection_parquet: Path,
        index_dir: Path,
        *,
        references: dict[str, tuple[str, ...]] | None = None,
        topk: int = JUDGMENT_TOPK,
        record_depth: int = RECORD_DEPTH,
        cap: int = JUDGMENT_CAP,
        model=None,
    ) -> "JudgmentSelector":
        """Constrói o seletor preservando D=50 no registro de recuperação.

        `display_limit` é configurado como >= record_depth (50) para não truncar
        o ranking antes de registrar a recuperação completa; o corte top-5 é
        aplicado DEPOIS, apenas para o conjunto de julgamento.
        """
        selection_parquet = Path(selection_parquet)
        index_dir = Path(index_dir)
        display_limit = max(record_depth, topk)
        hybrid = HybridRetriever.from_artifacts(
            selection_parquet, index_dir, model=model,
            display_limit=display_limit, verify_integrity=True,
        )
        df = pd.read_parquet(selection_parquet, engine="pyarrow")
        index_meta = hybrid._vector._index.meta
        fp = index_meta.get("selection_fingerprint")
        return cls(
            hybrid, selection_df=df, selection_fingerprint=fp, index_meta=index_meta,
            references=references, topk=topk, record_depth=record_depth, cap=cap,
        )

    # ------------------------------------------------------------------ #
    # Recuperação (registro completo top-D) + derivação do top-5
    # ------------------------------------------------------------------ #

    def _retrieve(self, need_id: str, formulation: str, query: str) -> dict:
        v = self._vector.retrieve(query)
        h = self._hybrid.retrieve(query)
        # Estruturada: CONJUNTO completo, SEM ranking (score=None; não se inventa
        # ordem de relevância). Registrada apenas no retrieval_record; NÃO entra
        # no corte top-5 do conjunto de julgamento (desenho Alternativa B).
        s = self._structured.retrieve(query)
        structured_set = [str(d.doc_id) for d in s.documents]
        structured_conditions = s.diagnostics.get("identified_conditions", {})
        n_corpus = s.diagnostics.get("n_corpus")
        no_conditions = bool(s.diagnostics.get("no_conditions_identified", False))
        # "Excessivamente amplo" é uma OBSERVAÇÃO factual (tamanho do conjunto
        # relativo ao corpus), não um ranking: sinaliza quando o interpretador
        # reconheceu poucas/nenhuma condição e devolveu um conjunto grande.
        overly_broad = bool(
            n_corpus and structured_set
            and len(structured_set) >= BROAD_SET_RATIO * int(n_corpus)
        )
        vec_full = [(str(d.doc_id), float(d.score)) for d in v.documents[: self.record_depth]]
        hyb_full = [
            (str(d.doc_id), float(d.score) if d.score is not None else None)
            for d in h.documents[: self.record_depth]
        ]
        return {
            "need_id": need_id,
            "formulation": formulation,
            "query": query,
            "vector_full": vec_full,         # até D=50 (registro completo)
            "hybrid_full": hyb_full,         # até D=50 (registro completo)
            "vector_top5": [d for d, _ in vec_full[: self.topk]],
            "hybrid_top5": [d for d, _ in hyb_full[: self.topk]],
            "hybrid_path": h.diagnostics.get("path"),
            # estruturada (conjunto completo, sem ordenação de relevância)
            "structured_set": structured_set,
            "structured_set_size": len(structured_set),
            "structured_conditions": structured_conditions,
            "structured_no_conditions": no_conditions,
            "structured_overly_broad": overly_broad,
            "structured_n_corpus": n_corpus,
        }

    # ------------------------------------------------------------------ #
    # Composição do conjunto de julgamento de UMA necessidade
    # ------------------------------------------------------------------ #

    def select_need(self, sheet: NeedSheet) -> tuple[dict[str, PairOrigin], list[dict]]:
        """Retorna (origens por doc_id, registros de recuperação) de uma necessidade."""
        need_id = sheet.need_id
        origins: dict[str, PairOrigin] = {}
        records: list[dict] = []

        def ensure(doc_id: str) -> PairOrigin:
            po = origins.get(doc_id)
            if po is None:
                po = PairOrigin()
                origins[doc_id] = po
            return po

        # (1) top-5 vetorial e híbrido, nas três formulações
        for f in FORMULATIONS:
            query = getattr(sheet.formulations, f)
            if not query:
                continue
            r = self._retrieve(need_id, f, query)
            records.append({
                "need_id": need_id,
                "formulation": f,
                "query": r["query"],
                "vector_top5": json.dumps(r["vector_top5"], ensure_ascii=False),
                "hybrid_top5": json.dumps(r["hybrid_top5"], ensure_ascii=False),
                "vector_full_topD": json.dumps(r["vector_full"], ensure_ascii=False),
                "hybrid_full_topD": json.dumps(r["hybrid_full"], ensure_ascii=False),
                "hybrid_path": r["hybrid_path"],
                # Estruturada: conjunto COMPLETO (sem ranking), tamanho, condições
                # reconhecidas e sinalizadores factuais (sem condição / amplo).
                "structured_set": json.dumps(r["structured_set"], ensure_ascii=False),
                "structured_set_size": r["structured_set_size"],
                "structured_conditions": json.dumps(r["structured_conditions"], ensure_ascii=False),
                "structured_no_conditions": r["structured_no_conditions"],
                "structured_overly_broad": r["structured_overly_broad"],
                "record_depth": self.record_depth,
                "judgment_topk": self.topk,
            })
            for did in r["vector_top5"]:
                po = ensure(did)
                po.top5_vector = True
                if f not in po.vector_formulations:
                    po.vector_formulations.append(f)
            for did in r["hybrid_top5"]:
                po = ensure(did)
                po.top5_hybrid = True
                if f not in po.hybrid_formulations:
                    po.hybrid_formulations.append(f)

        # (2) universo estrito ANTT+REPR, apenas para a NI-003
        if need_id == STRICT_UNIVERSE_NEED:
            for did in strict_antt_representation_universe(self._df):
                ensure(did).strict_universe = True

        # (3) referências confirmadas, apenas se ausentes
        for did in self._references.get(need_id, ()):  # noqa: B007
            if did not in self._corpus_ids:
                # referência fora da seleção congelada: não inventar; registrar aviso
                records.append({
                    "need_id": need_id, "formulation": "__reference_warning__",
                    "query": f"referencia {did} NAO esta na selecao congelada",
                    "vector_top5": "[]", "hybrid_top5": "[]",
                    "vector_full_topD": "[]", "hybrid_full_topD": "[]",
                    "hybrid_path": None,
                    "structured_set": "[]", "structured_set_size": 0,
                    "structured_conditions": "{}",
                    "structured_no_conditions": True,
                    "structured_overly_broad": False,
                    "record_depth": self.record_depth,
                    "judgment_topk": self.topk,
                })
                continue
            po = origins.get(did)
            if po is None:
                ensure(did).reference = True  # ausente → incluído como referência
            else:
                po.reference = True  # já presente por outra origem; apenas anota

        return origins, records

    # ------------------------------------------------------------------ #
    # Execução completa + escrita + validação do teto
    # ------------------------------------------------------------------ #

    def run(
        self,
        sheets: list[NeedSheet],
        out_dir: Path,
        run_id: str,
        *,
        enforce_cap: bool = True,
    ) -> dict:
        """Compõe o conjunto de julgamento, valida o teto e grava os artefatos.

        Levanta `JudgmentCapExceeded` (sem gravar) se o total obrigatório exceder
        o teto e `enforce_cap=True` — nenhum documento é descartado para caber.
        """
        out_dir = Path(out_dir)

        all_candidates: list[dict] = []
        all_records: list[dict] = []
        per_need_summary: list[dict] = []

        for sheet in sheets:
            origins, records = self.select_need(sheet)
            all_records.extend(records)
            need_counts = {
                "top5_vector": 0, "top5_hybrid": 0,
                "strict_universe_ni003": 0, "reference": 0,
            }
            for did, po in sorted(origins.items()):
                srcs = po.sources()
                for s in srcs:
                    need_counts[s] = need_counts.get(s, 0) + 1
                all_candidates.append({
                    "run_id": run_id,
                    "need_id": sheet.need_id,
                    "doc_id": did,
                    "inclusion_sources": json.dumps(srcs, ensure_ascii=False),
                    "n_inclusion_sources": len(srcs),
                    "top5_vector": po.top5_vector,
                    "top5_hybrid": po.top5_hybrid,
                    "strict_universe": po.strict_universe,
                    "reference": po.reference,
                    "vector_formulations": json.dumps(po.vector_formulations, ensure_ascii=False),
                    "hybrid_formulations": json.dumps(po.hybrid_formulations, ensure_ascii=False),
                })
            per_need_summary.append({
                "need_id": sheet.need_id,
                "n_judgments": len(origins),
                "by_source": need_counts,
            })

        # unicidade (run_id, need_id, doc_id)
        keys = [(c["run_id"], c["need_id"], c["doc_id"]) for c in all_candidates]
        if len(keys) != len(set(keys)):
            raise ValueError("Violação de unicidade em (run_id, need_id, doc_id).")

        total = len(all_candidates)

        # sobreposições (quantos pares vêm de mais de uma origem)
        overlaps = {
            "pairs_from_multiple_sources": sum(
                1 for c in all_candidates if c["n_inclusion_sources"] > 1
            ),
            "vector_and_hybrid": sum(
                1 for c in all_candidates if c["top5_vector"] and c["top5_hybrid"]
            ),
            "strict_and_ranking": sum(
                1 for c in all_candidates
                if c["strict_universe"] and (c["top5_vector"] or c["top5_hybrid"])
            ),
            "reference_already_present": sum(
                1 for c in all_candidates
                if c["reference"] and (c["top5_vector"] or c["top5_hybrid"] or c["strict_universe"])
            ),
        }

        breakdown = {
            "total_judgments": total,
            "cap": self.cap,
            "per_need": per_need_summary,
            "overlaps": overlaps,
        }

        if enforce_cap and total > self.cap:
            raise JudgmentCapExceeded(total, self.cap, breakdown)

        # grava artefatos
        out_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(all_candidates).to_parquet(out_dir / JUDGMENT_FILE, engine="pyarrow", index=False)
        pd.DataFrame(all_records).to_parquet(out_dir / RECORD_FILE, engine="pyarrow", index=False)

        manifest = {
            "selection_version": SELECTION_VERSION,
            "run_id": run_id,
            "created_at": _utcnow(),
            "design": "alternativa_b_recorte_reduzido_julgamento",
            "selection_fingerprint": self._fingerprint,
            "index": {
                "model_name": self._index_meta.get("model_name"),
                "embedding_dim": self._index_meta.get("embedding_dim"),
                "n_docs_indexed": self._index_meta.get("n_docs_indexed"),
                "n_chunks": self._index_meta.get("n_chunks"),
                "is_partial_index": self._index_meta.get("is_partial_index"),
            },
            "retriever_versions": {
                "structured": getattr(self._structured, "VERSION", None),
                "vector": getattr(self._vector, "VERSION", None),
                "hybrid": getattr(self._hybrid, "VERSION", None),
            },
            "params": {
                "judgment_topk": self.topk,
                "record_depth_D": self.record_depth,
                "cap": self.cap,
                "strict_universe_need": STRICT_UNIVERSE_NEED,
                "references": {k: list(v) for k, v in self._references.items()},
            },
            "counts": {
                "n_needs": len(sheets),
                "n_judgments": total,
                "n_record_rows": len(all_records),
            },
            "per_need": per_need_summary,
            "overlaps": overlaps,
            "note": (
                "SEM rotulos de relevancia; SEM gold. Documentos fora deste "
                "conjunto permanecem com relevancia DESCONHECIDA, nunca "
                "automaticamente irrelevantes. D=50 preservado no registro; "
                "top-5 e apenas o corte de julgamento."
            ),
        }
        (out_dir / MANIFEST_FILE).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return manifest


@dataclass
class JudgmentCheck:
    ok: bool
    total: int
    cap: int
    reasons: list[str] = field(default_factory=list)


def validate_judgment_manifest(manifest: dict, sheets: list[NeedSheet]) -> JudgmentCheck:
    """Valida a integridade do recorte de julgamento SEM desabilitar verificações.

    Condições: índice não parcial; fingerprint presente; topk=5; D=50 registrado;
    total ≤ cap; todas as fichas `validated`; contagem de necessidades coerente.
    """
    from evaluation.need_sheet import ValidationStatus  # local para evitar ciclo
    reasons: list[str] = []
    idx = manifest.get("index", {})
    if idx.get("is_partial_index"):
        reasons.append("índice parcial")
    if not manifest.get("selection_fingerprint"):
        reasons.append("selection_fingerprint ausente")
    params = manifest.get("params", {})
    if params.get("judgment_topk") != JUDGMENT_TOPK:
        reasons.append(f"judgment_topk != {JUDGMENT_TOPK}")
    if params.get("record_depth_D") != RECORD_DEPTH:
        reasons.append(f"record_depth_D != {RECORD_DEPTH}")
    counts = manifest.get("counts", {})
    total = int(counts.get("n_judgments", -1))
    cap = int(params.get("cap", JUDGMENT_CAP))
    if total > cap:
        reasons.append(f"total {total} excede cap {cap}")
    if counts.get("n_needs") != len(sheets):
        reasons.append("contagem de necessidades divergente")
    drafts = [
        s.need_id for s in sheets
        if s.equivalence_validation.status != ValidationStatus.VALIDATED
    ]
    if drafts:
        reasons.append(f"fichas não validadas: {drafts}")
    return JudgmentCheck(ok=(len(reasons) == 0), total=total, cap=cap, reasons=reasons)

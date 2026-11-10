"""Gerador de pools de candidatos para julgamento (SEM rótulos de relevância).

Produz, de forma reprodutível e auditável, o conjunto de documentos que será
submetido ao julgamento humano de relevância, a partir das três arquiteturas de
recuperação já implementadas (estruturada, vetorial, híbrida), SEM modificar seus
algoritmos e SEM criar ranking artificial para a estruturada.

Política implementada (aprovada; ver
`docs/experimento/proposta_operacional_avaliacao_e_gold.md`):

- parâmetros: D=50 (profundidade de pooling), T=100 (teto do conjunto
  estruturado), T_cond=100 (teto do complemento por condições),
  k_cuts=[5,10,50]; amostragem 95%/p=0,5/e=0,10 com correção de população finita;
- base determinística J0 = (top-D vetorial/híbrido de cada formulação) ∪
  (conjuntos estruturados com |C| ≤ T) ∪ (complemento por condições com
  |P_cond| ≤ T_cond);
- para conjuntos estruturados com |C| > T: estrato I = C ∩ J0; estrato R = C \\ J0;
  amostra por formulação, independente entre formulações, com seed determinística;
- complemento por condições com |P_cond| > T_cond: amostra do restante fora de
  J0, desenho separado;
- deduplicação por (need_id, doc_id); julgamento único, planos de inclusão
  preservados por formulação/fonte;
- NÃO produz rótulos de relevância; NÃO congela gold.

Estados: a execução é `exploratory` por padrão; só é `official` quando TODAS as
validações passam (ver `validate_official`). Fichas em `draft` NÃO geram pool
oficial.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    from evaluation.need_sheet import NeedSheet, ValidationStatus
    from evaluation.pool_sampling import StratumPlan, plan_stratified
    from retrieval.hybrid import HybridRetriever
except ImportError:  # pragma: no cover
    from .need_sheet import NeedSheet, ValidationStatus
    from .pool_sampling import StratumPlan, plan_stratified
    from ..retrieval.hybrid import HybridRetriever


POOL_VERSION = "0.1.0"
DEFAULT_D = 50
DEFAULT_T = 100
DEFAULT_T_COND = 100
DEFAULT_K_CUTS = (5, 10, 50)
FORMULATIONS = ("direct", "paraphrase", "verbose")

MANIFEST_FILE = "pool_manifest.json"
RAW_FILE = "retrieval_raw.parquet"
CANDIDATES_FILE = "pool_candidates.parquet"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FormulationRetrieval:
    """Saída bruta de recuperação de UMA formulação de UMA necessidade."""

    need_id: str
    formulation: str
    query: str
    structured_set: list[str]            # conjunto completo da estruturada (sem ranking)
    structured_conditions: dict          # condições reconhecidas pela estruturada
    vector_topD: list[tuple[str, float]] # (doc_id, score) top-D vetorial
    hybrid_topD: list[tuple[str, float]] # (doc_id, score) top-D híbrida
    hybrid_path: str | None              # caminho A/B/C da híbrida


class PoolGenerator:
    """Orquestra a geração de pools a partir dos artefatos congelados."""

    def __init__(
        self,
        hybrid: HybridRetriever,
        *,
        selection_df: pd.DataFrame,
        selection_fingerprint: str,
        index_meta: dict,
        D: int = DEFAULT_D,
        T: int = DEFAULT_T,
        T_cond: int = DEFAULT_T_COND,
        k_cuts: tuple[int, ...] = DEFAULT_K_CUTS,
    ) -> None:
        self._hybrid = hybrid
        self._structured = hybrid._structured  # reuso, sem alterar o algoritmo
        self._vector = hybrid._vector
        self._df = selection_df
        self._selection_fingerprint = selection_fingerprint
        self._index_meta = index_meta
        self.D = D
        self.T = T
        self.T_cond = T_cond
        self.k_cuts = tuple(k_cuts)
        # Índice doc_id -> linha (para o complemento por condições de metadados).
        self._by_doc = {str(r.doc_id): r for r in self._df.itertuples(index=False)}

    # ------------------------------------------------------------------ #
    # Construção
    # ------------------------------------------------------------------ #

    @classmethod
    def from_artifacts(
        cls,
        selection_parquet: Path,
        index_dir: Path,
        *,
        D: int = DEFAULT_D,
        T: int = DEFAULT_T,
        T_cond: int = DEFAULT_T_COND,
        k_cuts: tuple[int, ...] = DEFAULT_K_CUTS,
        model=None,
    ) -> "PoolGenerator":
        """Constrói o gerador validando a compatibilidade seleção↔índice.

        Reusa `HybridRetriever.from_artifacts(verify_integrity=True)`, que valida
        fingerprint, correspondência de doc_id e rejeita índice parcial. O
        `display_limit` é configurado como >= ao maior corte/profundidade para
        não truncar os rankings antes do pooling.
        """
        selection_parquet = Path(selection_parquet)
        index_dir = Path(index_dir)
        display_limit = max(max(k_cuts), D)
        hybrid = HybridRetriever.from_artifacts(
            selection_parquet, index_dir, model=model,
            display_limit=display_limit, verify_integrity=True,
        )
        df = pd.read_parquet(selection_parquet, engine="pyarrow")
        index_meta = hybrid._vector._index.meta
        fp = index_meta.get("selection_fingerprint")
        return cls(
            hybrid, selection_df=df, selection_fingerprint=fp,
            index_meta=index_meta, D=D, T=T, T_cond=T_cond, k_cuts=tuple(k_cuts),
        )

    # ------------------------------------------------------------------ #
    # Recuperação por formulação
    # ------------------------------------------------------------------ #

    def _retrieve_formulation(self, need_id: str, formulation: str, query: str) -> FormulationRetrieval:
        """Executa as três arquiteturas para uma formulação (texto apenas)."""
        s_res = self._structured.retrieve(query)
        structured_set = [str(d.doc_id) for d in s_res.documents]
        conditions = dict(s_res.diagnostics.get("identified_conditions", {}))

        v_res = self._vector.retrieve(query)
        vector_topD = [(str(d.doc_id), float(d.score)) for d in v_res.documents[: self.D]]

        h_res = self._hybrid.retrieve(query)
        hybrid_topD = [
            (str(d.doc_id), float(d.score) if d.score is not None else float("nan"))
            for d in h_res.documents[: self.D]
        ]
        hybrid_path = h_res.diagnostics.get("path")

        return FormulationRetrieval(
            need_id=need_id, formulation=formulation, query=query,
            structured_set=structured_set, structured_conditions=conditions,
            vector_topD=vector_topD, hybrid_topD=hybrid_topD, hybrid_path=hybrid_path,
        )

    # ------------------------------------------------------------------ #
    # Complemento por condições de metadados verificáveis
    # ------------------------------------------------------------------ #

    def _condition_complement(self, sheet: NeedSheet) -> list[str]:
        """doc_ids do corpus que satisfazem as condições de metadados da ficha.

        Apenas condições `relates_to == metadata` com `fields` informados são
        aplicadas (verificáveis deterministicamente). Condições textuais NÃO
        geram complemento. Aplicação por substring normalizada sobre os campos
        citados — independente de qualquer recuperador e do gold.
        """
        meta_conds = [
            c for c in sheet.mandatory_conditions
            if c.relates_to.value == "metadata" and c.fields
        ]
        if not meta_conds:
            return []
        # Uma condição é satisfeita se TODOS os seus campos citados contêm algum
        # termo não vazio da descrição (heurística conservadora e determinística,
        # sem gold). O complemento é a interseção das condições (AND).
        import re
        import unicodedata

        def _norm(s: object) -> str:
            s = "" if s is None else str(s)
            s = "".join(c for c in unicodedata.normalize("NFD", s)
                        if unicodedata.category(c) != "Mn")
            return re.sub(r"\s+", " ", s).strip().lower()

        selected: set[str] | None = None
        for c in meta_conds:
            desc = _norm(c.description)
            terms = [t for t in re.split(r"[^a-z0-9]+", desc) if len(t) >= 4]
            matched: set[str] = set()
            for did, row in self._by_doc.items():
                ok = True
                for fld in c.fields:
                    val = _norm(getattr(row, fld, ""))
                    if not any(t in val for t in terms):
                        ok = False
                        break
                if ok:
                    matched.add(did)
            selected = matched if selected is None else (selected & matched)
        return sorted(selected or set())

    # ------------------------------------------------------------------ #
    # Geração do pool de uma necessidade
    # ------------------------------------------------------------------ #

    def generate_need(
        self, sheet: NeedSheet, run_seed: int
    ) -> tuple[list[dict], list[dict]]:
        """Gera (linhas_raw, linhas_candidatos) de uma necessidade.

        Passos (política aprovada):
        1. recupera as três formulações;
        2. monta J0 determinístico;
        3. estratifica conjuntos estruturados > T e complemento > T_cond;
        4. deduplica candidatos por (need_id, doc_id), preservando plano por
           formulação/fonte.
        """
        need_id = sheet.need_id
        retrievals: dict[str, FormulationRetrieval] = {}
        for f in FORMULATIONS:
            query = getattr(sheet.formulations, f)
            if not query:
                continue
            retrievals[f] = self._retrieve_formulation(need_id, f, query)

        # Complemento por condições (independe de formulação; da ficha).
        cond_complement = self._condition_complement(sheet)

        # --- (2) J0 determinístico ---
        j0: set[str] = set()
        for r in retrievals.values():
            j0.update(d for d, _ in r.vector_topD)
            j0.update(d for d, _ in r.hybrid_topD)
            if len(r.structured_set) <= self.T:
                j0.update(r.structured_set)
        if len(cond_complement) <= self.T_cond:
            j0.update(cond_complement)

        # --- (3) estratificação dos conjuntos estruturados > T, por formulação ---
        struct_plans: dict[str, StratumPlan] = {}
        for f, r in retrievals.items():
            if len(r.structured_set) > self.T:
                struct_plans[f] = plan_stratified(
                    r.structured_set, j0, run_seed,
                    seed_parts=(need_id, f, "struct"), teto=self.T,
                )

        # complemento por condições > T_cond: desenho separado
        cond_plan: StratumPlan | None = None
        if len(cond_complement) > self.T_cond:
            cond_plan = plan_stratified(
                cond_complement, j0, run_seed,
                seed_parts=(need_id, "cond"), teto=self.T_cond,
            )

        # --- documentos efetivamente a julgar ---
        to_judge: set[str] = set(j0)
        for plan in struct_plans.values():
            to_judge.update(plan.to_judge)
        if cond_plan is not None:
            to_judge.update(cond_plan.to_judge)

        # --- (4) linhas de candidatos (uma por (need_id, doc_id)) ---
        candidates: list[dict] = []
        for doc_id in sorted(to_judge):
            per_formulation = {}
            for f, r in retrievals.items():
                vec_rank = _rank_of(doc_id, r.vector_topD)
                hyb_rank = _rank_of(doc_id, r.hybrid_topD)
                in_struct = doc_id in set(r.structured_set)
                stratum = None
                inclusion_prob = None
                if in_struct and f in struct_plans:
                    plan = struct_plans[f]
                    if doc_id in set(plan.stratum_I):
                        stratum, inclusion_prob = "I", 1.0
                    elif doc_id in set(plan.sampled_R):
                        stratum, inclusion_prob = "R", plan.inclusion_prob_R
                recalled_by = []
                if in_struct:
                    recalled_by.append("structured")
                if vec_rank is not None:
                    recalled_by.append("vector")
                if hyb_rank is not None:
                    recalled_by.append("hybrid")
                per_formulation[f] = {
                    "recalled_by": recalled_by,
                    "hybrid_path": r.hybrid_path,
                    "vector_rank": vec_rank,
                    "hybrid_rank": hyb_rank,
                    "in_structured_set": in_struct,
                    "stratum": stratum,
                    "inclusion_prob": inclusion_prob,
                    "structured_population_N": (len(r.structured_set) if in_struct else None),
                }
            in_cond = doc_id in set(cond_complement)
            cond_stratum = None
            cond_prob = None
            if in_cond and cond_plan is not None:
                if doc_id in set(cond_plan.stratum_I):
                    cond_stratum, cond_prob = "I", 1.0
                elif doc_id in set(cond_plan.sampled_R):
                    cond_stratum, cond_prob = "R", cond_plan.inclusion_prob_R
            candidates.append({
                "run_id": None,  # preenchido na escrita
                "need_id": need_id,
                "doc_id": doc_id,
                "in_condition_complement": in_cond,
                "condition_stratum": cond_stratum,
                "condition_inclusion_prob": cond_prob,
                "per_formulation": json.dumps(per_formulation, ensure_ascii=False),
            })

        # --- linhas raw (uma por (need_id, formulation)) ---
        raw: list[dict] = []
        for f, r in retrievals.items():
            sp = struct_plans.get(f)
            raw.append({
                "run_id": None,
                "need_id": need_id,
                "formulation": f,
                "query": r.query,
                "structured_set": json.dumps(r.structured_set, ensure_ascii=False),
                "structured_set_size": len(r.structured_set),
                "structured_conditions": json.dumps(r.structured_conditions, ensure_ascii=False),
                "vector_topD": json.dumps(r.vector_topD, ensure_ascii=False),
                "hybrid_topD": json.dumps(r.hybrid_topD, ensure_ascii=False),
                "hybrid_path": r.hybrid_path,
                "struct_stratum": json.dumps(_plan_summary(sp), ensure_ascii=False) if sp else None,
            })
        return raw, candidates

    # ------------------------------------------------------------------ #
    # Execução completa + escrita
    # ------------------------------------------------------------------ #

    def run(
        self,
        sheets: list[NeedSheet],
        out_dir: Path,
        run_id: str,
        run_seed: int,
        *,
        status: str = "exploratory",
    ) -> dict:
        """Gera os pools de todas as fichas e grava os três artefatos.

        Grava sempre com `status` informado (nunca promove a 'official'
        automaticamente). A promoção a 'official' deve passar por
        `validate_official`.
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        all_raw: list[dict] = []
        all_cand: list[dict] = []
        need_summ: list[dict] = []
        for sheet in sheets:
            raw, cand = self.generate_need(sheet, run_seed)
            for row in raw:
                row["run_id"] = run_id
            for row in cand:
                row["run_id"] = run_id
            all_raw.extend(raw)
            all_cand.extend(cand)
            need_summ.append({
                "need_id": sheet.need_id,
                "status": sheet.equivalence_validation.status.value,
                "n_candidates": len(cand),
                "n_formulations": len(raw),
            })

        # unicidade (run_id, need_id, doc_id)
        keys = [(c["run_id"], c["need_id"], c["doc_id"]) for c in all_cand]
        if len(keys) != len(set(keys)):
            raise ValueError("Violação de unicidade em (run_id, need_id, doc_id).")

        pd.DataFrame(all_raw).to_parquet(out_dir / RAW_FILE, engine="pyarrow", index=False)
        pd.DataFrame(all_cand).to_parquet(out_dir / CANDIDATES_FILE, engine="pyarrow", index=False)

        manifest = {
            "pool_version": POOL_VERSION,
            "run_id": run_id,
            "created_at": _utcnow(),
            "status": status,
            "selection_fingerprint": self._selection_fingerprint,
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
                "D": self.D, "T": self.T, "T_cond": self.T_cond,
                "k_cuts": list(self.k_cuts),
                "display_limit_used": max(max(self.k_cuts), self.D),
                "sampling": {"z": 1.96, "p": 0.5, "e": 0.10, "fpc": True},
            },
            "run_seed": run_seed,
            "needs": need_summ,
            "counts": {
                "n_needs": len(sheets),
                "n_raw_rows": len(all_raw),
                "n_candidates": len(all_cand),
            },
        }
        (out_dir / MANIFEST_FILE).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return manifest


def _rank_of(doc_id: str, ranked: list[tuple[str, float]]) -> int | None:
    for i, (d, _) in enumerate(ranked, start=1):
        if d == doc_id:
            return i
    return None


def _plan_summary(plan: StratumPlan) -> dict:
    return {
        "N": plan.n_total, "n_I": plan.n_I, "n_R": plan.n_R,
        "s_R": plan.s_R, "inclusion_prob_R": plan.inclusion_prob_R,
        "sampled_R": plan.sampled_R,
    }


# ---------------------------------------------------------------------- #
# Validação do status oficial
# ---------------------------------------------------------------------- #

@dataclass
class OfficialCheck:
    ok: bool
    reasons: list[str] = field(default_factory=list)


def validate_official(manifest: dict, sheets: list[NeedSheet]) -> OfficialCheck:
    """Verifica se um pool pode ser classificado como oficial.

    Condições: índice não parcial; parâmetros aprovados; TODAS as fichas
    `validated` (nenhuma `draft`); contagens coerentes; fingerprint presente.
    NÃO promove nada — apenas decide.
    """
    reasons: list[str] = []
    idx = manifest.get("index", {})
    if idx.get("is_partial_index"):
        reasons.append("índice parcial")
    if not manifest.get("selection_fingerprint"):
        reasons.append("selection_fingerprint ausente")
    params = manifest.get("params", {})
    if params.get("D") != DEFAULT_D:
        reasons.append(f"D != {DEFAULT_D}")
    if params.get("T") != DEFAULT_T:
        reasons.append(f"T != {DEFAULT_T}")
    if list(params.get("k_cuts", [])) != list(DEFAULT_K_CUTS):
        reasons.append("k_cuts != [5,10,50]")
    drafts = [s.need_id for s in sheets
              if s.equivalence_validation.status != ValidationStatus.VALIDATED]
    if drafts:
        reasons.append(f"fichas em draft: {drafts}")
    counts = manifest.get("counts", {})
    if counts.get("n_needs") != len(sheets):
        reasons.append("contagem de necessidades divergente")
    return OfficialCheck(ok=(len(reasons) == 0), reasons=reasons)

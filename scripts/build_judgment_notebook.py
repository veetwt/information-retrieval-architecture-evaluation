"""Gera um CADERNO DE AVALIAÇÃO HUMANA (cego) para os pares oficiais.

A partir de `runs/judgment/<run_id>/judgment_candidates.parquet` e da seleção
congelada, produz um caderno legível por necessidade, em lotes de ~5 documentos,
SEM atribuir rótulos e SEM revelar sinais que possam enviesar o julgamento.

Ocultação deliberada (anti-viés): NÃO exibe a arquitetura que recuperou o
documento, posição de ranking, pontuação, origem de inclusão (inclusive se foi
documento de referência) nem qualquer suspeita de relevância. Essas informações
permanecem nos manifestos técnicos (`judgment_candidates.parquet`,
`judgment_manifest.json`), que NÃO são alterados.

Produz em `runs/judgment/<run_id>/caderno_humano/`:
- `NI-XXX_loteN.md`  — lotes de ~5 documentos por necessidade;
- `registro_julgamento.csv` — estrutura de registro com campos de decisão em
  branco (relevante/não relevante/incerto), evidência, revisora e data;
- `LEIA-ME.md` — instruções e critérios de relevância por necessidade.

NÃO cria o gold definitivo, NÃO calcula métricas, NÃO usa LLM para classificar.
"""

from __future__ import annotations

import argparse
import csv
import sys
import textwrap
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data.config import CorpusConfig  # noqa: E402

BATCH_SIZE = 5
ACORDAO_EXCERPT_CHARS = 2500  # trecho inicial fiel; integral acessível via fonte

# Metadados exibidos para conferência (sem sinais de recuperação).
META_FIELDS = ["COLEGIADO", "RELATOR", "TIPOPROCESSO", "DATASESSAO", "ENTIDADE", "UNIDADETECNICA"]


def _latest_selection(experimental_dir: Path, batch_id: str) -> Path:
    cands = sorted(experimental_dir.glob(f"selection_{batch_id}_*.parquet"))
    if not cands:
        raise FileNotFoundError(f"Seleção não encontrada em {experimental_dir}")
    return cands[-1]


def _load_fichas(needs_dir: Path) -> dict:
    """Lê as fichas validated e extrai os critérios de relevância (texto bruto)."""
    out = {}
    for p in sorted(needs_dir.glob("NI-*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        out[data["need_id"]] = data
    return out


def _criteria_block(ficha: dict) -> str:
    """Monta o bloco de critérios de relevância a partir da ficha validated."""
    lines = []
    lines.append(f"**Necessidade ({ficha['need_id']}, natureza: {ficha['nature']}):**")
    lines.append("")
    lines.append(ficha["description"].strip())
    lines.append("")
    card = ficha.get("answer_cardinality")
    if card:
        lines.append(f"- **Cardinalidade esperada:** {card}")
    conds = ficha.get("mandatory_conditions", [])
    if conds:
        lines.append("- **Condições obrigatórias:**")
        for c in conds:
            rel = c.get("relates_to", "")
            lines.append(f"  - ({rel}) {c['description'].strip()}")
    ev = ficha.get("required_textual_evidence", [])
    if ev:
        lines.append("- **Evidência textual exigida:**")
        for e in ev:
            lines.append(f"  - {e.strip()}")
    prr = ficha.get("partial_relevance_rule", "").strip()
    if prr:
        lines.append("- **Regra de relevância por documento (multidocumental):**")
        lines.append(f"  - {prr}")
    rf = ficha.get("requested_facts", [])
    if rf:
        lines.append("- **Fatos solicitados:** " + "; ".join(rf))
    return "\n".join(lines)


def _clean(text: object) -> str:
    s = "" if text is None else str(text)
    if s.strip().lower() == "nan":
        return "(vazio)"
    return s


def _doc_block(order: int, need_id: str, row: pd.Series) -> str:
    """Bloco legível de UM documento, sem sinais de recuperação."""
    doc_id = str(row["doc_id"])
    out = []
    out.append(f"### Documento {order} — `{doc_id}`")
    out.append("")
    out.append(f"- **doc_id:** `{doc_id}`")
    out.append(f"- **source_key:** `{_clean(row.get('source_key'))}`")
    out.append("")
    out.append("**Metadados:**")
    out.append("")
    out.append("| Campo | Valor |")
    out.append("|---|---|")
    for f in META_FIELDS:
        val = _clean(row.get(f)).replace("\n", " ").replace("|", "\\|")
        out.append(f"| {f} | {val} |")
    out.append("")
    out.append("**ASSUNTO (texto original):**")
    out.append("")
    out.append("> " + _clean(row.get("ASSUNTO")).replace("\n", "\n> "))
    out.append("")
    acordao = _clean(row.get("ACORDAO"))
    truncated = len(acordao) > ACORDAO_EXCERPT_CHARS
    excerpt = acordao[:ACORDAO_EXCERPT_CHARS]
    out.append("**ACÓRDÃO (trecho inicial, conteúdo preservado):**")
    out.append("")
    out.append("> " + excerpt.replace("\n", "\n> "))
    if truncated:
        out.append("")
        out.append(
            f"> […] *(trecho truncado em {ACORDAO_EXCERPT_CHARS} caracteres; "
            f"texto integral do campo ACORDAO disponível na seleção congelada, "
            f"linha doc_id=`{doc_id}`.)*"
        )
    out.append("")
    out.append(
        "**Como acessar o texto integral:** abrir a seleção congelada "
        "(`data/processed/experimental/selection_*.parquet`), filtrar por "
        f"`doc_id == \"{doc_id}\"` e ler os campos ASSUNTO, ACORDAO, SUMARIO, "
        "RELATORIO e VOTO na íntegra."
    )
    out.append("")
    out.append("**Decisão humana (preencher):** [ ] relevante [ ] não relevante [ ] incerto")
    out.append("")
    out.append("**Evidência/justificativa:** _________________________________________________")
    out.append("")
    out.append("---")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="oficial_recuperacao_altb_2026")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "configs" / "acordaos_tcu_2024.yaml"))
    parser.add_argument("--needs-dir", default=str(PROJECT_ROOT / "evaluation" / "questions" / "needs"))
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args(argv)

    run_dir = PROJECT_ROOT / "runs" / "judgment" / args.run_id
    cand_path = run_dir / "judgment_candidates.parquet"
    if not cand_path.exists():
        print(f"Candidatos oficiais não encontrados: {cand_path}")
        return 1

    config = CorpusConfig.load(Path(args.config))
    sel = _latest_selection(Path(config.experimental_dir), config.batch_id)
    df = pd.read_parquet(sel, engine="pyarrow").set_index("doc_id", drop=False)

    # Lê APENAS as colunas (need_id, doc_id) dos candidatos — ignora
    # deliberadamente colunas técnicas (origem/arquitetura/ranking/referência).
    cand = pd.read_parquet(cand_path, engine="pyarrow")[["need_id", "doc_id"]].copy()
    cand["doc_id"] = cand["doc_id"].astype(str)
    cand = cand.drop_duplicates(["need_id", "doc_id"]).sort_values(["need_id", "doc_id"]).reset_index(drop=True)

    fichas = _load_fichas(Path(args.needs_dir))
    out_dir = run_dir / "caderno_humano"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Registro de julgamento em branco (CSV).
    reg_path = out_dir / "registro_julgamento.csv"
    with open(reg_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "need_id", "doc_id", "decisao", "evidencia_justificativa",
            "revisora", "data_decisao",
        ])
        for _, r in cand.iterrows():
            # Campos de julgamento explicitamente PENDENTES/vazios.
            w.writerow([r["need_id"], r["doc_id"], "PENDENTE", "", "", ""])

    # LEIA-ME com critérios por necessidade.
    readme = [
        "# Caderno de Avaliação Humana — julgamento de relevância",
        "",
        f"Run oficial: `{args.run_id}`",
        "",
        "Este caderno apresenta os documentos selecionados para julgamento humano "
        "de relevância, organizados por necessidade e em lotes de "
        f"~{args.batch_size} documentos. **Nenhum rótulo foi atribuído.**",
        "",
        "O caderno é CEGO por desenho: não indica qual arquitetura recuperou cada "
        "documento, nem posição de ranking, pontuação ou origem de inclusão. "
        "Avalie cada documento apenas pelo seu conteúdo frente aos critérios da "
        "necessidade.",
        "",
        "Para cada documento, marque **relevante / não relevante / incerto** e "
        "registre a evidência. Consolide as decisões em `registro_julgamento.csv`.",
        "",
        "## Critérios de relevância por necessidade",
        "",
    ]
    for need_id in sorted(fichas):
        if need_id in set(cand["need_id"]):
            readme.append(_criteria_block(fichas[need_id]))
            readme.append("")
            readme.append("---")
            readme.append("")
    (out_dir / "LEIA-ME.md").write_text("\n".join(readme), encoding="utf-8")

    # Lotes por necessidade.
    summary = {}
    for need_id in sorted(cand["need_id"].unique()):
        sub = cand[cand["need_id"] == need_id].reset_index(drop=True)
        summary[need_id] = len(sub)
        n_batches = (len(sub) + args.batch_size - 1) // args.batch_size
        for b in range(n_batches):
            chunk = sub.iloc[b * args.batch_size:(b + 1) * args.batch_size]
            lines = [
                f"# {need_id} — Lote {b + 1} de {n_batches}",
                "",
                f"Documentos {b * args.batch_size + 1}–{b * args.batch_size + len(chunk)} "
                f"de {len(sub)} (necessidade {need_id}).",
                "",
                "> Critérios de relevância: ver `LEIA-ME.md`. Avaliação cega: nenhum "
                "sinal de recuperação é exibido.",
                "",
                "---",
                "",
            ]
            for i, (_, crow) in enumerate(chunk.iterrows(), start=b * args.batch_size + 1):
                doc_id = str(crow["doc_id"])
                if doc_id in df.index:
                    row = df.loc[doc_id]
                    if isinstance(row, pd.DataFrame):  # defesa contra doc_id duplicado
                        row = row.iloc[0]
                else:
                    row = pd.Series({"doc_id": doc_id, "source_key": "(fora da seleção)"})
                lines.append(_doc_block(i, need_id, row))
                lines.append("")
            (out_dir / f"{need_id}_lote{b + 1}.md").write_text("\n".join(lines), encoding="utf-8")

    # Conferência de unicidade.
    keys = list(zip(cand["need_id"], cand["doc_id"]))
    assert len(keys) == len(set(keys)), "pares duplicados detectados"

    print(f"Caderno gravado em: {out_dir}")
    print(f"Total de pares: {len(cand)}")
    for n in sorted(summary):
        print(f"  {n}: {summary[n]} pares")
    print(f"Registro em branco: {reg_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

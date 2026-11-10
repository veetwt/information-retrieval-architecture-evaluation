# Avaliação Quantitativa Exploratória da Recuperação

Run: `oficial_recuperacao_altb_2026`
Natureza: **exploratória**, restrita aos 65 pares `(need_id, doc_id)` adjudicados.
Chave de cruzamento: sempre `(need_id, doc_id)`.

Fontes congeladas (somente leitura): `retrieval_record.parquet`,
`judgment_manifest.json`, `judgment_candidates.parquet`,
`caderno_humano/registro_julgamento.csv`. Recuperadores **não** foram
reexecutados; nenhuma fonte oficial foi alterada; nenhuma operação Git executada.

---

## 1. Validações (todas aprovadas)

- Combinações `need_id × formulation`: **9**.
- Configurações implícitas (3 arquiteturas por combinação): **27**.
- Configurações ranqueadas: **18** (9 vetoriais + 9 híbridas).
- Configurações estruturadas: **9**.
- Totais de rótulos: 8 relevantes + 57 não relevantes = **65**; por NI: NI-001
  (1R/17NR), NI-002 (1R/13NR), NI-003 (6R/27NR) — conforme esperado.
- Identidade entre os 65 pares adjudicados e os 65 candidatos: **confirmada**.
- Duplicatas dentro de algum top-5: **nenhuma**.
- `vector_top5`/`hybrid_top5` são **prefixos exatos** (mesma ordem) dos
  respectivos rankings completos: **confirmado** (listas curtas admitidas).
- Cobertura humana dos top-5 vetorial e híbrido: **completa** (0 pares sem
  rótulo).
- Diagnóstico da auditoria conferido: **52** pares distintos nos top-5, **45**
  ocorrências vetoriais, **37** híbridas, **82** no total — **batem exatamente**.

Nenhuma validação crítica falhou; o cálculo prosseguiu.

---

## 2. Precision@5 — 18 configurações (denominador fixo = 5)

Regras aplicadas: ordem original preservada; relevante = rótulo humano
`relevante` no par `(need_id, doc_id)`; denominador sempre 5 (mesmo com <5
retornos); posições inexistentes somam zero ao numerador, sem doc_ids
artificiais; referências não presentes no top-5 não contam; estruturada excluída.

| need_id | formulation | architecture | hybrid_path | returned_at_5 | relevant_at_5 | precision_at_5 | missing_positions | all_returned_judged |
|---|---|---|---|---|---|---|---|---|
| NI-001 | direct | vector | | 5 | 0 | 0.00 | 0 | sim |
| NI-001 | direct | hybrid | structured_filter_then_vector_rank | 1 | 1 | 0.20 | 4 | sim |
| NI-001 | paraphrase | vector | | 5 | 0 | 0.00 | 0 | sim |
| NI-001 | paraphrase | hybrid | structured_filter_then_vector_rank | 5 | 0 | 0.00 | 0 | sim |
| NI-001 | verbose | vector | | 5 | 0 | 0.00 | 0 | sim |
| NI-001 | verbose | hybrid | structured_filter_then_vector_rank | 1 | 1 | 0.20 | 4 | sim |
| NI-002 | direct | vector | | 5 | 1 | 0.20 | 0 | sim |
| NI-002 | direct | hybrid | structured_filter_then_vector_rank | 5 | 1 | 0.20 | 0 | sim |
| NI-002 | paraphrase | vector | | 5 | 1 | 0.20 | 0 | sim |
| NI-002 | paraphrase | hybrid | structured_filter_then_vector_rank | 5 | 1 | 0.20 | 0 | sim |
| NI-002 | verbose | vector | | 5 | 1 | 0.20 | 0 | sim |
| NI-002 | verbose | hybrid | structured_filter_then_vector_rank | 5 | 1 | 0.20 | 0 | sim |
| NI-003 | direct | vector | | 5 | 1 | 0.20 | 0 | sim |
| NI-003 | direct | hybrid | structured_filter_then_vector_rank | 5 | 2 | 0.40 | 0 | sim |
| NI-003 | paraphrase | vector | | 5 | 1 | 0.20 | 0 | sim |
| NI-003 | paraphrase | hybrid | structured_filter_then_vector_rank | 5 | 3 | 0.60 | 0 | sim |
| NI-003 | verbose | vector | | 5 | 0 | 0.00 | 0 | sim |
| NI-003 | verbose | hybrid | structured_filter_then_vector_rank | 5 | 3 | 0.60 | 0 | sim |

As duas listas híbridas de NI-001 (`direct` e `verbose`) retornaram **apenas 1
documento** (caminho estrutural `structured_filter_then_vector_rank`). Por
convenção, o denominador permanece 5; as 4 posições ausentes **não** são
documentos nem são tratadas como não relevantes.

---

## 3. Resumo descritivo (estatísticas deste experimento, não populacionais)

### 3.1 Média de Precision@5 por arquitetura (sobre 9 configurações cada)
- **vetorial: 0.1111**
- **híbrida: 0.2889**

### 3.2 Média por necessidade e arquitetura
| NI | vetorial | híbrida |
|---|---|---|
| NI-001 | 0.0000 | 0.1333 |
| NI-002 | 0.2000 | 0.2000 |
| NI-003 | 0.1333 | 0.5333 |

### 3.3 Comparação pareada vetorial × híbrida (mesma `need_id, formulation`)
| need_id | formulation | vetorial | híbrida | dif (vet − hyb) |
|---|---|---|---|---|
| NI-001 | direct | 0.00 | 0.20 | −0.20 |
| NI-001 | paraphrase | 0.00 | 0.00 | 0.00 |
| NI-001 | verbose | 0.00 | 0.20 | −0.20 |
| NI-002 | direct | 0.20 | 0.20 | 0.00 |
| NI-002 | paraphrase | 0.20 | 0.20 | 0.00 |
| NI-002 | verbose | 0.20 | 0.20 | 0.00 |
| NI-003 | direct | 0.20 | 0.40 | −0.20 |
| NI-003 | paraphrase | 0.20 | 0.60 | −0.40 |
| NI-003 | verbose | 0.00 | 0.60 | −0.60 |

Em nenhuma das 9 combinações a vetorial superou a híbrida; empate em 4 (todas de
NI-001/paraphrase e NI-002) e híbrida numericamente maior em 5. **Isto é uma
observação descritiva deste conjunto pequeno, não evidência de superioridade
generalizável** (ver §6).

### 3.4 Retornos efetivos por configuração
Todas as 18 configurações retornaram 5 documentos, **exceto** NI-001/direct e
NI-001/verbose na híbrida (1 retorno cada). Isso decorre do caminho
estrutural da híbrida, que filtrou o conjunto a 1 documento antes do ranking
vetorial.

### 3.5 Documentos relevantes recuperados em cada top-5 (por par, sem confundir formulações)
- **NI-001** (relevante adjudicado: `tcu-b8b9f99c805c`): recuperado no top-5 da
  **híbrida** em `direct` e `verbose`; **não** recuperado por nenhuma vetorial
  nem pela híbrida em `paraphrase`.
- **NI-002** (relevante: `tcu-5567c745c20f`): recuperado no top-5 de **todas** as
  6 configurações ranqueadas (vetorial e híbrida nas 3 formulações).
- **NI-003** (6 relevantes): a vetorial trouxe 1 relevante em `direct` e
  `paraphrase` e 0 em `verbose`; a híbrida trouxe 2 (`direct`), 3 (`paraphrase`)
  e 3 (`verbose`). Documentos relevantes distintos por formulação são tratados
  individualmente no `detalhamento_top5.csv`.

---

## 4. Arquitetura estruturada (9 conjuntos; SEM Precision@5)

A estruturada retorna **conjuntos filtrados sem ordenação de relevância** — não
se aplica Precision@5. Validado: `judged_in_set + unjudged_in_set =
structured_set_size` e `relevant_judged + nonrelevant_judged = judged_in_set` em
todas as linhas; **nenhuma duplicata técnica** encontrada.

| need_id | formulation | tamanho | julgados | rel. julg. | não-rel. julg. | não julgados | cobertura julg. | condições |
|---|---|---|---|---|---|---|---|---|
| NI-001 | direct | 1 | 1 | 1 | 0 | 0 | 1.000 | DEN + ENTIDADE=Sesc/MS |
| NI-001 | paraphrase | 319 | 7 | 1 | 6 | 312 | 0.022 | DEN |
| NI-001 | verbose | 1 | 1 | 1 | 0 | 0 | 1.000 | DEN + ENTIDADE=Sesc/MS |
| NI-002 | direct | 319 | 7 | 1 | 6 | 312 | 0.022 | DEN |
| NI-002 | paraphrase | 319 | 7 | 1 | 6 | 312 | 0.022 | DEN |
| NI-002 | verbose | 319 | 7 | 1 | 6 | 312 | 0.022 | DEN |
| NI-003 | direct | 1414 | 23 | 6 | 17 | 1391 | 0.016 | REPR |
| NI-003 | paraphrase | 21 | 21 | 6 | 15 | 0 | 1.000 | REPR + ENTIDADE=ANTT |
| NI-003 | verbose | 21 | 21 | 6 | 15 | 0 | 1.000 | REPR + ENTIDADE=ANTT |

**Composição conhecida (apenas conjuntos integralmente adjudicados):**
- NI-001 direct/verbose (tamanho 1): o único documento é relevante.
- NI-003 paraphrase/verbose (tamanho 21): 6 relevantes e 15 não relevantes
  conhecidos — conjunto **não ordenado**.

**Conjuntos grandes (319, 1414):** cobertura de julgamento muito baixa
(≈2,2% e ≈1,6%). Reporta-se apenas: positivos conhecidos, negativos conhecidos e
volume desconhecido. **NÃO** se divide positivos conhecidos pelo tamanho total
como "precisão do conjunto" — a maior parte permanece não julgada (desconhecida).

**Variação entre formulações:** a formulação muda drasticamente a interpretação
estrutural. Em NI-001, `direct`/`verbose` reconhecem DEN + ENTIDADE (conjunto=1),
enquanto `paraphrase` reconhece só DEN (conjunto=319). Em NI-003, `direct`
reconhece só REPR (1414), enquanto `paraphrase`/`verbose` reconhecem REPR +
ENTIDADE=ANTT (21). Em NI-002 as três formulações convergem para DEN (319). A
flag `overly_broad` ficou `false` em todos (nenhum conjunto atingiu ≥50% do
corpus); `no_conditions` `false` em todos.

---

## 5. Cobertura dos relevantes adjudicados (27 configurações; profundidades distintas)

Denominador = relevantes **adjudicados** na NI (NI-001=1, NI-002=1, NI-003=6).
Medida denominada **`cobertura_dos_relevantes_adjudicados`** — **nunca**
recall global. Profundidades **não equivalentes**: vetorial/híbrida observadas no
**top-5**; estruturada no **conjunto completo** retornado. Portanto os valores
**não** são comparáveis diretamente como desempenho entre arquiteturas.

Destaques (detalhe completo em `cobertura_relevantes_adjudicados.csv`):
- **Estruturada**: cobre **todos** os relevantes adjudicados em todas as 9
  configurações (1/1, 1/1, 6/6) — mas ao custo de conjuntos enormes e não
  ordenados (1414/319) e observando o conjunto inteiro, não o top-5.
- **Híbrida (top-5)**: NI-001 1/1 em direct/verbose, 0/1 em paraphrase; NI-002
  1/1 nas três; NI-003 2/6, 3/6, 3/6.
- **Vetorial (top-5)**: NI-001 0/1 nas três; NI-002 1/1 nas três; NI-003 1/6,
  1/6, 0/6.

**Interpretação restrita ao pool:** o conjunto de 65 pares foi construído por
**seleção dirigida**, que **inclui** os próprios resultados dos recuperadores
(top-5 de vetorial/híbrida) e o universo estrito dos 21 da NI-003. Logo, a
cobertura aqui é relativa aos relevantes **conhecidos no pool**, com dependência
explícita do processo que formou o pool. **Não** representa recall sobre os
relevantes de todos os 21.631 acórdãos.

---

## 6. Padrões observados (descritivos) e ameaças à validade

Padrões neste conjunto exploratório:
- A híbrida igualou ou superou numericamente a vetorial em todas as 9
  combinações pareadas de Precision@5; a maior diferença ocorreu em NI-003
  (mista), onde o filtro estrutural ANTT+REPR concentrou documentos pertinentes.
- Em NI-002 (textual) as duas arquiteturas foram idênticas (0.20 em todas).
- Em NI-001 (metadados, alvo único) a vetorial não trouxe o alvo em nenhuma
  formulação no top-5; a híbrida o trouxe quando o filtro estrutural isolou o
  conjunto (direct/verbose).
- A formulação afetou fortemente a estruturada (e, por consequência, o caminho
  da híbrida), evidência do acoplamento interpretação↔formulação.

Ameaças à validade (ver também §7):
- **9 combinações não são 9 observações independentes** sorteadas de uma
  população de consultas; são 3 necessidades × 3 formulações correlacionadas.
- Pool por seleção dirigida, dependente dos próprios recuperadores.
- Profundidades de observação distintas entre arquiteturas.
- Conjuntos estruturados grandes majoritariamente não julgados.
Nenhum teste de significância, intervalo de confiança amostral ou alegação de
superioridade generalizável é feito.

---

## 7. Limitações obrigatórias (declaradas)

- O corpus congelado tem **21.631 acórdãos**, mas apenas **65 pares**
  `(need_id, doc_id)` foram julgados.
- Os 65 pares foram selecionados **intencionalmente**, não aleatoriamente.
- Os **52 pares distintos** dos top-5 vetorial/híbrido estão **integralmente
  adjudicados**; por isso a Precision@5 é calculável para esses rankings.
- Resultados além do top-5 podem conter documentos **não julgados**; não
  extrapolar métricas para outras profundidades sem nova verificação.
- A relevância de documentos **fora dos 65 pares** é **desconhecida** (nunca
  negativa por omissão).
- **Não há base** para estimar recall global do corpus nem intervalos de
  confiança amostrais.
- Os conjuntos estruturados grandes **não** têm cobertura humana suficiente para
  estimar precisão integral.
- Três necessidades e suas formulações são um **desenho exploratório pequeno**,
  não amostra representativa de todas as consultas.
- Diferenças numéricas entre arquiteturas **não** demonstram, isoladamente,
  superioridade generalizável.

---

## 8. Arquivos gerados

Diretório: `runs/judgment/oficial_recuperacao_altb_2026/avaliacao_exploratoria/`
- `precision_at_5_por_configuracao.csv` (18 linhas)
- `detalhamento_top5.csv` (uma linha por documento efetivamente retornado; sem doc_ids fictícios)
- `analise_conjuntos_estruturados.csv` (9 linhas)
- `cobertura_relevantes_adjudicados.csv` (27 linhas, com profundidade observada por arquitetura)
- `relatorio_avaliacao_exploratoria.md` (este documento)

Reprodutível a partir das fontes congeladas, por script explícito, com chave
`(need_id, doc_id)` e denominador fixo 5 para Precision@5.

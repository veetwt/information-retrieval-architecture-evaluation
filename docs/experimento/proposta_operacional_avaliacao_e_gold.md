# Proposta operacional — pooling, gold standard e avaliação comparativa

**Natureza deste documento:** proposta técnica, **não** decisão ratificada. Os
parâmetros aparecem como **[EM ESTUDO]** ou **[A DEFINIR]**, conforme a convenção
do protocolo (`.kiro/specs/protocolo-experimental/`). Nada aqui promove decisões
a **[DECIDIDO]**. Este documento não altera código, specs, corpus, índice ou
embeddings; não constrói pools nem julgamentos reais.

Convenção de status usada: **[FATO]** verificado no repositório; **[DECIDIDO]**
já ratificado em outro documento; **[EM ESTUDO]** / **[A DEFINIR]** pendente de
aprovação do pesquisador.

---

## 1. Estado preservado (não reaberto)

- **[FATO]** Seleção experimental congelada: 21.631 documentos;
  `selection_fingerprint = ec125709322854d164e8f4aeaffb0351ef92e0adfede4d92b17b955b5ea1bc5c`.
- **[FATO]** Índice vetorial: 124.282 chunks.
- **[FATO]** Três recuperadores implementados: `StructuredRetriever` v0.3.0
  (conjunto sem ranking de relevância; `score=None`; ordem por `doc_id`),
  `VectorRetriever` v0.2.0 e `HybridRetriever` v0.2.0 (rankings; `display_limit`
  configurável; ranking completo calculado antes do corte).
- **[DECIDIDO]** Política híbrida A/B/C e regra de combinação do Caso C.
- **[FATO]** Gold standard ainda não construído (`evaluation/reference/` vazio);
  NI-001/002/003 em `draft`.

Nenhuma dessas decisões é reaberta aqui.

---

## 2. Parâmetros candidatos (não ratificados)

| Parâmetro | Papel | Valor | Status |
|---|---|---|---|
| k | cortes de avaliação de ranking (vetorial/híbrida) | 5, 10, 50 | **[DECIDIDO]** |
| D | profundidade de pooling por formulação | **50** | **[DECIDIDO]** |
| T | teto para julgamento integral do conjunto estruturado | **100** | **[DECIDIDO]** |
| rótulo de relevância | binário relevante/não-relevante; `uncertain` só na revisão | — | **[DECIDIDO]** |
| estruturada | avaliada como conjunto, sem ranking artificial | — | **[DECIDIDO]** |
| orçamentos | recuperação × contexto do gerador são separados | — | **[DECIDIDO]** |
| s_R | tamanho da amostra do estrato restante (estruturada > T) | por precisão-alvo (ver §4.4) | [A DEFINIR] |
| Precision@k p/ listas curtas | convenção de denominador (k vs. tamanho real) | pendente | [A DEFINIR] |

> Decisões promovidas a **[DECIDIDO]** nesta rodada foram aprovadas explicitamente pelo
> pesquisador; `s_R`, a convenção para listas < k, revisão/adjudicação, necessidades sem
> relevantes, política de geração e número de necessidades **permanecem em aberto**.

Os valores candidatos foram escolhidos por **prática de recuperação de
informação e orçamento operacional**, **nunca** pela posição de documentos
relevantes nas consultas-piloto nem por qualquer relevância preliminar.

A separação entre **orçamento de recuperação** (quantos documentos entram nas
métricas) e **orçamento de contexto do gerador** (quantos documentos/trechos vão
ao gerador) permanece válida e é uma decisão **[A DEFINIR]** posterior.

---

## 3. Procedimento de composição do pool

### 3.1 Por formulação e por necessidade

Uma necessidade tem três formulações (direta, parafraseada, prolixa). As três
são submetidas às três arquiteturas. **A saída estruturada pode diferir entre
formulações**, porque a `StructuredRetriever` interpreta cada texto
separadamente e pode reconhecer condições diferentes — portanto as três saídas
estruturadas **não** são tratadas como necessariamente idênticas.

Para cada necessidade `N`, o pool de julgamento reúne candidatos das **três
formulações** `f ∈ {direct, paraphrase, verbose}` e das três arquiteturas:

- `P_vet(N)` = união, sobre `f`, dos **top-D** da vetorial;
- `P_hib(N)` = união, sobre `f`, dos **top-D** da híbrida (registrando o caminho
  A/B/C de cada formulação);
- `P_est(N)` = união, sobre `f`, do **conjunto estruturado** de cada formulação
  (integral se o conjunto ≤ T; caso contrário, o subconjunto efetivamente
  julgado conforme a amostragem da Seção 4);
- `P_cond(N)` = complemento derivado das `mandatory_conditions` da ficha
  (subconjunto do corpus que satisfaz as condições estruturais verificáveis),
  amostrado quando grande; pode ser vazio para necessidades puramente textuais.

**Pool julgado:** `J(N) = P_vet(N) ∪ P_hib(N) ∪ P_est(N) ∪ P_cond(N)`,
**deduplicado por `doc_id`**.

### 3.2 Deduplicação e vínculo do julgamento

- O **julgamento de relevância é vinculado à necessidade e ao `doc_id`**, não à
  formulação nem à arquitetura. Um `doc_id` que aparece em várias formulações ou
  arquiteturas é **julgado uma única vez** por necessidade.
- Para cada `doc_id` em `J(N)`, registram-se **todas** as origens (quais
  arquiteturas, quais formulações, posições de ranking, pertencimento a
  conjuntos estruturados, estrato de amostragem). Isso preserva a rastreabilidade
  sem duplicar o julgamento.

### 3.3 Registro por formulação

Mesmo com julgamento único por `doc_id`, devem ser registrados **por
formulação**: a saída estruturada (tamanho do conjunto), a população de
candidatos e, para a estruturada > T, os elementos de estimativa de precisão
(Seção 4). Isso permite analisar a sensibilidade da interpretação estrutural à
formulação, sem reabrir a regra de combinação.

---

## 4. Amostragem de conjuntos estruturados grandes (estimador estratificado)

Quando o conjunto estruturado de uma formulação, `C`, tem `N = |C| > T`, julgar
`C` inteiro é inviável. Parte de `C` **já será julgada** por ter caído em
`P_vet ∪ P_hib ∪ P_cond` (seleção **intencional**, não aleatória); misturar
esses documentos com uma amostra aleatória e tomar a proporção bruta de
relevantes **enviesa** a estimativa. Por isso usa-se **amostragem estratificada**
em dois estratos de `C`:

- **Estrato I (inclusão certa):** `C_in = C ∩ (P_vet ∪ P_hib ∪ P_cond)`; tamanho
  `N_I`; **todos julgados** (probabilidade de inclusão = 1; é um censo deste
  estrato).
- **Estrato R (restante):** `C_rest = C \ C_in`; tamanho `N_R = N − N_I`; dele
  sorteia-se uma **amostra aleatória simples sem reposição** de tamanho `s_R`;
  probabilidade de inclusão = `s_R / N_R`.

**Estimador da precisão do conjunto `C`** (proporção de relevantes em `C`),
ponderado pelos tamanhos dos estratos:

```
p̂ = (N_I · p_I + N_R · p_R) / N
```

onde `p_I` = relevantes/julgados no estrato I (censo, exato) e `p_R` = proporção
amostral de relevantes no estrato R. O estrato I não contribui com variância; a
incerteza vem só do estrato R.

**Intervalo de confiança (aproximado):**

```
Var(p_R) = (p_R·(1 − p_R) / s_R) · (N_R − s_R)/(N_R − 1)   # correção de população finita
Var(p̂)  = (N_R / N)² · Var(p_R)
IC 95%  ≈ p̂ ± 1,96 · sqrt(Var(p̂))
```

### 4.1 Condições de validade do estimador e dos ICs

- O estrato R deve ser sorteado **aleatoriamente** de `C_rest`; a validade do IC
  depende disso.
- **Populações pequenas:** quando `N_R` é pequeno ou `s_R` próximo de `N_R`, a
  correção de população finita é indispensável; no limite `s_R = N_R`, o estrato
  R vira censo e a variância tende a zero.
- **Pouca variabilidade** (`p_R` próximo de 0 ou 1) ou `s_R` pequeno: o IC normal
  é inadequado; usar **intervalo de Wilson** (ou exato) em vez do normal.
- **Não** reportar a proporção bruta sobre "todos os julgados de `C`" como
  estimativa representativa: ela mistura censo intencional (estrato I) com
  amostra (estrato R) e só estima `p` corretamente com a ponderação por estrato.

### 4.2 Sobreposição entre formulações

Se o conjunto estruturado é amostrado em mais de uma formulação da mesma
necessidade, os documentos já julgados (por qualquer formulação/arquitetura)
entram no estrato I daquela formulação (probabilidade de inclusão = 1), e apenas
o restante não julgado compõe o estrato R a sortear. As **probabilidades de
inclusão e os estratos são registrados por formulação**, de modo que a
estimativa de `p̂` de cada formulação permaneça correta mesmo com sobreposição.

### 4.3 Documentos não julgados

Documentos fora de `J(N)` ficam **não julgados = desconhecidos**, nunca
irrelevantes. Nenhuma métrica os trata como negativos.

### 4.4 Planejamento do tamanho da amostra `s_R` (a partir de precisão-alvo) — [A DEFINIR]

`s_R` **não** é fixado arbitrariamente nem com base nas consultas-piloto. A
regra proposta (pendente de aprovação) deriva `s_R` de uma **precisão-alvo** do
intervalo de confiança do estrato R, por formulação:

1. Escolher nível de confiança (ex.: 95% → z=1,96) e **semi-largura alvo** `e` do
   IC da proporção (ex.: `e = 0,10`). Ambos são **[A DEFINIR]**.
2. Tamanho base (proporção, pior caso `p=0,5`, sem correção):
   `n0 = z² · p(1−p) / e²`.
3. **Correção de população finita** sobre o estrato R (tamanho `N_R`):
   `s_R = ceil( n0 / (1 + (n0 − 1)/N_R) )`.
4. Se `s_R ≥ N_R`, o estrato R vira **censo** (`s_R = N_R`) e a estimativa daquela
   formulação passa a ser exata (variância do estrato R = 0).
5. **Reutilização sem duplicação:** documentos já julgados (estrato I, por
   qualquer formulação/arquitetura) **não** entram novamente na conta de `s_R`;
   só o restante não julgado de `C_rest` é elegível ao sorteio. Um `doc_id`
   sorteado numa formulação e já julgado é reaproveitado (julgamento único por
   `(need_id, doc_id)`), ajustando-se os contadores do estrato R das demais
   formulações para não recontá-lo.

O valor concreto de `e` (e portanto de `s_R`) depende do esforço de julgamento
viável, que envolve a disponibilidade de revisores — **ainda em aberto**.

---

## 5. Recall sob pooling (interpretação corrigida)

Para vetorial e híbrida:

```
Recall-sob-pool@k(N, arq) = |relevantes recuperados por arq no top-k ∩ J(N)|
                            / |relevantes conhecidos em J(N)|
```

- O denominador é o número de **relevantes conhecidos (julgados) em `J(N)`**, não
  o número de relevantes no corpus.
- **Correção em relação ao plano anterior:** o Recall-sob-pool **não**
  necessariamente superestima o recall absoluto. Ele mede **cobertura entre os
  relevantes conhecidos no pool** e pode apresentar viés **em qualquer direção**
  em relação ao recall do corpus: a direção e a magnitude do viés dependem de
  quais relevantes ficaram fora do pool e de quais arquiteturas os teriam
  recuperado. Um **denominador compartilhado** entre as arquiteturas **não** o
  torna uma estimativa não enviesada do recall do corpus inteiro.
- **Ausência de relevantes no pool não comprova ausência de relevantes no
  corpus:** é "nenhum relevante **conhecido**", não "nenhum relevante existe".
- **Conclusões sustentáveis:** comparações de Recall-sob-pool entre arquiteturas
  devem ser sempre acompanhadas do **tamanho do resultado** de cada uma; não se
  deve declarar superioridade por recall quando os volumes recuperados diferem
  muito, nem apresentar o Recall-sob-pool como recall absoluto do corpus.

Para a estruturada, o recall é calculado de forma análoga sobre o conjunto
retornado, com a mesma ressalva de "sob pool".

---

## 6. Convenções de métricas (nomes distintos para definições distintas)

| Nome | Arquiteturas | Denominador | Definição |
|---|---|---|---|
| **Precision@k** | vetorial, híbrida | `k` fixo | relevantes nos top-k / k, quando a lista tem ≥ k itens |
| **Precision (lista curta)** | vetorial, híbrida | tamanho real (< k) | relevantes / nº retornado, quando a lista tem < k itens — **métrica distinta**; a convenção de denominador é [A DEFINIR] |
| **Precisão-de-conjunto (censo)** | estruturada (`|C| ≤ T`) | `|C|` | relevantes / tamanho do conjunto — **exata** |
| **Precisão-de-conjunto (estimada)** | estruturada (`|C| > T`) | `|C|` (via estimador §4) | `p̂` com IC — **estimativa**, nunca "exata" |
| **Recall-sob-pool@k** | vetorial, híbrida | relevantes conhecidos em `J(N)` | ver §5 |
| **Recall de conjunto (sob pool)** | estruturada | relevantes conhecidos em `J(N)` | ver §5 |
| **nDCG@k, MAP@k, MRR** | vetorial, híbrida | conforme a métrica | complementares (ordenação) |
| **Tamanho do resultado** | todas | — | esforço de inspeção (dimensão transversal) |
| **Recall do filtro estruturado** | híbrida | relevantes conhecidos | diagnóstico (candidatos ∩ relevantes / relevantes conhecidos) |

Regras: nunca usar "Precision@k" para denominadores diferentes de `k` sem
rótulo; distinguir sempre precisão **exata** (censo) de **estimada** (amostral);
não prometer recall absoluto nem precisão exata de conjuntos apenas parcialmente
julgados.

---

## 7. Estimativa de esforço (expressão conservadora)

**Correção em relação ao plano anterior:** **não** se pressupõe sobreposição
elevada entre os rankings vetorial e híbrido no Caso C. A cota superior do número
de candidatos **antes da deduplicação**, por necessidade `N`, é:

```
MAX_cand(N) = 3·D            # vetorial: 3 formulações × top-D
            + 3·D            # híbrida: 3 formulações × top-D
            + Σ_f |C_est(f)| # conjuntos estruturados das 3 formulações (ou, se > T, N_I + s_R por formulação)
            + |P_cond|       # complemento por condições (ou sua amostra)
            + amostras_adicionais
```

- Esta é uma **cota superior**: a deduplicação por `doc_id` reduz o total real,
  pois há interseção entre formulações, entre vetorial e híbrida, e entre
  `P_est`/`P_cond` e os rankings.
- A **sobreposição real só será conhecida após a geração dos pools**; não é
  presumida aqui.
- O esforço total depende do número de necessidades (**[A DEFINIR]**; não
  decidido nesta tarefa) e de D/T/s_R. Não se estimam horas nem número de
  revisores (não há base para inventá-los).
- À cota soma-se o custo de **revisão dos `uncertain`** (passe adicional sobre a
  fração marcada como incerta).

---

## 8. Contratos de dados

Três artefatos **separados**. Convenção de tipo: `str`, `int`, `float`, `bool`,
`datetime` (ISO-8601 UTC), `enum[...]`, `list[...]`, `map[k→v]`. "obrig." =
obrigatório; "opc." = opcional. A implementação (gerador de pools, executor de
métricas) **não** é feita nesta tarefa; aqui define-se o contrato.

Distinção essencial entre três objetos:
1. **Saída completa de recuperação** por arquitetura e formulação — é a entrada
   do processo; **não** é persistida como artefato de gold (pode ser registrada
   à parte para auditoria), e dela deriva-se o pool.
2. **Conjunto selecionado para julgamento** — `pool_candidates` (§8.B).
3. **Julgamento único por `(need_id, doc_id)`** — `relevance_judgments` (§8.C).

### 8.A `pool_manifest` — um registro por execução

| Campo | Tipo | Obrig. | Restrição/validação |
|---|---|---|---|
| `run_id` | str | obrig. | único entre execuções (chave) |
| `created_at` | datetime | obrig. | UTC |
| `selection_fingerprint` | str | obrig. | SHA-256 (64 hex); **deve** ser igual ao do índice e das fichas |
| `index_dir` | str | obrig. | caminho do índice vetorial usado |
| `model_name` | str | obrig. | modelo de embedding do índice |
| `structured_version` | str | obrig. | ex.: "0.3.0" |
| `vector_version` | str | obrig. | ex.: "0.2.0" |
| `hybrid_version` | str | obrig. | ex.: "0.2.0" |
| `params.D` | int | obrig. | = 50 (decidido); > 0 |
| `params.T` | int | obrig. | = 100 (decidido); > 0 |
| `params.k_cuts` | list[int] | obrig. | = [5,10,50]; cada k ≤ `display_limit` usado |
| `params.display_limit_used` | int | obrig. | ≥ max(`k_cuts` ∪ {D}) |
| `sampling.target_conf` | float | opc. | nível de confiança (ex.: 0.95) quando houver estrato R |
| `sampling.target_halfwidth` | float | opc. | semi-largura `e` do IC (ver §4.4) |
| `sampling.rng_seed` | int | obrig. se houver amostragem | reprodutibilidade |
| `needs_included` | list[str] | obrig. | cada item casa `^NI-[0-9]{3}$` |
| `notes` | str | opc. | — |

### 8.B `pool_candidates` — um registro por `(need_id, doc_id)`

Chave primária: `(run_id, need_id, doc_id)` — **único**. O julgamento **não** é
duplicado por formulação; as origens por formulação ficam aninhadas.

| Campo | Tipo | Obrig. | Restrição/validação |
|---|---|---|---|
| `run_id` | str | obrig. | FK → `pool_manifest.run_id` |
| `need_id` | str | obrig. | `^NI-[0-9]{3}$` |
| `doc_id` | str | obrig. | pertence à seleção congelada |
| `retrieval_sources` | list[enum{structured,vector,hybrid}] | obrig. | não vazio; sem repetição |
| `per_formulation` | map[enum{direct,paraphrase,verbose} → `FormulationEntry`] | obrig. | ao menos uma formulação; ver abaixo |
| `in_pool_reasons` | list[enum{vector_topD,hybrid_topD,structured_set,conditions_complement}] | obrig. | não vazio (justifica a presença no pool) |

`FormulationEntry` (por formulação — resolve a representação de amostragem **por
formulação**, pois os conjuntos estruturados podem diferir entre formulações):

| Campo | Tipo | Obrig. | Restrição/validação |
|---|---|---|---|
| `recalled_by` | list[enum{structured,vector,hybrid}] | obrig. | arquiteturas que trouxeram o doc **nesta** formulação (pode ser vazio se o doc veio só por outra formulação/condição) |
| `hybrid_path` | enum{A,B,C} \| null | opc. | caminho da híbrida nesta formulação, quando aplicável |
| `rank_positions` | map[enum{vector,hybrid} → int] | opc. | posição 1-based no ranking, quando houver |
| `in_structured_set` | bool | obrig. | se o doc pertence ao conjunto estruturado **desta** formulação |
| `stratum` | enum{I,R} \| null | obrig. se `in_structured_set` e `|C|>T` | I = inclusão certa; R = sorteado; null quando `|C|≤T` (censo) ou fora da estruturada |
| `inclusion_prob` | float \| null | obrig. se `stratum≠null` | 1.0 se `stratum=I`; `s_R/N_R` se `stratum=R`; null caso contrário |
| `structured_population_N` | int | opc. | `N=|C|` desta formulação (registrado p/ estimar precisão) |
| `structured_N_I` | int | opc. | tamanho do estrato I desta formulação |
| `structured_N_R` | int | opc. | tamanho do estrato R desta formulação |
| `structured_s_R` | int | opc. | amostra efetiva do estrato R desta formulação |

Validações-chave:
- `inclusion_prob ∈ (0,1]`; se `stratum=I` então `inclusion_prob=1.0`.
- a precisão estimada da estruturada é calculada **por formulação** a partir de
  `N, N_I, N_R, s_R` (ver §4); por isso esses campos são **por formulação**, não
  por `(need_id,doc_id)` global — um mesmo `doc_id` pode ser estrato I numa
  formulação e R em outra.

### 8.C `relevance_judgments` — um registro por `(need_id, doc_id)`

Chave primária: `(need_id, doc_id)` — **único por necessidade**, independente de
formulação e de arquitetura (julgamento único).

| Campo | Tipo | Obrig. | Restrição/validação |
|---|---|---|---|
| `need_id` | str | obrig. | `^NI-[0-9]{3}$` |
| `doc_id` | str | obrig. | deve existir em `pool_candidates` do mesmo `need_id` |
| `label` | enum{relevant,not_relevant,uncertain} | obrig. | `uncertain` **proibido** no gold congelado (só durante revisão) |
| `evidence` | str | obrig. se `label=relevant` | trecho/campo que sustenta |
| `reviewer` | str | obrig. | identificador do julgador |
| `judged_at` | datetime | obrig. | UTC |
| `review_status` | enum{primary,reviewed,adjudicated} | obrig. | — |
| `adjudication` | str | obrig. se houve discordância | resultado da resolução |
| `blind` | bool | obrig. | se o julgamento foi feito sem conhecer a arquitetura de origem |
| `source_run_id` | str | obrig. | FK → `pool_manifest.run_id` que originou o candidato |
| `notes` | str | opc. | — |

Relações e invariantes entre artefatos:
- todo `relevance_judgments` referencia um `pool_candidates` existente
  (`need_id, doc_id`) do mesmo `run_id` (via `source_run_id`);
- documentos em `pool_candidates` **sem** `relevance_judgments` ficam
  **desconhecidos** (não são negativos);
- o gold congelado = `relevance_judgments` com `label ∈ {relevant, not_relevant}`
  (nenhum `uncertain`), versionado com `selection_fingerprint`.

**Julgamento às cegas:** `pool_candidates` guarda a proveniência (arquitetura/
formulação), mas a interface de julgamento pode ocultá-la; `blind=true` registra
que o julgamento foi feito sem essa informação, reduzindo viés.

### 8.D Congelamento e versionamento do gold

- O gold congelado agrega os `relevance_judgments` com todos os `uncertain`
  resolvidos (viram `relevant`/`not_relevant`).
- Reside em `evaluation/reference/`, versionado, com `selection_fingerprint`
  gravado e idêntico ao da seleção/índice/fichas. Qualquer alteração da seleção
  invalida o gold (nova versão).
- O gold referencia o(s) `run_id` do(s) pool(s) que o originaram, para
  reprodutibilidade.

### 8.E Campos adicionais necessários nas fichas (especificação; fichas não alteradas aqui)

Para que o julgamento de relevância seja consistente, a ficha de cada
necessidade precisa declarar, **antes** do julgamento, os campos abaixo. Esta é
uma **especificação** do que será necessário; as fichas NI-001/002/003 **não**
são alteradas nesta tarefa nem promovidas a `validated`. O schema do `NeedSheet`
já traz `mandatory_conditions`, `requested_facts` e `operations` [FATO]; os itens
marcados como novos ainda não existem no schema e seriam acrescentados numa
tarefa futura de atualização do `NeedSheet`.

| Campo da ficha | Papel no julgamento | Situação |
|---|---|---|
| `answer_cardinality` (novo) | distingue **documento único** (identificação) de **enumeração/contagem**/**multidocumental** | a acrescentar ao schema |
| `mandatory_conditions` | condições que delimitam a pertinência (metadata/textual) | já existe |
| `required_textual_evidence` (novo) | evidência textual que um documento deve conter para ser relevante | a acrescentar |
| `partial_relevance_rule` (novo) | em necessidades multidocumentais, o que conta como "contribuir" para a resposta (um documento é relevante se cobre **parte** da necessidade) | a acrescentar |
| `requested_facts` | fatos que a resposta deve conter (no conjunto, não necessariamente num só documento) | já existe |

Regra de relevância conforme a cardinalidade:
- **`answer_cardinality = single`:** relevante = satisfaz as `mandatory_conditions`
  e contém os `requested_facts` que identificam o documento-alvo.
- **`answer_cardinality = enumeration` / `multidocument`:** relevante = satisfaz
  as `mandatory_conditions` e atende `partial_relevance_rule` (contribui com **ao
  menos** a parte que lhe cabe). **Não** se exige que um único documento contenha
  **todos** os `requested_facts` — a resposta é o **conjunto**.

Estes campos são **[A DEFINIR]** quanto à forma final no `NeedSheet`; sua
ausência hoje é uma pendência registrada, não uma decisão.

---

## 8.F Implementação do gerador de pools (v0.1.0) — [FATO]

O gerador de pools foi **implementado** (sem rótulos de relevância e sem gold):

- `src/evaluation/pool_sampling.py`: núcleo estatístico determinístico —
  `n0_base` (z=1,96; p=0,5; e=0,10; `n0` preservado em float até o arredondamento),
  `sample_size` (`s_R = min(N_R, ceil(n0/(1+(n0−1)/N_R)))`, `N_R=0 ⇒ 0`),
  `sample_without_replacement` (AAS sem reposição, seed derivada por SHA-256 de
  `run_seed`+identificadores), `plan_stratified` (estratos I/R relativos a J0).
- `src/evaluation/pool_generator.py`: `PoolGenerator` — valida integridade via
  `HybridRetriever.from_artifacts(verify_integrity=True)`, executa as três
  arquiteturas por formulação, monta J0, estratifica conjuntos > T e complemento
  > T_cond, deduplica por `(need_id, doc_id)` e grava os artefatos;
  `validate_official` decide o status.
- `scripts/build_pools.py`: ponto de entrada (`--run-id`, `--seed`, `--needs`);
  grava sempre `status="exploratory"`.
- Testes: `tests/test_pool_sampling.py` (14) e `tests/test_pool_generator.py` (10).

**Correção da amostragem efetivamente implementada (conforme aprovado):**
sorteio numa formulação **não** torna o documento "inclusão certa" de outra. J0
é a base determinística (top-D de vetorial/híbrida + conjuntos estruturados ≤T +
complemento ≤T_cond). Para cada conjunto estruturado > T de **cada** formulação,
o estrato I é a interseção com J0 (prob = 1) e o estrato R é o conjunto fora de
J0, com amostra **independente por formulação** (seed derivada de
`run_seed`+need_id+formulation). O julgamento é único por `(need_id, doc_id)`,
mas os planos de inclusão por formulação/fonte são preservados em
`per_formulation`; a estimativa de precisão de uma formulação usa **apenas** seu
estrato I e sua amostra planejada — documentos julgados por sorteios de outras
fontes não são incorporados como censo nem como amostra própria.

**Estados:** `exploratory` por padrão; `official` só quando `validate_official`
aprova (índice não parcial; D=50/T=100/k=[5,10,50]; fichas `validated`;
contagens coerentes; fingerprint presente). Fichas NI-001/002/003 em `draft`
podem ser usadas em testes exploratórios, mas **não** geram pool oficial.

Artefatos gravados em `runs/pools/<run_id>/` (`runs/` é gitignored [FATO]):
`pool_manifest.json`, `retrieval_raw.parquet` (conjuntos estruturados completos
preservados, mesmo quando só parte vai a julgamento), `pool_candidates.parquet`.
O gold permanece **não** criado, separado em `evaluation/reference/`.

---

## 9. Ordem de implementação (dependências)

1. **Aprovação do protocolo e dos parâmetros** (k, D, T, s_R, rótulos,
   convenção de Precision para listas curtas). — pré-requisito de tudo.
2. **Implementação do gerador de pools** (lê a seleção congelada e o índice,
   executa os três recuperadores por formulação, monta candidatos sem rótulos,
   aplica a estratificação da estruturada, grava manifesto + candidatos).
3. **Execução dos recuperadores** para produzir candidatos **sem rótulos**.
4. **Julgamento humano** e resolução dos `uncertain`.
5. **Congelamento do gold** (versionado, vinculado ao fingerprint).
6. **Implementação e execução das métricas** comparativas (instanciando
   vetorial/híbrida com `display_limit ≥ max(k, D)` — [FATO: o ranking completo é
   calculado antes do corte, então elevar o limite não altera scores/ordem).

O **gerador de pools necessariamente precede** a construção do gold baseado em
pooling.

Estado atual dos passos: **1 parcialmente concluído** (k=5/10/50, D=50, T=100,
rótulo binário e amostragem aprovados; `s_R` e convenção de Precision para listas
curtas ainda em aberto); **2 concluído** (ver §8.F); **3** executável como teste
exploratório (fichas em `draft` não geram pool oficial); **4–6** pendentes.

---

## 10. Limites estatísticos e ameaças à validade (resumo)

- Recall reportado é **sob pool**, com viés de direção desconhecida; não é recall
  absoluto do corpus.
- Precisão da estruturada é **exata** apenas quando o conjunto é julgado
  integralmente (`|C| ≤ T`); acima de T é **estimativa** com IC, válida sob
  amostragem aleatória do estrato R e com correção de população finita (Wilson
  para extremos/amostras pequenas).
- Documentos não julgados são **desconhecidos**, nunca irrelevantes.
- Viés de cobertura do pooling: relevantes que nenhuma fonte trouxe (nem rankings
  nem condições) ficam fora; mitigado parcialmente pela união simétrica das três
  arquiteturas e pelo complemento independente `P_cond`, não eliminado.
- A sobreposição real entre pools só é conhecida após a geração dos pools.

---

## 11. Estado das decisões

**Aprovadas (promovidas a [DECIDIDO] no protocolo nesta rodada):** desenho de
avaliação multidimensional; cortes k ∈ {5, 10, 50}; profundidade de pooling
D=50; teto T=100 com amostragem estratificada acima de T; julgamento binário
relevante/não-relevante com `uncertain` só na revisão; estruturada avaliada como
conjunto; separação entre orçamento de recuperação e orçamento de contexto do
gerador; granularidade `doc_id`; não-julgado = desconhecido.

**Permanecem pendentes (NÃO promovidas):**
- regra de dimensionamento de `s_R` (proposta em §4.4, mas `e`/confiança e esforço
  de julgamento ainda em aberto);
- convenção de Precision@k para listas menores que k;
- relevância binária vs. graduada (fixado binário para o gold; graduação para
  nDCG permanece em aberto);
- número de revisores e protocolo de adjudicação;
- admissão de necessidades sem relevantes;
- forma final dos campos adicionais da ficha (§8.E) no `NeedSheet`;
- política de contexto do gerador e número definitivo de necessidades.

Nenhum dos itens pendentes é promovido a **[DECIDIDO]** neste documento.

**Adaptação operacional posterior (Alternativa B):** após esta rodada, a
pesquisadora aprovou a adaptação do **desenho de julgamento** descrita na **§12**
(estudo de casos exploratório; avaliação principal no top-5 e no universo restrito
de 21 da NI-003; teto de 67 julgamentos). Essa adaptação redefine o alcance das
conclusões e torna o plano amostral `s_R` da §4.4 **não aplicável** ao conjunto
reduzido (mantido como referência documentada). Ver §12 para detalhes e
limitações.

---

## 12. Adaptação operacional aprovada — estudo de casos exploratório (Alternativa B)

**Status:** **[DECIDIDO — ADAPTAÇÃO OPERACIONAL]**, aprovada explicitamente pela
pesquisadora **Vitoria Novaes da Costa**. Esta seção **não** apaga nem substitui
as Seções 1–11: o plano de amostragem estratificada (§4), a fórmula `s_R` (§4.4)
e os demais parâmetros originais **permanecem documentados** como desenho de
referência. Registra-se aqui que esse plano amostral **não foi executado**; a
avaliação principal do TCC adota o recorte reduzido descrito abaixo por
**inviabilidade de realizar centenas de julgamentos humanos** com uma única
pesquisadora.

A adaptação afeta **o desenho de julgamento e o alcance das conclusões**. NÃO
altera o corpus, a seleção congelada, o índice vetorial nem o funcionamento dos
três recuperadores.

### 12.1 Desenho aprovado

- Comparação **exploratória** das três arquiteturas (estruturada, vetorial,
  híbrida) sobre as três necessidades validadas: **NI-001** (metadata), **NI-002**
  (textual), **NI-003** (mixed), cada uma com suas três formulações (direta,
  parafraseada, prolixa).
- Recuperação sobre a seleção congelada completa de **21.631 acórdãos**, mesmo
  `selection_fingerprint = ec125709322854d164e8f4aeaffb0351ef92e0adfede4d92b17b955b5ea1bc5c`.
- **Profundidade de recuperação preservada: D=50.** D é a profundidade de
  recuperação/pooling e **não** é o corte de julgamento humano — as duas
  dimensões são distintas e não devem ser confundidas.

### 12.2 Recorte de julgamento humano aprovado

O conjunto submetido ao julgamento humano é formado por:

1. **União dos top-5** das arquiteturas **vetorial e híbrida**, nas três
   formulações de cada necessidade, **deduplicada por `(need_id, doc_id)`**.
2. **Universo restrito da NI-003:** os **21 acórdãos** que satisfazem as condições
   estruturais **ENTIDADE = ANTT** (considerando variantes da denominação e
   valores múltiplos) **e TIPOPROCESSO = Representação**. Este universo restrito
   **não** se confunde com os ~240 candidatos da heurística ampla de substring do
   complemento por condições.
3. **Documentos de referência confirmados** da NI-001 e NI-002, caso ainda não
   estejam no conjunto de julgamento da respectiva necessidade.

**Previsão de esforço** (a partir da contagem exploratória persistida em
`runs/pools/contagem_exploratoria/EXPLORATORY_counting.json`):

| Componente | Pares distintos |
|---|---|
| União top-5 (3 needs, vetorial ∪ híbrida, 3 formulações, deduplicado) | 52 |
| Acréscimo para cobrir os 21 da NI-003 (além do que já cai no recorte) | 13 |
| **Subtotal** | **65** |
| Eventual inclusão dos 2 documentos de referência (NI-001, NI-002), se ainda ausentes | +0 a +2 |
| **Teto aprovado** | **67** |

Estes números são **previsão** baseada na contagem exploratória; o total **deve
ser reconferido na execução oficial** e **não** se presume idêntico caso os
resultados de recuperação mudem.

### 12.3 Métricas e limitações desta avaliação reduzida

- **Precision@5** (vetorial e híbrida) poderá ser calculada quando os documentos
  do respectivo corte top-5 estiverem julgados. **Convenção ratificada pela
  pesquisadora (Vitoria Novaes da Costa):** `Precision@5 = (relevantes nos top-5)
  / 5`, com **denominador fixo = 5**, registrando **separadamente** a quantidade
  de documentos efetivamente retornados (`n_retornado`); quando não houver
  resultados, `Precision@5 = 0`. A métrica aplica-se **apenas** aos rankings
  vetorial e híbrida — **nunca** ao conjunto estruturado (que não tem ordenação
  de relevância). Esta convenção resolve o item [A DEFINIR] de "Precision@k para
  listas < k" **no caso k=5 do recorte reduzido**.
- A **estruturada retorna conjuntos sem ranking de relevância**; não se atribui
  posição artificial aos seus documentos.
- A **precisão integral de conjuntos estruturados grandes NÃO** será estimada
  como se todos os documentos tivessem sido julgados (conjuntos como os 319 de
  denúncias ou os 1.414 de representações ficam majoritariamente não julgados).
- A **inspeção completa dos 21** candidatos da NI-003 permite avaliar a relevância
  **dentro desse universo restrito**, sem confundi-lo com todo o corpus.
- **Documentos não julgados permanecem com relevância desconhecida**, nunca
  automaticamente irrelevantes (consistente com §4.3 e §5).
- **Não** se reivindica **recall absoluto do corpus**.
- **Não** se apresentam estimativas de **confiança de 95%** ou **margem de erro de
  ±10 p.p.** (o plano `s_R` da §4.4 **não** foi aplicado ao conjunto reduzido);
  qualquer número dessa natureza referente a este recorte seria indevido.
- **Recall-sob-pool** e métricas correlatas só serão apresentadas quando seus
  **denominadores e conjuntos efetivamente julgados** sustentarem o cálculo, com
  as limitações da §5 explicitadas.
- A comparação é **exploratória**, restrita às três necessidades, **sem** pretensão
  de demonstrar superioridade estatística geral de qualquer arquitetura
  (consistente com a neutralidade experimental do protocolo).

### 12.4 Relação com o plano amostral original (§4)

- O **estimador estratificado** e a **fórmula `s_R`** (§4, §4.4) permanecem como
  **desenho de referência documentado**; **não** foram executados e **não** devem
  ser apresentados como aplicados ao conjunto reduzido.
- A avaliação principal concentra-se no **top-5** (vetorial/híbrida) e no
  **universo restrito de 21** da NI-003.
- Caso, futuramente, se decida estimar a precisão de um conjunto estruturado
  grande, isso exigiria **retomar explicitamente** o plano da §4 — o que seria uma
  nova decisão, fora do recorte aprovado aqui.

### 12.5 Pendências que esta adaptação torna supérfluas ou redefine

- **`s_R` / `e` / confiança (§4.4):** deixam de ser pré-requisito para a avaliação
  principal aprovada (não há amostragem de estrato R no recorte reduzido).
  Permanecem documentados para o caso de retomada futura do plano da §4.
- **Convenção de Precision@k para listas < k:** continua relevante, pois o top-5
  pode, em tese, ter menos de 5 itens em alguma formulação; permanece **[A
  DEFINIR]** e deve ser fixada antes da execução oficial.
- **Número de necessidades:** fixado em **três** para este estudo de casos
  exploratório.

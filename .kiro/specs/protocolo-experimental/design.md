# Design Document — Protocolo Experimental

## Overview

Este documento descreve o **desenho metodológico** (protocolo científico) do experimento que
compara três arquiteturas de recuperação de informação — **estruturada**, **vetorial** e
**híbrida** — sobre a Selecao_Experimental de acórdãos do TCU (2024, 21.631 documentos).

O design é **conceitual**: define entidades, fluxo experimental, variáveis e o mapa do que
está decidido versus aberto. Ele **não** especifica nem implementa limpeza de HTML, chunking,
embeddings, índices, consultas, métricas ou LLM. A execução técnica é escopo de uma spec
futura separada (ex.: `execucao-experimento`), não criada aqui.

A intenção central: tratar a **arquitetura de recuperação como fator central** do estudo.
Na comparação pareada de uma **mesma formulação** entre arquiteturas, a arquitetura é o
único fator alterado, mantendo-se constantes as variáveis controladas (universo documental,
gerador/prompt/parâmetros, política de contexto, avaliação), de modo que diferenças na
resposta final sejam atribuíveis à recuperação — e, com o registro da recuperação
intermediária, possa-se separar erro de recuperação de erro de geração. Além do fator
central, o experimento também estuda variação em dois **fatores experimentais**: a natureza
da necessidade de informação (tipologia **[DECIDIDO]**: metadados/textual/mista) e a
formulação da consulta (tipologia **[DECIDIDO]**: direta/parafraseada/prolixa).

> **Convenção de status:** cada bloco relevante marca **[DECIDIDO]**, **[EM ESTUDO]**,
> **[A DEFINIR]** ou **[OBSERVADO]** (resultado empírico já medido, que não representa
> decisão metodológica). Para itens abertos, indica-se a dependência de resolução:
> `literatura`, `análise do corpus`, `teste de viabilidade`, `controle experimental`.
> Nenhuma decisão aberta é fechada nesta spec.

---

## Estrutura conceitual do experimento

```
                    Necessidade de informação
                              │
                              ▼
             diferentes formulações da consulta
                              │
        ┌─────────────┬───────┴───────┬─────────────┐
        │ estruturada │   vetorial    │   híbrida   │
        └──────┬──────┴───────┬───────┴──────┬──────┘
               ▼              ▼              ▼
           evidências     evidências     evidências
           recuperadas    recuperadas    recuperadas
               │              │              │
               └────────── mesmo gerador ────┘
                              │
                              ▼
                        resposta final
                              │
                              ▼
                          avaliação
```

Leitura do fluxo:
- Uma **necessidade de informação** dá origem a uma ou mais **formulações** de **consulta**.
- Cada formulação do núcleo comparativo é submetida, **sem alteração de conteúdo**, às três
  **arquiteturas** (processadas em paralelo). A natureza da necessidade (estruturada,
  textual ou mista) **não** restringe a quais arquiteturas a formulação é submetida.
- Cada arquitetura retorna **evidências recuperadas** (documento, chunk ou outra unidade
  aplicável, podendo possuir rank/score quando aplicável).
- As evidências alimentam o **mesmo gerador** (mesmo prompt/parâmetros/política de contexto),
  que produz a **resposta final**.
- A **avaliação** ocorre em dois níveis: recuperação (evidências) e resposta final.

---

## Modelo de entidades conceituais

Hierarquia da unidade experimental (não é schema de implementação; nomes de campos são
ilustrativos e **não** congelados):

```
Necessidade de informação (information_need)  — natureza: metadados | textual | mista  [DECIDIDO]
  └─ Formulação (formulation)  — direta | parafraseada | prolixa  [DECIDIDO]
       └─ Consulta (query) submetida a uma Arquitetura
            └─ Evidência recuperada (documento, chunk ou outra unidade; rank/score quando aplicável)
                 └─ Contexto → Gerador → Resposta final
```

| Entidade | Definição | Status |
|---|---|---|
| Necessidade de informação | Demanda informacional de alto nível; unidade de organização da avaliação | [DECIDIDO] existência; [DECIDIDO] tipologia (metadados/textual/mista) |
| Formulação | Variante de consulta que expressa a mesma necessidade | [DECIDIDO] existência, condições (direta/parafraseada/prolixa) e regras de equivalência |
| Consulta (query) | Expressão concreta submetida a uma arquitetura | [DECIDIDO] papel |
| Documento | Acórdão, unidade = `doc_id` | [DECIDIDO] |
| Chunk | Fragmento de documento, se a vetorial operar por fragmentos | [A DEFINIR] existência |
| Evidência recuperada | Documento, chunk ou outra unidade aplicável; rank/score quando aplicável (a estruturada pode não ter ranking/score natural) | [DECIDIDO] papel; [EM ESTUDO] schema de registro |
| Resposta final | Texto gerado a partir das evidências | [DECIDIDO] papel |

> A distinção **necessidade ≠ consulta ≠ formulação ≠ documento ≠ chunk ≠ evidência ≠
> resposta** é deliberada: a avaliação se organiza por necessidade de informação, enquanto
> a recuperação opera por consulta/formulação e a geração por consulta.

---

## Variáveis do experimento

- **Fator central [DECIDIDO]:** a arquitetura de recuperação (estruturada, vetorial,
  híbrida). É o fator cujo efeito o experimento busca isolar na comparação pareada.
- **Fatores experimentais:** a **natureza da necessidade de informação** e a **formulação
  da consulta**, ambas variando deliberadamente entre casos. As **tipologias** da natureza da
  necessidade (metadados/textual/mista) e das formulações (direta/parafraseada/prolixa) estão
  **[DECIDIDO]** (ver Requirement 5); os **valores** variam entre casos.
- **Variáveis controladas (constantes quando aplicável) [DECIDIDO]:** gerador, prompt,
  política de contexto, universo documental (os 21.631 `doc_id`) e procedimento de
  avaliação, além das demais condições aplicáveis.
- **Variáveis dependentes (observadas):** qualidade da recuperação (evidências) e qualidade
  da resposta final. As **métricas específicas** dessas variáveis estão **[EM ESTUDO] /
  [A DEFINIR]** (ver Avaliação).

> **Comparação pareada:** para uma **mesma formulação**, a arquitetura de recuperação é o
> único fator alterado entre as três condições; as variáveis controladas permanecem
> constantes. A arquitetura é o fator central, mas **não** é o único fator estudado no
> conjunto do experimento (os fatores experimentais acima também variam, de forma
> deliberada, entre necessidades/formulações).

---

## Arquitetura A — Estruturada

**[DECIDIDO]**
- Baseia-se em campos estruturados/metadados; **não** é BM25 nem busca lexical/esparsa.
- Opera sobre os mesmos 21.631 `doc_id`.

**[A DEFINIR]** (dependências entre colchetes)
- Tradução de linguagem natural (formulação) em filtros estruturados. [`literatura`, `teste de viabilidade`]
- Quais campos de metadados são usados (`COLEGIADO`, `RELATOR`, `TIPOPROCESSO`,
  `DATASESSAO`, `ENTIDADE`, `UNIDADETECNICA`). [`análise do corpus`, `controle experimental`]
- Tratamento de consultas sem filtro estrutural explícito. [`teste de viabilidade`, `literatura`]
- Existência ou não de interpretador automático de consulta. [`teste de viabilidade`, `literatura`]
- Produção e ordenação dos resultados. [`literatura`, `controle experimental`]

---

## Arquitetura B — Vetorial

**[DECIDIDO]**
- Baseia-se em representação vetorial/semântica dos campos textuais principais
  (`ASSUNTO`, `ACORDAO`), operando sobre os mesmos 21.631 `doc_id`.

**[OBSERVADO]** — diagnóstico empírico, apenas para orientar decisões futuras:
- 21.631 documentos.
- ACORDAO limpo temporariamente (somente em memória): mediana ~166 palavras; P90 ~554;
  P95 ~740; P99 ~1.125.
- 339 docs > 1.000 palavras; 64 > 2.000; 49 > 4.000; nenhum > 8.000.
- Limpeza exploratória de HTML reduziu ~1/3 do tamanho médio sem perda grave aparente.

> Esses números são **[OBSERVADO]**, **não** decisões de chunking/unidade/embedding/parâmetro.

**[A DEFINIR]** (dependências entre colchetes)
- Limpeza definitiva de HTML. [`análise do corpus`, `teste de viabilidade`]
- Combinação de `ASSUNTO` + `ACORDAO`. [`análise do corpus`, `teste de viabilidade`, `literatura`]
- Modelo de embedding. [`literatura`, `teste de viabilidade`]
- Tokenizer. [`literatura`, `teste de viabilidade`]
- Documento inteiro vs. chunks. [`análise do corpus`, `teste de viabilidade`, `literatura`]
- Chunking, tamanho e overlap (se houver). [`análise do corpus`, `teste de viabilidade`, `literatura`]
- Agregação chunk → `doc_id` (se houver chunks). [`literatura`, `teste de viabilidade`]
- Medida de similaridade. [`literatura`, `teste de viabilidade`]
- Top-k. [`literatura`, `controle experimental`]

---

## Arquitetura C — Híbrida

**[DECIDIDO]**
- A híbrida **não** será um roteador que escolhe entre a arquitetura estruturada OU a
  vetorial.
- Combinará componentes estruturados e vetoriais segundo uma **regra fixa e reproduzível**.
- Implementada por **composição** de `StructuredRetriever` (v0.3.0) e `VectorRetriever`
  (v0.2.0), sem alterá-los; cumpre a interface comum `Retriever` (`HybridRetriever` v0.2.0).

**[DECIDIDO]** — política de fallback (aprovada; três caminhos mutuamente exclusivos)
- **Caso A** (nenhuma condição reconhecida): recuperação vetorial global
  (`path="vector_global_fallback"`). Nesse caso a híbrida equivale à vetorial para aquela
  consulta — a considerar na análise.
- **Caso B** (condições reconhecidas, interseção vazia): resultado **vazio**
  (`path="structured_no_candidates"`), sem fallback global e sem relaxar filtros.
- **Caso C** (condições reconhecidas e candidatos): filtro estruturado (AND) seguido de
  ranking vetorial (`path="structured_filter_then_vector_rank"`).

**[DECIDIDO]** — regra de combinação do Caso C (ratificada pelo pesquisador)
- Filtragem estruturada pela conjunção (AND) das condições; ranking de **todos os
  documentos candidatos elegíveis** (sem pré-corte por Top-k vetorial global);
  similaridade de cosseno calculada sobre **todos os chunks** dos candidatos; score por
  documento via **max-pooling**; ordenação por score decrescente com desempate por
  `doc_id`; limite de exibição aplicado após o ranking.
- **Justificativa:** simplicidade, determinismo, interpretabilidade, compatibilidade com a
  estruturada (conjunto, não ranking) e independência do gold standard. RRF e fusão
  ponderada **não** são diretamente aplicáveis à saída estruturada atual sem acrescentar
  ranking/score de relevância; por isso não foram adotadas.
- **Ressalvas:** recall do Caso C limitado pela cobertura/correção dos filtros; condições
  incorretas/restritivas podem excluir relevantes; a consulta vetorial permanece integral
  (pode reforçar termos já usados no filtro, sem duplicação matemática de scores);
  max-pooling pode favorecer documentos com mais chunks e não premia evidência distribuída.
  Ver `docs/experimento/decisao_estrategia_hibrida_e_integridade.md`.

**[DECIDIDO]** — integridade/reprodutibilidade na execução
- Execuções oficiais usam `HybridRetriever.from_artifacts(..., verify_integrity=True)`:
  recálculo do fingerprint da seleção (função canônica do projeto) comparado ao índice e,
  quando existir, ao manifesto; correspondência exata dos conjuntos de `doc_id`; rejeição
  de índice parcial/inconsistente no carregamento. `verify_integrity=False` e o construtor
  direto **não** oferecem essas garantias e não são usados em execuções oficiais.

**[A DEFINIR]**
- O valor de **Top-k** final da comparação (comum às três arquiteturas) permanece aberto;
  o `display_limit=10` atual é apenas provisório de exibição. [`controle experimental`, `literatura`]

---

## Necessidades de informação e formulações

**[DECIDIDO]**
- A unidade experimental é organizada por **necessidade de informação**; cada necessidade
  admite múltiplas **formulações** equivalentes.
- A **natureza das necessidades** tem três categorias operacionais (ver Requirement 5):
  - **Baseada em metadados:** satisfatível exclusivamente por operações sobre atributos
    documentais (seleção, contagem, identificação, agregação), sem interpretação textual.
  - **Textual:** exige informação do conteúdo dos documentos, sem condição estruturada
    obrigatória para definir os documentos pertinentes.
  - **Mista:** tem ao menos uma condição estruturada obrigatória para delimitar os
    documentos pertinentes e exige informação obtida/interpretada no conteúdo textual.
- Regras da classificação (ver Requirement 5 para o enunciado normativo completo):
  considera informações solicitadas **e** condições de pertinência; ocorre **antes** da
  recuperação e não depende de seus resultados; informação de fonte dupla (metadados **e**
  texto) não caracteriza mista por si só; uma condição documental obrigatória pode tornar a
  necessidade mista ainda que a resposta final seja textual; a quantidade de documentos
  relevantes é atributo **ortogonal** (não é categoria); natureza e formulação são dimensões
  distintas; todas as formulações vão às três arquiteturas, sem direcionamento por categoria;
  NI-01/NI-02/NI-03 permanecem exploratórios; as categorias são **operacionais** desta
  pesquisa, fundamentadas na literatura, e não constituem taxonomia atribuível aos autores
  citados.

- **Condições de formulação** (ver Requirement 5), categorias operacionais desta pesquisa,
  **não** atribuíveis a Bailey et al. (2016) nem a Hagen, Scells e Potthast (2024):
  - **Direta:** expressão objetiva e concisa; formulação de referência.
  - **Parafraseada:** reescrita lexical/sintática preservando o significado, com extensão
    aproximadamente semelhante à direta.
  - **Prolixa:** mais extensa (explicações, redundâncias), sem acrescentar condições, fatos
    solicitados ou pistas que revelem a resposta.
  - Formulações **ruidosas** ficam **fora** do núcleo experimental neste momento.
- **Ficha de invariantes** (ver Requirement 5): cada necessidade tem uma ficha criada
  **antes** da recuperação, com id, descrição, natureza, escopo documental/temporal,
  condições obrigatórias, fatos solicitados, operações exigidas, as três formulações e o
  estado/justificativa da validação de equivalência. A ficha documenta a necessidade; **não**
  substitui o gold.
- **Regras de equivalência:** as três formulações preservam (1) a necessidade, (2) o escopo
  documental/temporal, (3) as condições obrigatórias, (4) os fatos solicitados e (5) as
  operações necessárias. É proibido introduzir fatos que modifiquem a necessidade, antecipem
  a resposta ou revelem identificadores do documento-alvo ausentes na necessidade original.
  Sinônimos e reformulações lexicais legítimas são permitidos (a variação faz parte do objeto
  de estudo). A equivalência é revisada e registrada **antes** da execução; segunda revisão
  independente é **desejável**.

**[DECIDIDO]** — armazenamento e identificação (ver Requirement 5)
- Fichas em **YAML**, **um arquivo por necessidade**, em `evaluation/questions/needs/`,
  validadas por modelo Pydantic (`NeedSheet`). Gold/julgamentos ficam em
  `evaluation/reference/` (separados da ficha).
- `need_id` das fichas definitivas segue `^NI-[0-9]{3}$` (ex.: `NI-001`); os pilotos
  `NI-01/02/03` permanecem só em `docs/experimento/`.
- Vínculo ao corpus congelado por `scope.selection_fingerprint` (= manifesto da seleção).
  Validação estrutural checa presença/formato (SHA-256 64 hex); a conferência
  ficha×manifesto×corpus é **separada**, sem recalcular o fingerprint em cada leitura.

---

## Geração (comum às três arquiteturas)

**[DECIDIDO]** — princípio de invariância do gerador
- Mesmo modelo, mesmo prompt, mesmos parâmetros.
- Mesma política de contexto, mesmo limite de saída.
- Mesma aleatoriedade/seed entre arquiteturas, quando tecnicamente possível.
- O pipeline gera uma resposta final por consulta.
- O experimento **não** compara LLMs.

**[A DEFINIR]**
- Modelo gerador específico. Preferência por execução local/reprodutível, **sem** fixar
  runtime (ex.: Ollama) nem modelo. [`teste de viabilidade`, `literatura`]

---

## Registro da recuperação intermediária

**[DECIDIDO]**
- Para cada consulta e arquitetura, a recuperação intermediária é registrada de forma
  auditável, com o objetivo de **separar erro de recuperação de erro de geração**.

**[EM ESTUDO]** — schema não congelado; campos previstos (ilustrativos):
`query_id`, `architecture`, `doc_id`, `chunk_id` (se aplicável), `rank` (quando aplicável),
`score` (quando aplicável), evidência, contexto enviado ao gerador. Nem toda arquitetura tem
rank/score natural (ex.: a estruturada pode não ter). [`controle experimental`,
`teste de viabilidade`]

---

## Gold / reference

**[DECIDIDO]**
- Distinção entre **referência documental/evidência** (o que deveria ser recuperado) e
  **referência da resposta** (o que a resposta final deveria conter/afirmar).

**[DECIDIDO]**
- Construção por **pooling** das três arquiteturas, profundidade **D=50** por formulação, +
  complemento pelas condições obrigatórias da ficha; conjunto estruturado julgado integralmente
  até **T=100** e, acima, por amostragem estratificada (estrato I = censo dos já no pool;
  estrato R = amostra aleatória do restante). Ver
  `docs/experimento/proposta_operacional_avaliacao_e_gold.md`.
- **Granularidade:** `doc_id` (evidência textual como apoio, não unidade).
- **Julgamento binário** (relevante/não relevante); `uncertain` apenas durante a revisão.
- Documentos **não julgados** permanecem **desconhecidos** (nunca não relevantes).

**[DECIDIDO — ADAPTAÇÃO OPERACIONAL (Alternativa B)]**
- Por inviabilidade de centenas de julgamentos humanos, a pesquisadora aprovou um **recorte
  reduzido de julgamento** (estudo de casos exploratório): **união dos top-5 de vetorial e
  híbrida** (3 formulações × 3 necessidades, deduplicado por `(need_id, doc_id)`) + **universo
  restrito de 21 acórdãos da NI-003** (ENTIDADE = ANTT ∧ TIPOPROCESSO = Representação) +
  documentos de referência de NI-001/NI-002 ainda ausentes; teto previsto **67 julgamentos**.
- O recorte afeta **apenas o desenho de julgamento e o alcance das conclusões**; **D=50**
  (profundidade de recuperação) permanece e é distinta do corte de julgamento; o plano `s_R`
  segue documentado como referência e **não** é aplicado ao conjunto reduzido. Ver
  `docs/experimento/proposta_operacional_avaliacao_e_gold.md` §12.

**[A DEFINIR]** (dependências entre colchetes)
- Critérios detalhados de relevância por necessidade, incl. relevância parcial em
  necessidades multidocumentais. [`controle experimental`]
- Regra de dimensionamento de `s_R` (não aplicável ao recorte reduzido; referência para
  eventual retomada do plano amostral). [`controle experimental`]
- Procedimento de revisão/adjudicação e número de revisores. [`controle experimental`]
- Formato de armazenamento definitivo em `evaluation/reference/`. [`teste de viabilidade`]
- Tratamento de necessidades sem relevantes, se admitidas. [`controle experimental`]

---

## Avaliação

**Recuperação (evidências):**
- **[DECIDIDO]** Avaliação **multidimensional**: métricas de conjunto/cobertura para as três
  arquiteturas (com o tamanho do resultado reportado); métricas de ranking apenas para
  vetorial e híbrida. Estruturada avaliada como **conjunto**, sem ranking artificial.
- **[DECIDIDO]** Cortes de ranking **k ∈ {5, 10, 50}** (vetorial/híbrida); profundidade de
  pooling **D=50**; `display_limit ≥ max(k)` para não truncar antes das métricas.
- **[DECIDIDO]** **Orçamento de recuperação** (métricas) e **orçamento de contexto do gerador**
  são separados e não precisam coincidir.
- **[EM ESTUDO]** Conjunto específico de métricas (ex.: Precision@k, Recall-sob-pool@k,
  nDCG@k, MRR) e a convenção de Precision@k para listas menores que k. [`literatura`,
  `controle experimental`]

**Resposta final:**
- **[A DEFINIR]** Como medir correção factual, completude, suporte nas evidências e
  afirmações não sustentadas. [`literatura`, `controle experimental`]
- **[A DEFINIR]** Modalidade de avaliação (humana, automática, LLM-juiz) — não decidida agora.
  [`literatura`, `teste de viabilidade`, `controle experimental`]

---

## Fronteiras de escopo

**Fora do escopo desta spec (protocolo):**
- Qualquer implementação de código.
- Limpeza definitiva de HTML, chunking, embeddings, índices, consultas, métricas, LLM.
- Criação de `tasks.md`.
- Alterações na spec `construcao-corpus-piloto`, no corpus ou nos configs.

**Relação com specs vizinhas:**
- Herda os artefatos e definições de `construcao-corpus-piloto` (Corpus_Canonico,
  Selecao_Experimental, `doc_id`/`source_key`, campos textuais e metadados).
- Uma spec futura de execução (ex.: `execucao-experimento`) poderá materializar as decisões
  aqui deixadas abertas, sem que esta spec as feche antecipadamente.

---

## Mapa de decisões (resumo)

| Item | Status | Dependência |
|---|---|---|
| Domínio (acórdãos TCU), recorte 2024 | DECIDIDO | — |
| Corpus 21.661 / Seleção 21.631 / mesmos `doc_id` | DECIDIDO | — |
| Unidade documental = acórdão / `doc_id` | DECIDIDO | — |
| Unidade experimental / organização da avaliação = necessidade de informação | DECIDIDO | — |
| Campos textuais principais: ASSUNTO, ACORDAO | DECIDIDO | — |
| Metadados disponíveis (6 campos) | DECIDIDO | — |
| SUMARIO/RELATORIO/VOTO preservados, fora da baseline | DECIDIDO | — |
| 3 arquiteturas; recuperação é o fator central | DECIDIDO | — |
| Cada formulação do núcleo comparativo vai às 3 arquiteturas (sem alterar conteúdo) | DECIDIDO | — |
| Diversidade vem de necessidades/formulações, não de perguntas exclusivas por arquitetura | DECIDIDO | — |
| Estruturada ≠ BM25/lexical | DECIDIDO | — |
| Híbrida NÃO é roteador; combina por regra fixa reproduzível | DECIDIDO | — |
| Mesmo gerador/prompt/parâmetros; não compara LLMs | DECIDIDO | — |
| Registrar recuperação intermediária (objetivo) | DECIDIDO | — |
| Variáveis controladas constantes (gerador, prompt, contexto, universo, avaliação) | DECIDIDO | — |
| Comparação pareada: arquitetura é o único fator alterado p/ mesma formulação | DECIDIDO | — |
| Fatores experimentais: natureza da necessidade e formulação (tipologias decididas; valores variam entre casos) | DECIDIDO | — |
| Distinção referência documental × referência da resposta | DECIDIDO | — |
| Tipologia de necessidades (baseada em metadados / textual / mista) + 9 regras de classificação | DECIDIDO | — |
| Condições de formulação (direta/parafraseada/prolixa); sem ruidosa no núcleo | DECIDIDO | — |
| Ficha de invariantes por necessidade (criada antes da recuperação; não é o gold) | DECIDIDO | — |
| Regras de equivalência entre formulações + validação prévia (2ª revisão desejável) | DECIDIDO | — |
| Fichas em YAML (1 por necessidade) em evaluation/questions/needs/, validadas por Pydantic (NeedSheet); gold em evaluation/reference/ | DECIDIDO | — |
| need_id definitivo `^NI-[0-9]{3}$` (pilotos NI-01/02/03 só em docs/) | DECIDIDO | — |
| Vínculo ao corpus via scope.selection_fingerprint; conferência ao manifesto é validação separada | DECIDIDO | — |
| Combinação ASSUNTO+ACORDAO na representação vetorial | A DEFINIR | análise do corpus, teste de viabilidade, literatura |
| Schema do registro intermediário | EM ESTUDO | controle experimental, teste de viabilidade |
| Desenho de avaliação multidimensional (conjunto p/ as três + ranking p/ vetorial/híbrida) | DECIDIDO | — |
| Cortes de ranking k ∈ {5,10,50} (vetorial/híbrida); profundidade de pooling D=50 | DECIDIDO | — |
| Teto T=100 p/ julgamento integral do conjunto estruturado (acima: amostragem estratificada) | DECIDIDO | — |
| Julgamento binário relevante/não-relevante (`uncertain` só na revisão) | DECIDIDO | — |
| Estruturada avaliada como conjunto, sem ranking artificial | DECIDIDO | — |
| Separação orçamento de recuperação × orçamento de contexto do gerador | DECIDIDO | — |
| Conjunto específico de métricas e convenção de Precision@k p/ listas < k | EM ESTUDO | literatura, controle experimental |
| Política de fallback da híbrida (Casos A/B/C) | DECIDIDO | — |
| Integridade na execução da híbrida (`verify_integrity=True`) | DECIDIDO | — |
| Regra de combinação do Caso C (filtro → ranking vetorial, max-pooling) | DECIDIDO | — |
| Dimensionamento de `s_R` (amostra do estrato restante da estruturada) | A DEFINIR | controle experimental |
| Modelo gerador / runtime | A DEFINIR | teste de viabilidade, literatura |
| Critérios de equivalência semântica de formulações | A DEFINIR | literatura, controle experimental |
| Estruturada: NL→filtros, campos, sem-filtro, interpretador, ordenação | A DEFINIR | literatura, teste de viabilidade, análise do corpus, controle experimental |
| Vetorial: HTML, embedding, tokenizer, doc×chunk, chunking, agregação, similaridade, Top-k | A DEFINIR | análise do corpus, teste de viabilidade, literatura, controle experimental |
| Gold: pooling (D=50)+complemento por condições; granularidade doc_id; binário; não-julgado=desconhecido | DECIDIDO | — |
| Gold: critérios de relevância por necessidade, revisão/adjudicação, formato, necessidades sem relevantes | A DEFINIR | controle experimental, teste de viabilidade |
| Avaliação da resposta final e modalidade | A DEFINIR | literatura, teste de viabilidade, controle experimental |

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

**[A DEFINIR]** (dependências entre colchetes)
- Estratégia exata de combinação (ex.: filtro estrutural → ranking vetorial; fusão de
  listas; ponderação de scores). [`literatura`, `teste de viabilidade`, `controle experimental`]

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

**[A DEFINIR]** (dependências entre colchetes)
- Método de construção do gold. [`literatura`, `controle experimental`]
- Critérios de relevância. [`literatura`, `controle experimental`]
- Granularidade (documento/chunk/trecho). [`literatura`, `análise do corpus`]
- Julgamento binário vs. gradual. [`literatura`]
- Pooling. [`literatura`, `teste de viabilidade`]
- Revisão. [`controle experimental`]
- Formato de armazenamento. [`teste de viabilidade`]

---

## Avaliação

**Recuperação (evidências):**
- **[EM ESTUDO]** Candidatas: Precision@k, Recall@k, nDCG@k. Métricas finais e valores de k
  ainda não definidos. [`literatura`, `controle experimental`]

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
| Métricas de recuperação (P@k, R@k, nDCG@k) e k | EM ESTUDO | literatura, controle experimental |
| Estratégia exata da híbrida | A DEFINIR | literatura, teste de viabilidade, controle experimental |
| Modelo gerador / runtime | A DEFINIR | teste de viabilidade, literatura |
| Critérios de equivalência semântica de formulações | A DEFINIR | literatura, controle experimental |
| Estruturada: NL→filtros, campos, sem-filtro, interpretador, ordenação | A DEFINIR | literatura, teste de viabilidade, análise do corpus, controle experimental |
| Vetorial: HTML, embedding, tokenizer, doc×chunk, chunking, agregação, similaridade, Top-k | A DEFINIR | análise do corpus, teste de viabilidade, literatura, controle experimental |
| Gold: construção, relevância, granularidade, binário/gradual, pooling, revisão, formato | A DEFINIR | literatura, controle experimental, análise do corpus, teste de viabilidade |
| Avaliação da resposta final e modalidade | A DEFINIR | literatura, teste de viabilidade, controle experimental |

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
central, o experimento também pretende estudar variação em dois **fatores experimentais**
ainda **[EM ESTUDO]**: a natureza da necessidade de informação e a formulação da consulta.

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
- Cada arquitetura retorna **evidências recuperadas** (documentos ou chunks, com rank/score).
- As evidências alimentam o **mesmo gerador** (mesmo prompt/parâmetros/política de contexto),
  que produz a **resposta final**.
- A **avaliação** ocorre em dois níveis: recuperação (evidências) e resposta final.

---

## Modelo de entidades conceituais

Hierarquia da unidade experimental (não é schema de implementação; nomes de campos são
ilustrativos e **não** congelados):

```
Necessidade de informação (information_need)
  └─ Formulação (formulation)  — direta | parafraseada | prolixa  [EM ESTUDO]
       └─ Consulta (query) submetida a uma Arquitetura
            └─ Evidência recuperada (documento inteiro ou chunk, rank, score)
                 └─ Contexto → Gerador → Resposta final
```

| Entidade | Definição | Status |
|---|---|---|
| Necessidade de informação | Demanda informacional de alto nível; unidade de organização da avaliação | [DECIDIDO] existência; [EM ESTUDO] tipologia |
| Formulação | Variante de consulta que expressa a mesma necessidade | [DECIDIDO] existência; [EM ESTUDO] tipologia e critérios de equivalência |
| Consulta (query) | Expressão concreta submetida a uma arquitetura | [DECIDIDO] papel |
| Documento | Acórdão, unidade = `doc_id` | [DECIDIDO] |
| Chunk | Fragmento de documento, se a vetorial operar por fragmentos | [A DEFINIR] existência |
| Evidência recuperada | Item retornado (doc/chunk) com rank e score | [DECIDIDO] papel; [EM ESTUDO] schema de registro |
| Resposta final | Texto gerado a partir das evidências | [DECIDIDO] papel |

> A distinção **necessidade ≠ consulta ≠ formulação ≠ documento ≠ chunk ≠ evidência ≠
> resposta** é deliberada: a avaliação se organiza por necessidade de informação, enquanto
> a recuperação opera por consulta/formulação e a geração por consulta.

---

## Variáveis do experimento

- **Fator central [DECIDIDO]:** a arquitetura de recuperação (estruturada, vetorial,
  híbrida). É o fator cujo efeito o experimento busca isolar na comparação pareada.
- **Fatores experimentais [EM ESTUDO]:** a **natureza da necessidade de informação** e a
  **formulação da consulta**. O experimento pretende estudar sua variação; ambas as
  classificações permanecem EM ESTUDO e não são congeladas.
  Dependência: `literatura`, `análise do corpus`, `controle experimental`.
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

**[EM ESTUDO]** (hipóteses provisórias, não congeladas)
- Natureza das necessidades: estruturada/metadados, textual/semântica, mista.
  [`literatura`, `análise do corpus`]
- Tipologia de formulações: direta, parafraseada, prolixa.
  [`literatura`, `controle experimental`]

**[A DEFINIR]**
- Critérios objetivos de equivalência semântica entre formulações da mesma necessidade.
  [`literatura`, `controle experimental`]

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
`query_id`, `architecture`, `doc_id`, `chunk_id` (se aplicável), `rank`, `score`, evidência,
contexto enviado ao gerador. [`controle experimental`, `teste de viabilidade`]

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
| Unidade = acórdão / `doc_id`; avaliação por necessidade | DECIDIDO | — |
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
| Fatores experimentais: natureza da necessidade e formulação (variam, em estudo) | EM ESTUDO | literatura, análise do corpus, controle experimental |
| Distinção referência documental × referência da resposta | DECIDIDO | — |
| Tipologia de necessidades (estruturada/textual/mista) | EM ESTUDO | literatura, análise do corpus |
| Tipologia de formulações (direta/parafraseada/prolixa) | EM ESTUDO | literatura, controle experimental |
| Combinação ASSUNTO+ACORDAO | EM ESTUDO/A DEFINIR | análise do corpus, teste de viabilidade, literatura |
| Schema do registro intermediário | EM ESTUDO | controle experimental, teste de viabilidade |
| Métricas de recuperação (P@k, R@k, nDCG@k) e k | EM ESTUDO | literatura, controle experimental |
| Estratégia exata da híbrida | A DEFINIR | literatura, teste de viabilidade, controle experimental |
| Modelo gerador / runtime | A DEFINIR | teste de viabilidade, literatura |
| Critérios de equivalência semântica de formulações | A DEFINIR | literatura, controle experimental |
| Estruturada: NL→filtros, campos, sem-filtro, interpretador, ordenação | A DEFINIR | literatura, teste de viabilidade, análise do corpus, controle experimental |
| Vetorial: HTML, embedding, tokenizer, doc×chunk, chunking, agregação, similaridade, Top-k | A DEFINIR | análise do corpus, teste de viabilidade, literatura, controle experimental |
| Gold: construção, relevância, granularidade, binário/gradual, pooling, revisão, formato | A DEFINIR | literatura, controle experimental, análise do corpus, teste de viabilidade |
| Avaliação da resposta final e modalidade | A DEFINIR | literatura, teste de viabilidade, controle experimental |

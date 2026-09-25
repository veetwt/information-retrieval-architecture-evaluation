# Requirements Document — Protocolo Experimental

## Introduction

Esta spec documenta o **desenho metodológico** (protocolo científico) do experimento de
comparação entre três arquiteturas de recuperação de informação — **estruturada**,
**vetorial** e **híbrida** — aplicadas sobre a Selecao_Experimental de acórdãos públicos do
TCU (recorte 2024). O objetivo é registrar, de forma rastreável, o que já está **DECIDIDO**,
o que está **EM ESTUDO** e o que ainda está **A DEFINIR**, sem antecipar decisões abertas.

Esta spec é de **protocolo científico**, não de implementação. Ela **não** especifica nem
implementa limpeza de HTML, chunking, embeddings, índices, consultas, métricas ou LLM. A
execução técnica (código, índices, geração, métricas) poderá ser objeto de uma spec futura
separada (por exemplo, `execucao-experimento`), que **não** é criada aqui.

A variável central do experimento é a **arquitetura de recuperação**. As demais condições
(universo documental, necessidades de informação, formulações, gerador, prompt, política de
contexto e procedimento de avaliação) são mantidas constantes, quando aplicável, para
isolar o efeito da arquitetura.

### Convenção de status

Cada requisito é marcado com um status e, quando aberto, com a dependência que o resolverá:

- **[DECIDIDO]** — consolidado; não deve ser reaberto sem justificativa explícita.
- **[EM ESTUDO]** — há hipótese provisória, mas ainda sujeita a fundamentação/validação.
- **[A DEFINIR]** — ainda não há hipótese consolidada.
- **[OBSERVADO]** — resultado empírico já medido no corpus/diagnóstico; **não** representa
  decisão metodológica e não define nenhum parâmetro do experimento.
- Dependências possíveis: `literatura`, `análise do corpus`, `teste de viabilidade`,
  `controle experimental`.

---

## Glossary

Distinção conceitual central da unidade experimental (do mais abstrato ao mais concreto):

- **Necessidade de informação**: A demanda informacional de alto nível que o usuário/juiz
  deseja satisfazer, independente de como é expressa. É a unidade em torno da qual a
  avaliação é organizada. Uma mesma necessidade pode ter múltiplas formulações equivalentes.
- **Consulta (query)**: Uma expressão concreta submetida a uma arquitetura de recuperação
  para satisfazer (parte de) uma necessidade de informação.
- **Formulação**: Uma variante textual/estrutural específica de uma consulta que expressa a
  **mesma** necessidade de informação (ex.: direta, parafraseada, prolixa). Formulações
  equivalentes compartilham a necessidade de informação de origem.
- **Documento**: A unidade documental do corpus — um acórdão, identificado por `doc_id`.
- **Chunk** (se houver): Um fragmento de um documento, caso a arquitetura vetorial venha a
  operar sobre fragmentos em vez do documento inteiro. A existência de chunks é **A DEFINIR**.
- **Evidência recuperada**: Um item retornado por uma arquitetura de recuperação para uma
  consulta (documento inteiro ou chunk), com sua posição (rank) e pontuação (score),
  destinado a subsidiar a geração da resposta.
- **Resposta final**: O texto produzido pelo gerador a partir das evidências recuperadas,
  para uma dada consulta/necessidade.
- **Arquitetura de recuperação**: O método pelo qual evidências são recuperadas —
  estruturada, vetorial ou híbrida. É a variável central do experimento.
- **doc_id / source_key**: Identificadores herdados da spec `construcao-corpus-piloto`;
  `doc_id` é a unidade documental do experimento.

Termos herdados (não redefinidos aqui): `Corpus_Canonico`, `Selecao_Experimental`,
`retrieval_text_fields`, `metadata_fields`, `preserved_fields`, `dataset_fingerprint`,
`selection_fingerprint`.

---

## Requirements

### Requirement 1: Universo documental e unidade experimental

**User Story:** Como pesquisador, quero fixar o universo documental e a unidade
experimental, para que as três arquiteturas sejam comparadas sobre a mesma base.

#### Acceptance Criteria

1. **[DECIDIDO]** O domínio do experimento SHALL ser acórdãos públicos do TCU.
2. **[DECIDIDO]** O recorte temporal SHALL ser 2024.
3. **[DECIDIDO]** O Corpus_Canonico de referência SHALL conter 21.661 documentos.
4. **[DECIDIDO]** A Selecao_Experimental SHALL conter 21.631 documentos.
5. **[DECIDIDO]** As três arquiteturas (estruturada, vetorial, híbrida) SHALL operar sobre
   exatamente o mesmo conjunto de 21.631 `doc_id` da Selecao_Experimental.
6. **[DECIDIDO]** A unidade documental SHALL ser o acórdão, identificado por `doc_id`.
7. **[DECIDIDO]** A unidade experimental de avaliação SHALL ser organizada em torno de uma
   **necessidade de informação**, que pode ter múltiplas formulações equivalentes.

---

### Requirement 2: Campos textuais e metadados

**User Story:** Como pesquisador, quero fixar quais campos compõem a representação textual
principal e quais metadados estão disponíveis, para que as arquiteturas usem o mesmo
material documental.

#### Acceptance Criteria

1. **[DECIDIDO]** Os campos textuais principais SHALL ser `ASSUNTO` e `ACORDAO`.
2. **[DECIDIDO]** Os metadados disponíveis SHALL ser `COLEGIADO`, `RELATOR`, `TIPOPROCESSO`,
   `DATASESSAO`, `ENTIDADE`, `UNIDADETECNICA`.
3. **[DECIDIDO]** `SUMARIO`, `RELATORIO` e `VOTO` SHALL permanecer preservados no corpus,
   porém **fora** da baseline textual principal deste experimento.
4. **[EM ESTUDO]** A forma de combinar `ASSUNTO` e `ACORDAO` na representação textual da
   arquitetura vetorial ainda não está definida; NÃO SHALL haver concatenação decidida
   nesta spec. Dependência: `análise do corpus`, `teste de viabilidade`, `literatura`.

---

### Requirement 3: Arquiteturas comparadas

**User Story:** Como pesquisador, quero definir as arquiteturas comparadas e o que as
distingue, para isolar a arquitetura de recuperação como variável central.

#### Acceptance Criteria

1. **[DECIDIDO]** O experimento SHALL comparar três arquiteturas de recuperação:
   estruturada, vetorial e híbrida.
2. **[DECIDIDO]** A arquitetura de recuperação SHALL ser a variável central (independente)
   do experimento.
3. **[DECIDIDO]** "Estruturada" NÃO SHALL significar BM25 ou busca lexical/esparsa; refere-se
   a recuperação baseada em campos estruturados/metadados.
4. **[DECIDIDO]** O experimento NÃO SHALL comparar LLMs entre si.
5. **[DECIDIDO]** A arquitetura híbrida NÃO SHALL ser um roteador que escolhe entre a
   arquitetura estruturada OU a vetorial; ela SHALL combinar componentes estruturados e
   vetoriais segundo uma regra fixa e reproduzível.
6. **[A DEFINIR]** A estratégia exata de combinação da híbrida (ex.: filtro estrutural →
   ranking vetorial, fusão de listas, ponderação de scores) ainda está aberta.
   Dependência: `literatura`, `teste de viabilidade`, `controle experimental`.
7. **[DECIDIDO]** Cada formulação incluída no núcleo comparativo do experimento SHALL ser
   submetida, **sem alteração de conteúdo**, às três arquiteturas (estruturada, vetorial,
   híbrida). A diferença entre as condições comparadas SHALL vir exclusivamente da
   arquitetura de recuperação, não da entrada.
8. **[DECIDIDO]** A diversidade experimental SHALL vir das diferentes necessidades de
   informação e das diferentes formulações, e NÃO de atribuir previamente perguntas
   exclusivas a uma arquitetura.

---

### Requirement 4: Pipeline experimental e geração

**User Story:** Como pesquisador, quero que o pipeline produza uma resposta final por
consulta com gerador idêntico entre arquiteturas, para que a diferença observada seja
atribuível à recuperação, não ao gerador.

#### Acceptance Criteria

1. **[DECIDIDO]** O pipeline SHALL gerar uma resposta final para cada consulta.
2. **[DECIDIDO]** As três arquiteturas SHALL usar o **mesmo** gerador, o **mesmo** prompt e
   os **mesmos** parâmetros de geração.
3. **[DECIDIDO]** A geração SHALL usar a mesma política de contexto, o mesmo limite de saída
   e a mesma aleatoriedade/seed entre arquiteturas, quando tecnicamente possível.
4. **[DECIDIDO]** A recuperação intermediária SHALL ser registrada para explicar a resposta
   final, de modo a permitir distinguir erro de recuperação de erro de geração.
5. **[A DEFINIR]** O modelo gerador específico ainda não está definido. Há preferência por
   execução local/reprodutível, mas NÃO SHALL ser fixado agora nenhum runtime (ex.: Ollama)
   nem modelo. Dependência: `teste de viabilidade`, `literatura`.

---

### Requirement 5: Necessidades de informação e formulações

**User Story:** Como pesquisador, quero organizar o experimento em torno de necessidades de
informação com formulações equivalentes, para avaliar robustez das arquiteturas à variação
de expressão.

#### Acceptance Criteria

1. **[DECIDIDO]** Cada necessidade de informação SHALL poder ter múltiplas formulações
   equivalentes, que compartilham a mesma necessidade de origem.
2. **[EM ESTUDO]** A natureza/tipologia das necessidades de informação — hipótese
   provisória: **estruturada/metadados**, **textual/semântica**, **mista** — ainda não está
   consolidada; nomes e categorias NÃO SHALL ser congelados sem fundamentação.
   Dependência: `literatura`, `análise do corpus`.
   Independentemente de uma necessidade ser predominantemente estruturada, textual ou mista,
   sua(s) formulação(ões) do núcleo comparativo SHALL ser executada(s) nas três arquiteturas
   (ver Requirement 3.7); a natureza da necessidade **não** restringe a quais arquiteturas
   ela é submetida.
3. **[EM ESTUDO]** A tipologia de formulações — hipótese provisória: **direta**,
   **parafraseada**, **prolixa** — ainda não está consolidada; NÃO SHALL ser congelada sem
   fundamentação e sem critérios objetivos de equivalência semântica.
   Dependência: `literatura`, `controle experimental`.
4. **[A DEFINIR]** Os critérios objetivos de equivalência semântica entre formulações ainda
   não estão definidos. Dependência: `literatura`, `controle experimental`.

---

### Requirement 6: Arquitetura estruturada (aspectos abertos)

**User Story:** Como pesquisador, quero registrar os pontos abertos da arquitetura
estruturada, para defini-los com fundamentação posterior.

#### Acceptance Criteria

1. **[A DEFINIR]** Como a linguagem natural de uma formulação vira filtros estruturados.
   Dependência: `literatura`, `teste de viabilidade`.
2. **[A DEFINIR]** Quais campos de metadados são usados na recuperação estruturada.
   Dependência: `análise do corpus`, `controle experimental`.
3. **[A DEFINIR]** O tratamento de consultas sem filtro estrutural explícito.
   Dependência: `teste de viabilidade`, `literatura`.
4. **[A DEFINIR]** A existência ou não de um interpretador automático de consulta.
   Dependência: `teste de viabilidade`, `literatura`.
5. **[A DEFINIR]** Como produzir e ordenar os resultados da recuperação estruturada.
   Dependência: `literatura`, `controle experimental`.

---

### Requirement 7: Arquitetura vetorial (aspectos abertos)

**User Story:** Como pesquisador, quero registrar os pontos abertos da arquitetura vetorial,
para defini-los com fundamentação e testes posteriores.

#### Acceptance Criteria

1. **[A DEFINIR]** A limpeza definitiva de HTML (a exploratória foi apenas diagnóstica).
   Dependência: `análise do corpus`, `teste de viabilidade`.
2. **[A DEFINIR]** A combinação de `ASSUNTO` + `ACORDAO` na representação textual.
   Dependência: `análise do corpus`, `teste de viabilidade`, `literatura`.
3. **[A DEFINIR]** O modelo de embedding. Dependência: `literatura`, `teste de viabilidade`.
4. **[A DEFINIR]** O tokenizer. Dependência: `literatura`, `teste de viabilidade`.
5. **[A DEFINIR]** Documento inteiro vs. chunks como unidade de indexação.
   Dependência: `análise do corpus`, `teste de viabilidade`, `literatura`.
6. **[A DEFINIR]** Existência de chunking e, se houver, tamanho e overlap.
   Dependência: `análise do corpus`, `teste de viabilidade`, `literatura`.
7. **[A DEFINIR]** A agregação de resultados de chunk para `doc_id`, se houver chunks.
   Dependência: `literatura`, `teste de viabilidade`.
8. **[A DEFINIR]** A medida de similaridade. Dependência: `literatura`, `teste de viabilidade`.
9. **[A DEFINIR]** O valor de Top-k. Dependência: `literatura`, `controle experimental`.

---

### Requirement 8: Registro da recuperação intermediária

**User Story:** Como pesquisador, quero prever o registro da recuperação intermediária, para
distinguir erro de recuperação de erro de geração.

#### Acceptance Criteria

1. **[DECIDIDO]** A recuperação intermediária SHALL ser registrada para cada consulta e
   arquitetura, de forma auditável.
2. **[EM ESTUDO]** O registro previsto PODERÁ conter campos como: `query_id`, `architecture`,
   `doc_id`, `chunk_id` (se aplicável), `rank`, `score`, evidência e contexto enviado ao
   gerador. O schema NÃO SHALL ser congelado nesta spec. Dependência: `controle experimental`,
   `teste de viabilidade`.
3. **[DECIDIDO]** O objetivo do registro SHALL ser permitir separar falhas de recuperação de
   falhas de geração na análise dos resultados.

---

### Requirement 9: Gold/reference

**User Story:** Como pesquisador, quero distinguir referência documental de referência de
resposta, para avaliar recuperação e geração separadamente.

#### Acceptance Criteria

1. **[DECIDIDO]** A avaliação SHALL distinguir **referência documental/evidência** (o que
   deveria ser recuperado) de **referência da resposta** (o que a resposta final deveria
   conter/afirmar).
2. **[A DEFINIR]** O método de construção do gold/reference.
   Dependência: `literatura`, `controle experimental`.
3. **[A DEFINIR]** Os critérios de relevância. Dependência: `literatura`, `controle experimental`.
4. **[A DEFINIR]** A granularidade da referência (documento, chunk, trecho).
   Dependência: `literatura`, `análise do corpus`.
5. **[A DEFINIR]** Julgamento binário vs. gradual. Dependência: `literatura`.
6. **[A DEFINIR]** Uso de pooling. Dependência: `literatura`, `teste de viabilidade`.
7. **[A DEFINIR]** Procedimento de revisão. Dependência: `controle experimental`.
8. **[A DEFINIR]** Formato de armazenamento do gold/reference.
   Dependência: `teste de viabilidade`.

---

### Requirement 10: Avaliação

**User Story:** Como pesquisador, quero registrar as métricas candidatas e o que ainda falta
definir, para escolher a avaliação com fundamentação.

#### Acceptance Criteria

1. **[EM ESTUDO]** Para recuperação, Precision@k, Recall@k e nDCG@k são apenas **candidatas**;
   as métricas finais e os valores de k ainda não estão definidos.
   Dependência: `literatura`, `controle experimental`.
2. **[A DEFINIR]** Para a resposta final, como medir correção factual, completude, suporte nas
   evidências e afirmações não sustentadas. Dependência: `literatura`, `controle experimental`.
3. **[A DEFINIR]** Se a avaliação será humana, automática ou por LLM-juiz — NÃO SHALL ser
   decidido agora. Dependência: `literatura`, `teste de viabilidade`, `controle experimental`.

---

### Requirement 11: Variáveis controladas

**User Story:** Como pesquisador, quero manter constantes as variáveis não centrais, para que
diferenças de resultado sejam atribuíveis à arquitetura de recuperação.

#### Acceptance Criteria

1. **[DECIDIDO]** A arquitetura de recuperação SHALL ser o **fator central** do experimento.
2. **[EM ESTUDO]** Além do fator central, o experimento pretende estudar variação em dois
   **fatores experimentais**: a **natureza da necessidade de informação** e a **formulação
   da consulta**. Ambas as classificações permanecem EM ESTUDO e NÃO SHALL ser congeladas.
   Dependência: `literatura`, `análise do corpus`, `controle experimental`.
3. **[DECIDIDO]** As **variáveis controladas** — mantidas constantes, quando aplicável —
   SHALL incluir: o gerador, o prompt, a política de contexto, o universo documental
   (21.631 `doc_id`) e o procedimento de avaliação, além das demais condições aplicáveis.
4. **[DECIDIDO]** Na **comparação pareada** entre arquiteturas para uma **mesma formulação**,
   a arquitetura de recuperação SHALL ser o único fator alterado, mantendo-se constantes as
   demais condições (mesma formulação/necessidade, mesmo gerador, prompt, política de
   contexto, universo documental e avaliação).

---

### Requirement 12: Diagnóstico já realizado (não é decisão)

**User Story:** Como pesquisador, quero registrar os números de diagnóstico exploratório já
obtidos, deixando claro que não constituem decisões.

#### Acceptance Criteria

1. **[OBSERVADO]** Os seguintes valores foram medidos em análise exploratória e SHALL ser
   tratados apenas como diagnóstico empírico, NÃO como decisões de desenho:
   - Selecao_Experimental: 21.631 documentos.
   - ACORDAO limpo temporariamente (somente em memória): mediana ~166 palavras.
   - P90 ~554 palavras; P95 ~740; P99 ~1.125 palavras.
   - 339 documentos com > 1.000 palavras; 64 com > 2.000; 49 com > 4.000; nenhum > 8.000.
   - A limpeza exploratória de HTML reduziu ~1/3 do tamanho médio, sem perda grave aparente.
2. **[OBSERVADO]** Esses valores NÃO SHALL ser interpretados como escolha de tamanho de
   chunk, overlap, embedding, unidade de indexação ou qualquer outro parâmetro; servem
   apenas para orientar decisões futuras.

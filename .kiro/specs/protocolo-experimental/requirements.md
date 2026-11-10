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

O **fator central** do experimento é a **arquitetura de recuperação**. Além dele, a
**natureza da necessidade de informação** e a **formulação da consulta** são **fatores
experimentais** que variam deliberadamente no conjunto do experimento — ou seja,
necessidades e formulações **não** permanecem constantes globalmente. A **tipologia da
natureza da necessidade** (metadados/textual/mista) e a **tipologia de formulações**
(direta/parafraseada/prolixa) estão **[DECIDIDO]** (ver Requirement 5). O controle
experimental é aplicado principalmente na **comparação pareada** entre arquiteturas para uma
**mesma formulação**: nesse caso, a necessidade/formulação e as demais variáveis controladas
(universo documental, gerador, prompt, política de contexto e procedimento de avaliação)
permanecem constantes, e a arquitetura de recuperação é a diferença deliberada, isolando seu
efeito.

### Convenção de status

Cada requisito é marcado com um status e, quando aberto, com a dependência que o resolverá:

- **[DECIDIDO]** — consolidado; não deve ser reaberto sem justificativa explícita.
- **[EM RATIFICAÇÃO]** — implementado e validado tecnicamente, aguardando ratificação
  metodológica formal do pesquisador para ser promovido a **[DECIDIDO]**.
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
- **Evidência recuperada**: Documento, chunk ou outra unidade aplicável retornada por uma
  arquitetura de recuperação para uma consulta, podendo possuir posição (rank) e pontuação
  (score) **quando aplicável** (a arquitetura estruturada pode não ter ranking/score
  natural), destinada a subsidiar a geração da resposta.
- **Resposta final**: O texto produzido pelo gerador a partir das evidências recuperadas,
  para uma dada consulta/necessidade.
- **Arquitetura de recuperação**: O método pelo qual evidências são recuperadas —
  estruturada, vetorial ou híbrida. É o **fator central** do experimento.
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
4. **[A DEFINIR]** A forma de combinar `ASSUNTO` e `ACORDAO` na representação vetorial ainda
   não tem estratégia provisória consolidada; NÃO SHALL ser escolhida nesta spec nenhuma
   alternativa (concatenação, prefixo, representação separada ou outra).
   Dependência: `análise do corpus`, `teste de viabilidade`, `literatura`.

---

### Requirement 3: Arquiteturas comparadas

**User Story:** Como pesquisador, quero definir as arquiteturas comparadas e o que as
distingue, para tratar a arquitetura de recuperação como fator central do experimento.

#### Acceptance Criteria

1. **[DECIDIDO]** O experimento SHALL comparar três arquiteturas de recuperação:
   estruturada, vetorial e híbrida.
2. **[DECIDIDO]** A arquitetura de recuperação SHALL ser o **fator central** do experimento.
3. **[DECIDIDO]** "Estruturada" NÃO SHALL significar BM25 ou busca lexical/esparsa; refere-se
   a recuperação baseada em campos estruturados/metadados.
4. **[DECIDIDO]** O experimento NÃO SHALL comparar LLMs entre si.
5. **[DECIDIDO]** A arquitetura híbrida NÃO SHALL ser um roteador que escolhe entre a
   arquitetura estruturada OU a vetorial; ela SHALL combinar componentes estruturados e
   vetoriais segundo uma regra fixa e reproduzível.
6. **[DECIDIDO]** A estratégia de combinação da híbrida SHALL ser **filtragem estruturada
   (conjunção AND das condições reconhecidas) seguida de ranking vetorial de TODOS os
   documentos candidatos elegíveis, sem pré-corte por Top-k vetorial global**, com
   similaridade de cosseno sobre os chunks dos candidatos, consolidação do score por
   documento via **max-pooling** e ordenação determinística por score decrescente com
   desempate por `doc_id` (ver `docs/experimento/decisao_estrategia_hibrida_e_integridade.md`).
   **Justificativa da escolha filtro→ranking:** simplicidade, determinismo,
   interpretabilidade, compatibilidade com o funcionamento da arquitetura estruturada
   (que produz um conjunto, não um ranking de relevância) e independência em relação ao
   gold standard. Técnicas como Reciprocal Rank Fusion (RRF) e fusão ponderada de scores
   **não** são diretamente aplicáveis à saída estruturada atual sem acrescentar um
   ranking ou score de relevância, razão pela qual não foram adotadas.
   **Ressalvas metodológicas** (a observar na avaliação): o recall no Caso C é limitado
   pela cobertura e correção dos filtros estruturados; condições reconhecidas de forma
   incorreta ou excessivamente restritiva podem excluir documentos relevantes antes do
   ranking; a consulta vetorial permanece integral (inclusive termos já usados na
   interpretação de metadados), o que pode reforçar certos termos no ranking sem
   representar duplicação matemática de scores; o max-pooling pode favorecer documentos
   com mais chunks e não premia evidência distribuída. Esta decisão ratifica apenas a
   regra de combinação; os parâmetros de avaliação (Top-k, métricas, gold, geração)
   permanecem em aberto.
7. **[DECIDIDO]** A **política de fallback** da híbrida SHALL observar três caminhos
   mutuamente exclusivos, aprovada explicitamente pelo pesquisador:
   - **Caso A** — nenhuma condição estruturada reconhecida: recuperação vetorial
     global (`path="vector_global_fallback"`,
     `fallback_reason="no_conditions_identified"`).
   - **Caso B** — condições reconhecidas, mas interseção dos filtros vazia:
     resultado **vazio** (`path="structured_no_candidates"`), **sem** fallback
     global e **sem** relaxar filtros; condições e diagnósticos preservados.
   - **Caso C** — condições reconhecidas e candidatos existentes: ranking vetorial
     dos candidatos (`path="structured_filter_then_vector_rank"`).
   No Caso A, a híbrida produz, para aquela consulta, o mesmo resultado da
   arquitetura vetorial; isso SHALL ser considerado na análise experimental.
8. **[DECIDIDO]** As execuções experimentais oficiais da híbrida SHALL usar
   `HybridRetriever.from_artifacts(..., verify_integrity=True)`, que valida a
   compatibilidade entre a seleção congelada e o índice (fingerprint recalculado
   vs. índice e, quando existir, vs. manifesto; correspondência exata dos
   conjuntos de `doc_id`; rejeição de índice parcial no carregamento). O
   parâmetro `verify_integrity=False` NÃO SHALL ser usado nessas execuções.
9. **[DECIDIDO]** Cada formulação incluída no núcleo comparativo do experimento SHALL ser
   submetida, **sem alteração de conteúdo**, às três arquiteturas (estruturada, vetorial,
   híbrida). Na **comparação pareada de uma mesma formulação**, a diferença deliberada entre
   as condições SHALL ser a arquitetura de recuperação, mantendo-se constantes a
   formulação/necessidade e as demais variáveis controladas. Isso NÃO significa que a
   arquitetura seja o único fator que varia no experimento completo: a natureza da
   necessidade e a formulação também são fatores experimentais que variam
   entre necessidades/formulações.
10. **[DECIDIDO]** A diversidade experimental SHALL vir das diferentes necessidades de
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
2. **[DECIDIDO]** A tipologia da **natureza das necessidades de informação** SHALL ser
   composta por três categorias operacionais: **baseada em metadados**, **textual** e
   **mista**, definidas como segue.
   - **Necessidade baseada em metadados:** pode ser satisfeita exclusivamente por operações
     sobre atributos documentais (metadados) — incluindo seleção, contagem, identificação e
     agregação — sem exigir interpretação do conteúdo textual.
   - **Necessidade textual:** exige informações presentes no conteúdo dos documentos, sem
     uma condição estruturada obrigatória para definir quais documentos são pertinentes.
   - **Necessidade mista:** estabelece pelo menos uma condição estruturada obrigatória para
     delimitar os documentos pertinentes e exige informações obtidas ou interpretadas no
     conteúdo textual.
3. **[DECIDIDO]** A classificação da natureza da necessidade SHALL observar as seguintes
   regras metodológicas:
   1. A classificação SHALL considerar tanto as informações solicitadas quanto as condições
      que determinam quais documentos são pertinentes.
   2. A classificação SHALL ocorrer antes da execução dos recuperadores e NÃO SHALL depender
      de seus resultados.
   3. Uma informação presente simultaneamente em metadados e no texto NÃO SHALL, por si só,
      caracterizar uma necessidade mista.
   4. Uma condição documental obrigatória PODE caracterizar uma necessidade mista mesmo
      quando a resposta final contém apenas informações textuais.
   5. A quantidade de documentos relevantes SHALL ser uma característica separada da natureza
      da necessidade (atributo ortogonal; não é uma categoria).
   6. A natureza da necessidade e a formulação da consulta SHALL ser tratadas como dimensões
      distintas.
   7. Todas as formulações SHALL ser submetidas às três arquiteturas, sem direcionamento por
      categoria (ver Requirement 3.9).
   8. Os casos NI-01, NI-02 e NI-03 SHALL permanecer exploratórios e NÃO SHALL constituir o
      gabarito definitivo.
   9. As três categorias SHALL ser tratadas como categorias operacionais desta pesquisa,
      fundamentadas em conceitos da literatura, e NÃO SHALL ser atribuídas como taxonomia
      original aos autores citados.
4. **[DECIDIDO]** Cada necessidade de informação do núcleo comparativo SHALL ter três
   **condições de formulação** operacionais:
   - **Direta:** expressão objetiva e concisa da necessidade, usada como formulação de
     referência.
   - **Parafraseada:** reformulação lexical ou sintática da necessidade, preservando seu
     significado e mantendo extensão aproximadamente semelhante à formulação direta.
   - **Prolixa:** formulação mais extensa da mesma necessidade, com explicações, redundâncias
     ou construções linguísticas adicionais, sem acrescentar novas condições, fatos
     solicitados ou informações que revelem a resposta.
5. **[DECIDIDO]** Formulações **ruidosas** (ex.: com erros de digitação) NÃO SHALL integrar o
   núcleo experimental neste momento.
6. **[DECIDIDO]** As três condições de formulação SHALL ser categorias operacionais desta
   pesquisa e NÃO SHALL ser atribuídas como classificações propostas originalmente por
   Bailey et al. (2016) ou Hagen, Scells e Potthast (2024).
7. **[DECIDIDO]** Cada necessidade de informação SHALL possuir uma **ficha de invariantes**
   própria, criada **antes** da execução dos recuperadores, contendo ao menos:
   - identificador único da necessidade;
   - descrição da necessidade de informação;
   - natureza (baseada em metadados, textual ou mista);
   - escopo documental e temporal;
   - condições documentais obrigatórias;
   - informações e fatos solicitados;
   - operações exigidas, quando aplicáveis (identificar, contar, comparar, agregar);
   - as três formulações (direta, parafraseada, prolixa);
   - estado e justificativa da validação de equivalência.
   A ficha documenta a necessidade e suas formulações e NÃO SHALL substituir o conjunto de
   referência (gold), que posteriormente registrará documentos relevantes, evidências e
   respostas esperadas (ver Requirement 9).
8. **[DECIDIDO]** As três formulações de uma mesma necessidade SHALL preservar: (1) a mesma
   necessidade de informação; (2) o mesmo escopo documental e temporal; (3) as mesmas
   condições obrigatórias; (4) os mesmos fatos solicitados; (5) as mesmas operações
   necessárias para responder.
9. **[DECIDIDO]** Uma formulação NÃO SHALL introduzir fatos adicionais que modifiquem a
   necessidade, antecipem a resposta ou revelem identificadores dos documentos-alvo que não
   faziam parte da necessidade original. Sinônimos e reformulações lexicais legítimas SHALL
   ser permitidos, ainda que possam alterar o desempenho da recuperação, pois essa variação
   faz parte do objeto da pesquisa.
10. **[DECIDIDO]** A equivalência entre formulações SHALL ser revisada e registrada **antes**
    da execução das arquiteturas. Uma segunda revisão independente é **desejável**, conforme
    a viabilidade do projeto.
11. **[DECIDIDO]** As fichas de invariantes SHALL ser armazenadas em **YAML**, **um arquivo
    por necessidade**, no diretório `evaluation/questions/needs/`, e validadas
    estruturalmente por um modelo Pydantic (`NeedSheet`). Gold e julgamentos de relevância
    SHALL residir separadamente em `evaluation/reference/`.
12. **[DECIDIDO]** O identificador das fichas definitivas SHALL seguir o padrão
    `^NI-[0-9]{3}$` (ex.: `NI-001`). Os casos piloto `NI-01`/`NI-02`/`NI-03` SHALL permanecer
    apenas em `docs/experimento/` e NÃO são fichas definitivas.
13. **[DECIDIDO]** A ficha SHALL vincular-se à Selecao_Experimental congelada por
    `scope.selection_fingerprint`, igual ao `selection_fingerprint` registrado no manifesto
    da seleção. A validação estrutural SHALL verificar apenas presença e formato (SHA-256 de
    64 hex); a conferência entre ficha, manifesto e corpus SHALL ser uma validação
    **separada**, sem recalcular o fingerprint a cada leitura individual de ficha.

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
   `doc_id`, `chunk_id` (se aplicável), `rank` (quando aplicável), `score` (quando
   aplicável), evidência e contexto enviado ao gerador. Nem toda arquitetura possui
   rank/score natural (ex.: a estruturada pode não ter). O schema NÃO SHALL ser congelado
   nesta spec. Dependência: `controle experimental`, `teste de viabilidade`.
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
2. **[DECIDIDO]** O gold/reference documental SHALL ser construído por **pooling** dos
   resultados das três arquiteturas, com **profundidade D=50** por formulação, acrescido
   do complemento derivado das condições obrigatórias **de metadados verificáveis** da
   ficha (T_cond=100); cada conjunto estruturado SHALL ser julgado integralmente até o
   **teto T=100** e, acima de T, por **amostragem estratificada por formulação** — o
   estrato de inclusão certa é a interseção do conjunto com a base determinística do pool
   (prob = 1) e o estrato restante é amostrado independentemente por formulação; um sorteio
   numa formulação NÃO torna o documento de inclusão certa em outra. O gerador de pools que
   executa esta política está **implementado** (`src/evaluation/pool_generator.py`,
   `pool_sampling.py`; `scripts/build_pools.py`), sem rótulos de relevância. O
   dimensionamento de `s_R` permanece **[A DEFINIR]** (ver item 9). Ver
   `docs/experimento/proposta_operacional_avaliacao_e_gold.md`.
3. **[DECIDIDO]** A **granularidade** da referência documental SHALL ser o `doc_id` (unidade
   de avaliação); evidências textuais são registradas como apoio, não como unidade de
   julgamento.
4. **[DECIDIDO]** O julgamento de relevância SHALL ser **binário** (relevante / não
   relevante); o estado `uncertain` SHALL existir **apenas durante a revisão** e ser
   resolvido antes do congelamento do gold.
5. **[DECIDIDO]** Documentos não julgados (fora do pool) SHALL permanecer com estado
   **desconhecido**; NÃO SHALL ser classificados automaticamente como não relevantes.
6. **[A DEFINIR]** Os critérios detalhados de relevância por necessidade (incluindo relevância
   parcial em necessidades multidocumentais). Dependência: `controle experimental`.
7. **[A DEFINIR]** Procedimento de revisão e adjudicação; disponibilidade e número de
   revisores. Dependência: `controle experimental`.
8. **[A DEFINIR]** Formato de armazenamento definitivo do gold/reference em
   `evaluation/reference/`. Dependência: `teste de viabilidade`.
9. **[A DEFINIR]** Regra de dimensionamento de `s_R` (tamanho da amostra do estrato restante
   da estruturada) a partir de uma precisão-alvo. Dependência: `controle experimental`.
10. **[A DEFINIR]** Tratamento de necessidades sem documentos relevantes, caso admitidas.
    Dependência: `controle experimental`.
11. **[DECIDIDO — ADAPTAÇÃO OPERACIONAL]** A pesquisadora (Vitoria Novaes da Costa) aprovou,
    por inviabilidade de realizar centenas de julgamentos humanos, um **recorte reduzido de
    julgamento** (estudo de casos exploratório, "Alternativa B"): o conjunto submetido ao
    julgamento humano SHALL ser a **união dos top-5 de vetorial e híbrida** (3 formulações,
    3 necessidades, deduplicado por `(need_id, doc_id)`), acrescido do **universo restrito de
    21 acórdãos da NI-003** (ENTIDADE = ANTT ∧ TIPOPROCESSO = Representação) e dos documentos
    de referência confirmados de NI-001/NI-002 ainda ausentes; teto previsto de **67
    julgamentos distintos**. Este recorte SHALL afetar apenas o desenho de julgamento e o
    alcance das conclusões, NÃO o corpus, a seleção congelada, o índice nem os recuperadores.
    A profundidade de recuperação SHALL permanecer **D=50** (distinta do corte de julgamento).
    O plano amostral `s_R` (item 9) permanece documentado como referência e NÃO SHALL ser
    apresentado como aplicado ao conjunto reduzido. Detalhes e limitações em
    `docs/experimento/proposta_operacional_avaliacao_e_gold.md` §12.

---

### Requirement 10: Avaliação

**User Story:** Como pesquisador, quero registrar as métricas candidatas e o que ainda falta
definir, para escolher a avaliação com fundamentação.

#### Acceptance Criteria

1. **[DECIDIDO]** A avaliação da recuperação SHALL ser **multidimensional**, preservando a
   natureza de cada arquitetura: métricas de conjunto/cobertura para as três (com o tamanho
   do resultado reportado como esforço de inspeção) e métricas de ranking apenas para a
   vetorial e a híbrida. A arquitetura estruturada SHALL ser avaliada como **conjunto**, sem
   ranking artificial (não se usa a ordem por `doc_id` como relevância).
2. **[DECIDIDO]** Os **cortes de ranking** SHALL ser k ∈ {5, 10, 50}, aplicáveis **somente** à
   vetorial e à híbrida; a profundidade de pooling SHALL ser **D=50**. O `display_limit` dos
   recuperadores SHALL ser configurado como ≥ ao maior k avaliado, para não truncar o ranking
   antes do cálculo das métricas.
3. **[DECIDIDO]** O **orçamento de recuperação** (quantos documentos entram nas métricas) SHALL
   ser tratado separadamente do **orçamento de contexto do gerador** (quantos documentos/trechos
   são enviados ao gerador); os dois NÃO precisam coincidir.
4. **[EM ESTUDO]** O conjunto específico de métricas (ex.: Precision@k, Recall-sob-pool@k,
   nDCG@k, MRR) ainda não está totalmente fixado. Dependência: `literatura`, `controle
   experimental`. **Exceção [DECIDIDO]:** para o recorte reduzido (Req 9, item 11), a
   pesquisadora ratificou a convenção de **Precision@5 com denominador fixo = 5**, registrando
   `n_retornado` à parte e definindo `Precision@5 = 0` quando não houver resultados; aplicável
   **apenas** a vetorial e híbrida, **não** ao conjunto estruturado. Ver
   `docs/experimento/proposta_operacional_avaliacao_e_gold.md` §12.3.
5. **[A DEFINIR]** Para a resposta final, como medir correção factual, completude, suporte nas
   evidências e afirmações não sustentadas. Dependência: `literatura`, `controle experimental`.
6. **[A DEFINIR]** Se a avaliação da geração será humana, automática ou por LLM-juiz — NÃO SHALL
   ser decidido agora. Dependência: `literatura`, `teste de viabilidade`, `controle experimental`.
7. **[DECIDIDO — ADAPTAÇÃO OPERACIONAL]** Sob o recorte reduzido (Requirement 9, item 11): a
   **Precision@5** de vetorial e híbrida SHALL poder ser calculada quando os documentos do
   corte top-5 estiverem julgados; a **precisão integral de conjuntos estruturados grandes**
   NÃO SHALL ser estimada como se todos os documentos tivessem sido julgados; a inspeção
   completa dos 21 da NI-003 SHALL permitir avaliar a relevância **dentro desse universo
   restrito**, sem confundi-lo com o corpus; documentos não julgados SHALL permanecer
   desconhecidos; NÃO SHALL ser reivindicado **recall absoluto do corpus**, nem apresentadas
   **confiança de 95% / margem de ±10 p.p.** como resultado da avaliação reduzida (o plano
   `s_R` não é aplicado a este conjunto). A comparação SHALL ser **exploratória**, restrita às
   três necessidades, sem pretensão de superioridade estatística geral. Ver
   `docs/experimento/proposta_operacional_avaliacao_e_gold.md` §12.3.

---

### Requirement 11: Variáveis controladas

**User Story:** Como pesquisador, quero manter constantes as variáveis controladas na
comparação pareada entre arquiteturas para uma mesma formulação, para que, nesse pareamento,
diferenças de resultado sejam atribuíveis à arquitetura de recuperação — sem exigir que
necessidades e formulações permaneçam constantes no conjunto do experimento, já que são
fatores experimentais que variam entre casos.

#### Acceptance Criteria

1. **[DECIDIDO]** A arquitetura de recuperação SHALL ser o **fator central** do experimento.
2. **[DECIDIDO]** Além do fator central, o experimento estuda variação em dois **fatores
   experimentais**: a **natureza da necessidade de informação** e a **formulação da
   consulta**, que variam deliberadamente entre casos. As **tipologias** da natureza da
   necessidade (metadados/textual/mista) e das formulações (direta/parafraseada/prolixa)
   estão **[DECIDIDO]** (ver Requirement 5); os **valores** de necessidade e formulação
   variam entre casos e não são constantes globalmente.
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

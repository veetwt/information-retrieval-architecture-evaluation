# Decisão: chunking por tokens e indexação vetorial retomável

Status: adotada
Escopo: arquitetura de recuperação vetorial (preparação textual e índice)
Artefatos afetados: `src/retrieval/text_prep.py`, `src/retrieval/vector_index.py`,
`src/retrieval/vector.py`, `scripts/build_vector_index.py`,
`tests/test_vector_retrieval.py`
Versão do índice vetorial: `0.2.0`

## Contexto

A arquitetura vetorial representa `ASSUNTO` + `ACORDAO` por meio de embeddings
do modelo `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
(CPU, local, gratuito). Esse modelo possui janela máxima de **128 tokens**.

O corpus experimental congelado possui 21.631 acórdãos; a maioria dos
documentos é longa (mediana ~199 palavras, P99 > 1000 palavras), de forma que
um único vetor por documento causaria truncamento da maior parte do conteúdo.

Dois problemas foram tratados:

1. Dimensionamento das passagens (chunks) em relação ao limite do modelo.
2. Construção do índice completo em ambiente com memória limitada (~8 GB),
   onde uma execução única e não interrompível já havia travado a máquina.

## Problema 1 — palavras não são tokens

A primeira versão dividia o texto por janelas de ~100 **palavras**. A
verificação com o tokenizer real do modelo mostrou que, para este corpus
jurídico em português, 100 palavras correspondem a **~227 tokens em média**
(subpalavras, pontuação, números de processo, siglas). Numa amostra de 592
documentos, **94,8% dos chunks ultrapassavam 128 tokens**, o que provocaria
**truncamento silencioso** da maioria das passagens no momento da codificação.

### Alternativas consideradas

- Reduzir o número de palavras por chunk (ex.: ~35 palavras) para respeitar o
  pior caso de tokens/palavra. Rejeitada: estimativa frágil, dependente do
  idioma e do texto, e ainda sujeita a truncamento em casos extremos.
- Aceitar o truncamento. Rejeitada: viola a preservação da informação e a
  comparabilidade entre documentos.

### Decisão

Dividir o texto por **tokens do tokenizer real**, não por palavras:

- janela de 128 tokens, sobreposição de 16 tokens;
- reserva de 2 tokens para os tokens especiais do modelo (`[CLS]`/`[SEP]`);
- margem de segurança adicional de 4 tokens, porque o texto de cada chunk é
  decodificado dos ids e **re-tokenizado** pelo modelo na codificação, e essa
  ida-e-volta (decode → re-encode) pode deslocar a contagem em ±1 token;
- salvaguarda final determinística: cada passagem decodificada é re-tokenizada
  e, se ainda exceder 128 tokens, tem os ids finais descartados até caber.

### Justificativa

Garante, por construção e por verificação, que **nenhum chunk é truncado
silenciosamente**. A medição por tokens é a unidade correta para o limite do
modelo; a margem e a salvaguarda cobrem a variação do round-trip.

### Verificação

- Amostra (592 docs), chunking por tokens: tokens/chunk efetivo médio 120,6,
  máximo 128, **0 chunks acima de 128**; projeção ~158 mil chunks para o corpus.
- Índice de teste com o modelo real (300 docs, 2.387 chunks): após a
  salvaguarda de round-trip, **0 chunks acima de 128 tokens**, máximo efetivo
  125; embeddings L2-normalizados (norma 1,0).

### Impacto

- Mais chunks que a abordagem por palavras (~1,8×), em troca de preservação
  integral do conteúdo. A avaliação permanece **por documento** (consolidação
  por max-pooling sobre os chunks), sem duplicação de documentos no resultado.
- O índice passa a registrar `chunking="by_tokens"`, `max_tokens`,
  `overlap_tokens` nos metadados.

## Problema 2 — indexação retomável

A construção anterior gerava os embeddings numa única passagem e só gravava os
artefatos no fim. Em caso de interrupção (ou falta de memória), nada era
reaproveitável e a execução recomeçava do zero.

### Alternativas consideradas

- Manter execução única com memória pré-alocada. Rejeitada: não é retomável e
  já havia esgotado a memória do ambiente.
- Reduzir o corpus. Rejeitada por decisão metodológica: o objetivo é o índice
  **completo** dos 21.631 acórdãos.

### Decisão

Construção incremental, idempotente e verificável, em `embeddings/<batch_id>/`:

1. O plano de chunks (ordem canônica, vínculo `chunk → doc_id`) é gerado de
   forma determinística e **persistido em `chunks.parquet` antes** de qualquer
   embedding.
2. Os embeddings são gerados em **blocos independentes (shards)**
   `shards/emb_NNNNN.npy`, cada um cobrindo um intervalo contíguo de chunks.
3. Cada shard é gravado de forma **atômica** (arquivo temporário + rename) e
   validado por shape antes de ser considerado concluído.
4. Um `build_state.json` registra o fingerprint da construção (versão do
   índice, modelo, `max_tokens`, `overlap_tokens`, fingerprint da seleção,
   `n_docs_indexed`, `n_chunks`, dimensão, `shard_size`) e a lista de shards
   concluídos.
5. Uma reexecução **pula** shards já concluídos e compatíveis, e **refaz**
   shards ausentes ou incompletos.
6. A retomada é **rejeitada** se o estado salvo for incompatível com os
   parâmetros atuais (ex.: outra seleção, outro modelo), exigindo
   reconstrução explícita (`--overwrite`) em diretório limpo.
7. Os artefatos finais `embeddings.npy` e `index_meta.json` só são escritos
   **após todos os shards estarem presentes e válidos** (consolidação atômica).

### Justificativa

Preserva reprodutibilidade e rastreabilidade (fingerprint, versões de
dependências, contagens, timestamps) e permite concluir o índice completo em
ambiente de memória limitada, com lotes pequenos (`--batch-size 8`) e retomada
após interrupção, sem recomputar o que já foi feito.

### Verificação

- Teste real (300 docs) interrompido após 4 de 12 shards: a reexecução
  reaproveitou os shards concluídos e finalizou o índice, consolidando
  `embeddings.npy` + `index_meta.json` corretamente.
- Testes automatizados (31 no módulo vetorial; 270 na suíte completa) cobrem:
  criação de shards/estado, retomada que pula shards concluídos, refazimento de
  shard incompleto, rejeição de estado incompatível, equivalência entre o
  consolidado e a concatenação dos shards, e reconstrução limpa com
  `--overwrite`.

### Impacto

- `src/retrieval/vector_index.py` passa a expor `shard_size`, `build_state.json`
  e os diretórios de shards; `load_index` e a interface do `VectorRetriever`
  permanecem compatíveis.
- O script `scripts/build_vector_index.py` ganha `--shard-size` e adota
  `--batch-size 8` como padrão seguro para 8 GB de RAM.
- Nenhuma alteração nas arquiteturas estruturada, nas fichas de necessidade,
  nos gabaritos, na seleção congelada ou nos manifestos.

## Observações de execução

- Os artefatos do índice ficam fora do versionamento Git (`.gitignore` já
  exclui `embeddings/`, `models/`, `*.npy`).
- O aviso do tokenizer sobre sequências maiores que 128 tokens, emitido ao
  tokenizar o documento inteiro durante o planejamento, é esperado e não indica
  truncamento (o texto é fatiado em janelas ≤ 128 em seguida); o nível de log do
  tokenizer é ajustado para não induzir leitura equivocada.

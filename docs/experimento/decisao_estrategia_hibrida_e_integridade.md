# Decisão: estratégia da arquitetura híbrida, política de fallback e integridade

Status: política de fallback **aprovada**; estratégia geral filtro→ranking
**implementada e validada tecnicamente, pendente de ratificação metodológica**.
Escopo: arquitetura de recuperação híbrida (composição estruturada + vetorial).
Artefatos afetados: `src/retrieval/hybrid.py`, `src/retrieval/vector_index.py`
(apenas `load_index`), `tests/test_hybrid_retrieval.py`.
Versão da arquitetura híbrida: `0.2.0`.

Esta nota documenta o comportamento **real** do código validado. Ela não altera
código, corpus, seleção, índice, manifestos, fichas, gold, Top-k, métricas nem
modelo gerador. Complementa a spec `protocolo-experimental`; ver também
`docs/experimento/decisao_chunking_e_indexacao_vetorial.md`.

## Contexto

O experimento compara três arquiteturas de recuperação sobre a
Selecao_Experimental congelada (21.631 acórdãos; `selection_fingerprint`
`ec125709322854d164e8f4aeaffb0351ef92e0adfede4d92b17b955b5ea1bc5c`). Já estava
**[DECIDIDO]** no protocolo que a híbrida **não** é um roteador e que **combina**
componentes estruturado e vetorial por uma regra fixa e reproduzível
(Requirement 3.5). A **estratégia exata** permanecia **[A DEFINIR]**
(Requirement 3.6).

A `HybridRetriever` v0.2.0 implementa, por composição e sem alterar as
arquiteturas estruturada (`StructuredRetriever` v0.3.0) e vetorial
(`VectorRetriever` v0.2.0), a regra descrita abaixo. A integração foi validada
sobre os artefatos reais (21.631 docs, 124.282 chunks) e por 23 testes da
híbrida (293 na suíte completa) na revisão técnica anterior.

## Estratégia de combinação implementada

Regra operacional: **filtragem estruturada seguida de ranking vetorial sobre
todos os candidatos**, com consolidação do score por documento via max-pooling.

Entrada: apenas o TEXTO da consulta (cumpre a interface comum `Retriever`); sem
LLM, sem roteamento por natureza da necessidade, sem uso de fichas ou gold.

### Três caminhos de recuperação (política de fallback — APROVADA)

| Caso | Condição | `path` | Resultado |
|---|---|---|---|
| A | nenhuma condição estruturada reconhecida | `vector_global_fallback` (`fallback_reason="no_conditions_identified"`) | recuperação vetorial global |
| B | condições reconhecidas, interseção dos filtros vazia | `structured_no_candidates` (`structured_intersection_empty=True`, `n_ranked_candidates=0`) | conjunto VAZIO; sem fallback global; sem relaxar filtros |
| C | condições reconhecidas e candidatos existentes | `structured_filter_then_vector_rank` | candidatos ordenados por similaridade |

Detalhe do Caso C:
- a estruturada interpreta a conjunção (AND) das condições de metadados
  reconhecidas no texto e devolve o conjunto de `doc_id` candidatos (ordem por
  `doc_id`, que **não** representa relevância);
- a consulta é codificada pelo mesmo modelo de embedding do índice;
- a similaridade de cosseno (vetores L2-normalizados → produto interno) é
  calculada sobre **todos os chunks** dos documentos candidatos (não apenas a
  interseção com um Top-k vetorial global prévio);
- o score de cada documento é o maior score entre seus chunks (**max-pooling**);
- ordenação por score decrescente, com desempate estável por `doc_id`;
- o limite provisório de exibição (`display_limit=10`) é aplicado **após** o
  ranking. Esse limite NÃO é o Top-k experimental, que permanece **[A DEFINIR]**.

### Justificativa e limitações da política de fallback

- O Caso B foi **aprovado** para evitar que a híbrida retorne documentos que
  contradizem as condições reconhecidas quando nenhum documento as satisfaz. Um
  diagnóstico real ("denúncia julgada na Segunda Câmara") reconhecia as duas
  condições, mas a interseção é vazia no corpus; antes da aprovação, o
  comportamento retornava 10 documentos incompatíveis. Agora retorna vazio.
- O Caso A mantém a cobertura para consultas puramente textuais.
  **Consequência metodológica a considerar na análise:** no Caso A a híbrida
  produz exatamente o resultado da arquitetura vetorial para aquela consulta
  (mesmos `doc_id`, ranking e scores). Na comparação pareada, essas consultas
  não distinguem híbrida de vetorial e devem ser analisadas como tal.

## Garantias de integridade implementadas (reprodutibilidade)

Validações efetivamente presentes no código, sem exagerar sua cobertura:

### No carregamento do índice (`load_index`, componente compartilhado)
- rejeita o índice quando `index_meta.json`, `embeddings.npy` ou
  `chunks.parquet` estão ausentes (erro claro);
- rejeita **índice parcial** (`is_partial_index` verdadeiro) por padrão, salvo
  `allow_partial=True` (uso técnico, não experimental);
- verifica consistência de contagem `len(embeddings) == len(chunks) ==
  meta["n_chunks"]`;
- verifica dimensão `embeddings.dim == meta["embedding_dim"]`;
- exige as colunas `doc_id`, `chunk_index`, `text` no `chunks.parquet`.

Essas validações passam sem alteração de comportamento para um índice completo e
íntegro (como o de produção); apenas índices corrompidos/parciais são
rejeitados.

### Na construção da híbrida (`HybridRetriever.from_artifacts`, `verify_integrity=True` por padrão)
- **recalcula** o fingerprint da seleção a partir do DataFrame com a função
  canônica do projeto (`utils.hashing.compute_dataset_fingerprint`, sort por
  `doc_id`) — origem confiável, não um valor fornecido pelo chamador;
- compara o fingerprint recalculado ao `selection_fingerprint` registrado no
  índice; se o índice não registra fingerprint, a construção é recusada;
- compara o fingerprint recalculado ao do manifesto **quando o manifesto
  existe**; a verificação do manifesto é **condicional à sua existência** (não é
  uma verificação tripla obrigatória: na ausência do manifesto, a garantia se
  apoia na comparação com o índice);
- verifica a correspondência **exata** dos conjuntos de `doc_id` entre seleção e
  índice (sem documentos ausentes nem adicionais; rejeita duplicatas na
  seleção);
- no ranking do Caso C, um candidato estruturado sem embedding no índice gera
  **erro explícito** (`HybridIntegrityError`), em vez de descarte silencioso;
- as verificações rodam **uma vez na inicialização**, não por consulta.

### Condições de uso para execuções experimentais oficiais
- As execuções oficiais **devem** instanciar via
  `HybridRetriever.from_artifacts(..., verify_integrity=True)` (padrão).
- O parâmetro `verify_integrity=False` existe como escotilha de teste/uso
  técnico e **não deve** ser utilizado em execuções experimentais oficiais.
- O **construtor direto** `HybridRetriever(structured, vector)` **não** executa
  as verificações de compatibilidade de `from_artifacts`; não oferece as mesmas
  garantias e não deve ser usado para execuções oficiais.

## Limitações metodologicamente relevantes

1. Condições estruturadas **não reconhecidas** levam ao fallback vetorial global
   (Caso A).
2. Condições estruturadas **reconhecidas incorretamente** podem excluir
   documentos relevantes antes do ranking vetorial (Caso C/B).
3. A qualidade da filtragem depende da cobertura dos metadados do corpus e da
   interpretação da consulta pela estruturada.
4. O score vetorial é **similaridade semântica**, não relevância comprovada.
5. O max-pooling usa o chunk mais similar como representação do score do
   documento.
6. Híbrida e vetorial podem produzir resultados idênticos em consultas sem
   filtros reconhecidos (Caso A).
7. A comparação com a estruturada exige cuidado: a estruturada **não** possui
   ranking natural de relevância (score `None`, ordem por `doc_id`).

## Pendências de robustez (registro; não corrigidas nesta etapa)

- Ausência de teste que exercite **isoladamente** a comparação de conjuntos de
  `doc_id`: nos testes atuais de documento ausente/adicional, o fingerprint já
  diverge e o erro é levantado antes da checagem de `doc_id`.
- Ausência de testes para dimensão de embeddings incompatível e para arquivos
  obrigatórios ausentes além do `index_meta.json`.
- A verificação de `doc_id` nulo compara a representação textual contra `"nan"`
  e strings vazias; não trata explicitamente `None` antes da conversão para
  string (`str(None)` produz `"None"`), de modo que a proteção atual é menos
  abrangente do que o nome sugere. Registrado para endurecimento futuro.

Nenhuma dessas pendências é bloqueante para a validação técnica já concluída.

## Status

- Política de fallback (Casos A/B/C): **[DECIDIDO]** (aprovada explicitamente
  pelo pesquisador).
- Estratégia geral filtro→ranking com max-pooling: **implementada e validada
  tecnicamente; pendente de ratificação metodológica formal** ao revisar a spec.
- Garantias de integridade/reprodutibilidade: **[DECIDIDO]** como requisito de
  execução (uso de `verify_integrity=True`).
- Top-k experimental, métricas, gold standard e modelo gerador permanecem
  **[A DEFINIR]** (fora do escopo desta nota).

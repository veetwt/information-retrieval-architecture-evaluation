# Plano de Implementação: Construção do Corpus Piloto

## Visão Geral

Implementação incremental do pipeline Python de construção do corpus piloto de Acórdãos do TCU.
O pipeline é composto pelos módulos `hashing`, `CorpusConfig`, `ManifestWriter`, `Ingestor`,
`Auditor` e `Canonizador`, coordenados por CLIs e cobertos por testes automatizados com pytest e Hypothesis.

A implementação segue a ordem de dependências: utilitários → configuração → manifest → ingestor
→ auditor → canonizador → CLIs → testes → exemplo de configuração.

---

## Tarefas

- [ ] 1. Implementar utilitários de hashing
  - [ ] 1.1 Implementar `compute_sha256` em `src/utils/hashing.py`
    - Criar o arquivo `src/utils/hashing.py`
    - Implementar `compute_sha256(path: Path) -> str`: leitura em chunks de 8 MB, retorno de string hexadecimal de 64 caracteres
    - Lançar `IOError` se o arquivo não puder ser lido
    - Atualizar `src/utils/__init__.py` para exportar `compute_sha256`
    - _Requirements: 1.2, 2.3, 8.5_

  - [ ] 1.2 Implementar `compute_dataset_fingerprint` em `src/utils/hashing.py`
    - Implementar `compute_dataset_fingerprint(df: pd.DataFrame, sort_col: str = "doc_id") -> str`
    - Seguir o algoritmo completo do design: schema (lista ordenada de colunas+dtype) + conteúdo ordenado com serialização canônica por tipo (null, str, int, float, bool, date/datetime)
    - Retornar string hexadecimal de 64 caracteres; independente de compressão Parquet, row groups e timestamps internos
    - Atualizar `src/utils/__init__.py` para exportar `compute_dataset_fingerprint`
    - _Requirements: 9.4, 9.5_

  - [ ]* 1.3 Escrever testes unitários para `compute_sha256`
    - **Feature: construcao-corpus-piloto, Property 1: Integridade da cópia (SHA-256 preservado na promoção)**
    - `test_sha256_equivalente_hashlib`: verificar que `compute_sha256(path) == hashlib.sha256(path.read_bytes()).hexdigest()` para arquivo de conteúdo arbitrário
    - `test_sha256_arquivo_inexistente_levanta_ioerror`: verificar que IOError é levantado para caminho inválido
    - _Requirements: 8.5_

  - [ ]* 1.4 Escrever testes de propriedade para `compute_dataset_fingerprint`
    - **Feature: construcao-corpus-piloto, Property 5: Determinismo do `dataset_fingerprint` incluindo schema**
    - `test_property_dataset_fingerprint_determinístico`: para qualquer DataFrame gerado pelo Hypothesis, duas chamadas a `compute_dataset_fingerprint` retornam o mesmo valor (`settings(max_examples=100)`)
    - `test_fingerprint_muda_quando_schema_muda`: mesmo conteúdo textual, schema lógico diferente (coluna a mais) → fingerprint diferente
    - _Requirements: 9.4, 9.5_

- [ ] 2. Implementar `CorpusConfig` (Pydantic v2)
  - [ ] 2.1 Criar modelo Pydantic `CorpusConfig` em `src/data/config.py`
    - Criar `src/data/config.py`
    - Definir todos os campos obrigatórios: `source_identifier`, `batch_id`, `schema_version`, `config_version`, `allowed_fields`, `dataset`, `dataset_year`
    - Definir todos os campos opcionais com defaults: `source_url`, `primary_key_field`, `text_field`, `metadata_fields`, `required_fields`, caminhos de diretórios
    - Implementar `model_validator` para validações cross-field: `metadata_fields ⊆ allowed_fields`, `required_fields ⊆ allowed_fields`, `primary_key_field ∈ allowed_fields`, `text_field ∈ allowed_fields`
    - Atualizar `src/data/__init__.py` para exportar `CorpusConfig`
    - _Requirements: 7.1, 7.5, 9.1, 9.2_

  - [ ] 2.2 Implementar métodos de carregamento `from_yaml`, `from_toml` e `load` em `CorpusConfig`
    - `from_yaml(path: Path)`: carregar com `pyyaml`, validar com Pydantic
    - `from_toml(path: Path)`: carregar com `tomllib` (stdlib ≥ 3.11), validar com Pydantic
    - `load(path: Path)`: detectar formato pelo sufixo `.yaml`/`.yml` ou `.toml` e delegar
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ]* 2.3 Escrever testes unitários para `CorpusConfig`
    - `test_config_valida_campos_obrigatorios`: Config_File com todos os campos obrigatórios → carregado sem erro
    - `test_config_rejeita_campo_ausente`: omitir `batch_id` → `ValidationError` com nome do campo ausente
    - `test_config_rejeita_metadata_fields_fora_de_allowed_fields`: `metadata_fields` com campo não declarado em `allowed_fields` → `ValidationError`
    - `test_config_load_yaml_e_toml`: verificar que `load()` delega corretamente pelo sufixo
    - _Requirements: 9.2, 9.3_

- [ ] 3. Implementar `ManifestWriter` — leitura e escrita básica
  - [ ] 3.1 Criar estrutura básica do `ManifestWriter` em `src/data/manifest.py`
    - Criar `src/data/manifest.py`
    - Definir constante `REQUIRED_FIELDS` com os 12 campos obrigatórios do Manifest
    - Implementar `__init__(self, manifest_path: Path)`: inicializar sem criar arquivo
    - Implementar `load_entries() -> list[dict]`: ler JSON Lines; retornar lista vazia se arquivo não existir
    - Implementar `append_entry(entry: dict) -> None`: validar campos obrigatórios, escrever linha JSON em modo append; lançar `ValueError` se campo obrigatório ausente
    - Implementar `sha256_exists(sha256: str) -> tuple[bool, dict | None]`
    - Implementar `original_filename_exists(original_filename: str) -> tuple[bool, dict | None]`
    - Atualizar `src/data/__init__.py` para exportar `ManifestWriter`
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ] 3.2 Implementar validação de proveniência e pending.jsonl no `ManifestWriter`
    - Implementar `validate_file_provenance(stored_filename: str, raw_dir: Path) -> tuple[bool, str]`: verificar entrada no Manifest + SHA-256 atual do arquivo; retornar motivos `"provenance_missing"`, `"integrity_mismatch"`, `"file_not_found"`; lançar `IOError` se hash não puder ser calculado
    - Definir constante `PENDING_FILENAME = "pending.jsonl"`
    - Implementar `append_pending_entry(entry: dict) -> None`: gravar em `pending.jsonl` (modo append); lançar `IOError` se `pending.jsonl` também falhar
    - Implementar `has_pending_entries() -> bool`: retornar `True` se `pending.jsonl` existir e contiver ao menos uma linha
    - _Requirements: 2.5, 1.7_

  - [ ]* 3.3 Escrever testes unitários para `ManifestWriter`
    - `test_manifest_campos_obrigatorios`: entrada criada contém todos os campos de `REQUIRED_FIELDS`
    - `test_manifest_rejeita_campo_ausente`: `append_entry` sem campo obrigatório → `ValueError` indicando o campo
    - `test_sha256_exists_retorna_true_para_hash_existente`: verificar detecção de duplicidade por conteúdo
    - `test_validate_provenance_integrity_mismatch`: SHA-256 atual do arquivo diverge do registrado → retornar `(False, "integrity_mismatch")`
    - `test_validate_provenance_missing`: arquivo sem entrada no Manifest → retornar `(False, "provenance_missing")`
    - `test_has_pending_entries_true_com_arquivo`: `pending.jsonl` com uma linha → retornar `True`
    - `test_has_pending_entries_false_sem_arquivo`: `pending.jsonl` inexistente → retornar `False`
    - _Requirements: 2.1, 2.4, 2.5_

- [ ] 4. Checkpoint — utilitários e fundações
  - Garantir que todos os testes implementados até aqui passem. Verificar com `pytest tests/ -v`. Em caso de dúvida, consultar o pesquisador.

- [ ] 5. Implementar `Ingestor` — hashing e staging
  - [ ] 5.1 Criar estrutura base do `Ingestor` e fluxo de hashing/staging em `src/data/ingestor.py`
    - Criar `src/data/ingestor.py`
    - Definir `IngestorResult` (dataclass) com campos `status`, `stored_filename`, `sha256`, `message`
    - Definir os 9 literais de status: `"ingested"`, `"duplicate_content"`, `"name_conflict_versioned"`, `"integrity_error"`, `"validation_error"`, `"file_exists_consistent"`, `"inconsistency_orphan_file"`, `"manifest_pending"`, `"blocked_pending_manifest"`
    - Implementar `__init__(self, config: CorpusConfig, manifest: ManifestWriter)`
    - Implementar `_copy_to_staging(source: Path, staging_name: str) -> Path`: copiar para `data/interim/`; retornar Path do arquivo em staging
    - Implementar `_cleanup_staging(staging_path: Path) -> None`: remover arquivo de staging sem lançar exceção se não existir
    - Atualizar `src/data/__init__.py` para exportar `Ingestor` e `IngestorResult`
    - _Requirements: 1.1, 1.2, 1.5_

  - [ ] 5.2 Implementar `_resolve_stored_filename` com desambiguação progressiva
    - Implementar `_resolve_stored_filename(original_filename: str, sha256: str) -> str`
    - Sem `Conflito_Por_Nome`: retornar `original_filename`
    - Com `Conflito_Por_Nome`: gerar candidato `{stem}_{sha256[:8]}{suffix}`, verificar conflito no Manifest E fisicamente em `data/raw/`, ampliar progressivamente sha256[:10], sha256[:12], …, sha256[:64]; lançar `ValueError` se nenhuma extensão eliminar a colisão
    - _Requirements: 1.4_

  - [ ] 5.3 Implementar `_promote_to_raw` com verificação física e proteção contra sobrescrita
    - Implementar `_promote_to_raw(staging_path: Path, stored_filename: str) -> Path`
    - Verificar se o caminho físico final já existe em `data/raw/`
    - Se existir com entrada Manifest consistente → abortar com `"file_exists_consistent"`
    - Se existir sem entrada Manifest → abortar com `"inconsistency_orphan_file"` (não remover o arquivo existente)
    - Se não existir → mover staging para `data/raw/stored_filename`; retornar Path promovido
    - _Requirements: 1.5, 1.8_

  - [ ] 5.4 Implementar o fluxo completo do método `ingest` no `Ingestor`
    - Implementar `ingest(source_path: Path, downloaded_at: str) -> IngestorResult`
    - Passo 0: verificar `has_pending_entries()` → abortar com `"blocked_pending_manifest"` se True
    - Passos 1–4: validar arquivo, calcular SHA-256, verificar `Duplicidade_Por_Conteudo`, verificar `Conflito_Por_Nome`
    - Passos 5–8: resolver `stored_filename`, copiar para staging, calcular SHA-256 do staging, comparar hashes
    - Passos 9–10: promover staging → `data/raw/`, registrar no Manifest; se escrita falhar → `append_pending_entry` + retornar `"manifest_pending"`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 2.5_

  - [ ]* 5.5 Escrever testes unitários para o `Ingestor`
    - `test_conflict_por_nome_nao_sobrescreve`: mesmo `original_filename` e hash diferente → `stored_filename` distinto, arquivo original inalterado, ambas entradas no Manifest
    - `test_duplicidade_por_conteudo_aborta_antes_staging`: SHA-256 já no Manifest → nenhum arquivo em `data/interim/` ou `data/raw/`, `status == "duplicate_content"`
    - `test_integridade_staging_promovido`: SHA-256 do arquivo promovido em `data/raw/` é idêntico ao SHA-256 da origem *(Property 1)*
    - `test_falha_integridade_nao_afeta_raw`: simular SHA-256 divergente em staging → `data/raw/` inalterado, `data/interim/` limpo, nenhuma entrada no Manifest, `status == "integrity_error"`
    - `test_manifest_duplicidade_emite_aviso`: SHA-256 duplicado → aviso emitido, nenhuma cópia, `status == "duplicate_content"`
    - `test_promote_to_raw_nao_sobrescreve_fisicamente`: `stored_filename` já existe em `data/raw/` → operação abortada, arquivo existente inalterado
    - `test_stored_filename_desambiguacao_progressiva`: simular colisão em `sha256[:8]` → `stored_filename` com `sha256[:10]`; nenhum arquivo sobrescrito
    - `test_blocked_pending_manifest`: `pending.jsonl` existente → `status == "blocked_pending_manifest"`, nenhuma escrita
    - _Requirements: 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 5.6 Escrever teste de propriedade para integridade da cópia
    - **Feature: construcao-corpus-piloto, Property 1: Integridade da cópia (SHA-256 preservado na promoção)**
    - `test_property_integridade_copia`: para qualquer conteúdo binário válido gerado pelo Hypothesis, o SHA-256 do arquivo promovido deve ser igual ao SHA-256 calculado antes da cópia (`settings(max_examples=100)`)
    - _Requirements: 1.6, 2.1_

- [ ] 6. Implementar `Auditor` — análises estruturais e condicionais
  - [ ] 6.1 Criar estrutura base do `Auditor` e análises estruturais em `src/data/auditor.py`
    - Criar `src/data/auditor.py`
    - Definir `FieldAnalysisStatus` (Enum): `NOT_CONFIGURED`, `FIELD_MISSING`, `OK`
    - Definir `ConditionalAnalysis` (dataclass): `status: FieldAnalysisStatus`, `result`
    - Definir `AuditResult` (dataclass) com todos os campos do design: `n_rows`, `n_cols`, `column_names`, `column_types`, `missing_counts`, `coverage_pct`, `unique_counts`, `audit_timestamp`, `auditor_version`, `source_file`, análises condicionais e `config_inconsistencies`
    - Implementar `Auditor.__init__(self, config: CorpusConfig, manifest: ManifestWriter)`
    - Definir constante `VERSION = "1.0.0"`
    - Atualizar `src/data/__init__.py` para exportar `Auditor`, `AuditResult`, `FieldAnalysisStatus`
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ] 6.2 Implementar análises condicionais no `Auditor` (`run`)
    - Implementar `run(corpus_path: Path) -> AuditResult`
    - Verificar `has_pending_entries()` → levantar `PendingManifestError` se True
    - Chamar `validate_file_provenance()` → levantar `ProvenanceError` com motivo se inválido
    - Calcular análises estruturais: `n_rows`, `n_cols`, `column_names`, `column_types`, `missing_counts`, `coverage_pct` (em [0.00, 100.00]), `unique_counts`
    - Análises condicionais (somente se campo configurado E presente no dataset): duplicatas (N-1 por grupo), distribuição de tamanho de texto (mín, máx, média, mediana, P25, P75), `Documentos_Sem_Texto` (nulo, vazio, apenas espaços), cobertura de `metadata_fields`
    - Campos configurados mas ausentes no dataset → `FIELD_MISSING` + registrar em `config_inconsistencies`
    - Lançar `FileNotFoundError` se `corpus_path` não existir
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [ ] 6.3 Implementar `save_reports` no `Auditor`
    - Implementar `save_reports(result: AuditResult, reports_dir: Path) -> dict[str, Path]`
    - Produzir sempre os 5 arquivos: `raw_summary.json`, `column_profile.csv`, `text_length_profile.csv`, `sample_records.csv`, `audit_report.md`
    - Análises condicionais com status `NOT_CONFIGURED` ou `FIELD_MISSING` → indicar explicitamente no arquivo (nunca usar `0` para representar análise não executada)
    - `sample_records.csv`: amostra determinística de até 20 registros com `seed=42`
    - Incluir no relatório: timestamp ISO 8601 UTC, versão do Auditor (`VERSION`), nome do arquivo auditado
    - Se arquivo com mesmo nome já existir → gerar nome com sufixo `YYYYMMDDTHHMMSSZ`
    - Se diretório não existir → criar antes de salvar
    - Lançar `OSError` se escrita falhar; retornar dict com os 5 caminhos
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 6.4 Escrever testes unitários para o `Auditor`
    - `test_duplicatas_n_menos_1`: grupo de N registros com mesmo identificador → `duplicates_analysis.result == N - 1` *(Property 7)*
    - `test_documentos_sem_texto_nulo_vazio_espacos`: nulo, `""`, `"   "`, `"\t"` → todos contabilizados como `Documento_Sem_Texto` *(Property 9)*
    - `test_auditoria_estrutural_sem_config`: sem `primary_key_field`, `text_field` e `metadata_fields` → análises condicionais com `status == NOT_CONFIGURED`; análises estruturais presentes normalmente
    - `test_save_reports_nao_sobrescreve`: executar `save_reports` duas vezes → segundo conjunto com sufixo de timestamp; primeiro inalterado
    - `test_save_reports_cria_diretorio`: `reports_dir` inexistente → diretório criado e arquivos gravados sem erro
    - `test_arquivo_sem_manifest_bloqueia_auditor`: arquivo sem entrada no Manifest → `ProvenanceError`; nenhum relatório produzido
    - `test_hash_divergente_manifest_bloqueia_auditor`: SHA-256 atual diverge do registrado → `ProvenanceError("integrity_mismatch")`; nenhum relatório produzido
    - `test_campo_configurado_ausente_no_dataset`: `primary_key_field` configurado mas ausente nas colunas → `duplicates_analysis.status == FIELD_MISSING`; em `config_inconsistencies`; análises estruturais executadas normalmente
    - `test_cinco_outputs_produzidos_sem_config_semantico`: auditoria sem configuração semântica → todos os 5 arquivos produzidos; nenhum contém `0` para análise não executada
    - _Requirements: 8.7, 8.8, 8.9_

  - [ ]* 6.5 Escrever teste de propriedade para cobertura de coluna
    - **Feature: construcao-corpus-piloto, Property 6: Intervalo válido de cobertura por coluna**
    - `test_property_cobertura_intervalo_valido`: para qualquer DataFrame gerado pelo Hypothesis com pelo menos uma linha, `coverage_pct[col] ∈ [0.00, 100.00]` para toda coluna (`settings(max_examples=100)`)
    - _Requirements: 3.3_

- [ ] 7. Checkpoint — Ingestor e Auditor
  - Garantir que todos os testes implementados até aqui passem. Verificar com `pytest tests/ -v`. Em caso de dúvida, consultar o pesquisador.

- [ ] 8. Implementar `Canonizador` — filtragem, `doc_id` e elegibilidade
  - [ ] 8.1 Criar estrutura base do `Canonizador` e lógica de `doc_id` em `src/data/canonizador.py`
    - Criar `src/data/canonizador.py`
    - Definir `CanonicalizationResult` (dataclass) com todos os campos do design: `parquet_path`, `sidecar_path`, `rejected_log_path`, `issues_log_path`, `n_accepted`, `n_rejected`, `n_total`, `rejected_log`, `issues_log`, `dataset_fingerprint`, `excluded_fields`
    - Implementar `Canonizador.__init__(self, config: CorpusConfig, manifest: ManifestWriter)`
    - Implementar `_assign_doc_id(source_key: str) -> str`: formato `'tcu-' + sha256(source_key.encode('utf-8'))[:12]`; determinístico por `source_key`
    - Implementar `_validate_doc_id_uniqueness(df: pd.DataFrame) -> None`: detectar dois `source_key` distintos com mesmo `doc_id`; lançar `ValueError` descritivo se colisão
    - Atualizar `src/data/__init__.py` para exportar `Canonizador` e `CanonicalizationResult`
    - _Requirements: 5.2, 5.3, 5.4_

  - [ ] 8.2 Implementar `_apply_eligibility` no `Canonizador`
    - Implementar `_apply_eligibility(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]`
    - Pré-condição: registros com `source_key` nulo ou vazio já foram removidos antes desta função (no fluxo de `run`)
    - Para `primary_key_field` e `required_fields`: rejeitar registros com valores nulos, vazios ou malformados (regras declaradas no Config_File); registrar motivo em `rejected_log`
    - Para campos não obrigatórios: política padrão do baseline → preservar valor original, registrar em `issues_log`, aceitar registro; nunca inferir, normalizar ou preencher valores
    - _Requirements: 5.4, 5.5, 5.6, 5.7, 5.10, 5.11, 5.12, 7.1, 7.4_

  - [ ] 8.3 Implementar métodos de persistência de artefatos (`_write_sidecar`, `_write_rejected_log`, `_write_issues_log`)
    - Implementar `_write_sidecar(parquet_path, excluded_fields, dataset_fingerprint) -> Path`: gravar `{parquet_stem}_metadata.json` com campos `parquet_file`, `created_at`, `config_version`, `batch_id`, `allowed_fields`, `excluded_fields`, `dataset_fingerprint`; `dataset_fingerprint` é obrigatório no sidecar
    - Implementar `_write_rejected_log(stem_path, rejected) -> Path`: gravar `{stem}_rejected.jsonl`; sempre produzido mesmo vazio; cada linha com `source_key`, `row_index`, `reason`
    - Implementar `_write_issues_log(stem_path, issues) -> Path | None`: gravar `{stem}_issues.jsonl` somente se `issues` não estiver vazio; cada linha com `source_key`, `field`, `issue_type`, `original_value`
    - _Requirements: 5.4, 7.2, 7.3, 7.6_

  - [ ] 8.4 Implementar `_append_fingerprint_log` e publicação atômica no `Canonizador`
    - Implementar `_append_fingerprint_log(result: CanonicalizationResult) -> None`: acrescentar linha ao `fingerprint_log.jsonl` com timestamp, `parquet_file`, `dataset_fingerprint`, `config_version`, `batch_id`, `n_accepted`, `n_rejected`; falha neste método emite aviso mas não invalida o corpus já publicado
    - Implementar lógica de publicação atômica: produzir artefatos em `data/interim/canon_{timestamp}/`, validar legibilidade dos 3 obrigatórios (Parquet, sidecar, `_rejected.jsonl`), mover atomicamente para `data/processed/original/`; se qualquer artefato obrigatório falhar → descartar diretório temporário, nenhum arquivo em `data/processed/original/`
    - Nomenclatura obrigatória: `corpus_{batch_id}_{YYYYMMDD_HHMMSS}.*`
    - Se Parquet de saída já existir no destino → criar novo com sufixo de timestamp
    - _Requirements: 5.1, 5.9, 6.1, 9.4, 9.5, 9.6_

  - [ ] 8.5 Implementar o fluxo completo do método `run` no `Canonizador`
    - Implementar `run(corpus_path: Path) -> CanonicalizationResult`
    - Passo 1: `validate_file_provenance()` → abortar se inválido
    - Passo 1a: `has_pending_entries()` → levantar `PendingManifestError` se True
    - Passos 2–4: validar `primary_key_field` e `text_field` existem no dataset; ler CSV; aplicar `allowed_fields` → calcular `excluded_fields`
    - Passos 5–6: extrair `source_key` sem modificação; rejeitar registros com `source_key` nulo/vazio antes de gerar `doc_id`
    - Passos 7–8: derivar `doc_id`; chamar `_validate_doc_id_uniqueness`; aplicar `_apply_eligibility`
    - Passo 8c: calcular `dataset_fingerprint` sobre o DataFrame aceito
    - Passos 9–11: produzir artefatos em área temporária, validar legibilidade, mover atomicamente para `data/processed/original/`
    - Passo 12: chamar `_append_fingerprint_log`; falha → aviso, corpus permanece válido
    - `n_total == n_accepted + n_rejected` obrigatoriamente
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.11, 6.1, 6.3, 6.4, 7.2, 7.3, 9.5, 9.6_

  - [ ]* 8.6 Escrever testes unitários para o `Canonizador`
    - `test_source_key_doc_id_presentes_nao_nulos_bijetivos`: Parquet contém `source_key` e `doc_id` não-nulos; nenhum `doc_id` duplicado com `source_key` distinto *(Property 4)*
    - `test_round_trip_parquet`: escrita seguida de leitura retorna mesmo número de linhas e mesmos dtypes *(Property 8)*
    - `test_reconciliacao_total`: `n_accepted + n_rejected == n_total` para qualquer dataset *(Property 2)*
    - `test_campo_obrigatorio_ausente_rejeicao_auditavel`: `primary_key_field` nulo → rejeitado, motivo em `rejected_log`, demais aceitos
    - `test_campo_nao_obrigatorio_malformado_preservado`: campo não obrigatório malformado → valor original no Parquet, registro aceito, aviso em `issues_log`
    - `test_corpus_vazio_parquet_valido`: zero registros → Parquet com zero linhas e schema correto, sem erro
    - `test_nao_sobrescreve_parquet_existente`: Parquet já em `processed_dir` → novo arquivo com sufixo de timestamp; existente inalterado
    - `test_arquivo_sem_manifest_bloqueia_canonizador`: sem entrada válida no Manifest → nenhum artefato em `data/processed/original/`
    - `test_colisao_doc_id_aborta_canonizacao`: dois `source_key` que geram mesmo `doc_id` truncado → abortado antes de qualquer escrita
    - `test_metadata_fields_preservados_no_parquet`: campos de `metadata_fields` preservados com valores originais
    - `test_metadata_field_ausente_permanece_null`: campo de `metadata_fields` ausente em registro → `null` no Parquet; registro não rejeitado
    - `test_allowed_fields_controla_colunas_do_parquet`: campo não em `allowed_fields` (ex: `VISAOGERAL`) → ausente no Parquet; em `excluded_fields` do sidecar
    - `test_falha_antes_publicacao_nao_deixa_parquet_parcial`: simular falha nos artefatos → diretório temporário descartado; nenhum arquivo em `data/processed/original/`
    - `test_registros_rejeitados_persistidos`: `_rejected.jsonl` produzido com `source_key` e motivo; legível
    - `test_fingerprint_log_falha_nao_invalida_corpus`: simular falha em `_append_fingerprint_log` → aviso emitido, corpus em `data/processed/original/` válido
    - `test_source_key_nulo_rejeitado_antes_doc_id`: `source_key` nulo → rejeitado com `"source_key_null_or_empty"` antes de gerar `doc_id`
    - `test_sidecar_contem_dataset_fingerprint`: sidecar `_metadata.json` contém campo `dataset_fingerprint`
    - _Requirements: 8.10, 8.11_

  - [ ]* 8.7 Escrever testes de propriedade para o `Canonizador`
    - **Feature: construcao-corpus-piloto, Property 3: Determinismo do `doc_id` por `source_key`**
    - `test_property_doc_id_determinístico`: para qualquer `source_key` gerado pelo Hypothesis, duas chamadas consecutivas a `_assign_doc_id` retornam o mesmo valor (`settings(max_examples=100)`)
    - **Feature: construcao-corpus-piloto, Property 2: Reconciliação total de registros**
    - `test_property_reconciliacao_total`: para qualquer DataFrame gerado pelo Hypothesis, `n_accepted + n_rejected == n_total`
    - _Requirements: 5.3, 5.5_

- [ ] 9. Checkpoint — Canonizador
  - Garantir que todos os testes implementados até aqui passem. Verificar com `pytest tests/ -v`. Em caso de dúvida, consultar o pesquisador.

- [ ] 10. Implementar CLIs
  - [ ] 10.1 Implementar CLI do Ingestor em `scripts/ingest.py`
    - Criar `scripts/ingest.py`
    - Argumentos obrigatórios via `argparse`: `--config` (caminho do Config_File), `--file` (arquivo local a ingerir), `--downloaded-at` (ISO 8601 UTC)
    - Carregar `CorpusConfig.load(config)`, instanciar `ManifestWriter` e `Ingestor`, chamar `ingest()`
    - Exibir `IngestorResult.status` e `IngestorResult.message` no stdout
    - Encerrar com código de saída `0` para `"ingested"` e `"name_conflict_versioned"`, `1` para os demais
    - _Requirements: 9.1_

  - [ ] 10.2 Implementar CLI do Auditor em `scripts/audit.py`
    - Criar `scripts/audit.py`
    - Argumentos obrigatórios via `argparse`: `--config` (caminho do Config_File), `--file` (arquivo CSV em `data/raw/` a auditar)
    - Carregar `CorpusConfig.load(config)`, instanciar `ManifestWriter` e `Auditor`, chamar `run()` e `save_reports()`
    - Exibir no stdout os caminhos dos 5 arquivos gravados
    - Encerrar com código `0` em sucesso, `1` em erro; exibir mensagem de erro descritiva
    - _Requirements: 9.1_

  - [ ] 10.3 Implementar CLI do Canonizador em `scripts/canonize.py`
    - Criar `scripts/canonize.py`
    - Argumentos obrigatórios via `argparse`: `--config` (caminho do Config_File), `--file` (arquivo CSV em `data/raw/` a canonizar)
    - Carregar `CorpusConfig.load(config)`, instanciar `ManifestWriter` e `Canonizador`, chamar `run()`
    - Exibir no stdout: caminho do Parquet, do sidecar, do `_rejected.jsonl`, `n_accepted`, `n_rejected`, `dataset_fingerprint`
    - Encerrar com código `0` em sucesso, `1` em erro; exibir mensagem de erro descritiva
    - _Requirements: 9.1_

- [ ] 11. Criar arquivo de configuração de exemplo
  - [ ] 11.1 Criar `configs/corpus_config.yaml` com todos os campos documentados
    - Criar `configs/corpus_config.yaml` com o schema completo do design, comentários explicativos e valores de exemplo para cada campo
    - Incluir: `source_identifier`, `batch_id`, `dataset`, `dataset_year`, `schema_version`, `config_version`, `source_url`, `primary_key_field: null`, `text_field: null`, `allowed_fields: []`, `metadata_fields: []`, `required_fields: []`, caminhos de diretórios com defaults
    - Incluir comentário sobre `field_validation_rules` como seção opcional futura
    - _Requirements: 7.5, 9.1, 9.2_

- [ ] 12. Checkpoint final — garantir suite completa
  - Verificar que `pytest tests/ -v` passa sem falhas. Revisar cobertura dos 9 requisitos principais e das 9 propriedades de corretude. Em caso de dúvida, consultar o pesquisador.

---

## Notas

- Tarefas marcadas com `*` são opcionais e podem ser puladas para uma entrega MVP mais rápida
- Cada tarefa referencia os requisitos específicos do `requirements.md` para rastreabilidade
- Checkpoints garantem validação incremental antes de avançar para camadas dependentes
- Testes de propriedade usam `settings(max_examples=100)` e incluem tag de rastreabilidade no cabeçalho
- `pending.jsonl` é um estado de inconsistência que bloqueia `Ingestor.ingest()`, `Auditor.run()` e `Canonizador.run()` — coberto nos testes de cada módulo
- `dataset_fingerprint` é obrigatório no sidecar; falha no `fingerprint_log.jsonl` gera apenas aviso
- `config_version` é obrigatório e independente de `schema_version`; nenhum mecanismo de sincronização automática entre eles
- A publicação atômica via `data/interim/canon_{timestamp}/` garante que nenhum artefato parcial atinge `data/processed/original/`
- O Canonizador nunca infere, normaliza ou preenche valores; toda política é declarada explicitamente no Config_File

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1"] },
    { "id": 3, "tasks": ["2.3", "3.2"] },
    { "id": 4, "tasks": ["3.3", "5.1"] },
    { "id": 5, "tasks": ["5.2", "6.1"] },
    { "id": 6, "tasks": ["5.3"] },
    { "id": 7, "tasks": ["5.4", "6.2"] },
    { "id": 8, "tasks": ["5.5", "5.6", "6.3", "8.1"] },
    { "id": 9, "tasks": ["6.4", "6.5", "8.2"] },
    { "id": 10, "tasks": ["8.3"] },
    { "id": 11, "tasks": ["8.4"] },
    { "id": 12, "tasks": ["8.5"] },
    { "id": 13, "tasks": ["8.6", "8.7", "10.1", "10.2", "10.3"] },
    { "id": 14, "tasks": ["11.1"] }
  ]
}
```

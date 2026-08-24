# Requirements Document

## Introduction

Esta spec define os requisitos para obtenção, auditoria e construção do corpus piloto de
Acórdãos públicos do TCU (Tribunal de Contas da União). O corpus é a base documental
original que alimentará os experimentos posteriores de recuperação estruturada, vetorial e
híbrida. O pipeline deve garantir rastreabilidade completa, imutabilidade lógica dos
arquivos originais, separação entre conteúdo bruto e conteúdo processado, e
reprodutibilidade total do processo.

---

## Glossary

- **Pipeline**: Conjunto de scripts Python que executa o registro, auditoria e conversão
  dos documentos do corpus.
- **Corpus_Original**: Conjunto de Acórdãos públicos do TCU obtidos de fonte primária,
  armazenados sem modificação em `data/raw/`.
- **Corpus_Canonico**: Representação tabular padronizada do corpus, armazenada em formato
  Parquet em `data/processed/original/`. Contém, para cada documento elegível: `doc_id`,
  `source_key`, o campo de texto completo configurado, e os campos estruturados originais
  selecionados em `allowed_fields` / `metadata_fields` após a auditoria do dataset. Nenhum
  campo é preenchido, inferido ou completado por modelos de linguagem.
- **Manifest**: Arquivo de registro de proveniência que documenta metadados de cada arquivo
  bruto incorporado ao corpus (campos obrigatórios: `original_filename`, `stored_filename`,
  `downloaded_at`, `ingested_at`, `file_size_bytes`, `sha256`, `source_url` ou
  `source_identifier`, `dataset`, `dataset_year` (ano ao qual o lote/dataset se refere;
  exemplo: dataset de acórdãos de 2024 baixado em 2026 terá `dataset_year=2024`),
  `schema_version`, `batch_id`).
- **Auditor**: Módulo Python responsável por calcular e reportar estatísticas de qualidade
  do corpus.
- **Ingestor**: Módulo Python responsável por receber um arquivo local previamente obtido
  pelo pesquisador e incorporá-lo de forma controlada ao corpus bruto em `data/raw/`. O
  Ingestor não realiza download automático, web scraping ou descoberta de documentos.
- **Canonizador**: Módulo Python responsável por transformar arquivos brutos em tabela
  canônica Parquet.
- **Config_File**: Arquivo de configuração (YAML ou TOML) que parametriza o comportamento
  do Pipeline, incluindo os campos `allowed_fields` (lista de campos permitidos no corpus
  original) e os nomes configuráveis do identificador primário, do campo de texto completo
  e dos campos de metadados principais.
- **Report_Corpus**: Diretório `reports/corpus/` onde os resultados da auditoria são
  salvos.
- **Hash_SHA256**: Valor hexadecimal de 64 caracteres produzido pelo algoritmo SHA-256
  aplicado ao conteúdo binário de um arquivo.
- **Conteudo_Enriquecido**: Qualquer campo textual gerado, aumentado ou modificado por
  modelo de linguagem ou sistema de IA após a obtenção do documento original.
- **Documento_Sem_Texto**: Acórdão cujo campo configurado como texto completo está ausente,
  vazio ou contém apenas espaços em branco.
- **downloaded_at**: Data e hora em que o pesquisador obteve o arquivo da fonte original,
  informada explicitamente no momento da ingestão (formato ISO 8601 UTC).
- **ingested_at**: Data e hora em que o Ingestor executou a incorporação do arquivo ao
  corpus bruto (formato ISO 8601 UTC), registrada automaticamente pelo Ingestor.
- **dataset_fingerprint**: Identificador determinístico calculado sobre o schema e o
  conteúdo ordenado do Corpus_Canonico, independente de metadados internos do formato
  Parquet (timestamps de escrita, compressão, ordem dos row groups).
- **source_key**: Identificador original do documento proveniente da fonte (TCU), preservado
  sem modificação no Corpus_Canonico.
- **doc_id**: Identificador interno do experimento atribuído pelo Pipeline a cada documento
  do Corpus_Canonico, mantendo relação consistente com `source_key`.
- **allowed_fields**: Lista de campos do dataset original declarados no Config_File como
  elegíveis para inclusão no Corpus_Canonico.
- **metadata_fields**: Subconjunto de `allowed_fields` declarado no Config_File contendo
  os campos estruturados documentais (por exemplo: número do acórdão, ano do acórdão,
  relator, colegiado, data da sessão, número do processo, tipo de processo, assunto,
  entidade, unidade técnica) que serão preservados no Corpus_Canonico como metadados para
  uso nos experimentos posteriores. Os campos específicos são definidos após a auditoria
  do dataset real; nenhum campo é obrigatório antes da inspeção.
- **excluded_fields**: Lista de campos excluídos da representação canônica original,
  registrada de forma associada à versão do Corpus_Canonico para garantir auditabilidade.
- **Duplicidade_Por_Conteudo**: Situação em que o Hash_SHA256 de um arquivo recém-recebido
  coincide com o `sha256` de uma entrada já existente no Manifest, independentemente do
  nome do arquivo. O conteúdo já foi ingerido; nenhuma nova cópia deve ser criada.
- **Conflito_Por_Nome**: Situação em que já existe um arquivo associado ao mesmo
  `original_filename` no Manifest, mas o Hash_SHA256 do novo arquivo é diferente. Um
  conflito de nome com conteúdo diferente representa uma nova versão do arquivo-fonte e
  não deve resultar em descarte nem em sobrescrita: o Pipeline deverá atribuir um
  `stored_filename` distinto e rastreável, preservando o `original_filename` no Manifest.
- **Registro_Elegivel**: Registro do Corpus_Original que satisfaz todos os critérios de
  elegibilidade declarados na política de canonização configurada no Config_File.

---

## Requirements

### Requirement 1: Imutabilidade lógica dos arquivos brutos

**User Story:** Como pesquisador, quero garantir que os arquivos originais nunca sejam
alterados, para que eu possa reproduzir qualquer etapa do experimento a partir do dado
primário.

#### Acceptance Criteria

1. WHEN o Ingestor recebe um arquivo local, THE Ingestor SHALL validar a existência e a
   legibilidade do arquivo de entrada antes de qualquer outra operação; IF o arquivo não
   existir ou não puder ser lido, THEN THE Ingestor SHALL abortar a operação e registrar
   uma mensagem de erro indicando a causa, sem realizar nenhuma operação de escrita.
2. WHEN o Ingestor valida o arquivo de entrada com sucesso, THE Ingestor SHALL calcular o
   Hash_SHA256 do arquivo de origem antes de qualquer cópia; IF o cálculo do
   Hash_SHA256 de origem falhar por qualquer motivo (erro de leitura, interrupção ou
   outro), THEN THE Ingestor SHALL abortar a operação antes de qualquer cópia e
   registrar uma mensagem de erro indicando a causa da falha no cálculo do hash.
3. WHEN o Hash_SHA256 de origem for calculado com sucesso, THE Ingestor SHALL verificar
   no Manifest se esse valor já consta em uma entrada existente; IF o Hash_SHA256 já
   existir no Manifest (Duplicidade_Por_Conteudo), THEN THE Ingestor SHALL abortar a
   operação sem copiar o arquivo para `data/raw/`, sem criar nova entrada no Manifest, e
   registrar um aviso de tentativa de ingestão duplicada por conteúdo, indicando o
   `original_filename` e o `ingested_at` da entrada existente; IF o Hash_SHA256 não
   existir no Manifest, THE Ingestor SHALL prosseguir verificando Conflito_Por_Nome
   conforme AC 1.4.
4. WHEN o Hash_SHA256 de origem não constar no Manifest, THE Ingestor SHALL verificar se
   já existe uma entrada no Manifest com o mesmo `original_filename`; IF existir uma
   entrada com mesmo `original_filename` mas Hash_SHA256 diferente (Conflito_Por_Nome),
   THEN THE Ingestor SHALL não sobrescrever o arquivo existente em `data/raw/`, atribuir
   um `stored_filename` distinto e rastreável ao novo arquivo, e prosseguir com a cópia
   via área intermediária; o mecanismo exato de geração do `stored_filename` versionado
   (por exemplo, sufixo de timestamp, parte do hash ou versão) é responsabilidade do
   design.
5. WHEN não houver Duplicidade_Por_Conteudo e não houver impedimento de nome, THE Ingestor
   SHALL copiar o arquivo para uma área intermediária (staging) antes de qualquer escrita
   em `data/raw/`; somente após a validação de integridade do arquivo na área intermediária
   o arquivo SHALL ser promovido para `data/raw/` preservando o `stored_filename`
   determinado; o mecanismo da área intermediária (diretório de staging, arquivo
   temporário, movimentação atômica ou equivalente) é responsabilidade do design.
6. WHEN o Ingestor calcula o Hash_SHA256 do arquivo na área intermediária e compara com o
   Hash_SHA256 da origem, IF os hashes forem idênticos, THEN THE Ingestor SHALL promover
   o arquivo para `data/raw/` e prosseguir com o registro no Manifest; IF os hashes
   divergirem, THEN THE Ingestor SHALL registrar um erro de integridade de cópia,
   descartar ou isolar somente o artefato na área intermediária sem afetar `data/raw/`,
   não criar entrada no Manifest, e deixar o ambiente em estado que permita uma nova
   tentativa de ingestão do mesmo arquivo sem bloqueio por artefato órfão; arquivos
   validamente incorporados em `data/raw/` nunca são afetados por uma falha de
   integridade de cópia posterior; o mecanismo de descarte ou isolamento do artefato
   intermediário inválido é responsabilidade do design.
7. IF a verificação de existência do arquivo em `data/raw/` não puder ser concluída
   devido a erro de acesso ao sistema de arquivos, THEN THE Ingestor SHALL abortar a
   operação e registrar uma mensagem de erro indicando a causa da falha, sem realizar
   nenhuma operação de escrita.
8. THE Ingestor SHALL rejeitar qualquer operação de modificação ou exclusão sobre
   arquivos já presentes em `data/raw/`, registrando um erro que indica a tentativa de
   violação de imutabilidade.

---

### Requirement 2: Registro de proveniência (Manifest)

**User Story:** Como pesquisador, quero que cada arquivo bruto tenha seus metadados de
proveniência registrados, para que eu possa auditar a origem e integridade de cada
documento a qualquer momento.

#### Acceptance Criteria

1. WHEN o Ingestor promove um arquivo validado para `data/raw/` e confirma que o
   Hash_SHA256 do arquivo promovido é idêntico ao da origem, THE Ingestor SHALL criar
   uma entrada no Manifest contendo exatamente os seguintes campos: `original_filename`,
   `stored_filename`, `downloaded_at` (data informada pelo pesquisador em ISO 8601 UTC),
   `ingested_at` (data de execução do Ingestor em ISO 8601 UTC), `file_size_bytes`,
   `sha256` (calculado sobre o conteúdo binário completo do arquivo promovido para
   `data/raw/`), `source_url` ou `source_identifier`, `dataset`, `dataset_year`,
   `schema_version` e `batch_id`.
2. THE Manifest SHALL ser armazenado em `data/manifests/` em formato JSON Lines ou CSV,
   com cada entrada ocupando exatamente uma linha, permitindo leitura programática sem
   carregamento completo do arquivo.
3. WHEN o Hash_SHA256 de um arquivo for calculado, THE Ingestor SHALL calcular o hash
   sobre o conteúdo binário completo do arquivo sem modificação, sem normalização de
   linha ou transformação de encoding.
4. WHEN uma entrada do Manifest for criada, THE Ingestor SHALL rejeitar entradas com
   quaisquer dos campos obrigatórios ausentes — `original_filename`, `stored_filename`,
   `downloaded_at`, `ingested_at`, `file_size_bytes`, `sha256`, `source_url` ou
   `source_identifier`, `dataset`, `dataset_year`, `schema_version`, `batch_id` — e
   registrar um erro indicando qual campo está ausente.
5. IF a escrita de uma entrada no Manifest falhar após o arquivo ter sido armazenado em
   `data/raw/` com integridade confirmada, THEN THE Ingestor SHALL reter o arquivo em
   `data/raw/` sem removê-lo — pois a integridade do conteúdo foi verificada com
   sucesso — e SHALL registrar um erro indicando que a proveniência do arquivo está
   pendente de registro, identificando o `stored_filename` afetado; THE Ingestor SHALL
   registrar explicitamente que qualquer operação posterior que dependa desse arquivo
   (canonização, auditoria, consulta de proveniência) não deve ser executada até que a
   inconsistência entre `data/raw/` e o Manifest seja resolvida manualmente.

---

### Requirement 3: Script de auditoria do corpus

**User Story:** Como pesquisador, quero executar uma auditoria completa do corpus para
identificar problemas de qualidade antes de iniciar os experimentos.

#### Acceptance Criteria

1. WHEN o Auditor é executado sobre o Corpus_Original, THE Auditor SHALL calcular e
   reportar a quantidade total de linhas do dataset.
2. WHEN o Auditor é executado sobre o Corpus_Original, THE Auditor SHALL calcular e
   reportar a quantidade total de colunas do dataset, os nomes de cada coluna e o tipo
   de dado de cada coluna.
3. WHEN o Auditor é executado sobre o Corpus_Original, THE Auditor SHALL calcular e
   reportar, para cada coluna, a contagem de valores ausentes e o percentual de
   cobertura (razão entre valores presentes e total de registros, expressa em
   porcentagem com duas casas decimais).
4. WHEN o Auditor é executado sobre o Corpus_Original, THE Auditor SHALL calcular e
   reportar a quantidade de valores únicos por coluna.
5. WHEN o Auditor é executado sobre o Corpus_Original, WHERE o campo configurado como
   identificador primário estiver declarado no Config_File, THE Auditor SHALL identificar
   e reportar o número de registros duplicados com base nesse campo, contabilizando como
   duplicatas N-1 registros de cada grupo de N registros com identificador idêntico; IF
   o campo configurado como identificador primário não estiver presente no Config_File,
   THEN THE Auditor SHALL omitir essa análise do relatório e registrar explicitamente que
   a análise de duplicatas por identificador primário foi omitida por falta de
   configuração.
6. WHEN o Auditor é executado sobre o Corpus_Original, WHERE o campo configurado como
   texto completo estiver declarado no Config_File, THE Auditor SHALL calcular e reportar
   a distribuição do tamanho dos textos desse campo, em número de caracteres, incluindo
   mínimo, máximo, média arredondada a duas casas decimais, mediana arredondada a duas
   casas decimais e percentis P25 e P75; IF o campo configurado como texto completo não
   estiver presente no Config_File, THEN THE Auditor SHALL omitir essa análise do
   relatório e registrar explicitamente que a análise de distribuição de tamanho de texto
   foi omitida por falta de configuração.
7. WHEN o Auditor é executado sobre o Corpus_Original, WHERE o campo configurado como
   texto completo estiver declarado no Config_File, THE Auditor SHALL identificar e
   reportar a lista de Documentos_Sem_Texto e a contagem total desses documentos; IF o
   campo configurado como texto completo não estiver presente no Config_File, THEN THE
   Auditor SHALL omitir essa análise do relatório e registrar explicitamente que a
   identificação de Documentos_Sem_Texto foi omitida por falta de configuração.
8. WHEN o Auditor é executado sobre o Corpus_Original, WHERE os campos configurados como
   `metadata_fields` estiverem declarados no Config_File, THE Auditor SHALL calcular e
   reportar a cobertura de cada um desses campos, informando o percentual preenchido —
   definido como não nulo, não vazio e não composto exclusivamente por espaços em branco
   — com duas casas decimais; o relatório `audit_report.md` SHALL destacar a cobertura
   desses campos estruturados para subsidiar a decisão sobre quais serão utilizados nos
   experimentos posteriores; IF nenhum campo `metadata_fields` estiver declarado no
   Config_File, THEN THE Auditor SHALL omitir essa análise e registrar explicitamente que
   foi omitida por falta de configuração; IF apenas alguns campos estiverem declarados,
   THE Auditor SHALL analisar os presentes e registrar quais foram omitidos.
9. IF o Corpus_Original não existir no caminho especificado ou estiver ilegível, THEN
   THE Auditor SHALL encerrar com código de erro e exibir uma mensagem indicando o
   caminho inválido, sem gravar nenhum relatório parcial.

---

### Requirement 4: Persistência dos relatórios de auditoria

**User Story:** Como pesquisador, quero que os resultados da auditoria sejam salvos em
arquivos estruturados, para que eu possa consultá-los e versionar os resultados ao longo
do tempo.

#### Acceptance Criteria

1. WHEN o Auditor conclui a execução, THE Auditor SHALL salvar os seguintes arquivos em
   `reports/corpus/`: `raw_summary.json` (totais gerais: linhas, colunas, documentos
   sem texto, duplicatas), `column_profile.csv` (perfil por coluna: nome, tipo, valores
   ausentes, cobertura, únicos), `text_length_profile.csv` (distribuição do tamanho dos
   textos: mín, máx, média, mediana, P25, P75), `sample_records.csv` (amostra de
   registros para inspeção visual) e `audit_report.md` (relatório narrativo
   consolidado).
2. WHEN o Auditor salva o relatório, THE Auditor SHALL incluir no relatório o timestamp
   de execução (ISO 8601 UTC), a versão do Auditor e o nome do arquivo ou dataset
   auditado.
3. IF um relatório com o mesmo nome já existir em `reports/corpus/`, THEN THE Auditor
   SHALL gerar um nome de arquivo com sufixo de timestamp no formato
   `YYYYMMDDTHHMMSSZ` para evitar sobrescrita, sem modificar ou excluir o arquivo
   existente.
4. IF o diretório `reports/corpus/` não existir no momento de salvar o relatório, THEN
   THE Auditor SHALL criar o diretório antes de salvar os arquivos.
5. IF o Auditor falhar ao salvar o relatório em disco (por exemplo, por falta de
   permissão de escrita ou espaço insuficiente), THEN THE Auditor SHALL encerrar com
   código de erro e exibir uma mensagem indicando que a persistência falhou e o caminho
   de destino que não pôde ser utilizado.

---

### Requirement 5: Construção da tabela canônica

**User Story:** Como pesquisador, quero uma representação tabular padronizada do corpus
em Parquet, para que eu possa utilizá-la diretamente nos experimentos de recuperação de
informação.

#### Acceptance Criteria

1. WHEN o Canonizador é executado sobre o Corpus_Original, THE Canonizador SHALL
   produzir o Corpus_Canonico como um único arquivo Parquet armazenado em
   `data/processed/original/`.
2. THE Corpus_Canonico SHALL conter uma coluna `source_key` com o identificador original
   do documento proveniente da fonte, preservado sem modificação.
3. THE Corpus_Canonico SHALL conter uma coluna `doc_id` com o identificador interno do
   experimento, mantendo relação consistente e biunívoca com `source_key`.
4. THE Corpus_Canonico SHALL conter exatamente uma linha por Registro_Elegivel segundo a
   política de canonização configurada no Config_File, sem omissão ou duplicação de
   registros elegíveis; registros não elegíveis SHALL ser identificados e registrados de
   forma auditável com o motivo de rejeição (por exemplo: identificador ausente,
   identificador duplicado, texto completo vazio, valor de campo obrigatório
   malformado).
5. THE Canonizador SHALL garantir que o total de registros processados é igual à soma de
   registros aceitos e registros rejeitados, de modo que nenhum registro possa
   desaparecer sem rastreio auditável.
6. THE Canonizador SHALL rejeitar qualquer operação de correção silenciosa sobre campos
   obrigatórios para elegibilidade, conforme declarados na política de canonização
   configurada no Config_File: o Canonizador não pode inventar, inferir ou corrigir
   valores ausentes ou malformados nesses campos para tornar um registro elegível; a
   ausência ou malformação de um valor em campo obrigatório deve resultar em rejeição
   auditável do registro, com registro do motivo, sem substituição ou inferência de
   valor; `data/raw/` permanece inalterado e nenhum registro pode desaparecer sem
   rastreabilidade.
7. THE Canonizador SHALL preservar o texto completo do documento, no campo configurado
   como texto completo no Config_File, sem alteração de conteúdo.
8. IF o Corpus_Original estiver vazio (zero documentos), THEN THE Canonizador SHALL
   produzir um arquivo Parquet válido com zero linhas e o schema de colunas definido no
   Config_File, sem encerrar com erro.
9. IF o Corpus_Canonico já existir em `data/processed/original/`, THEN THE Canonizador
   SHALL criar um novo arquivo com sufixo de timestamp no formato `YYYYMMDD_HHMMSS` sem
   sobrescrever o arquivo existente.
10. IF o Canonizador encontrar um campo não obrigatório — conforme a política de
    canonização configurada no Config_File — com valor conflitante, inválido ou
    malformado durante a canonização, THEN THE Canonizador SHALL preservar o valor
    original do campo sem normalização ou correção, registrar o problema indicando o
    identificador do registro e o campo afetado, e continuar o processamento dos demais
    registros sem interromper a execução; o tratamento exato do campo problemático no
    artefato de saída (incluir com valor original, excluir ou marcar como inválido) SHALL
    ser definido pela política de canonização configurada no Config_File; `data/raw/`
    permanece inalterado e nenhum registro pode desaparecer sem rastreabilidade.
11. THE Corpus_Canonico SHALL preservar, para cada Registro_Elegivel, os valores originais
    dos campos declarados em `metadata_fields` no Config_File (campos estruturados
    documentais tais como, conforme a estrutura real do dataset: número do acórdão, ano do
    acórdão, relator, colegiado, data da sessão, número do processo, tipo de processo,
    assunto, entidade, unidade técnica e outros campos estruturados relevantes identificados
    na auditoria); os valores SHALL ser preservados sem modificação, preenchimento ou
    inferência; IF um campo de `metadata_fields` estiver ausente em determinado documento,
    THEN o valor SHALL permanecer nulo no Corpus_Canonico e essa ausência SHALL ser
    considerada na análise de cobertura; a ausência de um campo de `metadata_fields` não
    torna o documento não elegível, salvo se a política de canonização declarar
    explicitamente aquele campo como obrigatório.
12. THE Canonizador SHALL rejeitar qualquer operação que utilize modelo de linguagem,
    sistema de IA ou inferência automática para preencher, completar ou substituir valores
    ausentes ou malformados nos campos de `metadata_fields`; qualquer criação futura de
    metadados semânticos derivados SHALL ocorrer exclusivamente em artefatos separados em
    `data/processed/enriched/`, preservando o `doc_id` do documento original
    correspondente.

---

### Requirement 6: Separação entre conteúdo original e conteúdo enriquecido

**User Story:** Como pesquisador, quero que o Corpus_Original e o Conteudo_Enriquecido
permaneçam em artefatos distintos, para que não haja contaminação da base documental
primária por transformações posteriores.

#### Acceptance Criteria

1. THE Pipeline SHALL armazenar o Corpus_Original exclusivamente em `data/raw/` e o
   Corpus_Canonico exclusivamente em `data/processed/original/`.
2. THE Pipeline SHALL armazenar futuros artefatos de enriquecimento exclusivamente em
   `data/processed/enriched/`, nunca adicionando colunas derivadas de enriquecimento ao
   arquivo Parquet em `data/processed/original/`.
3. THE Pipeline SHALL rejeitar qualquer operação que tente gravar Conteudo_Enriquecido
   no diretório `data/raw/` ou em `data/processed/original/`, retornando um erro que
   indica a violação de isolamento antes de qualquer escrita ser efetivada.
4. WHEN o Canonizador concluir a canonização, THE Canonizador SHALL preservar todos os
   arquivos preexistentes em `data/raw/` sem modificação, adição ou remoção de
   conteúdo.
5. WHEN um artefato de Conteudo_Enriquecido for criado a partir de um documento do
   Corpus_Canonico, THE Pipeline SHALL preservar o mesmo `doc_id` do documento original
   correspondente, sem criar ou atribuir um identificador distinto ao artefato
   enriquecido.

---

### Requirement 7: Exclusão de campos gerados por IA do corpus original

**User Story:** Como pesquisador, quero que nenhum campo gerado por modelos de IA entre
na representação canônica original do corpus, para garantir a validade científica dos
experimentos de recuperação.

#### Acceptance Criteria

1. THE Config_File SHALL declarar uma lista explícita de campos permitidos no corpus
   original (`allowed_fields`); THE Canonizador SHALL incluir no Corpus_Canonico
   exclusivamente os campos presentes nessa lista.
2. WHEN o Canonizador identificar campos do dataset de entrada que não constam em
   `allowed_fields`, THE Canonizador SHALL excluir esses campos da representação
   canônica original e registrá-los como `excluded_fields` de forma associada
   inequivocamente à versão do Corpus_Canonico produzida.
3. THE Canonizador SHALL registrar a lista `excluded_fields` de forma associada e
   versionada à versão do Corpus_Canonico, de modo que a exclusão seja auditável sem
   inspecionar o Config_File; o mecanismo físico de associação (metadados internos do
   Parquet, arquivo sidecar, manifesto do corpus ou outro) é responsabilidade do design.
4. IF o dataset de entrada contiver campos conhecidamente derivados ou gerados por IA
   (por exemplo, `VISAOGERAL` ou equivalente declarado no Config_File), THEN THE
   Canonizador SHALL excluir esses campos da representação em `data/processed/original/`
   sem rejeitar o documento; o restante dos campos elegíveis do documento SHALL
   permanecer no corpus.
5. THE Config_File SHALL incluir os campos obrigatórios `source_identifier`
   (identificador da fonte oficial do TCU), `batch_id` (identificador único do lote) e
   `allowed_fields` (lista de campos elegíveis para o Corpus_Canonico), para
   rastreabilidade de lote e controle de canonização.
6. IF o Canonizador não puder registrar a lista `excluded_fields` de forma associada à
   versão do Corpus_Canonico, THEN THE Canonizador SHALL abortar a criação do arquivo
   Parquet, não gravar nenhum artefato parcial em `data/processed/original/`, e
   registrar uma mensagem de erro indicando que a auditabilidade de campos excluídos não
   pôde ser garantida.

---

### Requirement 8: Testes automatizados

**User Story:** Como desenvolvedor, quero que os módulos críticos do Pipeline possuam
testes automatizados das invariantes essenciais, para garantir corretude e facilitar
manutenção.

#### Acceptance Criteria

1. THE Pipeline SHALL incluir uma suíte de testes automatizados cobrindo o Ingestor, o
   Auditor e o Canonizador, localizada no diretório `tests/`.
2. WHEN o Ingestor tenta incorporar um arquivo cujo `original_filename` já consta no
   Manifest com Hash_SHA256 diferente (Conflito_Por_Nome), THE teste SHALL verificar que
   o arquivo existente em `data/raw/` não é modificado ou sobrescrito, que o novo arquivo
   recebe um `stored_filename` distinto, e que ambas as entradas ficam rastreáveis no
   Manifest.
3. WHEN o Ingestor tenta incorporar um arquivo cujo Hash_SHA256 já consta no Manifest
   (Duplicidade_Por_Conteudo), THE teste SHALL verificar que a operação é abortada antes
   de qualquer cópia para `data/raw/`, que nenhum arquivo é gravado em `data/raw/`
   mesmo que o nome do arquivo seja diferente do existente, e que o aviso registrado
   indica duplicidade por conteúdo.
4. WHEN o Ingestor promove um arquivo da área intermediária para `data/raw/`, THE teste
   SHALL verificar que o Hash_SHA256 do arquivo promovido é idêntico ao Hash_SHA256 do
   arquivo de origem calculado antes da cópia, e que nenhum arquivo é promovido para
   `data/raw/` sem essa confirmação de integridade.
5. WHEN o Ingestor calcula o Hash_SHA256 de um arquivo, THE teste SHALL verificar que o
   valor produzido é idêntico ao produzido pela biblioteca `hashlib` do Python aplicada
   ao conteúdo binário completo do mesmo arquivo.
6. WHEN o Ingestor cria uma entrada no Manifest, THE teste SHALL verificar que todos os
   campos obrigatórios estão presentes; WHEN o Ingestor recebe um arquivo cujo `sha256`
   já consta no Manifest, THE teste SHALL verificar que um aviso de duplicidade por
   conteúdo é emitido e nenhuma cópia é realizada; IF algum campo obrigatório estiver
   ausente, THEN THE teste SHALL verificar que um erro é registrado indicando o campo
   ausente.
7. WHEN o Auditor calcula o percentual de cobertura de uma coluna, THE teste SHALL
   verificar que o valor retornado está no intervalo [0.00, 100.00] para qualquer
   dataset de entrada válido.
8. WHEN o Auditor identifica duplicatas, THE teste SHALL verificar que a contagem
   reportada é N-1 para cada grupo de N registros com identificador idêntico.
9. WHEN o Auditor identifica Documentos_Sem_Texto, THE teste SHALL verificar que
   registros com campo de texto completo nulo, vazio ou composto apenas por espaços em
   branco são todos contabilizados.
10. WHEN o Canonizador produz um arquivo Parquet, THE teste SHALL verificar que as
    colunas `source_key` e `doc_id` estão presentes, são não nulas e mantêm relação
    consistente (sem `doc_id` duplicado associado a `source_key` distinto).
11. WHEN o Canonizador produz um arquivo Parquet, THE teste SHALL verificar que o
    arquivo é legível após a escrita (round-trip: escrita seguida de leitura retorna o
    mesmo número de linhas e os mesmos tipos de coluna).
12. WHEN a suíte de testes encontrar ao menos um teste com falha, THE Pipeline SHALL
    encerrar com código de saída diferente de zero e exibir o identificador e a causa de
    cada teste falho.

---

### Requirement 9: Reprodutibilidade e configuração

**User Story:** Como pesquisador, quero que o Pipeline seja completamente parametrizável
por arquivos de configuração e produza resultados logicamente idênticos para a mesma
entrada, para que qualquer colaborador possa reproduzir o corpus a partir do mesmo
Config_File.

#### Acceptance Criteria

1. THE Pipeline SHALL ler todos os parâmetros de execução (caminhos de diretórios,
   identificador da fonte, campos de metadados obrigatórios, versão do schema do
   Manifest, `allowed_fields`) a partir de um único Config_File localizado no diretório
   `configs/`, cujo nome de arquivo é especificado como argumento obrigatório na
   invocação do Pipeline.
2. THE Config_File SHALL estar em formato YAML ou TOML e ser validado contra um schema
   definido pelo Pipeline antes da execução; se ambos os formatos forem fornecidos, THE
   Pipeline SHALL utilizar o arquivo cujo nome foi passado como argumento.
3. IF o Config_File estiver ausente ou contiver campos que violem o schema de validação,
   THEN THE Pipeline SHALL interromper a execução sem processar nenhum dado e exibir
   uma mensagem de erro indicando o nome exato de cada campo ausente ou inválido.
4. THE Canonizador SHALL calcular um `dataset_fingerprint` determinístico sobre o schema
   e o conteúdo ordenado do Corpus_Canonico, independente de metadados internos do
   formato Parquet (timestamps de escrita, compressão, ordem dos row groups).
5. WHEN o Pipeline é executado com o mesmo Config_File e com um Corpus_Original cujo
   conteúdo é idêntico ao de uma execução anterior, THE Pipeline SHALL produzir um
   Corpus_Canonico com `dataset_fingerprint` idêntico ao dessa execução anterior
   (propriedade de reprodutibilidade determinística), desde que o Pipeline não consuma
   entradas não-determinísticas externas durante o processamento.
6. WHEN o Pipeline é executado, THE Pipeline SHALL registrar o `dataset_fingerprint` do
   Corpus_Canonico produzido em um arquivo de log de reprodutibilidade, de modo que
   execuções futuras possam verificar a propriedade determinística.

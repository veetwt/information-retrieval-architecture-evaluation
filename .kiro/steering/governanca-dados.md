# Governança de dados

Este arquivo define regras permanentes para preservação, rastreabilidade,
versionamento e separação dos dados utilizados no experimento.

## Fonte primária

Dados utilizados como corpus original devem ter origem identificável e
rastreável.

Sempre que possível, utilizar fontes públicas primárias.

Registrar informações suficientes para permitir identificar posteriormente:

- fonte;
- dataset;
- lote ou versão;
- período correspondente;
- data de obtenção;
- integridade do arquivo obtido.

## Ingestão e imutabilidade

`data/raw/` deve conter exclusivamente arquivos cuja integridade tenha sido
validada.

Arquivos recebidos devem passar por uma área temporária, staging ou
mecanismo equivalente antes da incorporação definitiva em `data/raw/`.

A incorporação definitiva em `data/raw/` somente pode ocorrer após a
confirmação de integridade da cópia por SHA-256.

Depois de validamente incorporado em `data/raw/`, um arquivo não pode ser
alterado, corrigido, sobrescrito ou excluído pelo Pipeline.

Scripts posteriores devem tratar `data/raw/` como somente leitura.

Falhas ocorridas antes da validação definitiva devem ser tratadas fora do
corpus bruto validado.

Artefatos temporários que falharem na validação podem ser descartados ou
isolados sem alterar arquivos previamente aceitos em `data/raw/`.

## Integridade

O SHA-256 deve ser calculado sobre o conteúdo binário completo dos arquivos,
sem:

- normalização de encoding;
- alteração de quebras de linha;
- transformação textual;
- limpeza;
- reescrita.

A integridade da cópia deve ser confirmada comparando o SHA-256 do arquivo
de origem com o SHA-256 da cópia antes de sua incorporação definitiva em
`data/raw/`.

## Duplicidade de conteúdo

Mesmo SHA-256 já registrado no Manifest representa duplicidade de conteúdo.

Uma tentativa de ingerir novamente o mesmo conteúdo não deve criar uma nova
cópia no corpus bruto.

A duplicidade de conteúdo deve ser identificada independentemente do nome
do arquivo recebido.

## Conflito de nome e versionamento

Mesmo `original_filename` com SHA-256 diferente não representa duplicidade
de conteúdo.

Essa situação representa conflito de nome ou possível nova versão do
arquivo-fonte.

O arquivo anteriormente incorporado não deve ser sobrescrito ou removido.

A nova versão deve poder receber um `stored_filename` distinto e
rastreável.

O Manifest deve preservar tanto:

- `original_filename`, correspondente ao nome recebido;
- `stored_filename`, correspondente ao nome efetivamente utilizado para
  identificar aquela versão no corpus.

O mecanismo concreto para formação de nomes versionados deverá ser definido
no Design da implementação.

## Manifest de proveniência

O Manifest registra informações referentes ao arquivo-fonte como unidade de
ingestão.

O Manifest não representa os metadados individuais de cada documento
contido no arquivo.

Informações de proveniência podem incluir:

- original_filename;
- stored_filename;
- sha256;
- downloaded_at;
- ingested_at;
- file_size_bytes;
- source_url ou source_identifier;
- dataset;
- dataset_year;
- schema_version;
- batch_id.

`dataset_year` representa o ano ou período atribuído ao dataset/lote.

`dataset_year` não deve ser confundido com:

- o ano corrente;
- `downloaded_at`;
- `ingested_at`;
- o ano individual de um documento.

## Metadados documentais

Metadados como:

- identificador do documento;
- número;
- ano;
- relator;
- colegiado;
- assunto;
- tipo de processo;
- entidade;
- unidade técnica;

ou campos equivalentes pertencem aos registros/documentos da fonte.

Esses campos não devem ser confundidos com os metadados de proveniência do
Manifest.

A existência e a cobertura desses campos devem ser verificadas pela
auditoria do dataset antes da seleção definitiva para o corpus experimental.

Metadados documentais selecionados devem manter rastreabilidade até seus
valores originais.

## Ausência de metadados

Valores ausentes no corpus original não devem ser inventados.

Não utilizar modelos de linguagem para preencher automaticamente metadados
faltantes na camada original.

A ausência de um metadado opcional deve ser preservada e considerada nas
estatísticas de cobertura.

Regras de rejeição de documentos devem depender de uma política de
elegibilidade explícita e versionada.

## Separação entre raw e processed

Arquivos em `data/raw/` representam as fontes validadas e não devem sofrer
transformações.

Transformações necessárias ao experimento devem produzir novos artefatos em
diretórios apropriados de `data/processed/`.

A construção de um artefato processado nunca deve sobrescrever ou alterar a
fonte bruta correspondente.

## Corpus original e corpus enriquecido

Manter separação explícita entre:

`data/processed/original/`

e:

`data/processed/enriched/`.

`data/processed/original/` deve conter apenas informações provenientes da
fonte original e transformações determinísticas documentadas necessárias à
representação canônica.

`data/processed/enriched/` deve conter campos derivados posteriormente,
inclusive campos produzidos por modelos de linguagem ou outros métodos de
enriquecimento semântico.

Nenhum conteúdo enriquecido deve ser gravado em:

- `data/raw/`;
- `data/processed/original/`.

## Campos gerados por IA presentes na própria fonte

Se a fonte distribuída contiver campos previamente gerados ou derivados por
IA, esses campos não devem ser automaticamente incorporados ao baseline
original do experimento.

Campos dessa natureza devem ser identificados e excluídos do corpus original
quando assim definido no protocolo metodológico.

Sua exclusão deve permanecer auditável.

O documento não deve ser rejeitado apenas porque contém um campo excluído,
desde que seus demais campos satisfaçam a política de elegibilidade.

## Identificadores

Preservar o identificador original do documento como `source_key` sempre que
houver identificador adequado na fonte.

Utilizar `doc_id` como identificador interno do experimento.

A relação entre `source_key` e `doc_id` deve ser consistente e rastreável.

Artefatos enriquecidos ou derivados de um documento devem preservar o
`doc_id` correspondente.

Não criar silenciosamente novos identificadores para o mesmo documento em
diferentes condições experimentais.

## Canonização

A canonização deve produzir novos artefatos e nunca alterar os arquivos
brutos.

Nenhum valor ausente, inválido ou conflitante deve ser corrigido,
completado ou inferido silenciosamente.

Correções ou normalizações, quando metodologicamente permitidas, devem ser:

- determinísticas;
- explicitamente definidas;
- rastreáveis;
- aplicadas somente em artefatos derivados.

Registros rejeitados durante a canonização devem permanecer contabilizados
e associados a um motivo de rejeição.

Nenhum registro pode desaparecer silenciosamente.

## Versionamento do corpus

Versões utilizadas nos experimentos devem ser identificáveis.

Alterações em:

- documentos;
- política de elegibilidade;
- campos selecionados;
- transformação canônica;
- conjunto experimental;

devem resultar em versão distinta quando alterarem o conteúdo lógico do
corpus.

Artefatos anteriores não devem ser sobrescritos silenciosamente.

## Reprodutibilidade

Transformações do corpus devem ser executáveis novamente a partir das fontes
brutas e das configurações versionadas.

Sempre que aplicável, registrar:

- configuração utilizada;
- versão do código;
- identificadores do corpus;
- fingerprints;
- timestamps de execução;
- relatórios de erros e rejeições.

## Credenciais e dados sensíveis de infraestrutura

Credenciais de AWS, tokens, chaves privadas, arquivos `.env` ou outros
segredos não devem ser armazenados no Git.

Não inserir credenciais diretamente em código, notebooks, configurações
versionadas ou documentação.

Utilizar mecanismos apropriados de configuração de ambiente quando
integrações externas forem introduzidas.

## Operações externas

Operações de infraestrutura que possam gerar custo, alterar recursos
remotos ou excluir dados não devem ser executadas automaticamente por
agentes sem aprovação explícita.

Antes de aumentar recursos computacionais, investigar o gargalo e registrar
a justificativa técnica quando aplicável.
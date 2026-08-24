# Regras metodológicas

Este arquivo contém princípios metodológicos permanentes do experimento.

As decisões aqui descritas devem orientar todas as Specs relacionadas à
construção do corpus, recuperação, avaliação, enriquecimento e geração.

## Neutralidade experimental

Nenhuma arquitetura deve ser tratada previamente como vencedora.

O experimento não deve ser desenhado para demonstrar que recuperação
estruturada, vetorial, híbrida ou enriquecida é superior.

O objetivo é identificar em quais condições cada abordagem apresenta
vantagens, limitações ou ganhos marginais.

Resultados negativos, ausência de ganho ou equivalência entre arquiteturas
são resultados válidos.

## Separação entre formulação, evidência e mecanismo

Manter separadas três dimensões:

### Formulação da consulta

Exemplos:

- direta;
- parafraseada;
- prolixa;
- ruidosa.

### Características da evidência

Exemplos:

- evidência presente em metadados;
- evidência presente no texto;
- evidência distribuída entre metadados e texto;
- evidência distribuída entre múltiplos documentos.

### Mecanismo de recuperação

Exemplos:

- estruturado;
- vetorial;
- híbrido.

Não assumir relações determinísticas como:

- consulta direta implica recuperação estruturada;
- consulta prolixa implica recuperação vetorial;
- evidência mista implica obrigatoriamente recuperação híbrida.

Essas relações devem ser verificadas empiricamente.

## Baseline original

Os experimentos sobre o corpus original devem utilizar somente informações
provenientes da fonte primária e transformações determinísticas,
documentadas e reproduzíveis necessárias à representação dos dados.

Metadados documentais originais, como relator, colegiado, ano, assunto,
tipo de processo, entidade ou campos equivalentes, devem ser preservados
quando disponíveis e selecionados após auditoria.

Metadados opcionais ausentes devem permanecer ausentes.

Não utilizar modelos de linguagem para preencher, inferir ou completar
valores faltantes no baseline original.

A cobertura dos metadados é uma característica do dataset e deve ser
medida, não artificialmente corrigida antes dos experimentos.

## Metadados e recuperação estruturada

A seleção dos campos utilizados pela recuperação estruturada deve ser
realizada somente após a auditoria do dataset real.

A auditoria deve subsidiar a decisão utilizando informações como:

- existência do campo;
- tipo de dado;
- cobertura;
- quantidade de valores únicos;
- presença de valores ausentes;
- consistência dos valores.

Não estabelecer arbitrariamente que um campo é adequado antes da inspeção
do corpus.

Baixa cobertura de determinado metadado não deve ser automaticamente
corrigida com IA.

Ela pode constituir uma característica relevante para explicar o
desempenho da recuperação estruturada.

## Corpus congelado

Comparações experimentais devem utilizar versões explicitamente
identificadas e congeladas do corpus.

Uma vez iniciado um conjunto de experimentos comparativos, não alterar
silenciosamente:

- documentos;
- metadados;
- política de elegibilidade;
- texto utilizado;
- perguntas;
- referências;
- parâmetros principais.

Mudanças necessárias devem gerar nova versão experimental.

## Perguntas e referência de avaliação

As perguntas de avaliação devem representar necessidades de informação
definidas antes da análise dos resultados finais.

O conjunto de referência, documentos relevantes e evidências deve ser
construído antes da comparação final entre os recuperadores.

Não modificar o gold standard com o objetivo de favorecer um resultado
observado posteriormente.

Quando houver diferentes formulações linguísticas da mesma necessidade de
informação, elas devem compartilhar a mesma intenção e a mesma referência
semântica sempre que metodologicamente aplicável.

## Separação entre desenvolvimento e avaliação

Parâmetros, regras de fusão, thresholds e demais escolhas experimentais não
devem ser ajustados usando continuamente o conjunto destinado à avaliação
final.

Quando aplicável, utilizar separação entre desenvolvimento e teste.

Não realizar tuning deliberado sobre o conjunto final apenas para melhorar
métricas.

## Comparabilidade entre recuperadores

Comparações entre mecanismos de recuperação devem utilizar condições
comparáveis.

Quando forem comparados rankings documentais, utilizar o mesmo número final
de resultados (`top_k`) ou um orçamento final de contexto equivalente,
conforme definido no protocolo experimental.

Um método híbrido pode recuperar internamente um número maior de
candidatos, mas o conjunto final utilizado na comparação deve respeitar a
mesma regra dos demais métodos.

## Recuperação antes de geração

A qualidade da recuperação deve ser avaliada antes da introdução da geração
de respostas por modelos de linguagem.

Não utilizar a qualidade aparente da resposta gerada como substituto das
métricas de recuperação.

A geração, quando introduzida, constitui uma etapa experimental posterior.

## Geração de respostas

Quando houver comparação de geração entre arquiteturas, manter constantes,
na medida do possível:

- modelo gerador;
- prompt;
- temperatura;
- orçamento de contexto;
- demais parâmetros de geração.

A principal variável deve ser a evidência fornecida pelo mecanismo de
recuperação que está sendo avaliado.

## Enriquecimento semântico

Qualquer enriquecimento semântico deve permanecer separado do corpus
original e ser tratado como uma condição experimental distinta.

O enriquecimento não deve alterar o baseline original.

Exemplos de campos derivados futuros podem incluir:

- temas;
- resumos;
- legislação identificada;
- entidades extraídas;
- tipos de irregularidade;
- informações normalizadas sobre decisões.

A escolha efetiva dos campos de enriquecimento deverá ser feita em etapa
posterior e não deve ser presumida durante a construção do corpus original.

Recuperação estruturada, vetorial e híbrida devem partir do mesmo corpus
experimental congelado, salvo quando a comparação envolver explicitamente
uma versão enriquecida.

## Uso de LLM na referência

Um modelo de linguagem pode auxiliar processos de anotação ou revisão, mas
não deve ser a única fonte de verdade para construir respostas de referência
ou evidências do experimento.

As referências devem permanecer rastreáveis aos documentos utilizados.

Sempre que uma evidência textual for necessária, preservar sua relação com
o documento e com o trecho que a sustenta.

## Ganho marginal e complexidade

A adição de componentes não deve ser considerada benéfica apenas por
aumentar a complexidade da arquitetura.

Quando aplicável, avaliar o ganho de uma arquitetura híbrida ou enriquecida
em relação à melhor abordagem isolada comparável.

Qualidade deve ser analisada juntamente com fatores como:

- custo;
- latência;
- complexidade;
- rastreabilidade;
- manutenção.

Um ganho pequeno pode não justificar aumento significativo de custo ou
complexidade.

## Registro de decisões

Decisões metodológicas relevantes devem ser documentadas.

O registro deve permitir identificar:

- contexto;
- alternativas consideradas;
- decisão adotada;
- justificativa;
- impacto esperado no experimento.

Não alterar retrospectivamente decisões metodológicas sem registrar a nova
decisão e sua motivação.
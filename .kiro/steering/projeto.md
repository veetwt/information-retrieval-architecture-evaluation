# Contexto do projeto

Este projeto contém o experimento de um TCC sobre recuperação de informação
em bases documentais institucionais longas e semiestruturadas.

O objeto principal do trabalho não é uma interface de chatbot.

O foco é a avaliação comparativa de diferentes mecanismos e condições de
recuperação de informação.

Serão estudadas configurações:

- estruturadas;
- vetoriais;
- híbridas;
- com dados originais;
- com dados enriquecidos.

O experimento deve priorizar:

- reprodutibilidade;
- rastreabilidade;
- comparabilidade;
- separação entre recuperação e geração;
- preservação dos dados originais;
- registro das configurações experimentais;
- controle de versões do corpus e dos experimentos.

## Organização experimental

A construção do corpus deve ser concluída e validada antes da implementação
das arquiteturas de recuperação.

O Corpus_Canonico em `data/processed/original/` será a fonte comum para os
experimentos posteriores de:

- recuperação estruturada;
- recuperação vetorial;
- recuperação híbrida;
- enriquecimento semântico, quando aplicável.

As arquiteturas de recuperação não devem ser implementadas durante a Spec
de construção do corpus.

O baseline original deverá preservar texto e metadados estruturados
provenientes da fonte, permitindo que todas as arquiteturas sejam avaliadas
sobre a mesma base documental.

As comparações entre arquiteturas deverão utilizar a mesma versão congelada
do corpus experimental, exceto quando a própria condição experimental
avaliada envolver explicitamente a comparação entre dados originais e dados
enriquecidos.

## Separação das etapas

A implementação deve ocorrer de forma incremental.

A ordem geral do projeto é:

1. obtenção e registro das fontes;
2. construção e auditoria do corpus original;
3. canonização dos documentos;
4. definição e congelamento do corpus experimental;
5. construção das perguntas e referências de avaliação;
6. recuperação estruturada;
7. recuperação vetorial;
8. recuperação híbrida;
9. avaliação comparativa;
10. testes de robustez das consultas;
11. enriquecimento semântico, quando aplicável;
12. geração de respostas, quando aplicável;
13. execução final em ambiente de nuvem, quando aplicável.

Etapas posteriores não devem ser antecipadas quando a etapa anterior ainda
não estiver validada.

## Escopo das arquiteturas

Recuperação estruturada, vetorial e híbrida são mecanismos diferentes e
devem ser avaliados separadamente antes de qualquer conclusão sobre sua
combinação.

A existência de uma pergunta formulada em linguagem natural não determina
automaticamente qual mecanismo de recuperação é o mais adequado.

A formulação linguística da consulta, a localização das evidências e o
mecanismo de recuperação são dimensões distintas do experimento.

## Assistência por IA no desenvolvimento

Ferramentas de IA, incluindo o agente do Kiro, podem auxiliar na criação de
código, testes, documentação e revisão técnica.

Decisões metodológicas do experimento não devem ser delegadas
automaticamente a agentes ou modelos de linguagem.

Mudanças relevantes no desenho experimental devem ser revisadas antes de
serem implementadas.

A utilização de IA durante o desenvolvimento deve preservar a
reprodutibilidade e a rastreabilidade do projeto.
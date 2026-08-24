# Padrões Python

Este arquivo define padrões permanentes para o código Python do projeto.

## Versão

Utilizar Python 3.13.7 como versão de referência do ambiente de
desenvolvimento.

Alterações de versão devem ser deliberadas e documentadas.

## Ambiente virtual

Utilizar ambiente virtual local em:

`.venv/`

Dependências do projeto devem ser instaladas no ambiente virtual.

O diretório `.venv/` não deve ser versionado no Git.

## Dependências

Manter as dependências diretas do projeto em:

`requirements.txt`

Quando necessário para reprodução exata do ambiente, gerar:

`requirements-lock.txt`

a partir do ambiente validado.

Não adicionar dependências sem necessidade técnica clara quando a biblioteca
padrão do Python for suficiente.

## Organização do código

Preferir código reutilizável dentro de `src/`.

Scripts em `scripts/` devem atuar principalmente como pontos de entrada para
tarefas executáveis.

Evitar duplicação de lógica entre scripts.

Funções reutilizáveis devem ser movidas para módulos apropriados.

## Caminhos

Não utilizar caminhos absolutos específicos da máquina do desenvolvedor no
código.

Evitar código como:

`C:\Users\usuario\...`

Caminhos devem ser recebidos por:

- configuração;
- argumentos;
- variáveis apropriadas;
- caminhos relativos ao projeto.

Utilizar `pathlib.Path` para manipulação de caminhos sempre que possível.

## Configuração

Parâmetros que podem variar entre execuções não devem ser espalhados como
valores fixos pelo código.

Preferir arquivos de configuração versionados em `configs/` para parâmetros
do experimento.

Configurações devem ser validadas antes do início de operações que escrevam
dados.

Falhas de configuração devem resultar em mensagens claras e impedir
execuções parciais inadequadas.

## Tipagem

Utilizar type hints nas funções e métodos implementados pelo projeto sempre
que razoável.

Exemplo:

```python
from pathlib import Path


def calculate_sha256(file_path: Path) -> str:
    ...
# Casos-Piloto do Experimento — v01 (RASCUNHO)

> **Status:** rascunho para revisão. As respostas de referência abaixo **não** são gold
> definitivo; devem ser revisadas antes de qualquer uso experimental.
>
> **Universo de avaliação (escopo fixo):** todas as consultas são avaliadas sobre os
> **21.631 documentos da Selecao_Experimental**
> (`selection_tcu-acordaos-completo-2024-v1_20260924_212633.parquet`).
> O nome técnico `Selecao_Experimental` **não** aparece no enunciado das consultas; as
> formulações usam linguagem natural como uma pergunta real.
>
> **Campos da baseline textual principal:** `ASSUNTO` e `ACORDAO`. Os campos `SUMARIO`,
> `RELATORIO` e `VOTO` **não** são usados para sustentar fatos da resposta.
>
> **Classificação provisória:** os três grupos (metadados / textual / mista) são rótulos de
> trabalho, **não** categorias científicas congeladas (tipologia de necessidades permanece
> EM ESTUDO na spec `protocolo-experimental`). Nenhum caso é exclusivo de uma arquitetura:
> futuramente **todas** as formulações serão executadas nas três arquiteturas.
>
> **Rótulos de formulação** ("direta", "paráfrase concisa", "mais extensa") permanecem
> **PROVISÓRIOS e EM ESTUDO**.
>
> **Convenção — fatos obrigatórios vs. metadados de apoio:**
> - *Fatos obrigatórios da resposta:* exatamente o que a necessidade solicita; devem estar
>   presentes para a resposta ser considerada correta (rascunho).
> - *Metadados/contexto de apoio:* informações usadas para localizar ou caracterizar os
>   documentos; podem sustentar evidências, mas não precisam aparecer na resposta por não
>   terem sido solicitados.

---

## Caso NI-01 — Respondível por metadados

- **Identificador:** `NI-01`
- **Classificação provisória:** metadados.
- **O que precisamos descobrir:** Quantos acórdãos do Plenário do TCU estão registrados
  para a sessão de 05/03/2024 e quem foi o relator?
- **Justificativa:** a resposta é determinada por combinação de metadados (`COLEGIADO` +
  `DATASESSAO` → contagem; `RELATOR` → nome). O texto dos documentos não é necessário.
  (Rótulo provisório.)
- **Escopo:** 3 documentos com `COLEGIADO = "Plenário"` e `DATASESSAO = "05/03/2024"` na
  seleção experimental.

### Fatos obrigatórios da resposta (rascunho)
*(exatamente o que a necessidade solicita: quantidade + relator)*

1. **Quantidade:** 3 acórdãos do Plenário na sessão de 05/03/2024.
2. **Relator:** AUGUSTO SHERMAN (mesmo relator para os três).

### Metadados de apoio e evidências documentais
*(sustentam a contagem; não precisam aparecer na resposta)*

| doc_id | source_key | COLEGIADO | DATASESSAO | RELATOR | TIPOPROCESSO |
|---|---|---|---|---|---|
| `tcu-4ef6621f2c01` | `ACORDAO-COMPLETO-2547488` | Plenário | 05/03/2024 | AUGUSTO SHERMAN | REPRESENTAÇÃO (REPR) |
| `tcu-7a64efaf2714` | `ACORDAO-COMPLETO-2542047` | Plenário | 05/03/2024 | AUGUSTO SHERMAN | REPRESENTAÇÃO (REPR) |
| `tcu-80e87eb6ab0c` | `ACORDAO-COMPLETO-2571036` | Plenário | 05/03/2024 | AUGUSTO SHERMAN | REPRESENTAÇÃO (REPR) |

`TIPOPROCESSO` é metadado de apoio. `doc_id`/`source_key` são apenas para rastreabilidade.

> **Nota:** os três documentos não possuem cabeçalho com número próprio no campo `ACORDAO`
> (que inicia com "VISTOS, relatados e discutidos…"). Os identificadores disponíveis para
> rastreabilidade são `source_key` e a descrição do `ASSUNTO`; eles não compõem a resposta.

### Formulações
- **Direta:** "Quantos acórdãos do Plenário do TCU foram registrados para a sessão de
  05/03/2024 e quem foi o relator?"
- **Paráfrase concisa:** "Qual é o total de acórdãos do Plenário do TCU da sessão de 5 de
  março de 2024 e quem foi o relator nesses casos?"
- **Mais extensa:** "Considerando as deliberações do Plenário do Tribunal de Contas da
  União, quantos acórdãos foram registrados para a sessão realizada em 05/03/2024 e quem
  atuou como relator?"

> **Verificação de equivalência:** as três formulações pedem os mesmos fatos (quantidade +
> relator), impõem as mesmas restrições (Plenário, 05/03/2024), não entregam a resposta e
> não alteram o caráter dos fatos.

### Ambiguidades / limitações a resolver na revisão
- "Quantidade = 3" e "relator = AUGUSTO SHERMAN" referem-se à seleção experimental
  (21.631 docs), não ao universo completo do TCU.
- A ausência de número próprio no `ACORDAO` dificulta identificação numérica individual;
  decidir na revisão se a necessidade deve ser restrita apenas à contagem+relator (como
  está) ou se deve ser expandida.

---

## Caso NI-02 — Exige consultar ASSUNTO e/ou ACORDAO

- **Identificador:** `NI-02`
- **Classificação provisória:** textual/semântica.
- **O que precisamos descobrir:** Qual acórdão do TCU — indicando número e colegiado —
  tratou da representação a respeito do suposto sumiço de recursos de conta bancária
  ligada a processo da 13ª Vara Federal de Curitiba relacionados à Operação Lava Jato?
- **Justificativa:** a identificação depende do conteúdo textual (`ASSUNTO`/`ACORDAO`);
  não é recuperável só por metadados. (Rótulo provisório.)
- **Escopo:** um único documento na seleção.

### Fatos obrigatórios da resposta (rascunho)
*(exatamente o que a necessidade solicita: número do acórdão + colegiado)*

1. **Número:** Acórdão nº 2639/2024.
2. **Colegiado:** Plenário.

### Contexto/evidência — usado para localizar o caso, não obrigatório na resposta
*(preservado aqui para sustentar o gold; caráter não confirmado mantido)*

- Representação formulada pelo Ministério Público junto ao TCU.
- Objeto: investigar o suposto sumiço/alegado desaparecimento de recursos de conta vinculada
  a processo da 13ª Vara Federal de Curitiba/PR, no âmbito da Operação Lava Jato (montante
  alegado: R$ 2,8 bilhões — caráter não confirmado).

### Metadados de apoio e evidência documental

| doc_id | source_key | COLEGIADO | DATASESSAO | RELATOR | TIPOPROCESSO |
|---|---|---|---|---|---|
| `tcu-b0f98321902a` | `ACORDAO-COMPLETO-2683482` | Plenário | 04/12/2024 | WALTON ALENCAR RODRIGUES | REPRESENTAÇÃO (REPR) |

### Trechos que sustentam os fatos obrigatórios
- **Número e colegiado** — `ACORDAO`: "ACÓRDÃO Nº 2639/2024 - TCU - Plenário".
- **Contexto que leva a esse acórdão** — `ASSUNTO`: "REPRESENTAÇÃO. Investigar suposto
  sumiço de R$ 2,8 bilhões da conta bancária vinculada ao Processo … da 13ª Vara Federal
  de Curitiba … no âmbito da operação Lava Jato."

### Formulações
- **Direta:** "Qual acórdão do TCU — informando o número e o colegiado — tratou da
  representação sobre o suposto sumiço de recursos de conta judicial de Curitiba ligada à
  Operação Lava Jato?"
- **Paráfrase concisa:** "Que acórdão do TCU cuidou da representação sobre o alegado
  desaparecimento de recursos de uma conta judicial de Curitiba relacionada à Lava Jato?
  Indique o número do acórdão e o colegiado."
- **Mais extensa:** "Houve uma representação no Tribunal de Contas da União a respeito do
  suposto sumiço de recursos de uma conta bancária vinculada a um processo da 13ª Vara
  Federal de Curitiba, aberta para destinação de valores recuperados no âmbito da Operação
  Lava Jato. Qual foi o número do acórdão que tratou desse assunto e em qual colegiado foi
  proferido?"

> **Verificação de equivalência:** as três formulações pedem os mesmos fatos (número +
> colegiado), preservam o caráter alegado/não confirmado ("suposto sumiço" / "alegado
> desaparecimento"), não incluem o número do processo judicial, não entregam a resposta e
> não alteram a certeza dos fatos.

### Ambiguidades / limitações a resolver na revisão
- "R$ 2,8 bilhões" é valor alegado/investigado (consta como tal no acórdão); a resposta de
  referência deve preservar esse caráter.
- Decidir na revisão se "número do processo judicial" pode eventualmente entrar nas
  formulações futuras ou deve ser mantido fora.

---

## Caso NI-03 — Combina restrição por metadado e informação textual

> **Nota de substituição:** o documento `tcu-5f8f9beba8d0` (aposentadoria, Ministério da
> Saúde) foi descartado porque nenhuma combinação dos cinco metadados disponíveis o isola
> unicamente (mínimo encontrado = 6 documentos), e os 6 candidatos não sustentam a mesma
> resposta (fundamentos constitucionais distintos), sem que haja característica textual
> semanticamente relevante que diferencie o caso-alvo sem revelar a resposta. O caso foi
> substituído por `tcu-034103ccb211`, que é unicamente delimitado por `TIPOPROCESSO +
> ENTIDADE + RELATOR` (1 documento verificado).

- **Identificador:** `NI-03`
- **Classificação provisória:** mista.
- **O que precisamos descobrir:** Em uma representação relativa ao Instituto Federal de
  Educação, Ciência e Tecnologia de São Paulo (IFSP) e ao relator Benjamin Zymler, qual foi
  a decisão do Plenário do TCU quanto à procedência da representação e ao pedido de medida
  cautelar?
- **Justificativa:** os metadados (`TIPOPROCESSO + ENTIDADE + RELATOR`) delimitam
  univocamente o documento; a resposta sobre procedência e medida cautelar exige leitura de
  `ACORDAO`. (Rótulo provisório.)
- **Escopo e unicidade verificada:**

  | Combinação de metadados | Documentos na seleção |
  |---|---|
  | TIPOPROCESSO | 1.414 |
  | ENTIDADE | 23 |
  | RELATOR | 2.073 |
  | TIPOPROCESSO + ENTIDADE | 5 |
  | TIPOPROCESSO + RELATOR | 144 |
  | ENTIDADE + RELATOR | 3 |
  | **TIPOPROCESSO + ENTIDADE + RELATOR** | **1** ← menor combinação testada que isola o documento |

  > Nenhum campo isolado nem nenhum par retorna 1 documento.
  > `TIPOPROCESSO + ENTIDADE + RELATOR` é a menor combinação de metadados testada capaz
  > de isolar unicamente `tcu-034103ccb211` na seleção. Esta verificação vale apenas para
  > o caso-piloto NI-03; não é uma decisão geral sobre a arquitetura estruturada.

### Fatos obrigatórios da resposta (rascunho)
*(exatamente o que a necessidade solicita: decisão sobre procedência + pedido de cautelar)*

1. A representação foi considerada **parcialmente procedente**.
2. O pedido de **medida cautelar** foi **indeferido**.
3. O processo foi **arquivado**.

### Metadados de apoio e evidência documental

| doc_id | source_key | COLEGIADO | DATASESSAO | RELATOR | TIPOPROCESSO | ENTIDADE |
|---|---|---|---|---|---|---|
| `tcu-034103ccb211` | `ACORDAO-COMPLETO-2647128` | Plenário | 06/03/2024 | BENJAMIN ZYMLER | REPRESENTAÇÃO (REPR) | Instituto Federal de Educação, Ciência e Tecnologia de São Paulo. |

### Trechos que sustentam os fatos obrigatórios
- **Contexto que delimita o caso** — `ASSUNTO`: "REPRESENTAÇÃO. Representação referente à
  licitação com número 422023, modalidade Pregão e Uasg 158154. Objeto: Contratação de
  empresa para a prestação de serviços especializados, de caráter continuado, para atender
  os estudantes com necessidades educacionais específicas (NEE)…"
- **Fatos 1–3** — `ACORDAO` (Acórdão nº 333/2024 - TCU - Plenário): "… ACORDAM, por
  unanimidade … em conhecer da representação, considerá-la **parcialmente procedente**,
  **indeferindo o pedido de medida cautelar**, com o **arquivamento** do processo…"

### Formulações
- **Direta:** "Em uma representação relativa ao IFSP sob relatoria de Benjamin Zymler, qual
  foi a decisão do Plenário do TCU quanto à procedência da representação e ao pedido de
  medida cautelar?"
- **Paráfrase concisa:** "Como o Plenário do TCU decidiu sobre a representação referente ao
  IFSP com relator Benjamin Zymler — ela foi considerada procedente? O pedido de cautelar
  foi atendido?"
- **Mais extensa:** "Considerando a representação sobre um pregão do Instituto Federal de
  Educação, Ciência e Tecnologia de São Paulo examinada pelo Plenário do Tribunal de Contas
  da União sob relatoria de Benjamin Zymler, qual foi a deliberação do Tribunal quanto à
  procedência da representação e qual foi a decisão sobre o pedido de medida cautelar
  formulado?"

> **Verificação de equivalência:** as três formulações pedem os mesmos fatos (procedência +
> decisão sobre cautelar), impõem as mesmas restrições (IFSP, Zymler), não entregam a
> resposta, não alteram a certeza dos fatos e não revelam o resultado da deliberação no
> enunciado.

### Ambiguidades / limitações a resolver na revisão
- "IFSP" é a sigla; verificar se o campo `ENTIDADE` precisa ser citado por extenso nas
  formulações ou se a sigla é suficiente para recuperação.
- A formulação atual não inclui a data da sessão (06/03/2024); a unicidade já é garantida
  por TIPO+ENTIDADE+RELATOR sem precisar da data — mantida assim para deixar as consultas
  mais naturais.

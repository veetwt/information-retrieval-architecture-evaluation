# Caderno de Avaliação Humana — julgamento de relevância

Run oficial: `oficial_recuperacao_altb_2026`

Este caderno apresenta os documentos selecionados para julgamento humano de relevância, organizados por necessidade e em lotes de ~5 documentos. **Nenhum rótulo foi atribuído.**

O caderno é CEGO por desenho: não indica qual arquitetura recuperou cada documento, nem posição de ranking, pontuação ou origem de inclusão. Avalie cada documento apenas pelo seu conteúdo frente aos critérios da necessidade.

Para cada documento, marque **relevante / não relevante / incerto** e registre a evidência. Consolide as decisões em `registro_julgamento.csv`.

## Critérios de relevância por necessidade

**Necessidade (NI-001, natureza: metadata):**

Em uma denúncia relativa à Administração Regional do Sesc no Mato Grosso do Sul (Sesc/MS), qual foi o colegiado do TCU que a apreciou e quem foi o relator?

- **Cardinalidade esperada:** single
- **Condições obrigatórias:**
  - (metadata) Tipo de processo é Denúncia (DEN).
  - (metadata) Entidade é a Administração Regional do Sesc no Estado do Mato Grosso do Sul (Sesc/MS).
- **Evidência textual exigida:**
  - O documento é o acórdão que apreciou a denúncia (TIPOPROCESSO = DEN) referente à Administração Regional do Sesc no Estado do Mato Grosso do Sul (Sesc/MS), e não um acórdão que apenas cita o Sesc/MS ou que apreciou outra denúncia de entidade distinta.
- **Fatos solicitados:** Colegiado do TCU que apreciou a denúncia.; Relator da denúncia.

---

**Necessidade (NI-002, natureza: textual):**

Qual acórdão do TCU — indicando o número e o colegiado — tratou de denúncia sobre possíveis irregularidades na aplicação de recursos federais da educação no Estado de Pernambuco que abordasse, conjuntamente, a alegada falta de merenda nas escolas e a manutenção de contratos temporários de professores?

- **Cardinalidade esperada:** single
- **Condições obrigatórias:**
  - (textual) O conteúdo do documento trata de denúncia sobre POSSÍVEIS irregularidades na aplicação de recursos federais da educação no Estado de Pernambuco e aborda, de forma CONJUNTA (ambos os subtemas no mesmo caso documental): (1) a alegada falta de merenda nas escolas; e (2) a contratação ou manutenção de contratos temporários de professores. Documento que trate de apenas um dos subtemas NÃO é pertinente. Evidência no ASSUNTO e/ou ACORDAO.
- **Evidência textual exigida:**
  - O conteúdo trata de denúncia sobre possíveis irregularidades na aplicação de recursos federais da educação no Estado de Pernambuco.
  - O mesmo caso aborda, de forma CONJUNTA, os dois subtemas: (1) a alegada falta de merenda nas escolas; e (2) a contratação ou a manutenção de contratos temporários de professores. A presença de apenas um dos subtemas não caracteriza relevância.
- **Fatos solicitados:** Número do acórdão.; Colegiado do TCU.

---

**Necessidade (NI-003, natureza: mixed):**

Quais representações relativas à Agência Nacional de Transportes Terrestres (ANTT) trataram de reajuste, aumento ou incremento de tarifa de pedágio em concessões rodoviárias, e qual foi a deliberação do TCU em cada caso?

- **Cardinalidade esperada:** multidocument
- **Condições obrigatórias:**
  - (metadata) Entidade envolvida é a Agência Nacional de Transportes Terrestres (ANTT).
  - (metadata) Tipo de processo é Representação (REPR).
  - (textual) O conteúdo trata de reajuste, aumento ou incremento de tarifa de pedágio em concessão rodoviária. Menções à Tarifa Básica de Pedágio (TBP) são elegíveis quando correspondem a esse tema. Reequilíbrio econômico-financeiro ou revisão contratual só são pertinentes quando houver relação documental EXPLÍCITA com reajuste/aumento de tarifa de pedágio; não incluir automaticamente qualquer documento sobre reequilíbrio econômico-financeiro. Evidência no ASSUNTO e/ou ACORDAO.
- **Evidência textual exigida:**
  - O conteúdo trata de reajuste, aumento ou incremento de tarifa de pedágio em concessão rodoviária. Menções à Tarifa Básica de Pedágio (TBP) são elegíveis quando correspondem a esse tema.
  - Reequilíbrio econômico-financeiro ou revisão contratual só constituem evidência quando houver relação documental EXPLÍCITA com reajuste/aumento de tarifa de pedágio; não basta o documento tratar genericamente de reequilíbrio econômico-financeiro.
- **Regra de relevância por documento (multidocumental):**
  - Um documento é relevante (integra o conjunto-resposta) se, e somente se, satisfizer AS DUAS condições estruturais (ENTIDADE = ANTT e TIPOPROCESSO = Representação) E contiver evidência textual de que a representação trata de reajuste, aumento ou incremento de tarifa de pedágio em concessão rodoviária (incluindo TBP quando corresponder a esse tema). Cada documento relevante contribui com uma parte da resposta — a identificação daquela representação e a deliberação do TCU no caso —, não se exigindo que um único documento contenha todas as representações. Acórdãos recursais — incluindo pedidos de reexame e embargos de declaração — PODEM ser documentos relevantes quando satisfizerem as condições estruturais da ficha (ENTIDADE = ANTT e TIPOPROCESSO = Representação) e discutirem efetivamente o tema de reajuste, aumento ou incremento de tarifa de pedágio; essa inclusão NÃO é automática: é necessário comprovar a pertinência documental do recurso ou embargo ao objeto investigado. A unidade de julgamento da recuperação permanece o doc_id: cada acórdão é julgado individualmente. Acórdãos diferentes associados à mesma representação podem constituir, cada um, evidência documental relevante, mas a representação (o processo) NÃO deve ser contabilizada repetidamente na enumeração da resposta final. NÃO são relevantes, ainda que citem a ANTT ou pedágio: representações sobre outros temas da ANTT; documentos que tratam apenas de reequilíbrio econômico-financeiro sem vínculo explícito com reajuste de tarifa de pedágio; e documentos que apenas mencionam tarifa de pedágio de passagem, incidentalmente, sem que esse seja o objeto da representação.
- **Fatos solicitados:** Conjunto das representações da ANTT sobre tarifa de pedágio (identificação de cada uma).; Deliberação do TCU em cada representação identificada.

---

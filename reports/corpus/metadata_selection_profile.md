# Auditoria de Metadados — Selecao_Experimental

> Auditoria exploratória **somente leitura** dos campos de metadados da seleção experimental. Nenhum registro foi alterado, inferido ou excluído. A normalização aplicada é **apenas diagnóstica** e não é persistida no corpus nem adotada como estratégia experimental.

## Proveniência e reprodutibilidade

- **Arquivo de origem:** `selection_tcu-acordaos-completo-2024-v1_20260924_212633.parquet`
- **Documentos analisados:** 21631
- **Timestamp (UTC):** 2026-10-22T23:13:10Z
- **Versão do MetadataProfiler:** 1.0.0
- **config_version (manifesto):** 1.0
- **eligibility_policy_version (manifesto):** 1.0
- **selection_fingerprint (recalculado):** `ec125709322854d164e8f4aeaffb0351ef92e0adfede4d92b17b955b5ea1bc5c`
- **selection_fingerprint (manifesto):** `ec125709322854d164e8f4aeaffb0351ef92e0adfede4d92b17b955b5ea1bc5c`
- **Fingerprint confere com o manifesto:** **SIM**

## Critérios de contagem e transformações diagnósticas

- **Nulo:** valor ausente no Parquet (None/NaN/pd.NA).
- **Vazio/só-espaços:** valor não nulo que, após `strip()`, fica vazio.
- **Ausente (cobertura):** nulo **ou** vazio/só-espaços. Cobertura = presentes / total × 100, em [0,00; 100,00].
- **Distintos (brutos):** valores únicos sobre o texto **original** dos presentes, **sem nenhum strip** — variações de espaço nas bordas, caixa e ponto final contam como valores distintos.
- **Distintos (normalizados):** após normalização diagnóstica — `strip` + colapso de espaços internos + remoção de ponto final + `casefold`. Serve só para medir inconsistência de formatação.
- **Multivalorado:** valor que contém o separador `;` (vários itens numa mesma célula).
- **Valor raro (outlier):** valor cuja frequência é ≤ 1; sinalizado para inspeção, sem qualquer alteração.

## Tabela consolidada dos campos

| Campo | Tipo | Nulos | Vazios/ws | Ausentes | Cobertura % | Distintos (brutos) | Distintos (norm.) | Multivalor (`;`) | Espaço ini/fim |
|---|---|---|---|---|---|---|---|---|---|
| COLEGIADO | str | 0 | 0 | 0 (0.00%) | 100.00 | 3 | 3 | 0 | 0 |
| RELATOR | str | 0 | 0 | 0 (0.00%) | 100.00 | 12 | 12 | 0 | 0 |
| TIPOPROCESSO | str | 4 | 0 | 4 (0.02%) | 99.98 | 33 | 33 | 0 | 0 |
| DATASESSAO | str | 0 | 0 | 0 (0.00%) | 100.00 | 89 | 89 | 0 | 0 |
| ENTIDADE | str | 90 | 0 | 90 (0.42%) | 99.58 | 4324 | 3904 | 641 | 21540 |
| UNIDADETECNICA | str | 22 | 0 | 22 (0.10%) | 99.90 | 213 | 160 | 1166 | 21609 |

## Detalhe por campo

### COLEGIADO

- Tipo armazenado: `str`
- Nulos: 0 | Vazios/só-espaços: 0 | Ausentes (total): 0 (0.00%)
- Cobertura: 100.00%
- Distintos (brutos): 3 | Distintos (normalizados): 3
- Valores com ponto final: 0 | Valores com espaço inicial/final: 0 | Valores multivalorados (`;`): 0

Valores mais frequentes:

| Frequência | Valor |
|---|---|
| 10519 | Primeira Câmara |
| 8459 | Segunda Câmara |
| 2653 | Plenário |

### RELATOR

- Tipo armazenado: `str`
- Nulos: 0 | Vazios/só-espaços: 0 | Ausentes (total): 0 (0.00%)
- Cobertura: 100.00%
- Distintos (brutos): 12 | Distintos (normalizados): 12
- Valores com ponto final: 0 | Valores com espaço inicial/final: 0 | Valores multivalorados (`;`): 0

Valores mais frequentes:

| Frequência | Valor |
|---|---|
| 2291 | WALTON ALENCAR RODRIGUES |
| 2154 | JHONATAN DE JESUS |
| 2142 | VITAL DO RÊGO |
| 2073 | BENJAMIN ZYMLER |
| 2029 | AROLDO CEDRAZ |
| 1996 | JORGE OLIVEIRA |
| 1980 | AUGUSTO NARDES |
| 1798 | ANTONIO ANASTASIA |
| 1762 | AUGUSTO SHERMAN |
| 1734 | WEDER DE OLIVEIRA |
| 1671 | MARCOS BEMQUERER |
| 1 | BRUNO DANTAS |

Valores raros (frequência ≤ 1): **1** no total — sinalizados para inspeção, **sem qualquer alteração**.

- `BRUNO DANTAS` → 1

### TIPOPROCESSO

- Tipo armazenado: `str`
- Nulos: 4 | Vazios/só-espaços: 0 | Ausentes (total): 4 (0.02%)
- Cobertura: 99.98%
- Distintos (brutos): 33 | Distintos (normalizados): 33
- Valores com ponto final: 0 | Valores com espaço inicial/final: 0 | Valores multivalorados (`;`): 0

Valores mais frequentes:

| Frequência | Valor |
|---|---|
| 8435 | APOSENTADORIA (APOS) |
| 4125 | TOMADA DE CONTAS ESPECIAL (TCE) |
| 3400 | PENSÃO CIVIL (PCIV) |
| 2086 | PENSÃO MILITAR (PMIL) |
| 1414 | REPRESENTAÇÃO (REPR) |
| 471 | ATOS DE ADMISSÃO (ADS) |
| 336 | MONITORAMENTO (MON) |
| 319 | DENÚNCIA (DEN) |
| 212 | RELATÓRIO DE AUDITORIA (RA) |
| 178 | REFORMA (REFO) |
| 122 | PRESTAÇÃO DE CONTAS (PC) |
| 94 | SOLICITAÇÃO DO CONGRESSO NACIONAL (SCN) |
| 72 | ACOMPANHAMENTO (ACOM) |
| 64 | RELATÓRIO DE ACOMPANHAMENTO (RACOM) |
| 63 | ADMINISTRATIVO (ADM) |
| … | (33 valores distintos no total) |

Valores raros (frequência ≤ 1): **3** no total — sinalizados para inspeção, **sem qualquer alteração**.

- `AÇÕES JUDICIAIS_SOLICITAÇÃO DE SUBSÍDIOS (AJSOL)` → 1
- `CONTAS DO PRESIDENTE DA REPÚBLICA (CGOV)` → 1
- `PRESTAÇÃO DE CONTAS SIMPLIFICADA (PCSP)` → 1

### DATASESSAO

- Tipo armazenado: `str`
- Nulos: 0 | Vazios/só-espaços: 0 | Ausentes (total): 0 (0.00%)
- Cobertura: 100.00%
- Distintos (brutos): 89 | Distintos (normalizados): 89
- Valores com ponto final: 0 | Valores com espaço inicial/final: 0 | Valores multivalorados (`;`): 0

Valores mais frequentes:

| Frequência | Valor |
|---|---|
| 969 | 23/01/2024 |
| 957 | 09/07/2024 |
| 752 | 06/08/2024 |
| 751 | 02/07/2024 |
| 615 | 18/06/2024 |
| 606 | 02/04/2024 |
| 550 | 20/08/2024 |
| 549 | 16/07/2024 |
| 531 | 08/10/2024 |
| 514 | 13/08/2024 |
| 500 | 23/07/2024 |
| 493 | 26/11/2024 |
| 491 | 16/04/2024 |
| 484 | 27/02/2024 |
| 480 | 06/02/2024 |
| … | (89 valores distintos no total) |

### ENTIDADE

- Tipo armazenado: `str`
- Nulos: 90 | Vazios/só-espaços: 0 | Ausentes (total): 90 (0.42%)
- Cobertura: 99.58%
- Distintos (brutos): 4324 | Distintos (normalizados): 3904
- Valores com ponto final: 20664 | Valores com espaço inicial/final: 21540 | Valores multivalorados (`;`): 641

Valores mais frequentes:

| Frequência | Valor |
|---|---|
| 1259 |  Ministério da Saúde. |
| 845 |  Diretoria de Inativos e Pensionistas - Comando do Exército. |
| 707 |  Serviço de Inativos e Pensionistas da Marinha. |
| 570 |  Instituto Nacional do Seguro Social. |
| 486 |  Departamento de Centralização de Serviços de Inativos e Pensionistas. |
| 470 |  Fundação Instituto Brasileiro de Geografia e Estatística. |
| 426 |  Ministério da Economia (extinto). |
| 413 |  Comando da Aeronáutica. |
| 318 |  Caixa Econômica Federal. |
| 294 |  Fundação Nacional de Saúde. |
| 267 |  Comando da Marinha. |
| 265 |  Departamento de Polícia Federal. |
| 231 |  Ministério da Agricultura, Pecuária e Abastecimento (extinto). |
| 216 |  Instituto Nacional de Colonização e Reforma Agrária. |
| 205 |  Comando do Exército. |
| … | (4324 valores distintos no total) |

Valores raros (frequência ≤ 1): **3265** no total — sinalizados para inspeção, **sem qualquer alteração**.
Exibindo os primeiros 20 (de 3265):

- ` Serpro - Regional Brasília.` → 1
- ` Grupamento de Apoio Logístico da Aeronáutica.` → 1
- ` Contas do Governo - Presidência da República.` → 1
- ` Autoridade Portuária de Santos S/A.` → 1
- ` Prefeitura Municipal de São João da Baliza - RR.` → 1
- ` Conselho Federal de Engenharia e Agronomia (Confea); e Agência Nacional de Águas e Saneamento Básic…` → 1
- ` Prefeitura Municipal de Aracati - CE.` → 1
- ` Secretaria de Empreendedorismo e Inovação do Ministério da Ciência, Tecnologia e Inovações (Sempi/M…` → 1
- ` São Paulo Urbanismo - SP-Urbanismo.` → 1
- ` Município de Guarujá (SP).` → 1
- ` Procuradoria da República no Estado do Paraná - MPF.` → 1
- ` Secretaria de Estado de Licitação e Contratação do Estado de Roraima (SELC)` → 1
- ` Ministérios da Defesa; da Educação; da Integração e do Desenvolvimento Regional; da Saúde; das Cida…` → 1
- ` Ministério do Turismo (05.457.283/0001-19)` → 1
- ` Departamento Nacional de Infraestrutura de Transportes (Dnit) e Secretaria de Infraestrutura do est…` → 1
- ` Grupamento de Apoio de Canoas.` → 1
- ` Serviço de Apoio às Micro e Pequenas Empresas do Rio de Janeiro (Sebrae/RJ).` → 1
- ` Departamento de Logística eam Saúde.` → 1
- ` Ministério do Trabalho e Emprego (MTE)` → 1
- ` Município de Bom Despacho-MG.` → 1

### UNIDADETECNICA

- Tipo armazenado: `str`
- Nulos: 22 | Vazios/só-espaços: 0 | Ausentes (total): 22 (0.10%)
- Cobertura: 99.90%
- Distintos (brutos): 213 | Distintos (normalizados): 160
- Valores com ponto final: 20729 | Valores com espaço inicial/final: 21609 | Valores multivalorados (`;`): 1166

Valores mais frequentes:

| Frequência | Valor |
|---|---|
| 13149 |  Unidade de Auditoria Especializada em Pessoal (AudPessoal). |
| 2866 |  Unidade de Auditoria Especializada em Tomada de Contas Especial (AudTCE). |
| 890 |  Unidade de Auditoria Especializada em Contratações (AudContratações). |
| 508 |  Unidade de Auditoria Especializada em Recursos (AudRecursos); Unidade de Auditoria Especializada em… |
| 434 |  Unidade de Auditoria Especializada em Recursos (AudRecursos). |
| 340 |  Unidade de Auditoria Especializada em Recursos (AudRecursos); Unidade de Auditoria Especializada em… |
| 275 |  não atuou. |
| 225 |  Unidade de Auditoria Especializada em Recursos (AudRecursos) |
| 204 |  AudPessoal. |
| 182 |  Unidade de Auditoria Especializada em Educação, Cultura, Esporte e Direitos Humanos (AudEducação). |
| 163 |  Unidade de Auditoria Especializada em Tomada de Contas Especial (AudTCE) |
| 161 |  Unidade de Auditoria Especializada em Governança e Inovação (AudGovernanca). |
| 149 |  Unidade de Auditoria Especializada em Saúde (AudSaúde). |
| 143 |  Unidade de Auditoria Especializada em Agricultura, Meio Ambiente e Desenvolvimento Econômico (AudAg… |
| 141 |  Unidade de Auditoria Especializada em Infraestrutura Rodoviária e de Aviação Civil (AudRodoviaAviaç… |
| … | (213 valores distintos no total) |

Valores raros (frequência ≤ 1): **98** no total — sinalizados para inspeção, **sem qualquer alteração**.
Exibindo os primeiros 20 (de 98):

- ` Unidade de Auditoria Especializada em Orçamento, Tributação e Gestão Fiscal (AudFiscal); Unidade de…` → 1
- ` Unidade de Auditoria Especializada em Educação, Cultura, Esporte e Direitos Humanos (AudEducação) e…` → 1
- ` Unidade de Auditoria Especializada em Previdência, Assistência e Trabalho - AudBenefícios.` → 1
- ` Consultoria Jurídica (Conjur) e Unidade de Auditoria Especializada em Pessoal (AudPessoal).` → 1
- ` Auditoria Especializada em Tecnologia da Informação (AudTI).` → 1
- ` Unidade Especializada em Tomada de Contas Especial - AudTCE.` → 1
- ` Secretaria de Controle Externo de Solução Consensual e Prevenção de Conflitos (SecexConsenso) e Uni…` → 1
- ` AudBancos.` → 1
- ` Secretaria de Recursos (extinta).` → 1
- ` Unidade de Auditoria Especializada em Transferências de Recursos da União (AudTransferências).` → 1
- ` Unidade de Auditoria Especializada em Bancos Públicos e Reguladores Financeiros (AudBancos); Unidad…` → 1
- ` SecexInfra e SecexEnergia` → 1
- ` Unidade de Auditoria Especializada em Petróleo, Gás Natural e Mineração - AudPetróleo.` → 1
- ` Unidade Especializada em Previdência, Assistência e Trabalho (AudBenefícios). ` → 1
- ` Secretaria de Apoio a Gestão de Processos (Seproc).` → 1
- ` Unidade de Auditoria Especializada em Tomada de Contas Especial - AudTCE).` → 1
- ` AudContratações ` → 1
- ` Unidade de Auditoria Especializada em Infraestrutura Rodoviária e de Aviação Civil (AudRodoviaAviaç…` → 1
- ` Secex-TCE.` → 1
- ` Gabinete do Ministro Corregedor` → 1

---

_Relatório gerado por `MetadataProfiler`. Diagnóstico exploratório; não define, por si, quais campos ou normalizações serão usados nas arquiteturas de recuperação._

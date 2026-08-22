# IBGE Mercado — Onda 1

**Data de corte:** 12/08/2026. **Extração:** API de Agregados/SIDRA direta; URLs e SHA-256 estão no manifesto bruto.

## Fontes, períodos e unidades

| Uso | SIDRA | variável | período | unidade original |
|---|---:|---:|---:|---|
| RDPC municipal e UF | 10295 | 13431 | Censo 2022 | R$/morador/mês, nominal |
| atualização UF | 7395 | 4196 | PNAD Contínua anual 2025 | R$/morador/mês, real a preços médios de 2025 |
| população corrente | 6579 | 9324 | estimativa 2025 | pessoas |
| estrutura 18–64 | 9514 | 93 | Censo 2022 | pessoas |
| PIB municipal | 5938 | 37 | 2021–2023 | mil R$, correntes |
| deflator nacional | 6784 | 9811 | 2021–2023 | variação anual, % |

A PNAD anual de 2025 é a observação mais recente disponível no SIDRA na data de corte (modificação registrada pelo IBGE em 02/07/2026). Ela evita misturar trimestre móvel com a distribuição censitária anual. A tabela 10295 usa exatamente os mesmos filtros para município e UF: sexo, cor/raça e idade totais. Assim, numerador e referência estadual têm conceito consistente.

## Tratamentos e fórmulas

`RDPC_est = RDPC_Censo_m / RDPC_Censo_UF × RDPC_PNAD_UF_2025`; `MassaRenda = RDPC_est × população estimada 2025`. MassaRenda está em reais por mês. É uma estimativa, não observação municipal de 2025, e ainda não recebe ponderação por tempo de viagem.

Para MER-DIAG-02, somam-se no Censo as idades simples 18 e 19 e os grupos quinquenais 20–24 até 60–64. A participação municipal de 2022 é aplicada à estimativa populacional total de 2025. O resultado permanece decimal e chama-se **estimado**, pois o IBGE não publica estimativa municipal anual por idade. Não se modelou envelhecimento nem se inventou precisão anual.

MER-DIAG-03 respeita `100 × (PIB_2023/deflator_2023)/(PIB_2021/deflator_2021) - 100`. O índice é encadeado com as variações anuais do deflator implícito do PIB nacional (100 em 2021; 108,6 em 2022; 114,2472 em 2023). A janela contém os três anos municipais comparáveis mais recentes disponíveis.

## QA e cobertura

* Renda/população: 5.571 códigos em 2025; 5.570 massas completas. `5101837` (Boa Esperança do Norte/MT), instalado depois do Censo 2022, não tem RDPC municipal censitário e permanece explicitamente ausente — não foi imputado silenciosamente.
* População 18–64: 1.191/1.191 municípios de PR, SC e RS.
* PIB real: 1.191/1.191 municípios do SIT, sem denominador nulo.
* Códigos são texto de sete dígitos; chaves repetidas, valores monetários/populacionais negativos e perdas no universo Sul são bloqueáveis pelos testes e relatório `qa.json`.
* `qa.json` registra faixas e inspeção de São Paulo, Rio de Janeiro, Curitiba, Florianópolis, Porto Alegre e pequenos municípios de cada UF do Sul.

A soma de RDPC municipal não é um teste válido. A consistência por UF é conceitual (mesma tabela/variável/filtros) e a atualização PNAD é aplicada uma única vez por código UF. Uma futura reconciliação ponderada exigiria também o universo de moradores elegíveis da tabela 10295.

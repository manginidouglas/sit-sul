# ANEEL — DEC/FEC municipal, ano completo de 2025

## Fontes oficiais e recorte

- **Indicadores Coletivos de Continuidade (DEC e FEC)**, recurso bulk oficial
  `indicadores-continuidade-coletivos-2020-2029.zip`, consultado diretamente no
  Portal de Dados Abertos da ANEEL. Snapshot obtido em 12/08/2026: 71.132.869
  bytes, SHA-256 `597bf06384edd12bcf4044c1c4555ff1a8b975a39be25041ca019d6b95d4c8f4`.
- **IndQual Município**, chave oficial entre conjunto elétrico e município.
  Snapshot gerado pela fonte em 05/08/2026 e obtido em 12/08/2026: 2.182.847
  bytes, SHA-256 `ca21e65595eff64077967a4e53aebe4c980ba319e4a314eec837b8807d8596ba`.
- Licença declarada no catálogo ANEEL: Open Data Commons ODbL. URLs e metadados
  são constantes do coletor; o manifesto auditável é criado junto ao raw.

Foram selecionados exclusivamente `DEC` e `FEC`, `AnoIndice=2025`. O valor anual
é a soma dos doze períodos mensais; pares conjunto–indicador sem os doze meses
não são publicados. O universo canônico contém 1.191 municípios e a saída longa
contém 2.382 linhas. Ausência permanece ausência, sem imputação.

## Territorialização e tentativas de pesos

1. Um único conjunto ativo relacionado: valor anual direto (**nível 1**).
2. O IndQual Município não informa UCs na célula município × conjunto; portanto
   não houve célula com peso real utilizável (**nível 2**).
3. Foram avaliados os caminhos oficiais previstos. `NumCon` da própria base de
   continuidade dá margem por conjunto, mas não a margem municipal. INDGER não
   publica matriz município × conjunto; SAMP 2025 publica mercado por agente,
   classe e modalidade, sem código municipal; e o recurso nacional BDGD disponível
   no catálogo não oferece snapshot temporal de 2025 consolidado adequado a esta
   execução. Sem as duas margens contemporâneas, executar IPF inventaria uma
   margem municipal e foi corretamente recusado. A implementação de IPF registra
   margens incompatíveis e não converge silenciosamente (**nível 3: zero**).
4. Para relações múltiplas remanescentes aplicou-se a média simples explícita
   aprovada apenas para o MVP, sempre marcada
   `territorializacao_aproximada=true` (**nível 4**).

A relação IndQual não traz vigência da aresta. Para evitar misturar conjuntos
históricos, uma aresta só foi considerada ativa quando o conjunto possuía DEC/FEC
completo em 2025. Esta limitação e todo nível 4 permanecem visíveis na saída.

## Auditoria de cobertura

| classificação | municípios |
|---|---:|
| nível 1 | 241 |
| nível 2 | 0 |
| nível 3 | 0 |
| nível 4 | 945 |
| sem resultado | 5 |

`sem resultado` significa que pelo menos um dos indicadores não pôde ser obtido;
nenhum zero ou média estadual foi usado para preencher a lacuna. A contagem
reexecutável também está em `auditoria.json`.

## Inspeção manual nos três estados

Foram conferidas as relações, os doze registros mensais dos conjuntos e o valor
anual produzido para um caso de cada UF: **Abatiá/PR** (nível 4, DEC 6,835),
**Abdon Batista/SC** (nível 1, DEC 9,18) e **Aceguá/RS** (nível 1, DEC 28,28).
Os casos confirmam que conjunto não foi tratado como sinônimo de município e que
o fallback do Paraná está marcado na própria linha.

## Endpoints oficiais

- Continuidade: <https://dadosabertos.aneel.gov.br/dataset/indicadores-coletivos-de-continuidade-dec-e-fec>
- IndQual Município: <https://dadosabertos.aneel.gov.br/dataset/indqual-municipio>
- BDGD: <https://dadosabertos.aneel.gov.br/dataset/base-de-dados-geografica-da-distribuidora-bdgd>
- INDGER: <https://dadosabertos.aneel.gov.br/dataset/indger-indicadores-gerenciais-da-distribuicao>
- SAMP: <https://dadosabertos.aneel.gov.br/dataset/samp>

# SIT — Sistema de Inteligência Territorial

Sistema municipal multidimensional para medir e organizar informações sobre as
condições do ambiente local que favorecem a criação, instalação, operação e
desenvolvimento de atividades empresariais nos 1.191 municípios do Paraná, de
Santa Catarina e do Rio Grande do Sul.

O SIT apoia diagnóstico territorial e inteligência estratégica. Rankings são
apenas um produto possível: o valor principal está em decompor os resultados e
mostrar, por exemplo, que um município combina infraestrutura e mercado fortes
com fragilidades em capital humano.

O sistema **não** mede desenvolvimento municipal ou qualidade de vida em sentido
amplo, não prevê o sucesso de empresas específicas e não constitui, isoladamente,
recomendação locacional de investimento.

## Situação do projeto

- **Etapa 0 — concluída:** as decisões normativas estão em
  [Decisões metodológicas preliminares](docs/decisoes-metodologicas-preliminares.md).
- **Etapa 1 — concluída e preservada:** cadastro canônico dos 1.191 municípios,
  identificado pelo código IBGE, com pipeline, testes e relatórios de qualidade.
- **Etapa 2 — iniciada:** catálogo amplo de candidatos em
  [`config/indicadores.yml`](config/indicadores.yml), matriz conceitual e
  [relatório da primeira rodada](docs/etapa-2-inventario-indicadores.md). Nenhum
  indicador foi aprovado em massa e nenhum índice foi calculado.

O método, as escolhas ainda provisórias e os portões de aprovação estão no
[Guia de implementação](docs/guia-de-implementacao.md).

## Cadastro municipal (Etapa 1)

O pipeline consulta a API de Localidades do IBGE, preserva as respostas brutas
e publica o cadastro canônico acompanhado de relatório de validação:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
ice-sul-municipios --config config/edicoes/2026.yml
pytest
```

`ice-sul-municipios` e o pacote `ice_sul` são identificadores técnicos legados,
mantidos para evitar uma refatoração cosmética e não representam a identidade
pública do produto.

O CSV é gravado em `data/processed/<edicao>/municipios.csv`; relatório e
manifesto ficam em `reports/quality/<edicao>/municipios.json`. A edição de 2026
foi produzida pelo fallback geobr/Ipea porque o proxy do ambiente bloqueou a API
do IBGE; justificativa, reprodução e limitações constam na
[ficha da fonte](docs/fontes/ibge-localidades.md).

# SIT — Sistema de Inteligência Territorial

Sistema municipal multidimensional para medir as condições do ambiente local que determinam a criação, instalação, operação e
desenvolvimento de atividades empresariais nos 1.191 municípios do Paraná, de
Santa Catarina e do Rio Grande do Sul.

As dimensões são seis: 
- Infraestrutura;
- Mercado;
- Ambiente Regulatório;
- Acesso a Capital
- Capital Humano;
- Inovação.

Cada eixo é composto de indicadores de condição local. Exemplos: Quão fácil é acessar um aeroporto, quanto tempo o município fica sem luz, qual o tamanho do mercado explorável pela empresa. 

Esses indicadores são combinados para formar um ranking dos municípios. Há o ranking geral, os estaduais, por porte, e, no futuro, os setoriais. 

O SIT apoia diagnóstico territorial e inteligência estratégica ao decompor os resultados dos indicadores e
mostrar, por exemplo, que um município combina infraestrutura e mercado fortes, mas
com fragilidades em capital humano. 

Há também indicadores de resultado, que ao invés de medir as condições de negócios, medem o desempenho dos municípios. Por exemplo, o crescimento do PIB ou número de decolagens de um aeroporto refletem os resultados da exploração do ambiente, que pode ser ótimo, mas estar sub-utilizado por algum motivo. Indicadores de resultado são úteis para validar os rankings e medir evolução dos municípios. 

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

## Demonstração experimental 2026

As regras isoladas da edição **SIT — Demonstração Experimental 2026 | Infraestrutura e Mercado** estão em `config/edicoes/mvp-demo-2026.yml`; a documentação começa em `docs/mvp-demo-2026/metodologia-experimental.md`.

Após produzir e auditar o CSV longo real:

```bash
python -m ice_sul.mvp.pipeline --indicadores data/processed/mvp-demo-2026/indicadores.csv
```

O pipeline não cria substitutos: coleta não verificada permanece ausente e impede nota/ranking abaixo de 80% de cobertura.

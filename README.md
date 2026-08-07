# ICE Sul

Projeto para construir um índice municipal multidimensional, reproduzível e
auditável para os municípios do Paraná, de Santa Catarina e do Rio Grande do
Sul.

O método, as decisões pendentes, o fluxo de dados e o roteiro de execução estão
descritos no [Guia de implementação](docs/guia-de-implementacao.md).

## Cadastro municipal (etapa 1)

O primeiro pipeline consulta a API de Localidades do IBGE, preserva as respostas
brutas e publica o cadastro canônico acompanhado de um relatório de validação:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
ice-sul-municipios --config config/edicoes/2026.yml
pytest
```

O CSV é gravado em `data/processed/<edicao>/municipios.csv`; o relatório e o
manifesto das extrações ficam em `reports/quality/<edicao>/municipios.json`.
Arquivos brutos são deliberadamente ignorados pelo Git. A configuração da edição
define a data de corte, a vigência e o endpoint, sem espalhar esses parâmetros
pelo código.

O cadastro versionado de 2026 foi produzido pelo fallback geobr/Ipea porque o
proxy do ambiente bloqueou a API do IBGE. A justificativa, a reprodução e as
limitações estão registradas na [ficha da fonte](docs/fontes/ibge-localidades.md).

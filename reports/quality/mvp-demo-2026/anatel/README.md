# Anatel — evidência de qualidade (corte 12/08/2026)

## Fontes e snapshots verificados

* **SCM/Banda Larga Fixa:** bulk download oficial
  `acessos_banda_larga_fixa.zip` (HTTP 200, 1.029.180.610 bytes), atualizado
  em 31/07/2026. O arquivo anual mais recente termina em **junho/2026** e traz
  CNPJ, grupo econômico, velocidade numérica, meio de acesso, tipo de produto
  e acessos. A tabela em colunas foi usada para a inspeção eficiente.
* **Cobertura Móvel:** bulk download oficial `cobertura_movel.zip` (HTTP 200,
  307.467.778 bytes), atualizado em 04/07/2026. A medida municipal mais recente
  dentro do ZIP é **março/2026**; junho/2026 existe em nível de setor censitário.
* **Áreas Cobertas:** `areas_cobertas.zip` respondeu HTTP 200 e declarou
  3.641.649.642 bytes (08/07/2026). A camada foi localizada, mas não versionada
  no Git nem baixada integralmente nesta execução.
* Caminhos alternativos verificados: portal `gov.br/anatel` (documentação),
  painel `informacoes.anatel.gov.br` (links oficiais) e catálogo `dados.gov.br`.
  A pesquisa intermediária retornou 401, mas os endpoints diretos funcionaram.

## Regras implementadas e resultado

`INF-DIG-01` filtra `Tipo de Produto = INTERNET` e velocidade numérica maior
ou igual a 100 Mbps. A transformação está concluída, mas o produto substantivo
fica **parcial** porque a população municipal da edição não está integrada.
Linha dedicada e demais produtos não comparáveis ficam fora.

`INF-DIG-02` usa `Meio de Acesso = Fibra` sobre todo acesso `INTERNET`; total
zero vira `ausente`. `INF-DIG-03` usa o **CNPJ declarado** como prestador, pois
essa é a unidade empresarial granular disponível. O campo grupo econômico é
preservado na fonte, mas não substitui CNPJ nem recebe agregação inferida.

`INF-DIG-04` seleciona `Tecnologia = 4G5G` e `Operadora = Todas`, evitando soma
com dupla contagem entre operadoras. Embora rotulado como percentual, o snapshot
municipal publica proporções 0–1; o parser converte para 0–100. Linhas idênticas
repetidas são aceitas somente quando seus valores coincidem.

`INF-DIG-05` permanece **parcial**: a Anatel fornece cobertura setorial/polígonos,
mas não a área passível de uso agrícola. A camada elegível não existe no projeto;
portanto, não se fabrica zero e municípios sem área deverão receber
`nao_aplicavel` quando essa dependência entrar na Onda 2.

## Validações

Foram conferidos schema, meses, códigos IBGE de sete dígitos, unidade, faixas,
ausentes, repetições e limites 0–100. Curitiba (4106902), Florianópolis (4205407)
e os filtros de velocidade, fibra, produto e monopólio constam das fixtures
offline. A validação de produção deve ainda registrar totais e exemplos de Porto
Alegre e de municípios pequenos antes da publicação.

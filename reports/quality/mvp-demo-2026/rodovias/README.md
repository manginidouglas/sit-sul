# Onda 1 — malha rodoviária estruturante elegível

**Data de corte da pesquisa:** 2026-08-14. **Base de integração:**
`ded566692633b8e5b36ae884e2c268fc6e3e49ae`.

## Definição e proveniência

A camada aceita exclusivamente trechos que a própria fonte oficial classifica
simultaneamente como (1) federais ou estaduais, (2) pavimentados e (3)
operacionais/existentes. As fontes cadastradas são DNIT/SNV (federal), DER/PR,
SIE/GeoSIE SC e DAER/RS. Concessão não muda a jurisdição e não exclui o trecho.
OSM não participa da elegibilidade.

O catálogo auditável em `data/raw/rodovias/catalogo-fontes.json` registra órgão,
URL principal, eventual alternativa **da mesma instituição**, território e data
de referência. O coletor guarda bytes sem alteração e cria, ao lado do pacote,
manifesto com URL inicial/final, redirecionamentos, HTTP, horário UTC, tamanho e
SHA-256. Um raw existente nunca é sobrescrito.

> Execução concluída em 2026-08-15: as quatro fontes foram materializadas, as
> seis células passaram pelos portões, as inspeções obrigatórias foram produzidas
> e a geração `20260815T013657273373Z` foi publicada atomicamente. O estudo OSRM
> real concluiu que incluir rodovias estaduais altera materialmente o indicador.

## Harmonização e decisões conservadoras

Saída em GeoJSON, CRS84/EPSG:4326, com `segmento_id`, `rodovia_id`,
`jurisdicao`, `situacao`, `pavimento`, `uf`, `vigencia_data`, `fonte_id`,
`fonte_instituicao`, `concessao`, `elegivel`, `motivo_exclusao` e
`extensao_km_qa`. Identificadores são normalizados como `BR-###`, `PR-###`,
`SC-###` ou `RS-###`.

Decisões para categorias ambíguas:

* **planejada / em planejamento:** excluída;
* **leito natural / não pavimentada:** excluída;
* **em implantação:** excluída, salvo se a fonte também fornecer uma categoria
  operacional inequívoca no registro que será mapeada explicitamente;
* **obras de duplicação:** pavimento aceito somente quando a situação do trecho
  continua operacional;
* **concedida:** incluída se federal/estadual, pavimentada e operacional;
* campo de situação ou pavimento ausente/desconhecido: excluído, nunca inferido
  pela geometria, nome, OSM ou imagem;
* via municipal: excluída mesmo quando conectada ou sobreposta à malha;
* geometria que cruza município: não gera tempo zero nem indicador municipal.

## QA e portão para a Onda 2

`process()` informa segmentos recebidos/elegíveis, quilômetros geodésicos de QA
por UF e jurisdição, missing de situação/pavimento, duplicidades por impressão
digital, geometrias inválidas e exclusões por motivo. Comprimento é apenas uma
checagem de cobertura; não é distância de rota.

A execução integral confirmou cobertura federal e estadual nas três UFs e zero
geometria inválida. `inspecoes.json` registra BR-116 e PR-323 (PR), BR-101 e
SC-401 (SC), BR-290 e ERS-040/RS-040 (RS), com fonte, categorias, segmentos e
extensão. `estudo-osrm.json` preserva resultados pareados, snapping, falhas,
vencedores e sensibilidade para 5 km e 1 km.

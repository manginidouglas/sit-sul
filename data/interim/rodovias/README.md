# Camada intermediária de rodovias
O materializador publica `universo-antes.geojson`, `universo-depois.geojson`,
`elegiveis.geojson`, `qa.json` e `manifesto.json` como uma única geração. Os
binários brutos e produtos integrais são reproduzíveis e permanecem ignorados.

DAER declara literalmente `AccessConstraints=vedado o uso comercial`. O fluxo
é destinado ao uso institucional não comercial; redistribuição comercial exige
autorização e revisão jurídica.
O produto integral (GeoJSON/GeoParquet) não é versionado no Git. Ele deve ser
regenerado dos pacotes brutos imutáveis, e publicado aqui com seu manifesto e
`sha256`. O contrato de saída é descrito no relatório metodológico em
`reports/quality/mvp-demo-2026/rodovias/README.md`.

A camada elegível fornece exclusivamente os destinos oficiais do estudo; o
deslocamento usa o grafo Brasil OSM/OSRM congelado já existente. Todos os
vértices são candidatos e os trechos são densificados geodesicamente a no
máximo 5 km. O relatório preserva segmento vencedor, coordenada, rota e snapping;
snapping acima de 1 km é marcado para sensibilidade, nunca descartado em silêncio.

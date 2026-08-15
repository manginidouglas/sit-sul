# Execução real concluída — 2026-08-15 UTC

Estado: **apta a revisão/merge**. As quatro fontes, seis células, inspeções,
geração atômica e estudo OSRM real foram concluídos.

## Fontes

| fonte | transporte | bytes | SHA-256 | feições |
|---|---|---:|---|---:|
| DNIT/SNV 202607A | ativo temporário GitHub Release; fonte original permanece DNIT | 78.034.601 | `c1db63e22f6e074bcf378d915a94a30c1f31939c6d4d68e9b19e65762f885091` | 1.476 em PR/SC/RS |
| DER/PR 2021 | DER/PR | 4.426.401 | `4e238f003034858159422fcec0ab7eb7c9bad45951d734829d6ab24c160c5845` | 2.328 |
| GeoSIE/SC | GeoSIE | 4.862.195 | `ff4318dab8f7d4306c04610a179b8522a76e87fe921a8834b6a80cead0c1d65a` | 624 |
| IEDE/DAER | IEDE MapServer/0 | 49.244.538 | `d607dbe0aec8a7e47384b058e18d44433472aa70018c24a6bfcec97976d08376` | 1.683 |

O RAR DNIT teve tamanho, SHA-256 e magic bytes confirmados antes da extração.
O inventário confirmou `pub_202607A/02_Dados/Shapefile 202607A.zip`, CRC válido,
SHP/SHX/DBF/PRJ, camada `SNV_202607A`, CRS EPSG:4674 e 1.476 feições nas três UFs.
A sidecar distingue a URL oficial DNIT da URL temporária usada só no transporte.

## Geração publicada

Geração ativa: `20260815T013657273373Z`.

| célula | segmentos elegíveis |
|---|---:|
| PR federal | 401 |
| PR estadual | 1.312 |
| SC federal | 216 |
| SC estadual | 542 |
| RS federal | 373 |
| RS estadual | 809 |

Foram recebidos 6.111 segmentos (65.214,533 km QA); 4.755 permaneceram após a
precedência (48.844,214 km); 3.653 foram publicados como elegíveis. A saída tem
zero geometria inválida. `manifesto.json` contém hashes e contagens de todos os
produtos, inclusive QA, inspeções e estudo.

## Inspeções

As seis inspeções contratuais foram executadas sobre a geração: BR-116/PR (20
segmentos; 240,331 km), PR-323 (43; 292,760 km), BR-101/SC (61; 525,601 km),
SC-401 (8; 31,359 km), BR-290/RS (40; 729,866 km) e RS-040 (6; 94,620 km).
Todas têm classificação elegível e fonte autoritativa esperada.

## OSRM regional e estudo

O PBF Brasil congelado (`2b2ae9d8eb9a2d27501e4ab3a7097cab904439cbc7627319e5a4ce070dba27fd`)
foi recortado com `osmium extract --strategy complete_ways` na bbox
`[-58.0,-34.5,-47.0,-21.5]`. O recorte tem 544.067.976 bytes e SHA-256
`690a689196927486d3df97405192e6a29540107c4f8a1bb4ea957dbf51ee1340`.
Foi usada a imagem OCI OSRM 5.25.0 fixada pelo projeto, via skopeo/umoci/chroot,
MLD e `--max-table-size 10000`. As 48 rotas vencedoras auditadas ficaram dentro
da bbox; a menor margem à borda foi 1,54714 grau.

Todos os vértices oficiais e a densificação foram gerados. A busca ordenou os
candidatos por distância geodésica e aplicou branch-and-bound com limite superior
conservador de 140 km/h: candidatos restantes só foram podados quando nem seu
tempo linear teórico poderia superar a melhor rota OSRM já observada. As
contagens totais e avaliadas permanecem em cada vencedor no estudo.

Nos 12 municípios não houve falha nem snapping excessivo, em 5 km ou 1 km. Os
vencedores e durações foram estáveis. A redução mediana ao incluir estaduais foi
2,556 minutos e 21,102%; a máxima foi 37,347 minutos e 99,275%. Decisão:
`inclusao_das_estaduais_altera_materialmente`.

## Comandos principais

```text
curl -fL --retry 4 .../pub_202607A.rar
python -m ice_sul.transform.rodovias_materialize --collect-only
osmium extract -b -58.0,-34.5,-47.0,-21.5 --strategy complete_ways ...
skopeo copy docker://osrm/osrm-backend@sha256:bdfa... oci:...:v5.25.0
umoci unpack --image ...:v5.25.0 ...
osrm-extract -p /opt/car.lua /data/south-buffer-260801.osm.pbf
osrm-partition /data/south-buffer-260801.osrm
osrm-customize /data/south-buffer-260801.osrm
osrm-routed --algorithm mld --max-table-size 10000 /data/south-buffer-260801.osrm
python -m ice_sul.transform.rodovias_materialize --municipal-sample ... --osrm-url http://127.0.0.1:5000
```

Raws, PBF, arquivos extraídos e grafo continuam ignorados e não integram o Git.

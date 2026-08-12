# Rebuild reproduzível do roteamento OSM/OSRM

## Decisões congeladas

* **Rede:** extrato Brasil do OpenStreetMap publicado pela Geofabrik, snapshot
  `2026-08-01`. URL datada, 2.066.032.748 bytes e MD5
  `265d58e0eb10236a28b64fe846c92925` estão em
  `data/raw/osm/snapshot.json`. O download é retomável, mas só é promovido após
  validação de tamanho e hash.
* **Motor:** OSRM Backend `v5.25.0`, imagem Linux oficial fixada pelo digest
  `sha256:bdfa...d555`; algoritmo MLD; perfil `/opt/car.lua`. Não há API paga ou
  serviço externo na arquitetura de produção.
* **Sedes:** `municipal_seats_south_2022.csv` contém exatamente uma sede (não o
  centroide) para cada um dos 1.191 municípios. Ela deriva de *Localidades do
  Brasil 2022* do IBGE (GeoPackage de 6.477.540 bytes, SHA-256
  `1d96d5...eb57`). Capitais duplicadas nas classes “sede” e “capital” são
  desduplicadas por código IBGE. Rode `python scripts/routing/build_municipal_seats.py`.

## Build e operação

Requisitos: Docker Engine 24+, `curl`, 64-bit Linux, cerca de **35 GB livres** e
**16 GB RAM** (24 GB recomendados; sem swap o extrator pode ser encerrado). O
host desta execução tinha 17 GiB RAM, 29 GB livres, 3 CPUs e não tinha Docker;
portanto o build Brasil não foi iniciado para não produzir artefato parcial.

```bash
scripts/routing/osrm.sh build       # download, extract, partition, customize
scripts/routing/osrm.sh serve       # localhost:5000; MLD e table-size=10000
python -m ice_sul.routing.cli -25.4296,-49.2719 -25.5285,-49.1758
```

O diretório `data/interim/routing/osrm/` é derivado, grande e ignorado. Um
rebuild limpo consiste em removê-lo e repetir `build`; não troque a URL, digest
da imagem ou perfil sem uma nova versão metodológica. Registre tempos máximos de
RSS e espaço com `/usr/bin/time -v scripts/routing/osrm.sh build`.

## Uso na Onda 2 e escala

`OSRMClient.route` devolve sucesso, minutos, metros, pontos ajustados (*snapped*)
e erro. `table` usa uma única chamada matricial muitos-para-muitos e preserva
`null` para pares sem rota. `table_chunks` fatia destinos pelo limite de células.
Assim, 1.191 origens × poucos aeroportos/portos devem ser enviadas em blocos, e
não como chamadas `route` sequenciais. Para Mercado (truncagem 360 min), dividir
a matriz nacional em blocos com no máximo 10.000 células, persistir cada bloco
atomicamente (Parquet recomendado), retomar por índice e descartar durações
acima de 360 após o roteamento. Mais throughput pode ser obtido com processos
OSRM somente leitura atrás de um balanceador; não aumente concorrência até medir
RAM e latência. A matriz nacional final fica explicitamente para a Onda 2.

## Sanity checks e benchmark pequeno

Em 2026-08-12, como o runner não tinha Docker, verificou-se conectividade e
plausibilidade no servidor público de demonstração do projeto OSRM **somente
como diagnóstico manual**, nunca como dependência ou fonte de resultados. Uma
chamada fria por par retornou:

| par | minutos | km | latência cliente |
|---|---:|---:|---:|
| Curitiba → Afonso Pena | 24,99 | 18,34 | 1.363 ms |
| Florianópolis → Hercílio Luz | 21,81 | 17,21 | 765 ms |
| Porto Alegre → Salgado Filho | 18,64 | 10,98 | 759 ms |
| Lapa → Curitiba | 69,48 | 68,95 | 605 ms |

As origens são as sedes IBGE; as coordenadas dos aeroportos utilizadas no sanity
check devem ser substituídas/conferidas pelo cadastro ANAC versionado na tarefa
de destinos. Todos os resultados foram positivos e rodoviariamente plausíveis.
A suíte automatizada confirma distância/duração, snapping, `NoRoute`, nulos e
chunking sem depender da rede. Após o build local, repita os quatro pares e
registre `waypoints[].distance`; trate snapping excessivo como falha de qualidade.
Não se afirma benchmark do grafo Brasil neste host: isso seria confundir o demo
remoto e seu snapshot desconhecido com a infraestrutura congelada.

## Limitações

A imagem oficial disponível e fixada é OSRM 5.25.0 (não a tag mutável `latest`).
Dados OSM incluem as limitações de cobertura/velocidade da comunidade; travessias
por balsa e fronteiras precisam revisão. O limite de tabela é número de
coordenadas no OSRM 5.25.0 e o wrapper adota conservadoramente células; ajuste só
com benchmark. As coordenadas de sedes são referência 2022, embora o snapshot da
rede seja 2026. Nenhum dos seis indicadores finais é calculado aqui.

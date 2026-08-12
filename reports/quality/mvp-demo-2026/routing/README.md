# Rebuild reproduzível e prova local OSM/OSRM

## Entradas e decisões congeladas

A rede metodológica é o extrato Brasil OSM/Geofabrik de 2026-08-01, perfil
`car.lua`, OSRM 5.25.0 e MLD. O manifesto registra GET, resposta HTTP, URL final,
redirects, tipo, bytes transferidos/persistidos, MD5 oficial e SHA-256 calculado
sobre o PBF real. `download_osm.sh` reutiliza raw válido, rejeita raw final
inválido sem alterá-lo e somente promove um `.part` validado.

As 1.191 sedes (não centroides) derivam de *Localidades do Brasil 2022* do IBGE.
O ZIP oficial de 6.477.540 bytes fica imutável em
`data/raw/routing/ibge-seats/` (ignorado pelo Git) e tem manifesto versionado.
O gerador valida tamanho/SHA-256, preserva o ZIP, rejeita duplicidades e exige
igualdade exata de código, nome e UF com `data/processed/2026/municipios.csv`.
Quatro grafias atualizadas são harmonizadas pelo cadastro canônico; coordenadas
continuam sendo as sedes IBGE.

## Produção Brasil

```bash
scripts/routing/osrm.sh build
scripts/routing/osrm.sh serve
python -m ice_sul.routing.cli -25.4133,-49.2679 -25.5285,-49.1758
```

Recomenda-se 35 GB livres, 16 GB RAM mínimos (24 GB recomendados), Docker Engine
24+ e Linux 64-bit. O host tinha 17 GiB RAM e, após baixar o PBF, 25 GB livres:
o Brasil completo não foi construído, pois grafo, temporários e imagem poderiam
exceder o disco. Isso não muda o snapshot Brasil exigido para Mercado.

## Caminhos locais tentados

1. **Docker nativo:** Docker 29.1.3 foi instalado. O daemon padrão falhou ao criar
   regras nftables (`Permission denied`). Com `--iptables=false --bridge=none
   --storage-driver=vfs`, o daemon iniciou, mas `docker run hello-world` falhou em
   `failed to register layer: unshare: operation not permitted`. O container do
   runner não concede namespaces/mounts necessários.
2. **Build nativo OSRM 5.25.0:** dependências foram instaladas e o fonte oficial
   no commit da tag `051e931...` foi configurado por CMake. Falhou porque o
   detector legado do 5.25.0 não reconhece oneTBB do Ubuntu 24.04 (`Intel TBB NOT
   found`). Trocar a versão do OSRM não provaria o artefato fixado.
3. **OCI sem runtime — funcionou:** `skopeo` baixou a mesma imagem fixada,
   `umoci` extraiu seu rootfs e os binários foram executados localmente por
   `chroot`. Isso contorna somente a limitação do runtime, sem trocar OSRM,
   perfil, algoritmo ou rede.

## Smoke end-to-end real

O smoke foi derivado **do PBF Brasil congelado e validado**, com `osmium extract
-b -49.9,-26.0,-48.8,-25.1 --strategy complete_ways`. O extrato Curitiba/Lapa
tem 22.294.295 bytes e SHA-256 `b22d875...a3833`. Ele prova o pipeline, mas não
substitui o grafo Brasil para MER-01/MER-02. Comandos reproduzíveis estão em
`scripts/routing/smoke_test_local.sh` e medições estruturadas em
`local-smoke-results.json`.

Os tempos, RSS, hashes, snapping e respostas exatas não são duplicados neste
README: o próprio script mede as etapas e gera
`local-smoke-results.json`, que é a fonte versionada desses números. A consulta
`route` usa Curitiba → Afonso Pena. A consulta `table` usa as sedes IBGE de
Curitiba e Lapa como duas origens e Afonso Pena e a sede de Curitiba como dois
destinos, produzindo e validando uma matriz 2 × 2. Nenhum servidor remoto
participa da prova.

## Interface, QA e escala da Onda 2

`route` retorna minutos, metros, coordenadas ajustadas, distâncias de snapping e
falha explícita. `table` preserva matrizes, nulos, coordenadas e distâncias de
snapping de `sources`/`destinations`. QA detalhado deve usar `route` em amostras
e casos críticos; nenhum limiar de snapping foi congelado nesta tarefa.

Para 1.191 origens e destinos logísticos, use `table`/`table_chunks`, não milhões
de chamadas sequenciais. Mercado deve persistir blocos atomicamente, retomá-los
por índice e aplicar a truncagem de 360 minutos após roteamento. A matriz nacional
final e os seis indicadores continuam fora deste PR.

## Limitações reais restantes

O build Brasil ainda requer host com disco suficiente e runtime Docker permitido
(ou o método OCI/chroot documentado). Coordenadas aeroportuárias de sanity devem
ser substituídas pelo cadastro ANAC versionado da tarefa própria. OSM mantém
limitações comunitárias de velocidades, balsas e conectividade; isso demanda QA
amostral na Onda 2.

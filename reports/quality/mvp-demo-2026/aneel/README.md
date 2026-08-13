# ANEEL — DEC/FEC municipal, ano completo de 2025

## Reprodução

```bash
python -m pip install -e '.[dev]'
python -m pip install pyogrio
python -m ice_sul.transform.aneel_materialize \
  --bdgd data/raw/aneel/ceee.zip data/raw/aneel/celesc.zip \
  data/raw/aneel/copel.zip data/raw/aneel/rge.zip
```

O comando valida o ZIP, extrai em diretório temporário exatamente
`indicadores-continuidade-coletivos-2020-2029.csv`, exige 12 competências,
lê IndQual e as BDGDs, carrega diretamente o cadastro canônico, valida 1.191 IDs
e duas linhas por ID e grava `data/interim/aneel/{indicadores_municipais_2025.csv,auditoria.json}` e este diretório de QA. Raw nunca é alterado.

## Fontes oficiais, fórmula anual e proveniência

Foram efetivamente usados: **Indicadores Coletivos de Continuidade (DEC/FEC)** e
**IndQual Município**, do catálogo ANEEL, e as BDGD 2024 de Copel-DIS, Celesc-DIS,
RGE e CEEE Equatorial, do ArcGIS oficial ANEEL. URLs exatas, vintage, horário,
tamanho, hash, tipo HTTP, licença e validações estão em `manifest.json`.

O dicionário oficial de Continuidade v1.0 (06/06/2022) define DEC em horas e FEC
em número de interrupções; `AnoIndice` como ano de competência;
`NumPeriodoIndice` como “período do índice expressado em meses”; e
`VlrIndiceEnviado` como o valor enviado. Também declara atualização mensal e que
DEC/FEC representam tempo/número de interrupções no período considerado (mês,
trimestre ou ano). O recurso 2025 contém competências 1–12 e não contém uma linha
anual separada. Conforme a acumulação temporal do Módulo 8 do PRODIST referenciado
pelo próprio dicionário, o anual é a soma das doze parcelas mensais. O pipeline
recusa qualquer conjunto × indicador que não tenha exatamente os meses 1–12 e
recusa competências duplicadas; não mistura denominadores nem calcula média dos
meses. Fonte documental: dicionário oficial disponível no recurso
`dm-indicadores-continuidade.pdf` do catálogo de Continuidade.

## Investigação operacional da BDGD

O catálogo ArcGIS oficial foi consultado por `orgId=J5unWNi0P2dwjI3y`, tag BDGD
e vintage `2024-12-31`; não havia item com tag/vintage 2025. Foram identificados
os grandes agentes Sul Copel-DIS, Celesc-DIS, RGE e CEEE Equatorial e os agentes
locais Mux Energia, Cocel, Forcel, Hidropan, DEMEI, EFLUL, Certel, Ceriluz,
Cerfox, Cooperluz, Certaja, Cersul, Ceris, Ceripa, Cernhe, Ceral-DIS, Coopermila,
Coopercocal, Coopera, Cerpro, Cergapa, Coopersul, Cermc, Coopernorte, Cerpalo,
Cerrp, Ceraca, Certrel, Cooperzem, Certhil, Cergal, Cercos, Cerej, Cervam,
Cermissões, Cermoful, Cersad, Cergral e Cerbranorte.

A tentativa operacional baixou e abriu os quatro File Geodatabases dos grandes
agentes (4,52 GB transferidos). Todos expõem 43 layers. Os layers relevantes e
seus schemas reais são `UCBT_tab`, `UCMT_tab` e `UCAT_tab`, cada registro sendo
uma UC no universo de baixa, média e alta tensão, respectivamente; são universos
de tensão mutuamente exclusivos. Foram usados somente `MUN` (IBGE), `CONJ`
(identificador do conjunto) e `SIT_ATIV`; somente `SIT_ATIV='AT'` foi contado.
`CONJ` (polígono) foi inspecionado e rejeitado como peso, pois área não é UC.
As tabelas de ativos/rede foram rejeitadas por não representarem UCs. As BDGDs
locais foram inventariadas, mas não baixadas em massa porque os quatro grandes
arquivos já forneceram todos os pesos completos que puderam ser aplicados aos
municípios multiconjunto atendidos por esses agentes; não se atribuiu peso parcial.

Foram obtidas **3.084 células município × conjunto** com UCs ativas. Só há nível
2 quando todos os conjuntos com DEC/FEC completo relacionados ao município têm
peso positivo; isso tornou 382 municípios ponderáveis. Ausência de uma célula
leva ao nível 4, nunca a peso zero. Não havia duas margens oficiais contemporâneas
para os restantes, portanto IPF (nível 3) não foi acionado.

## Resultado e QA

| situação | municípios | % do universo |
|---|---:|---:|
| nível 1 | 241 | 20,24% |
| nível 2 (BDGD) | 382 | 32,07% |
| nível 3 | 0 | 0,00% |
| nível 4 | 563 | 47,27% |
| sem DEC e FEC | 5 | 0,42% |

A BDGD retirou **382 municípios** do nível 4. DEC e FEC têm, cada um, 1.186
observações (99,58%) e 5 ausências. Os ausentes são Anitápolis/SC, Bombinhas/SC,
Balneário Rincão/SC, Colorado/RS e Pinto Bandeira/RS; detalhes por indicador,
motivo e conjuntos constam em `qa.json`.

Nos 382 ponderados, ponderação BDGD versus média simples apresentou: DEC Spearman
0,8296, diferença absoluta mediana 1,4718, P95 5,4675 e máxima 12,1006;
FEC Spearman 0,8191, mediana 0,8112, P95 2,7445 e máxima 5,6902. Maiores mudanças
e cortes por UF estão em `qa.json`, que também contém estatísticas Sul/UF/método,
percentis, extremos, zeros, negativos, não finitos e inspeções de Curitiba,
Florianópolis, Porto Alegre, Abatiá, Abdon Batista e Aceguá. Nenhum extremo foi
removido, imputado ou winsorizado.

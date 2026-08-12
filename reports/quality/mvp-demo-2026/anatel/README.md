# Anatel — QA substantivo (corte 12/08/2026)

## Execução real e períodos

Os três bulk downloads oficiais responderam HTTP 200 e foram validados por CRC e
SHA-256. O SCM contém janeiro–junho/2026; adotou-se junho/2026. O ZIP de cobertura
contém séries municipais até março/2026 e dados setoriais até junho/2026; adotou-se
março/2026, o último mês municipal comum até o corte. O manifesto registra a hora
UTC real da validação, tamanho, hash e caminho esperado dos raws, que não são
versionados por terem 1,03 GB, 307 MB e 3,64 GB.

`data/interim/anatel/indicadores_digitais_municipais.csv` materializa 3.573 linhas:
1.191 municípios em cada INF-DIG-02/03/04, conjunto exato do cadastro canônico,
sem duplicidade e sem ausentes. `qa.json` contém distribuição, cobertura, outliers
e componentes dos casos manuais. Nenhum valor ficou fora das faixas lógicas.

## Fórmulas e unidade empresarial

INF-DIG-02 = 100 × acessos `INTERNET` em `Meio de Acesso = Fibra` / acessos
`INTERNET`. INF-DIG-03 oficial usa a unidade econômica **híbrida**: 1 − Σp².
O artefato `inf-dig-03_unidades_exploratorias.csv` também calcula a unidade híbrida:
grupo econômico oficial informativo; para `OUTROS`, vazio ou genérico, CNPJ.

Nas 1.191 observações, a correlação de Spearman CNPJ × híbrida é 0,9999975423367914,
calculada como Pearson dos ranks médios (empates recebem a média das posições); diferença
absoluta média 0,0000811, mediana zero, P95 0,0005773, P99 0,0014007 e máximo
0,0040062 (Londrina). Foram encontrados 17 grupos informativos abrangendo 26 CNPJs.
A **unidade híbrida** é a versão oficial, pois representa melhor a unidade econômica
sem fundir prestadores independentes em `OUTROS`. A versão por CNPJ permanece no
artefato exploratório como diagnóstico e comparação histórica.

INF-DIG-04 usa apenas `Tecnologia = 4G5G`, `Operadora = Todas`; seleciona primeiro
o maior período municipal até o corte e só então rejeita duplicidades divergentes.
A escala publicada 0–1 é convertida em percentual 0–100.

## INF-DIG-01 e INF-DIG-05

`inf-dig-01_numerador.csv` preserva, para cada município, acessos `INTERNET` com
velocidade ≥100 Mbps, total de acessos, período e flag. Falta somente a população
IBGE; nenhuma população foi inventada e o raw não precisará ser relido.

O bulk espacial de 3.641.649.642 bytes foi efetivamente baixado e validado. Ele
contém 1.044 KML (12,47 GB descompactados). Para o Sul, os membros oficiais
`4G5G_todas_{pr,sc,rs}_municipio_simple.kml` somam 130,57 MB descompactados. São
KML 2.2, EPSG:4326, polígonos por município e classes R/U, período junho/2026.
`inf-dig-05_insumo_espacial.json` registra schema, CRCs e procedimento. O indicador
continua parcial exclusivamente porque falta a camada externa de área agrícola:
dissolver por código, intersectar em CRS equal-area e aplicar `nao_aplicavel` se
a área elegível for zero.

## Inspeção manual e plausibilidade

* Curitiba: fibra 639.050/798.971 = 79,98%; competitividade híbrida 0,7994
  (188 unidades);
  cobertura 100%. Plausível para mercado metropolitano denso.
* Florianópolis: 223.623/303.546 = 73,67%; 0,7671 (90); cobertura 99,96%.
* Porto Alegre: 423.865/615.902 = 68,82%; 0,7385 (180); cobertura 99,98%.
* Abatiá/PR: 801/868 = 92,28%; 0,4699 (16); cobertura 90,28%.
* Abdon Batista/SC: 172/220 = 78,18%; 0,6621 (11); cobertura 64,81%.
* Aceguá/RS: 322/1.065 = 30,23%; 0,5220 (13); cobertura 60,90%.

As capitais têm cobertura populacional quase universal e mercados mais numerosos;
os pequenos exibem variação rural esperada. Extremos foram inspecionados via top
10 da diferença HHI e distribuições completas em `qa.json`; não houve valor
aritmeticamente implausível ou fora de faixa.

## Reprodução

```bash
python -m ice_sul.transform.anatel_materialize \
  data/raw/anatel/2026-08-12/acessos_banda_larga_fixa.zip \
  data/raw/anatel/2026-08-12/cobertura_movel.zip
```

Suíte final desta revisão: `pytest -q` com 56 testes aprovados, além de
`git diff --check` e `python -m compileall -q src` sem erros.

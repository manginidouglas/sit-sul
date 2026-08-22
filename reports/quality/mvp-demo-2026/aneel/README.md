# ANEEL — DEC/FEC municipal, ano completo de 2025

## Reprodução

```bash
python -m pip install -e '.[dev]'
python -m pip install pyogrio
python -m ice_sul.transform.aneel_materialize --bdgd $(find data/raw/aneel \
  -maxdepth 1 -name '*.zip' ! -name 'indicadores-*' -print | sort)
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

Na primeira execução, apenas com as quatro BDGDs principais, foram obtidas
**3.084 células município × conjunto** com UCs ativas. Só há nível
2 quando todos os conjuntos com DEC/FEC completo relacionados ao município têm
peso positivo; isso tornou 382 municípios ponderáveis. Ausência de uma célula
leva ao nível 4, nunca a peso zero. Não havia duas margens oficiais contemporâneas
para os restantes, portanto IPF (nível 3) não foi acionado.

## Baseline anterior às BDGDs locais

| situação | municípios | % do universo |
|---|---:|---:|
| nível 1 | 241 | 20,24% |
| nível 2 (BDGD) | 382 | 32,07% |
| nível 3 | 0 | 0,00% |
| nível 4 | 563 | 47,27% |
| sem DEC e FEC | 5 | 0,42% |

As quatro BDGDs principais retiraram **382 municípios** do nível 4. DEC e FEC
têm, cada um, 1.186
observações (99,58%) e 5 ausências. Os ausentes são Anitápolis/SC, Bombinhas/SC,
Balneário Rincão/SC, Colorado/RS e Pinto Bandeira/RS; detalhes por indicador,
motivo e conjuntos constam em `qa.json`.

Esse quadro é preservado somente como baseline para mensurar o ganho incremental;
o resultado publicável final aparece abaixo.

## Fechamento dos fallbacks e BDGDs locais direcionadas

Partindo dos 563 municípios em nível 4, o cruzamento `conjunto_id → SigAgente`
foi feito diretamente nas linhas DEC/FEC 2025 da base de continuidade. Os maiores
responsáveis por conjuntos ainda sem célula eram RGE SUL (161 municípios),
COPEL-DIS (95), COPREL (67), CELESC (52), conjunto com agente “Não Informado”
(39), CERTEL Energia (43), CERFOX (34), CRELUZ-D (32), CELETRO (30),
CERMISSÕES (24), CERILUZ (23), CERTAJA (17), COOPERLUZ (17) e ELETROCAR (17).

Foram então baixadas apenas as BDGDs locais oficiais com alto potencial e baixo
volume: Certel, Cerfox, Creluz-D, Celetro, Cermissões, Ceriluz, Certaja,
Cooperluz, Eletrocar (vintage 2024-12-31) e Coprel (última disponível,
2023-12-31). Elas trouxeram 264 novas células únicas além das quatro BDGDs
principais. Em conjunto, converteram mais 84 municípios para nível 2. Coprel não
converteu municípios: sua publicação 2023 não contém os conjuntos 15457/15458 de
2025. URLs, hashes, tamanhos, schemas, células por arquivo e conversões isoladas
estão no manifesto.

A distribuição final é nível 1: 241; nível 2: 466; nível 3: 0; nível 4: 479; e
ambos ausentes: 5. Para cada um dos 479 fallbacks, o arquivo
`fallback_nivel4_diagnostico.csv` lista conjuntos necessários/presentes/ausentes,
agente oficial, disponibilidade/investigação e motivo categorizado. São 240
conjuntos sem peso. Os motivos agregados são: 289 municípios com conjunto sem
célula municipal apesar da BDGD principal; 106 associados a agente local ainda
não investigado; 45 compatíveis com mudança de conjunto entre vintages; e 39 com
agente não informado pela fonte.

Nos 466 ponderados finais, ponderação BDGD versus média simples apresentou: DEC
Spearman 0,8246, diferença absoluta mediana 1,5488, P95 5,9772 e máxima 15,9916;
FEC Spearman 0,7844, mediana 0,8275, P95 3,4361 e máxima 8,3686. Maiores mudanças
e cortes por UF estão em `qa.json`, que também preserva estatísticas Sul/UF/método,
percentis, extremos, zeros, negativos, não finitos e sanity checks. Nenhum extremo
foi removido, imputado ou winsorizado.

### Curitiba e Porto Alegre

**Curitiba** usa 34 conjuntos COPEL-DIS. A BDGD possui peso municipal positivo
para 31; faltam `15921` (São José dos Pinhais), `15924` (Araucária) e `15938`
(Fazenda Iguaçu). Esses IDs existem na BDGD 2024 em outras células, mas não na
célula Curitiba × conjunto. Portanto não é outra distribuidora nem ID totalmente
novo: é ausência da célula municipal no vintage 2024 em relação ao vínculo
IndQual/continuidade 2025. Sem evidência oficial para transferir UCs entre
municípios, Curitiba permanece nível 4.

**Porto Alegre** usa 23 conjuntos CEEE-D. Há peso para 22; falta `12542` (Guaíba).
O conjunto existe na BDGD CEEE Equatorial 2024, porém sem UC ativa na célula
Porto Alegre × 12542, enquanto o IndQual 2025 relaciona ambos. Sem peso parcial e
sem equivalência oficial, Porto Alegre permanece nível 4.

### Compatibilidade temporal

Entre os conjuntos completos requeridos em 2025, 501 IDs são usados e 44 não
aparecem em nenhuma BDGD carregada. Isso afeta 203 municípios multiconjunto.
Ausências e células municipais divergentes são compatíveis com criação,
renomeação, reorganização ou alteração de área 2024→2025, mas nenhuma equivalência
foi inferida por nome. O QA registra `equivalencias_inferidas=0` e preserva o
fallback quando não existe relação oficial entre IDs.

## Verificação final do catálogo residual

A rodada final partiu de 479 municípios nível 4 e pesquisou individualmente no
ArcGIS oficial ANEEL as **34 distribuidoras identificadas que ainda não tinham
catálogo encerrado**. O inventário auditável está em
`bdgd_catalogo_investigacao.json` e separa identificação do agente, consulta ao
catálogo, disponibilidade real e download. A consulta encontrou BDGD baixável
para 30 agentes; todas eram de volume operacionalmente razoável (inclusive CPFL
Jaguari/Santa Cruz, 166.838.408 bytes), foram baixadas e processadas. Não foi
encontrada File Geodatabase 2024/2023 aplicável para UHENPAL, ESS, Pacto Energia
PR e EFLJC. Não houve arquivo disponível deixado sem download por restrição.

As 30 BDGDs acrescentaram **172 células município × conjunto** às 3.351 anteriores
e promoveram **56 municípios** adicionais ao nível 2. O resultado final é:
nível 1 = 241; nível 2 = 522; nível 3 = 0; nível 4 = 423; ausentes = 5; com
3.523 células de peso e 210 conjuntos ainda sem peso.

Todos os 423 fallbacks finais estão em categorias fechadas:

- `bdgd_investigada_sem_celula_municipio_conjunto`: 323 municípios;
- `incompatibilidade_vintage_2024_2025`: 47;
- `bdgd_oficial_nao_disponivel`: 14;
- `agente_nao_informado_na_fonte`: 39;
- `bdgd_disponivel_mas_nao_baixada_por_restricao_operacional`: 0;
- `nao_diagnosticado`: 0.

Assim, não permanece a categoria aberta “conjunto provavelmente pertence a
distribuidora local”. `bdgd_disponivel` somente é verdadeiro quando uma consulta
documentada encontrou item oficial realmente baixável; agente identificado não
implica disponibilidade. Para os agentes relevantes aos fallbacks finais: 21
entradas, 20 identificadas e com catálogo verificado, 16 com BDGD disponível e
baixada, quatro sem recurso oficial e nenhuma não baixada por restrição.

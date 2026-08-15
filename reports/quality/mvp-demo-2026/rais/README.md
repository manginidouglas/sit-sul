# RAIS — emprego formal privado nacional e MER-DIAG-01

## Decisão temporal e estado da fonte

Na data de corte de 12/08/2026, a RAIS 2025 possuía publicação estatística
agregada, mas isso não comprova a existência do bulk VINC_PUB 2025. O recurso
individual e o layout que puderam ser confirmados são da RAIS 2024; ela é,
portanto, a edição operacional adotada. A disponibilidade dos microdados 2025
permanece não confirmada.

Estado: **em_verificacao**. O De-Para foi validado, mas nenhuma listagem real dos
`.7z` nem microdado VINC_PUB real pôde ser processado neste ambiente. Logo,
licença, cobertura nacional, amostra manual, quebra de série, padrão nominal e
topologia territorial real dos arquivos ainda não estão confirmados.

## De-Para oficial validado

O recurso `de-para-microdados.xlsx/@@download/file` respondeu HTTP 200 em
15/08/2026. O arquivo tem 23.640 bytes e SHA-256
`4be7a7421ce44e40c4b18ea044c624e16775a5d0e3429dac18acb6afd7545117`.
O `openpyxl`, em modo somente leitura, confirmou um workbook OOXML funcional com
as abas `VINC_PUB`, `VINC_ID`, `ESTAB_PUB` e `ESTAB_ID`. Na aba `VINC_PUB` foram
confirmados `cnae20classecódigo`, `indvínculoativo3112código`,
`municípiotrabcódigo`, `municípiocódigo` e `naturezajurídicacódigo`.

O coletor tenta o download direto e, se necessário, lê a página oficial
`rais-2024/rais-2024-1`, aceita o link `.xlsx/view` e o converte de forma
controlada para `@@download/file`. HTML, host/redirect externo, ZIP artificial,
workbook sem aba/campos e arquivo corrompido são rejeitados antes da promoção do
`.part` ao raw definitivo.

## Descoberta, partições e cobertura territorial

A descoberta tenta HTTPS e depois FTP anônimo: `MLSD`, com fallback `NLST`.
Todas as tentativas e o hash da listagem usada são registrados. A listagem
completa é validada antes de qualquer download.

O contrato não exige 27 arquivos. Cada `RaisArchive` preserva o nome publicado e
registra `partition_id` e `covered_ufs`. O portão global exige que a união das
partições cubra exatamente as 27 UFs, sem lacunas, UFs inválidas, arquivos ou
partições duplicados e sobreposições territoriais.

Enquanto a listagem oficial permanecer bloqueada, o parser exerce offline três
famílias de topologia, sem apresentá-las como observação da RAIS 2024:

- 27 arquivos estaduais;
- seis partições regionais historicamente plausíveis: `SUL`, `NORTE`,
  `NORDESTE`, `CENTRO_OESTE`, `SP` e `MG_ES_RJ`;
- uma partição nacional `BRASIL`.

A quantidade real de arquivos pode ser 27, seis, um ou outra quantidade
oficialmente publicada. O critério de sucesso é a cobertura territorial, não a
contagem de arquivos. A topologia oficial de 2024 continua não observada.

Cada 7-Zip é validado por assinatura, abertura, `testzip()`, semântica correta de
`test()` (`False` falha; `True` passa; `None` exige extração), segurança de todos
os membros e exatamente um `.comt`. O `.comt` é extraído e lido, inclusive sem
CRC. HTML, truncamento, path traversal, caminho absoluto e múltiplos `.comt` são
rejeitados. Os nomes dos membros entram no manifesto.

Downloads novos seguem `.part` → hash em streaming → validação → rename atômico.
Raw existente é integralmente revalidado e re-hasheado em streaming e recebe
`status=reused`; raw inválido interrompe a execução sem outputs.

## Classificação de falhas de fonte e validação

Falha de transporte em HTTPS seguida de falha de transporte em FTP é encapsulada
com evidência das duas tentativas e retorna `BLOCKED_SOURCE`. Bytes efetivamente
recebidos mas inválidos (HTML, truncamento, contêiner/layout inválido) e domínio
incompatível retornam `FAILED_VALIDATION`; nesses casos não há reclassificação
como indisponibilidade de rede nem publicação parcial.

## Parser, produtos e portões nacionais

A inspeção integral da aba `VINC_PUB` mostrou que as linhas críticas possuem
conteúdo somente nas colunas `De` e `Para`: CNAE na linha 10, vínculo ativo na
13, município de trabalho na 26, município na 27 e Natureza Jurídica na 29. O
De-Para confirma os nomes e confirma que o campo CNAE é **classe**, mas não
informa tipo, largura, domínio, ausentes ou zeros à esquerda. A evidência célula
a célula e essas limitações estão em `layout-campos-confirmados.json`.

O parser CNAE usa cinco dígitos de classe, preserva zeros (`07235`), deriva a
divisão somente após validar e rejeita subclasse de sete dígitos. Os contratos
operacionais de ativo (`[01]`), município bruto (`\d{6}`) e Natureza
(`\d{4}`, grupos 1–5) continuam estritos, mas suas larguras/domínios não são
confirmados pelo De-Para e aguardam confronto com `.comt` real.

Na transformação, a UF é derivada do município IBGE canônico de cada vínculo e
precisa pertencer a `allowed_ufs` da partição. Uma eventual coluna UF também deve
coincidir com a UF derivada. Assim, PR, SC e RS podem coexistir numa partição
`SUL`, enquanto um município de SP nessa partição falha na validação. O QA de
cada partição registra UFs permitidas e vínculos ativos por UF.

`emprego_privado_municipal.csv` é esparso e contém `municipio_id`, estoque,
período, flag `observado`, `fonte_id`, `fonte_arquivo` e `versao_fonte`.
Ausência de linha equivale a zero somente com `coverage_complete=true`.

`mer_diag_01.csv` contém exatamente os 1.191 municípios do Sul, os campos
analíticos e a mesma proveniência. Sem vínculo privado usa `ausente` e
`sem_vinculo_privado`; uma divisão usa `zero_observado`; mais de uma usa
`observado`. Até município ausente aponta para o arquivo da partição que cobre
sua UF.

Nenhum CSV é publicado antes de validar todas as partições, a cobertura das 27
UFs, os raws, domínios, ligação territorial, 1.191 diagnósticos e reconciliações.
A publicação usa staging e promoção conjunta. O QA nacional registra partições
esperadas/processadas, UFs cobertas, ausentes e sobrepostas, arquivos,
`coverage_complete`, estoque positivo, vínculos elegíveis, não ligados e
reconciliações.

## Evidência de teste versus execução real

Os testes integrais offline exercitam:

- 27 arquivos estaduais;
- seis arquivos regionais multi-UF;
- um único arquivo nacional.

As execuções provam cobertura das 27 UFs, `coverage_complete=true`, 1.191
diagnósticos, proveniência regional/nacional e rejeição de lacuna, sobreposição,
partição desconhecida e município fora da cobertura. Fixtures validam o código;
não são execução dos microdados reais. As rotas reais continuaram bloqueadas e
nenhum `.7z`, `.comt`, raw nacional ou output nacional real foi declarado
processado.

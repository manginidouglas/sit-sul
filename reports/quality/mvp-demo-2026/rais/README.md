# RAIS — emprego formal privado nacional e MER-DIAG-01

## Decisão temporal e estado da fonte

Na data de corte de 12/08/2026, a RAIS 2025 possuía publicação estatística
agregada, mas isso não comprova a existência do bulk VINC_PUB 2025. O recurso
individual e o layout que puderam ser confirmados são da RAIS 2024; ela é,
portanto, a edição operacional adotada. A disponibilidade dos microdados 2025
permanece não confirmada.

Estado: **em_verificacao**. O De-Para foi validado, mas nenhuma listagem real dos
`.7z` nem microdado VINC_PUB real pôde ser processado neste ambiente. Logo,
licença, cobertura nacional, amostra manual, quebra de série e padrão nominal
real dos arquivos ainda não estão confirmados.

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

## Descoberta e validação dos `.7z`

A descoberta tenta HTTPS e depois FTP anônimo: `MLSD`, com fallback `NLST`.
Todas as tentativas e o hash da listagem usada são registrados. A listagem
completa é validada antes de qualquer download. O parser offline aceita como
**hipótese testada** o padrão `RAIS_VINC_PUB_<UF>[_2024].7z`, preserva o nome
listado, exclui Estabelecimentos, rejeita ano/nome/host inesperado, duplicidade e
UF ausente e exige 27 UFs. Esse padrão não é declarado como padrão real
confirmado enquanto uma listagem oficial não for observada.

Cada 7-Zip é validado por assinatura, abertura, `testzip()`, semântica correta de
`test()` (`False` falha; `True` passa; `None` exige extração), segurança de todos
os membros e exatamente um `.comt`. O `.comt` é extraído e lido, inclusive sem
CRC. HTML, truncamento, path traversal, caminho absoluto e múltiplos `.comt` são
rejeitados. Os nomes dos membros entram no manifesto.

Downloads novos seguem `.part` → hash em streaming → validação → rename atômico.
Raw existente é integralmente revalidado e re-hasheado em streaming e recebe
`status=reused`; raw inválido interrompe a execução sem outputs.

## Parser, produtos e portões nacionais

Os parsers de ativo, município, CNAE e Natureza usam correspondência integral e
não removem caracteres. Ativo aceita somente `0`/`1`; município, seis ou sete
dígitos; CNAE classe, sete dígitos; Natureza, quatro dígitos e grupos 1–5. Lixo,
pontuação, vazio, comprimento incorreto e grupo desconhecido falham.

`emprego_privado_municipal.csv` é esparso e contém `municipio_id`, estoque,
período, flag `observado`, `fonte_id`, `fonte_arquivo` e `versao_fonte`.
Ausência de linha equivale a zero somente com `coverage_complete=true`.

`mer_diag_01.csv` contém exatamente os 1.191 municípios do Sul, os campos
analíticos e a mesma proveniência. Sem vínculo privado usa `ausente` e
`sem_vinculo_privado`; uma divisão usa `zero_observado`; mais de uma usa
`observado`. Até município ausente aponta para o arquivo de sua UF.

Nenhum CSV é publicado antes de validar 27 UFs únicas, todos os raws, domínios,
ligação territorial, 1.191 diagnósticos e reconciliações. A publicação usa staging
e promoção conjunta. O QA inclui UFs/arquivos esperados e processados,
`coverage_complete`, estoque positivo, vínculos elegíveis, não ligados e
reconciliações.

## Evidência de teste versus execução real

O teste integral offline gera 27 7-Zips pequenos, cadastro nacional e exatamente
1.191 municípios do Sul, sem rede. Ele prova os contratos e a publicação atômica,
mas **não é execução dos microdados reais**. As rotas reais do diretório
continuaram bloqueadas; nenhum `.7z` real, raw nacional ou output nacional foi
versionado ou declarado processado.

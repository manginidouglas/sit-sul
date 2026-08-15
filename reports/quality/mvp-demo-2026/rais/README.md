# RAIS 2024 — Onda 1

## Especificação oficial usada

A implementação é orientada pela documentação da RAIS 2024 e pela aba
`VINC_PUB` da planilha oficial **De-Para Microdados.xlsx**, obtida no mesmo
diretório da distribuição MTE/PDET. Os nomes primários implementados são
`cnae20classecódigo`, `indvínculoativo3112código`,
`municípiotrabcódigo` (com `municípiocódigo` como alternativa documentada) e
`naturezajurídicacódigo`. Aliases antigos existem apenas para compatibilidade.

Fonte: `https://ftp.mtps.gov.br/pdet/microdados/RAIS/2024/`. A planilha e cada
`.7z` são persistidos imutavelmente com URL, horário, tamanho e SHA-256. O
download dos arquivos grandes é feito em blocos. O `.7z` deve conter exatamente
um `.comt`; caminhos absolutos/traversal e arquivos sem ou com múltiplos `.comt`
são rejeitados.

## Conceito e método

Conta-se o estoque de vínculos formais ativos em 31/12/2024 — não trabalhadores
únicos, estabelecimentos ou vínculos movimentados. Exclui-se Administração
Pública se a divisão CNAE 2.0 for `84` **OU** o primeiro dígito da Natureza
Jurídica for `1`. O MER-DIAG-01 é `1 - Σp_s²`, por divisão CNAE 2.0.

Os códigos RAIS são ligados por de-para explícito: os seis dígitos observados no
campo municipal são procurados em uma tabela construída a partir dos IDs de
sete dígitos do cadastro oficial IBGE. O dígito verificador nunca é calculado ou
preenchido. Códigos não ligados ficam no `qa.json`, com frequência.

O arquivo não precisa ter coluna UF: a UF obrigatória vem do metadado da
distribuição por UF e é confrontada com o código IBGE ligado. Caso uma coluna UF
esteja presente, ela também é validada.

## Contratos de saída

- `data/interim/rais/2024/emprego_privado_municipal.csv`: município IBGE
  harmonizado, estoque, período e proveniência, para uso futuro do MER-02;
- `data/interim/rais/2024/mer_diag_01.csv`: `municipio_id`, `indicador_id`,
  `valor_bruto`, `periodo_referencia`, `flag_qualidade` para os 1.191 municípios;
- `reports/quality/mvp-demo-2026/rais/qa.json`: UFs processadas, vínculos lidos,
  inativos, públicos e privados, municípios ligados/não ligados e reconciliação.

Sem vínculo privado elegível, `valor_bruto` é `NA` e a flag é
`ausente_sem_vinculo_privado`. Havendo vínculos em uma só divisão, o valor é
zero observado. Esta onda não calcula a acessibilidade temporal do MER-02.

## Evidência desta revisão

### Arquivo oficial real

Em 15/08/2026 foi tentado acesso ao diretório, à planilha e ao arquivo DF no
servidor oficial. O endpoint respondeu HTTP 503, documentado em
`validacao-arquivo-real.json`. Portanto **nenhum cabeçalho, encoding,
delimitador, código municipal ou contagem foi declarado como empiricamente
confirmado em arquivo real neste ambiente**. O coletor retorna `blocked_source`
nessa condição, em vez de declarar sucesso com base na fixture.

### Fixture derivada do De-Para

A fixture usa os nomes reais acima, `.comt` delimitado por ponto e vírgula e
UTF-8, empacotado como `.7z` durante o teste. Ela confirma todo o caminho local,
incluindo inativo, CNAE 84, Natureza grupo 1, Brasília, ausência, concentração e
diversificação. São 9 vínculos nas duas fixtures: 2 inativos, 3 públicos e 4
privados elegíveis. A fixture não prova o encoding/delimitador nem os valores de
código da distribuição real; esses itens permanecem bloqueados até a fonte
responder.

**Cobertura real processada nesta revisão:** 0 UFs, 0 vínculos e 0 municípios.
Não foram fabricados produtos reais a partir de dados sintéticos.

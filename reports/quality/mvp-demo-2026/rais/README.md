# RAIS — emprego formal privado nacional e MER-DIAG-01

## Decisão temporal na data de corte

A data de corte da edição é **12/08/2026**. O portal do MTE já apresenta a
RAIS 2025 e seus produtos estatísticos (página atualizada em 17/06/2026), mas o
comunicado oficial de **microdados** vigente e a planilha De-Para disponibilizam
explicitamente a RAIS **2024**. Não foi encontrada evidência oficial suficiente
de que os microdados individualizados 2025 estivessem publicados e completos
até o corte. Portanto 2024 é a edição mais recente *tecnicamente utilizável para
este contrato*, e não se afirma que seja a estatística RAIS mais recente.

A decisão deve ser revista quando uma listagem oficial 2025 expuser os arquivos
VINC_PUB e seu dicionário. Uma página de resultados agregados 2025, isoladamente,
não autoriza inventar URLs de microdados.

## Descoberta e validação oficiais

O De-Para vem do recurso vinculado no comunicado oficial “Microdados RAIS
2024”; o coletor reconhece tanto `.xlsx/view`/`.xlsx` quanto `@@download/file`.
Em 15/08/2026 o download oficial respondeu 200, com 23.640 bytes e SHA-256
`4be7a7421ce44e40c4b18ea044c624e16775a5d0e3429dac18acb6afd7545117`.
O contêiner OOXML foi integralmente testado e contém, entre outros,
`cnae20classecódigo`, `indvínculoativo3112código`,
`municípiotrabcódigo` e `naturezajurídicacódigo`.

Os `.7z` não têm nomes sintetizados. O coletor primeiro lista o diretório
oficial 2024, aceita apenas `RAIS_VINC_PUB_<UF>.7z`, exige exatamente as 27 UFs
e só então baixa as URLs enumeradas. Nesta execução o endpoint do diretório
retornou 503 via proxy e FTP direto era inalcançável; por isso nenhum `.7z` real
foi baixado e nenhum produto real foi materializado. O estado correto permanece
`blocked_source`, sem substituir arquivo real por fixture.

Todo XLSX é verificado como ZIP OOXML íntegro. Todo 7-Zip tem assinatura,
integridade, caminho seguro e exatamente um `.comt` verificados. Raw existente
não é confiado: ele é revalidado, re-hasheado e recebe entrada completa de
manifesto com método `REUSE`.

## Parser e regra substantiva

Conta-se estoque de **vínculos** formais ativos em 31/12/2024. O domínio do
indicador ativo é estritamente `{0,1}`; qualquer outro valor interrompe a
execução. Exclui-se Administração Pública quando a divisão CNAE 2.0 é 84 **ou**
a Natureza Jurídica pertence ao grupo 1. Natureza vazia, com comprimento inválido
ou grupo desconhecido também interrompe a execução, em vez de virar “privada”.
CNAE, UF, código municipal, encoding e delimitador têm validação explícita.

A ligação RAIS (seis dígitos) → IBGE (sete) deriva do cadastro nacional oficial;
o dígito verificador nunca é calculado. Qualquer vínculo ativo não ligado impede
a publicação.

## Produtos e semântica

* `emprego_privado_municipal.csv` é a base nacional preparada para MER-02. Ela é
  **esparsa**: contém somente municípios com estoque privado positivo. Ausência
  de linha significa zero apenas quando a execução terminou com sucesso para as
  27 UFs e reconciliou integralmente todos os vínculos; em execução parcial ou
  bloqueada significa desconhecido e não pode ser convertida em zero.
* `mer_diag_01.csv` contém exatamente os 1.191 municípios canônicos do Sul.
  Calcula `1 - Σp²` por divisão CNAE. Sem vínculo privado, usa `ausente`; uma só
  divisão produz `zero_observado`; demais valores usam `observado`.
* `qa.json` registra leitura, exclusões, ligação, reconciliação, UFs e a semântica
  da base esparsa. As linhas nacionais preservam período e fonte/arquivo.

Esta etapa fornece o recurso municipal nacional para a futura acessibilidade do
MER-02; não calcula aqui as rotas nem a soma com decaimento temporal.

## Testes offline

As fixtures usam os cabeçalhos confirmados no XLSX real e exercitam `.7z` →
`.comt`, UTF-8, delimitador, ativo/inativo, CNAE 84, Natureza grupo 1, Brasília,
ligação desconhecida, ausência, concentração e diversificação. Testes separados
cobrem domínios inválidos, listagem incompleta, contêiner corrompido, reuso de raw
e esgotamento HTTPS/FTP. Fixture valida código; nunca serve como evidência de
que os 27 arquivos reais foram coletados.

# RAIS — base municipal da Onda 1

## Fonte, edição e conceito

- **Fonte primária:** Ministério do Trabalho e Emprego (MTE), Programa de
  Disseminação das Estatísticas do Trabalho (PDET), microdados RAIS Vínculos,
  distribuição oficial em `https://ftp.mtps.gov.br/pdet/microdados/RAIS/`.
- **Edição selecionada:** RAIS 2024, a edição anual definitiva mais recente
  identificada como publicamente distribuída até a data de corte de 12/08/2026.
- **Unidade contada:** estoque de **vínculos formais ativos em 31/12/2024**. Uma
  linha elegível do microdado de vínculos vale um emprego; quando usada uma
  distribuição oficial já agregada, usa-se a coluna de estoque. Não se trata de
  trabalhador único, estabelecimento ou soma de vínculos movimentados no ano.

Os arquivos brutos são imutáveis e não entram no Git. O coletor registra URL,
data/hora, resposta HTTP, tamanho e SHA-256 em `data/raw/rais/2024/manifest.json`.
Uma indisponibilidade temporária do FTP não autoriza substituir a RAIS pelo
CAGED.

## Filtro de emprego privado

Um vínculo é excluído quando **qualquer** condição for verdadeira:

1. divisão CNAE 2.0 (dois primeiros dígitos da classe) igual a `84` —
   Administração pública, defesa e seguridade social; ou
2. primeiro dígito da Natureza Jurídica CONCLA igual a `1` — grupo
   Administração Pública.

A união evita manter órgãos públicos classificados fora da divisão 84 e evita
manter, por inconsistência institucional, atividade 84 declarada sob outra
natureza. A regra é aplicada antes das agregações. Empresas públicas e
sociedades de economia mista que a tabela CONCLA classifica fora do grupo 1 não
são automaticamente removidas: a definição operacional exclui administração
pública, não toda participação estatal.

## Produtos

1. `data/interim/rais/2024/emprego_privado_municipal.csv`: todos os municípios
   brasileiros com ao menos um vínculo privado elegível; insumo de estoque para
   a acessibilidade futura do MER-02. Esta onda **não calcula tempos de viagem**.
2. `data/interim/rais/2024/mer_diag_01.csv`: os 1.191 municípios de PR, SC e RS,
   com `1 - sum(p_s²)`, onde `s` é a divisão CNAE 2.0. Município sem emprego
   elegível recebe campo vazio (`NA`), e não zero. Zero é possível e correto
   quando todo o emprego elegível está em uma única divisão.
3. `reports/quality/mvp-demo-2026/rais/qa.json`: contagens de leitura, descartes,
   exclusão pública, cobertura e ausências.

## Portões de QA

O transformador bloqueia ano divergente, código não harmonizado para sete
dígitos, UF incompatível com o prefixo IBGE, CNAE inválida e estoque negativo,
fracionário ou não finito. A revisão da execução integral deve ainda registrar:

- unicidade das linhas municipais em cada produto e os 1.191 registros do
  diagnóstico;
- soma municipal versus total privado elegível e soma por divisão versus total;
- cobertura das 27 UFs no insumo nacional;
- inspeção dos maiores volumes excluídos e, em especial, Brasília, capitais e
  municípios com elevada presença de administração pública;
- ausência de divisão 84 e de Natureza Jurídica grupo 1 após o filtro.

Os testes automatizados incluem um caso explícito de Brasília e casos de
exclusão por cada uma das duas regras. Totais reais e
casos extremos devem constar no `qa.json` gerado pela execução integral; não são
inventados enquanto o arquivo oficial não tiver sido processado.

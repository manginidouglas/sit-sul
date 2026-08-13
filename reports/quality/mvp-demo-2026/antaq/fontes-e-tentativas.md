# ANTAQ — fontes, materialização e QA (INF-LOG-04)

**Investigação:** 12–13/08/2026. **Janela ideal:** 12 meses completos mais recentes até 12/08/2026. **Vintage efetivamente materializado:** ano oficial completo de 2025 (01/01–31/12/2025), porque o bulk mensal atual não foi recuperável.

## Tentativas oficiais

| recurso oficial | HTTP / tipo / tamanho | redirects | resultado |
|---|---|---|---|
| `https://estatistica.antaq.gov.br/` e `/ea/sense/download.html` | 403 Cloudflare; HTML ~5,6 kB | o `/` redirecionou à página ANTAQ que informa painel indisponível | rejeitado: desafio automatizado, sem bulk |
| `https://aquarela.antaq.gov.br/` | 200; Qlik HTML 1.907 B | `/` → `/hub/` | painel localizado; não é artefato tabular |
| links `single` do Aquarela publicados nas páginas ANTAQ | 403/400; HTML | sem download | Qlik não forneceu exportação reproduzível sem sessão |
| dados.gov.br, `anuario-estatistico-aquaviario` | página 200, HTML 9.632 B; API de metadados 401, vazia | nenhum | catálogo localizado; recursos não enumeráveis pela API no ambiente |
| `https://web3.antaq.gov.br/ea/sense/download.html` | 503, texto 22 B | nenhum | legado indisponível; não usado como fonte principal |
| página oficial `informacoes-geograficas` | 200, HTML 174.173 B | nenhum | descobriu o ZIP nominal oficial |
| `Instalaesporturias06052025.zip` | 200, ZIP 518.623 B | nenhum | aceito; SHA-256 `79e28332...040fb63`; inclui `Portos.xlsx`, SHP, DBF e KML |
| página oficial de Estatísticos Aquaviários | 200, HTML | nenhum | descobriu `Anuario2025.pdf` |
| `Anuario2025.pdf` | 200, PDF 6.318.182 B | nenhum | aceito; SHA-256 `75a258ba...961e2e`; p. 19 traz instalações e toneladas de milho/soja |
| páginas oficiais Portos, Instalações Privadas e painel privado | 200/403, HTML | nenhum | cadastro/painel investigados; sem segundo bulk exportável |

## Resultado e limite explícito

A camada operacional `data/interim/antaq/instalacoes_elegiveis_2025.csv` contém **sete portos organizados** com evidência oficial positiva de movimentação em 2025: Antonina, Imbituba, Itajaí, Paranaguá, Rio Grande, Santos e São Francisco do Sul. Quatro deles são comprovados nominalmente no Anuário ANTAQ 2025; Antonina, Itajaí e Imbituba são complementados por evidências institucionais oficiais das respectivas autoridades portuárias.

Esta é uma **camada conservadora, não exaustiva**. O Anuário não lista todas as instalações nem permite decidir todos os TUPs. Nenhum TUP foi incluído sem evidência oficial de carga geral/conteinerizada; ausência não equivale a inelegibilidade. O bloqueio do bulk detalhado permanece e impede afirmar que a base oficial nacional completa foi concluída. Navegantes/Portonave permanece TUP `indeterminado`.

## Schema, codificação e QA

O parser valida os campos reais de `Portos.xlsx`: `cdi_tuaria`, `nome`, `tipo`, `estado`, `cidade`, `latitude`, `longitude` e `fonte`. Como o XML do XLSX deste snapshot contém U+FFFD em textos acentuados, os valores são lidos do `Portos.dbf` companheiro, que preserva os bytes Windows-1252 e possui o mesmo número de linhas. A materialização falha se qualquer U+FFFD alcançar o output; o QA final registra `encoding_replacement_char_count = 0`.

O materializador processa 1.179 linhas cadastrais: 37 Portos Organizados, 259 TUPs e 883 registros de outras categorias. O resultado é: **7 elegíveis, 0 não elegíveis, 290 indeterminados e 882 fora do escopo**. A diferença entre 883 registros de outras categorias e 882 `fora_escopo_mvp` decorre do conflito cadastral `BRAM021`: suas duas linhas recebem UIDs internos distintos, são marcadas com `conflito_cadastral = true` e ficam `indeterminado`, sem possibilidade de entrar na elegibilidade ou no routing.

Há 1.162 registros com coordenadas válidas e 17 sem coordenadas válidas. `coordenada_valida` mede somente presença, numericidade e faixa. Como a camada não identifica os pontos como portões rodoviários oficiais, `ajuste_acesso_terrestre_onda2 = true` para todas as 1.179 linhas, inclusive quando a coordenada está ausente.

A p. 19 do Anuário evidencia somente milho e soja. Seu valor é armazenado como `movimentacao_evidenciada_t` com `escopo_movimentacao_evidenciada = "milho e soja"`; não é interpretado como tonelagem total do porto.

## Evidências institucionais complementares

A tabela versionada `data/raw/antaq/anuario-2025-evidencias.tsv` registra também: estatísticas operacionais de 2025 da Portos do Paraná para Antonina; relatório estatístico oficial de dezembro de 2025 da Superintendência do Porto de Itajaí; e a série anual da autoridade do Porto de Imbituba, que informa 7.071.663 toneladas em 2025. As duas primeiras comprovam movimentação positiva, mas seu valor não foi transcrito como tonelagem total; Imbituba possui valor e escopo total explícitos.

## Reprodução

Em clone limpo:

1. `python -m ice_sul.extract.antaq` baixa os binários ausentes, valida ZIP/PDF e confere os SHA-256 registrados;
2. `python -m ice_sul.transform.antaq_materialize` valida o manifesto, gera o universo avaliado, deriva a camada de elegíveis e atualiza o QA.

Os testes end-to-end usam fixtures locais e não dependem da presença dos binários oficiais no clone.

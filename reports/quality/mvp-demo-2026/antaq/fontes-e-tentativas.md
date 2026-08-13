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

A camada `data/interim/antaq/instalacoes_elegiveis_2025.csv` contém quatro portos organizados comprovadamente movimentados no ano completo de 2025: Paranaguá, São Francisco do Sul, Rio Grande e Santos (porto relevante próximo). Ela combina IDs e coordenadas do ZIP geográfico com valores nominais do Anuário. Todas as coordenadas são marcadas para ajuste terrestre na Onda 2, pois a camada não as descreve como portões.

Os dois raws binários usados na investigação (ZIP geográfico e PDF do Anuário) não são versionados no Git porque `data/raw/*` é deliberadamente ignorado pelo repositório. O manifesto registra URLs, tamanhos e SHA-256 para reprodução e validação local.

Esta é uma **camada conservadora, não exaustiva**. O Anuário não lista todas as instalações nem permite decidir todos os TUPs. Nenhum TUP foi incluído sem evidência oficial de carga geral/conteinerizada; ausência não equivale a inelegibilidade. O bloqueio do bulk detalhado permanece e impede afirmar que a base oficial nacional completa foi concluída.

## Schema e QA

O parser valida os campos reais de `Portos.xlsx`: `cdi_tuaria`, `nome`, `tipo`, `estado`, `cidade`, `latitude`, `longitude` e `fonte`. A evidência do PDF preserva nome, valor publicado, unidade e página; `mi t` é convertido por código. IDs duplicados conflitantes continuam bloqueando a transformação. QA nominal confirmou os três portos organizados do Sul presentes no gráfico e Santos. Antonina, Itajaí/Navegantes e Imbituba não aparecem nominalmente na evidência publicada e não foram presumidos.

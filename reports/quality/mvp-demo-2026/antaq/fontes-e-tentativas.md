# ANTAQ — fontes e tentativas (INF-LOG-04)

**Corte da investigação:** 12/08/2026. **Janela-alvo:** 12 meses completos mais recentes disponíveis no recurso oficial, nunca incluindo agosto de 2026. A transformação determina a janela pela última competência efetivamente presente e exige 12 competências contíguas.

## Endpoints oficiais tentados

| recurso | resultado em 12/08/2026 | decisão |
|---|---|---|
| `https://web3.antaq.gov.br/ea/sense/download.html` | HTTP 503 | `endpoint_review`; não prova indisponibilidade dos dados |
| `https://web3.antaq.gov.br/ea/sense/index.html` | HTTP 503 | painel interativo indisponível no teste |
| Catálogo Nacional de Dados, conjunto `anuario-estatistico-aquaviario` | página pública HTTP 200; API de metadados HTTP 401 | catálogo localizado, recurso bulk ainda não resolvido |
| caminhos públicos alternativos sob `web3.antaq.gov.br/ea/sense/download/` | HTTP 503 | sem artefato persistido; nomes de arquivo não presumidos |

Não foi possível obter com segurança o cadastro e as movimentações oficiais nesta execução. Portanto, **nenhuma tabela de instalações foi publicada em `data/interim`** e nenhuma coordenada foi inventada. O coletor fica preparado para receber a URL oficial do recurso quando identificada. Esta entrega não afirma uma lista oficial completa.

## Regra implementada

* porto organizado: qualquer tonelagem positiva na janela;
* TUP: tonelagem positiva de carga geral ou conteinerizada, sem mínimo;
* TUP apenas graneleiro/bulk: não elegível;
* cadastro sem tonelagem positiva: não elegível;
* coordenada que não esteja explicitamente referenciada ao acesso terrestre recebe marcação para ajuste na Onda 2; ela não é convertida em portão presumido.

## QA e bloqueio restante

Os casos determinísticos cobrem Porto de Paranaguá (porto organizado), TUP com carga geral, TUP exclusivamente graneleiro e cadastro sem movimentação. Isso verifica a regra, não substitui a conferência manual na fonte. A investigação nominal de Paranaguá, Antonina, São Francisco do Sul, Itajaí/Navegantes, Imbituba, Rio Grande e portos próximos deve ocorrer após o bulk oficial ser obtido. IDs duplicados idênticos são consolidados; atributos conflitantes para o mesmo ID bloqueiam a transformação.

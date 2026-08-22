# Fontes e períodos — registro de verificação

**Data de corte:** 12/08/2026. **Data desta revisão:** 12/08/2026.

Uma fonte só muda para `apta` depois de confirmação de esquema, licença, cobertura, período, amostra manual, hash e quebra de série. O 401 anterior veio da chamada `web__run` da ferramenta intermediária de pesquisa, antes de uma fonte oficial. Em 12/08/2026 ele não se reproduziu por HTTP direto: a API de Localidades do IBGE respondeu 200, sem redirects, tanto por `curl` quanto por Python `requests` (JSON, 170.538 bytes). Há proxy HTTP/HTTPS no ambiente, com valores redigidos, mas ele não bloqueia GET direto. Classificação: `erro_ferramenta_intermediaria`; solução: coletores acessam endpoints oficiais diretamente. Evidência completa em `reports/quality/mvp-demo-2026/network-preflight.json`.

| Indicadores | Fonte pública primária | Período exigido | Estado |
|---|---|---|---|
| INF-DIG-01–03 | Anatel, Dados Abertos, acessos SCM | mesmo mês mais recente até o corte | pendente de amostra/esquema |
| INF-DIG-04–05 | Anatel, cobertura móvel | mais recente até o corte | pendente de amostra/esquema |
| INF-ENE-01–02 | ANEEL, IndQual/INDGER/BDGD | ano completo 2025 | pendente de territorialização |
| INF-LOG-01 | DNIT/SNV, DER/PR, SIE/SC, DAER/RS; OSM/OSRM | snapshots congelados | pendente de snapshots/rotas |
| INF-LOG-02–03 | ANAC, aeródromos e voos realizados | 12 meses completos mais recentes | pendente de elegibilidade/rotas |
| INF-LOG-04 | ANTAQ, instalações e Estatístico Aquaviário | 12 meses completos mais recentes | pendente de elegibilidade/rotas |
| MER-01 | IBGE Censo 2022, PNAD Contínua e população | últimas PNAD/população até o corte | pendente de extração/rotas Brasil |
| MER-02 e DIAG-01 | MTE, RAIS | microdados 2024 (mais recentes tecnicamente confirmados até o corte) | em_verificacao — De-Para validado; listagem e microdados VINC_PUB bloqueados no ambiente |
| MER-DIAG-02 | RFB, Dados Abertos CNPJ; IBGE | snapshot mais recente/população 18–64 | pendente de extração |
| MER-DIAG-03 | IBGE/SIDRA, PIB e deflator nacional | três anos comparáveis mais recentes | pendente de extração |

SCM deve documentar unidade da velocidade, códigos de fibra e prestador/grupo. Voos são regulares de passageiros realizados em ao menos seis meses. Portos precisam de carga efetiva; TUPs entram somente com carga geral/conteinerizada. RAIS deve excluir administração pública por regra reproduzível. Cada raw precisa de URL, parâmetros, horário UTC, status HTTP, tamanho, SHA-256, licença e versão.

Para RAIS, a página de resultados estatísticos 2025 existia até o corte, mas não
foi tomada como prova de microdados 2025 completos. O comunicado oficial de
microdados e o De-Para efetivamente identificados são da edição 2024. Assim,
“mais recente disponível” significa aqui a edição mais recente cujo recurso
individual VINC_PUB e esquema podem ser tecnicamente sustentados, não o ano mais
recente exibido em uma publicação agregada. A decisão e as tentativas oficiais
estão em `reports/quality/mvp-demo-2026/rais/`. O De-Para confirma os nomes e o
nível classe de `cnae20classecódigo`; a largura de cinco dígitos segue a estrutura
oficial CNAE. O workbook não informa largura/domínio de ativo, município ou
Natureza Jurídica, que permanecem contratos operacionais ainda não confrontados
com `.comt` real. A quantidade e a partição territorial dos arquivos também não
foram observadas: o coletor valida cobertura das 27 UFs e foi exercitado offline
com topologias estadual, regional e nacional, sem afirmar qual delas corresponde
à publicação RAIS 2024.

## Preflight das instituições em 12/08/2026

GET direto retornou 200 para páginas oficiais de Anatel, ANEEL e ANAC e para a API SIDRA. O portal interativo da ANTAQ retornou 503 e `servicos.dnit.gov.br/dadosabertos` retornou 503; são respostas específicas dos endpoints, não evidência de bloqueio geral. O caminho testado da RFB retornou 404 e foi classificado `endpoint_em_revisao`, não restrição de acesso. A amostra real do cadastro IBGE/PR foi coletada em raw imutável e manifestada; ela é controle de infraestrutura, não indicador do MVP. A identificação e validação dos bulk downloads de cada indicador permanece necessária antes de afirmar cobertura.

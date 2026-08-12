# Fontes e períodos — registro de verificação

**Data de corte:** 12/08/2026. **Data desta revisão:** 12/08/2026.

Uma fonte só muda para `apta` depois de confirmação de esquema, licença, cobertura, período, amostra manual (capital e município pequeno nas três UFs), hash e quebra de série. Nesta execução, o acesso automatizado à pesquisa externa respondeu HTTP 401; nenhuma disponibilidade na data de corte foi presumida e nenhum dado foi fabricado.

| Indicadores | Fonte pública primária | Período exigido | Estado |
|---|---|---|---|
| INF-DIG-01–03 | Anatel, Dados Abertos, acessos SCM | mesmo mês mais recente até o corte | pendente de amostra/esquema |
| INF-DIG-04–05 | Anatel, cobertura móvel | mais recente até o corte | pendente de amostra/esquema |
| INF-ENE-01–02 | ANEEL, IndQual/INDGER/BDGD | ano completo 2025 | pendente de territorialização |
| INF-LOG-01 | DNIT/SNV, DER/PR, SIE/SC, DAER/RS; OSM/OSRM | snapshots congelados | pendente de snapshots/rotas |
| INF-LOG-02–03 | ANAC, aeródromos e voos realizados | 12 meses completos mais recentes | pendente de elegibilidade/rotas |
| INF-LOG-04 | ANTAQ, instalações e Estatístico Aquaviário | 12 meses completos mais recentes | pendente de elegibilidade/rotas |
| MER-01 | IBGE Censo 2022, PNAD Contínua e população | últimas PNAD/população até o corte | pendente de extração/rotas Brasil |
| MER-02 e DIAG-01 | MTE, RAIS | edição mais recente disponível | pendente de filtro público/rotas |
| MER-DIAG-02 | RFB, Dados Abertos CNPJ; IBGE | snapshot mais recente/população 18–64 | pendente de extração |
| MER-DIAG-03 | IBGE/SIDRA, PIB e deflator nacional | três anos comparáveis mais recentes | pendente de extração |

SCM deve documentar unidade da velocidade, códigos de fibra e prestador/grupo. Voos são regulares de passageiros realizados em ao menos seis meses. Portos precisam de carga efetiva; TUPs entram somente com carga geral/conteinerizada. RAIS deve excluir administração pública por regra reproduzível. Cada raw precisa de URL, parâmetros, horário UTC, status HTTP, tamanho, SHA-256, licença e versão.

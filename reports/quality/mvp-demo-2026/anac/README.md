# ANAC — Onda 1 (INF-LOG-02 e INF-LOG-03)

## Snapshot oficial completo

A edição congela `Dados_Estatisticos.csv` (`Atualizado em: 2026-08-09`,
357.795.130 bytes) e a janela **2025-07 a 2026-06**. O materializador valida em
streaming cada SHA-256 contra `frozen-snapshot.json`; reuso preserva coleta,
URL final, redirects, ETag e Last-Modified e registra revalidação separadamente.

Os recursos descobertos pelas páginas V2 e processados integralmente são:

| recurso | vintage | registros brutos | promovidos | exclusão |
|---|---|---:|---:|---|
| aeródromos públicos | 2026-08-15 | 496 | 496 | 0 |
| aeródromos privativos | 2026-08-18 | 3.863 | 3.863 | 0 |
| helipontos | 2026-08-18 | 1.598 | 0 | 1.598 pelo tipo HELIPONTO |
| helidecks | 2026-08-18 | 203 | 0 | 203 pelo tipo HELIDECK |
| SIROS | HTTP 2026-08-17 | 10.560 | diagnóstico | não é cadastro substituto |

O catálogo unificado possui **4.359 aeródromos**. CIAD é preservado em todos os
registros. O cadastro privativo não publica situação ou validade; portanto esses
campos permanecem vazios em vez de receber `ATIVO` ou outra invenção. O tipo
`AERODROMO` decorre do recurso oficial separado por infraestrutura, e a versão é
a primeira linha oficial `Atualizado em`, nunca o grupo do cabeçalho. Três OACI
ambíguos no próprio recurso (SS3G, SS7V e SD09) usam CIAD como identificador
canônico e não geram alias OACI destrutivo.

## Movimentos, reconciliação e elegibilidade

As 1.093.296 linhas são processadas em duas passagens streaming, sem
`list(reader)`: inspeção de versão/schema/meses/total e releitura para filtros e
agregações. Aplicam-se `GRUPO_DE_VOO=REGULAR`, assentos ou passageiros positivos,
`DECOLAGENS>0`, origem brasileira ligada, coordenadas válidas e seis meses. O
destino é primeiro resolvido pelo catálogo; somente depois país/UF o classificam.
As identidades de linhas e decolagens estão verdadeiras em `qa.json`, não há
origem brasileira relevante sem ligação e `coverage_complete=true`.

O resultado final é **137 elegíveis: 134 públicos e 3 privativos**. A regra
operacional isolada encontra 138; somente SNVS é retido pelo portão de situação
cadastral. Isso resulta
naturalmente da fonte completa, não de seleção prévia:

| código | CIAD | operador oficial observado | rotas observadas | meses | decolagens | decisão |
|---|---|---|---|---:|---:|---|
| SDLO | BA0074 | ATA — Aerotáxi Abaeté Ltda. | SDLO–SBSV; SDLO–SNCL | 10 | 69 | elegível |
| SNCL | BA0131 | ATA — Aerotáxi Abaeté Ltda. | SNCL–SBSV; SNCL–SDLO | 11 | 572 | elegível |
| SSOU | MT0303 | Azul Conecta Ltda. | SSOU–SBCY; SSOU–SBVH | 12 | 236 | elegível |

A evidência é reproduzível no próprio arquivo oficial: operador identificado,
grupo regular, oferta/uso de passageiros, decolagens positivas e rotas. Isso
demonstra serviço comercial regular acessível mediante contratação do transporte,
embora o sítio aeroportuário seja privativo. Logo, não se excluiu por cadastro
privativo nem se incluiu por mera existência física. O impacto ante os 135 é
**+3 aeroportos privativos e +877 decolagens**. Depois do portão, o total final
é um abaixo dos 138 operacionais e dois acima dos 135 publicados anteriormente.

## Situação, validade e corte temporal

Os cadastros de 15/08 e 18/08 são posteriores ao corte de **12/08/2026** e são
marcados `cadastro_pos_corte=true`. Eles funcionam como crosswalk auxiliar e não
como afirmação silenciosa da situação no corte. `Situação=Interditado` significa
que o recurso oficial posterior registra incompatibilidade com operação;
`Validade do Registro` é preservada literalmente como metadado histórico. Sob a
**Resolução ANAC nº 736, de 9/2/2024, arts. 5º, 7º, 8º e 10**, inscrições antes
sujeitas a prazo passaram ao regime por tempo indeterminado. Assim, data antiga
isolada não bloqueia `Situação=Cadastrado`; apenas evidência oficial específica
de cancelamento, exclusão, suspensão ou interdição bloqueia ou torna o caso
indeterminado.
Fonte normativa oficial: `https://www.anac.gov.br/assuntos/legislacao/legislacao-1/resolucoes/2024/resolucao-736`.

| código | evidência pós-corte | decisão no corte |
|---|---|---|
| SNVS | Interditado; validade 28/03/2026 | inelegível, data da interdição não reconstruível |
| SBCA | Cadastrado; validade histórica 20/11/2025 | elegível; data não bloqueante |
| SBDN | Cadastrado; validade histórica 09/05/2026 | elegível; data não bloqueante |
| SBRJ | Cadastrado; validade histórica 11/07/2024 | elegível; data não bloqueante |
| SBTU | Cadastrado; validade histórica 23/07/2026 | elegível; data não bloqueante |
| SJZA | Cadastrado; validade histórica 17/03/2026 | elegível; data não bloqueante |
| SNGI | Cadastrado; validade histórica 08/07/2025 | elegível; data não bloqueante |
| SNPD | Cadastrado; validade histórica 15/03/2026 | elegível; data não bloqueante |

Os três privativos permanecem elegíveis porque, além da regra operacional, têm
operador identificado e rotas com serviço regular de passageiros e decolagens
positivas. Um privativo operacional sem operador ou rota fica com
`indeterminado_servico_comercial` e `elegivel=false`; não existe combinação
`elegivel=true` com `acesso_publico_status=nao_demonstrado`.

## Reprodutibilidade e publicação

O coletor baixa público, privativo, helipontos, helidecks, movimentos e SIROS,
valida antes da promoção e manifesta os seis raws. `.part` sem sidecar contendo
ETag ou Last-Modified é descartado. A publicação prepara o conjunto, valida tudo
e mantém backups para rollback se qualquer troca falhar. Relatórios vazios
mantêm cabeçalhos estáveis e todos os CSV usam LF.

Uma integração materializa os mesmos raws em duas raízes distintas, fixa apenas
o instante comum da execução e compara byte a byte todos os produtos. Caminhos
persistidos são lógicos (`data/raw/anac/...`), enquanto cada execução real gera
uma nova `data_revalidacao_utc`; coleta e metadados HTTP originais não mudam.

## INF-LOG-03 e OSRM

`score_exploratorio_frequencia_diversidade` continua exploratório. A evidência
OSRM inclui municípios/aeroportos e coordenadas em ordem lon/lat, servidor,
perfil, parâmetros, horário, resposta, SHA-256 e distâncias de snapping. O
servidor público não representa snapshot Brasil congelado; não há indicador
municipal definitivo nem fórmula congelada de INF-LOG-03.

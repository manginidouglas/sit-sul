# ExecPlan — CNPJ/RFB Onda 1

## Objetivo e aceitação
Finalizar no PR 12 um coletor reiniciável e uma transformação municipal auditável para o numerador de MER-DIAG-02 e diagnósticos MEI/não estatal. A entrega integral requer snapshot oficial anterior ao corte, bulk completo, 1.191 municípios e QA real; se a fonte continuar indisponível, código/testes independentes e evidência devem ficar completos, sem produto ou cobertura falsos e com PR draft.

## Contexto e estado inicial
Base remota observada: `533bc3e9aaa9acbe62f6c1d50178d77483da2cae`. Head remoto original do PR: `155acfa8499165911651978636ab1724fd37a4b2`, preservado em `backup/pr12-remote-155acfa`. O PR remoto está aberto/draft, com quatro arquivos e um commit, 33 commits atrás da integração. A branch foi reconstruída linearmente pela reaplicação do único commit sobre a integração.

O protótipo não implementa Collector/CollectionResult, não coleta Empresas/Naturezas, não possui identidade segura de parciais, trata ausência de Simples como não-MEI e não publica um conjunto transacional.

## Marcos e progresso
- [x] instruções, documentos normativos, catálogo e PR remoto inspecionados.
- [x] backup do head remoto e reconstrução sobre integração atual.
- [ ] evidência oficial de snapshot/topologia/layout congelada.
- [ ] coletor, manifesto e retomada seguros.
- [ ] transformação/QA/publicação transacional.
- [ ] testes offline substantivos.
- [ ] tentativa e, se possível, processamento real.
- [ ] validação, commit, push e PR atualizado.

## Decisões, descobertas e recuperação
A atualizar durante a execução. Raw validado é imutável; parcial só será retomado com identidade de representação comprovada. Outputs serão preparados em diretório de geração e promovidos com rollback integral.

## Validação
`pytest -q tests/test_cnpj.py`; `pytest -q`; `python -m compileall -q src tests scripts`; `git diff --check`; tentativa real e inspeção do diff/histórico.

## Atualização final observada

A documentação oficial foi coletada (PDF de 59.315 bytes, SHA-256 `0a52d6bdfb61a07425e352a0e692932306a5ec9ecad682f5f9e28059e1a5fce0`) e confirma layout 8+4+2, ativo conceitual `2`, delimitador `;` e MEI `S`/`N`/branco. O catálogo oficial respondeu 200. O índice bulk candidato 2026-07 respondeu 503 em quatro tentativas com backoff; o endpoint legado respondeu 404. Logo snapshot, topologia, vintage e domínios raw permanecem não confirmados.

Decisões: ativo compara o valor raw normalizado sem zeros à esquerda com `2` e registra o domínio bruto; MEI é somente `S`; `sem_mei_identificado` é total menos `S` (inclui `N` e branco/OUTROS), mas ausência de join bloqueia; proxy não estatal inclui grupos 2/3/4, exceto 201-1 e 203-8, exclui grupo 1 e grupo 5 e é descrita como proxy, não controle perfeito.

- [x] documentação/layout oficial congelados com hash.
- [x] coletor, manifesto, identidade de parcial, reuso e retries implementados.
- [x] transformação, bridge, QA e rollback integral implementados.
- [x] testes offline substantivos concluídos.
- [x] tentativa real com retries registrada.
- [ ] bulk/topologia/processamento/QA real: bloqueados por HTTP 503 oficial.
- [ ] ready for review: proibido enquanto a materialização real estiver bloqueada.

A recuperação preserva checkpoints por artefato. O próximo comando está no README. Este ExecPlan tem valor de auditoria para explicar a decisão temporal e permanece no diff.

## Validação final local

- `pytest -q tests/test_cnpj.py`: 25 passed.
- `pytest -q`: 287 passed.
- `python -m compileall -q src tests scripts`: passou.
- `git diff --check`: passou.
- Espaço observado antes da coleta: 29 GiB; memória disponível: 17 GiB.
- Branch local: zero commits atrás da integração observada; histórico sem merge novo.

Resultado: condição de bloqueio externo. Não existem contagens, cobertura municipal materializada nem sanity checks reais porque o índice não expôs a listagem. O PR deve permanecer draft.

## Revisão complementar — CNPJ alfanumérico e durabilidade

A pesquisa oficial contemporânea corrigiu uma omissão bloqueante: a página da
RFB registra produção em 27/07/2026 e primeiro CNPJ alfanumérico em 31/07/2026;
o FAQ oficial confirma coexistência e 12 primeiras posições A-Z/0-9, com dois
DVs numéricos. O identificador permanece texto e os testes cobrem legado, ordem
E08G, raiz alfanumérica e caracteres/DV inválidos.

A janela raw-promovido/manifesto foi eliminada por receipt atômico por artefato:
o receipt `validated_part` precede a promoção e é finalizado como `promoted`.
Qualquer queda entre promoção e journal permite revalidar hash/tamanho/ZIP e
reusar o raw sem sobrescrita ou rede. IncompleteRead, reset e demais falhas de
rede plausíveis são `unavailable` e preservam parcial com identidade.

Cada entrada agora contém proveniência contratual completa; licença permanece
`null` com `license_status=not_confirmed_in_official_material_reviewed`, sem
inventar licença. Snapshot alternativo deriva seu destino por padrão. Erros bulk
usam contagem e no máximo 20 amostras. O output longo foi removido até a
integração do denominador IBGE. Após descoberta, HEAD/Content-Length alimenta
preflight conservador de raw + SQLite + staging e bloqueia volume conhecido
maior que o disco livre.

## Resultado da revisão complementar

Validações após as correções: `pytest -q tests/test_cnpj.py` 36 passed;
`pytest -q` 298 passed; compileall e diff-check passaram. Nova tentativa real em
22/08/2026, com quatro respostas 503 e backoff, manteve `coverage_complete=false`.
Logo não há topologia/contagens/1.191 linhas reais nem sanity checks a declarar e
o PR permanece draft.

## Pre-mortem adversarial final

Mesmo com testes verdes, o desenho anterior poderia falhar por quatro motivos
substantivos encontrados: materializava Empresas/Simples nacionais; um `.part`
completo antes de promoção ainda exigia rede; publicação só revertia exceções
Python, não término abrupto; normalizadores aceitavam valores malformados como
`0002`/prefixos em Natureza. Todos viraram correções e regressões.

O fluxo agora reduz primeiro por ativo+Sul, persiste apenas raízes relacionadas e
filtra passes nacionais em lotes SQLite. Há preflight em duas fases com tamanhos
comprimidos e, depois, tamanhos ZIP descomprimidos reais. Receipt recupera tanto
`validated_part` quanto raw promovido. Journal de publicação permite rollback na
execução seguinte após BaseException. Domínios e Naturezas usam formatos
explícitos, sem normalização permissiva.

A investigação oficial adicional cobriu: diretório RFB; URLs diagnósticas de
Estabelecimentos/Empresas/Simples/Municipios/Naturezas (todas 503, sem inferir
existência/topologia); host legado (404); página dados.gov.br (200 sem recursos);
API pública e CKAN em dados.gov.br (401); variante www (502/DNS do proxy). Não há
outro transporte oficial identificado cuja identidade do snapshot possa ser
sustentada. O bloqueio permanece externo.

## Fechamento adversarial

A última rodada passou com 47 testes CNPJ e 309 testes totais. A tentativa final
do coletor repetiu quatro respostas HTTP 503 e manteve `coverage_complete=false`.
A arquitetura de escala foi efetivamente alterada; fixture sintética com 1.000
raízes nacionais irrelevantes prova que são lidas para QA, mas somente três raízes
ativas necessárias são persistidas. Isso demonstra a propriedade de redução, não
finge medir o volume oficial ainda inacessível.

## Revisão final — fronteira de commit

O último pre-mortem encontrou a janela entre promoção completa e destruição de
backups: sem decisão de commit, uma queda após apagar parte dos backups tornaria
o rollback impossível. O protocolo agora grava atomicamente `committed` antes da
primeira remoção. Recovery de `promoting` escolhe a geração antiga; recovery de
`committed` escolhe a nova e termina a limpeza. Regressões cobrem BaseException
durante promoção, depois do movimento de backup e durante limpeza parcial.

Também foi corrigido o primeiro uso: storage preflight cria o destino derivado do
snapshot antes de `disk_usage`. Checkout limpo não vira bloqueio ambiental por
diretório ausente.

A verificação externa final foi deliberadamente limitada a duas tentativas; ambas
retornaram HTTP 503. `coverage_complete=false` e o PR permanece draft.

## Último pre-mortem de crash consistency

Foi confirmado o contraexemplo final: recovery apenas dentro de `promote_outputs`
era tarde demais se a execução seguinte falhasse na validação. `build_numerators`
agora resolve o journal na primeira instrução operacional, antes de manifesto,
preflight, raws ou staging. A regressão deixa uma geração `promoting`, inicia nova
materialização com manifesto inexistente e prova que os três outputs antigos já
foram restaurados apesar da falha precoce. Não foi encontrada outra fronteira de
crash equivalente: checkpoints do journal são atômicos; `promoting` mantém
backups recuperáveis; `committed` só existe depois de todos os novos outputs; e
backups só são destruídos após essa decisão durável.

Verificação curta final via curl: HTTP 503 em 2026-08-22T14:39:53Z; nenhuma mudança de estado da fonte.

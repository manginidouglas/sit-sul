# CNPJ/RFB — numeradores de MER-DIAG-02 e diagnóstico MER-02

## Estado da fonte em 22/08/2026

O catálogo oficial do CNPJ em `dados.gov.br` respondeu HTTP 200 e o PDF oficial
do leiaute respondeu HTTP 200. O índice bulk candidato
`https://dadosabertos.rfb.gov.br/CNPJ/dados_abertos_cnpj/2026-07/`, entretanto,
permaneceu em HTTP 503; a verificação final limitada repetiu duas tentativas com backoff. O endereço legado testado
respondeu 404. As respostas e os metadados estão em `source-verification.json` e
`collection-latest.json`.

Consequentemente, **2026-07 continua candidato não confirmado**: não foi possível
observar sua listagem, topologia, `Last-Modified`, bytes ou domínios reais. Não há
manifesto completo, raw promovido, produto municipal nem contagem real. O PR deve
permanecer draft e `coverage_complete` permanece falso.

## Contratos implementados

O coletor exige, sem quantidade prefixada, sequências contíguas iniciadas em zero
para `Estabelecimentos` e `Empresas` e singletons únicos `Simples`, `Municipios` e
`Naturezas`. Cada ZIP validado gera checkpoint atômico com URL, URL final, HTTP,
ETag, Last-Modified, tamanho, SHA-256 e topologia. Raw só é reutilizado quando
bytes, hash e ZIP coincidem com o manifesto.

Um `.part` somente é concatenado se um ETag ou Last-Modified persistido, enviado
em `If-Range`, coincidir com resposta HTTP 206 e `Content-Range` no offset e total
esperados. Sem identidade demonstrável, o parcial é descartado; se o servidor
ignora Range e devolve 200, a representação é regravada desde o início.

A transformação só aceita manifesto `complete`, `coverage_complete=true`,
proveniência completa, topologia congelada, hashes, tamanhos e ZIPs válidos. O
leiaute oficial sustenta CNPJ completo 8+4+2, situação ativa conceitual `2` e
`OPÇÃO PELO MEI` com `S`, `N` e branco/OUTROS. A implementação aceita a
representação raw `2` ou `02`, registra o domínio bruto e só conta `S` como MEI.
A medida `sem_mei_identificado` significa total menos MEIs identificados e inclui
`N` e branco/OUTROS; raiz ativa ausente no Simples bloqueia publicação.

A proxy `nao_estatal_proxy` usa Natureza Jurídica: grupo 1, Empresa Pública
`201-1` e Sociedade de Economia Mista `203-8` ficam fora; grupos 2 (exceto essas
entidades), 3 e 4 entram; grupo 5 fica explicitamente fora. Essa é uma proxy de
“não estatal identificável por Natureza Jurídica”, não prova perfeita de controle
e não é automaticamente equivalente ao filtro de emprego privado da RAIS.

A bridge parte de `UF observada + código municipal RFB`, obtém o nome no domínio
RFB e exige correspondência única por nome normalizado + UF no cadastro IBGE. O
conjunto final exige exatamente 1.191 IDs canônicos (PR 399, SC 295, RS 497).
Zero só é emitido depois de cobertura, joins, bridge e reconciliações completos.
As três saídas (base larga, bridge e QA) são preparadas juntas e a promoção restaura integralmente a
versão anterior se qualquer `replace` intermediário falhar.

Próximo comando operacional exato:

```bash
PYTHONPATH=src python -c 'from ice_sul.extract.cnpj import CNPJCollector; print(CNPJCollector().collect().as_dict())'
```

O denominador população 18–64 e a densidade final de MER-DIAG-02 não pertencem a
esta frente.

## Compatibilidade com CNPJ alfanumérico

A revisão contemporânea identificou a página oficial do programa CNPJ
Alfanumérico e o FAQ oficial. A cronologia da RFB registra entrada dos sistemas
em produção em 27/07/2026 e implementação do primeiro CNPJ alfanumérico em
31/07/2026, antes do corte. O FAQ confirma coexistência dos formatos: as oito
posições da raiz e quatro da ordem aceitam `A-Z` ou `0-9`; os dois DVs continuam
numéricos. O identificador é sempre texto, preservando letras e zeros. Assim, o
pipeline aceita tanto o legado numérico quanto casos como
`00.000.000/E08G-12` e raízes alfanuméricas, rejeitando pontuação, símbolos,
minúsculas e DV não numérico. URLs, tamanhos e hashes dos documentos oficiais
estão em `source-verification.json`.

## Produto publicado

A saída desta frente é somente a base-fonte municipal larga e sua bridge/QA. Não
é gerado CSV longo nem `indicador_id`: a materialização longa de MER-DIAG-02
ocorrerá apenas quando o denominador IBGE 18–64 for integrado.

A revisão não confirmou uma licença explícita nos materiais oficiais examinados.
Por isso, manifesto e receipts registram `license=null` e
`license_status=not_confirmed_in_official_material_reviewed`, em vez de atribuir
uma licença genérica.

## Escala e recuperação — revisão adversarial

O processamento foi reordenado: primeiro lê `Estabelecimentos` em streaming e
persiste somente CNPJs ativos de PR/SC/RS e suas raízes. `Simples` e `Empresas`
continuam sendo varridos integralmente para domínios/QA, mas lotes de 50 mil são
filtrados em SQLite contra `active_roots`; linhas nacionais irrelevantes nunca
entram nas tabelas persistentes. Isso remove o maior risco do desenho anterior,
que materializava tabelas nacionais completas.

O preflight de coleta usa `Content-Length` para raw + maior `.part` + reserva de
8 GiB para scratch + 1 GiB de margem. Após download, o preflight de transformação
usa o tamanho descomprimido real dos ZIPs `Estabelecimentos` e reserva 20% para
SQLite/WAL/índices mais 1 GiB. A hipótese e os bytes livres ficam no QA; se o
valor conhecido não couber, a execução bloqueia. Essa estimativa não é apresentada
como medição do bulk enquanto a listagem estiver inacessível.

Receipts também recuperam um `.part` já completo/validado antes da promoção sem
rede. A publicação mantém journal durável; se o processo terminar entre replaces,
a próxima execução restaura todos os outputs anteriores antes de iniciar outra
geração. Normalizadores agora rejeitam, em vez de corrigir silenciosamente,
situação `0002`, MEI minúsculo, Natureza com prefixos/sufixos e códigos municipais
fora do esquema.

Foram tentados o diretório e recursos diagnósticos no host RFB, host legado,
página do catálogo, API pública atual, API CKAN compatível e variante `www`. Os
resultados estruturados estão em `source-verification.json`. Nenhuma rota oficial
expôs a listagem 2026-07, portanto a topologia continua não observada.

## Commit durável da publicação

O journal agora distingue duravelmente `promoting` de `committed`. Backups só
começam a ser removidos depois do checkpoint atômico `committed`. Na recuperação,
`promoting` escolhe integralmente a geração antiga; `committed` preserva
integralmente a geração nova e apenas conclui a limpeza remanescente. Assim, uma
queda depois de todos os replaces, durante qualquer remoção de backup ou antes de
apagar o journal não pode remover a geração nova nem criar mistura.

O preflight cria `data/raw/cnpj/<snapshot>` com `parents=True` antes de consultar
o filesystem. Portanto o primeiro uso em checkout limpo não depende da existência
prévia de diretórios específicos da fonte.

A materialização resolve o journal pendente como sua primeira operação, antes de
validar manifesto, executar preflight ou ler raws. Portanto, mesmo que a nova
execução falhe nessas etapas, a transação anterior já foi decidida e os três
produtos estão novamente em uma única geração coerente.

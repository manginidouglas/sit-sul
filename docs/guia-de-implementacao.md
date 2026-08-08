# SIT — Sistema de Inteligência Territorial — guia de implementação

## 1. Propósito, escopo e resultado esperado

O **SIT — Sistema de Inteligência Territorial** é um sistema municipal
multidimensional voltado a medir e organizar informações sobre as condições do
ambiente local que favorecem a criação, instalação, operação e desenvolvimento
de atividades empresariais nos municípios da Região Sul do Brasil. Seu propósito
é apoiar diagnóstico territorial e inteligência estratégica, permitindo
identificar vantagens, gargalos e diferenças entre municípios e regiões.

O SIT não é apenas um ranking. Pontuações sintéticas e rankings são produtos
possíveis, mas seu maior valor é a decomposição por eixo e indicador: uma leitura
como “infraestrutura e mercado fortes, mas capital humano fraco” é mais útil ao
diagnóstico que uma posição ordinal isolada.

O SIT:

- não mede desenvolvimento municipal em sentido amplo;
- não mede qualidade de vida de forma geral;
- não prevê o sucesso de uma empresa específica;
- não deve ser interpretado isoladamente como recomendação locacional de investimento.

O núcleo é geral, transversal, não setorial e não centrado em startups. Cada
edição terá versão, data de corte e metodologia congeladas. Alterações de fonte,
conceito, cobertura ou cálculo serão registradas.

## 2. Princípios do projeto

1. **Reprodutibilidade:** toda transformação relevante será executada por código.
2. **Rastreabilidade:** cada valor publicado apontará para fonte, variável,
   período e regra de transformação.
3. **Comparabilidade responsável:** indicadores só serão combinados depois de
   verificar unidade, direção, população de referência e período.
4. **Parcimônia:** um indicador só entra se acrescentar informação relevante e
   tiver qualidade e cobertura suficientes.
5. **Transparência:** valores ausentes, imputações, revisões e exceções não serão
   escondidos.
6. **Robustez:** decisões sobre extremos, padronização e pesos serão submetidas a
   análises de sensibilidade.
7. **Separação entre dado e método:** arquivos brutos são imutáveis; limpeza,
   normalização e agregação formam camadas distintas.

## 3. Universo municipal

### 3.1 Lista canônica

A primeira entrega de dados será uma tabela canônica dos municípios dos três
estados, obtida da API de Localidades do IBGE ou de outro arquivo oficial do
IBGE que esteja vigente na data de corte. A lista esperada deve ser validada
contra os totais oficiais, sem fixá-los como verdade dentro do código.

O identificador principal será o **código IBGE de sete dígitos**, armazenado
como texto para preservar zeros e impedir operações aritméticas acidentais. O
nome não será usado como chave. A tabela conterá, no mínimo:

| campo | tipo | descrição |
|---|---|---|
| `municipio_id` | string | código IBGE de sete dígitos |
| `municipio_nome` | string | nome oficial vigente |
| `uf_sigla` | categoria | `PR`, `SC` ou `RS` |
| `uf_codigo` | string | código da unidade da federação |
| `regiao_nome` | string | região geográfica |
| `mesorregiao` / `microrregiao` | string anulável | recortes legados, se necessários |
| `regiao_intermediaria` / `regiao_imediata` | string | recortes geográficos vigentes |
| `vigencia_inicio` | data | início conhecido da validade cadastral |
| `vigencia_fim` | data anulável | fim da validade, quando aplicável |
| `ativo_edicao` | booleano | participação no universo da edição |

### 3.2 Verificações da lista

O pipeline bloqueará a execução se houver código duplicado, código fora das UFs
selecionadas, chave vazia ou divergência não explicada em relação à fonte. Uma
revisão manual tratará mudanças territoriais, nomes homônimos, acentos e
eventuais alterações de código. Toda fonte posterior será ligada à tabela por
`municipio_id`; correspondências por nome ficarão em uma tabela explícita de
de/para, com justificativa e nunca como correção silenciosa.

## 4. Arquitetura conceitual dos indicadores

### 4.1 Hierarquia

O sistema terá quatro níveis possíveis:

1. **variável de origem:** campo extraído da fonte;
2. **indicador:** medida interpretável, já tratada (por exemplo, taxa por
   100 mil habitantes);
3. **eixo:** agregado temático de indicadores relacionados;
4. **síntese geral:** agregado opcional dos eixos, sem substituir sua decomposição.

A estrutura inicial aprovada compreende **Ambiente regulatório;
Infraestrutura e conectividade; Mercado; Acesso a capital; Capital humano; e
Inovação**. Cultura empreendedora, qualidade de vida e sustentabilidade podem ser
avaliadas, mas não integram automaticamente o núcleo. A escolha entre estoque
local e acesso territorial será feita indicador a indicador.

### 4.2 Ficha obrigatória de cada indicador

Antes da coleta em escala, cada indicador terá uma ficha no catálogo:

| grupo | campos mínimos |
|---|---|
| identidade | `indicador_id`, nome curto, nome de publicação, descrição, eixo |
| conceito | fenômeno medido, justificativa, interpretação, limitações |
| fonte | órgão, sistema, tabela/recurso, URL, licença, contato |
| recorte | unidade geográfica, população de referência, cobertura, periodicidade |
| tempo | ano/período do numerador, denominador e edição; defasagem aceita |
| cálculo | variáveis, fórmula, unidade, denominador e multiplicador |
| direção | `positiva` (maior é melhor) ou `negativa` (menor é melhor) |
| tratamento | filtros, categorias incluídas, extremos, ausentes e arredondamento |
| qualidade | cobertura mínima, validações, quebras de série e nível de confiança |
| governança | responsável, revisor, data da verificação e versão da ficha |

O formato analítico será longo: uma linha por `municipio_id`, `indicador_id` e
`periodo_referencia`. Além das chaves, preservará `valor_bruto`, `valor_tratado`,
`valor_padronizado`, unidade, direção, data de extração, versão da fonte e
marcadores como `ausente`, `imputado`, `winsorizado` e `suprimido_fonte`.

## 5. Revisão e seleção dos indicadores

Cada candidato passará por uma revisão em duas partes.

### 5.1 Revisão substantiva

- relação causal ou descritiva clara com o eixo;
- interpretação inequívoca da direção desejável;
- ausência de redundância conceitual com outros indicadores;
- adequação municipal e possibilidade de ação ou diagnóstico;
- denominador correto e comparável entre municípios de portes diferentes;
- risco de incentivos perversos ou leitura estigmatizante.

### 5.2 Revisão dos dados

- autoridade, estabilidade, licença e documentação da fonte;
- cobertura municipal e temporal nos três estados;
- granularidade, frequência de atualização e defasagem;
- consistência do conceito entre UFs e anos;
- volume de zeros, ausentes, supressões e valores extremos;
- volatilidade, especialmente em municípios pequenos;
- correlação entre candidatos e eventual dupla contagem do mesmo fenômeno;
- custo e possibilidade técnica de coleta automatizada.

Cada indicador receberá situação `proposto`, `em_verificacao`, `aprovado`,
`reserva` ou `rejeitado`, acompanhada de parecer. A seleção final procurará
equilíbrio entre relevância e qualidade, não uma quantidade idêntica de
indicadores por eixo. Indicadores correlacionados não serão excluídos
automaticamente: primeiro se verificará se medem conceitos distintos; caso
contrário, será mantido o mais claro, estável e atual.

## 6. Fontes, coleta e tratamento

Para cada fonte, faremos uma verificação externa antes de programar o coletor:
documentação, disponibilidade histórica, chaves municipais, formatos,
paginação, limites de API, licença, revisão retroativa e exemplos de valores.
Uma pequena amostra de municípios grandes e pequenos dos três estados será
conferida manualmente no sistema de origem.

Coletores serão idempotentes: a mesma entrada e os mesmos parâmetros produzirão
o mesmo arquivo. O arquivo recebido será guardado sem alteração, com URL,
parâmetros, horário, código de resposta e hash. Credenciais e arquivos grandes
não serão versionados no Git.

O tratamento seguirá esta ordem:

1. validar esquema e tipos da extração;
2. filtrar período, categorias e território conforme a ficha;
3. harmonizar códigos e ligar ao cadastro canônico;
4. distinguir zero verdadeiro, ausente e valor suprimido;
5. calcular taxas, proporções ou médias com seus denominadores;
6. verificar faixas, duplicidades, cobertura e consistência aritmética;
7. tratar extremos segundo a regra aprovada;
8. gerar tabela intermediária e relatório de qualidade.

Não haverá imputação automática como padrão. Se um indicador tiver cobertura
abaixo do limiar aprovado, ele será suspenso ou substituído. Quando a imputação
for indispensável, o método será simples, justificável, marcado linha a linha e
testado contra a alternativa de excluir e renormalizar os pesos disponíveis.

## 7. Padronização, extremos, pesos e agregação — decisões provisórias

O método definitivo de normalização e o tratamento definitivo de extremos serão
decididos somente depois da Etapa 2, quando forem conhecidas as distribuições do
conjunto provisório. Até lá, tratamento robusto e escala comparável são apenas
referências para testes; não há percentis ou método congelados.

Também permanecem referências provisórias, e não decisões finais, pesos iguais
entre indicadores e entre eixos e média aritmética. Serão comparados cenários e
avaliadas estabilidade por porte, mudanças de resultado e compensação entre
dimensões. A seleção conceitual não será orientada pelo efeito no ranking.

Não haverá imputação automática. Os limiares quantitativos de cobertura por
indicador, município e eixo, eventual renormalização dos itens disponíveis,
pesos e forma de agregação só serão definidos após observar cobertura e
comportamento reais. Ausência não será convertida em zero.

## 9. Estrutura do repositório

```text
sit-sul/                         # nome ilustrativo; o diretório técnico pode permanecer ice-sul
├── README.md
├── LICENSE
├── pyproject.toml
├── .env.example
├── .gitignore
├── config/
│   ├── edicoes/              # data de corte, universo e parâmetros por edição
│   ├── indicadores.yml       # catálogo legível por máquina
│   └── fontes.yml            # endpoints e metadados das fontes
├── data/
│   ├── raw/                  # cópias imutáveis (normalmente fora do Git)
│   ├── interim/              # dados harmonizados por fonte
│   ├── processed/            # indicadores prontos para cálculo
│   └── output/               # pontuações e tabelas publicáveis
├── docs/
│   ├── guia-de-implementacao.md
│   ├── decisoes-metodologicas-preliminares.md
│   ├── etapa-2-inventario-indicadores.md
│   ├── decisoes/             # registros de decisões metodológicas (ADRs)
│   ├── indicadores/          # fichas detalhadas
│   └── fontes/               # resultados das verificações externas
├── notebooks/                # exploração; nunca a única implementação
├── src/ice_sul/
│   ├── extract/              # um adaptador por fonte
│   ├── transform/            # limpeza e construção dos indicadores
│   ├── validate/             # contratos e testes de qualidade
│   ├── score/                # padronização, pesos e agregação
│   └── publish/              # tabelas, metadados e relatórios
├── scripts/                  # pontos de entrada operacionais curtos
├── tests/
│   ├── fixtures/             # amostras pequenas e versionadas
│   ├── unit/
│   ├── integration/
│   └── data_quality/
└── reports/
    ├── figures/
    └── quality/
```

Os caminhos e parâmetros entrarão em configuração, não espalhados pelo código.
Notebooks servirão para investigação e visualização; regras aprovadas migrarão
para `src/` e terão testes. Produtos grandes serão armazenados em repositório de
dados/artefatos ou regenerados pelo pipeline.

## 10. Etapas detalhadas de implementação

O trabalho avançará por portões de aprovação. Não iniciaremos coleta em escala
antes de concluir as decisões e validar uma fonte-piloto.

### Etapa 0 — decisões metodológicas preliminares — **concluída**

A referência normativa é
[`docs/decisoes-metodologicas-preliminares.md`](decisoes-metodologicas-preliminares.md).
Ela encerra formalmente a Etapa 0 e prevalece sobre formulações exploratórias
anteriores. Permanecem deliberadamente abertas, até depois do inventário da
Etapa 2, apenas decisões dependentes da evidência empírica: limiares
quantitativos de cobertura, normalização definitiva, tratamento definitivo de
extremos, pesos e forma definitiva de agregação.

**Saída concluída:** propósito, não-usos, universo, regra temporal, seis eixos,
princípios de seleção, política de ausentes e decisões provisórias versionadas.

### Etapa 1 — cadastro dos municípios — **concluída e preservada**

Foi implementada a extração oficial e construído o cadastro canônico dos 1.191
municípios, com código IBGE como identificador e testes de chaves, UFs,
duplicidades e contagens. O pipeline, seus testes, relatórios de qualidade e o
fallback geobr/Ipea documentado são preservados. Tabelas de aliases só serão
criadas para fontes que não forneçam código IBGE.

**Saída:** `municipios` versionado, relatório de validação e teste automatizado.

### Etapa 2 — inventário e revisão dos indicadores — **em andamento**

Produzir uma lista ampla de candidatos, preencher fichas, localizar fontes
primárias e avaliar mérito, redundância, cobertura e viabilidade. Montar uma
matriz `eixo × conceito × indicador` para revelar lacunas e excesso de medidas.

**Saída desta primeira rodada:** infraestrutura do catálogo, inventário amplo,
fontes primárias candidatas, matriz conceitual e relatório. A aprovação
substantiva continuará um eixo e um indicador por vez.

### Etapa 3 — verificação externa das fontes

Para cada candidato aprovado, consultar documentação e fonte real, registrar
URL e licença, baixar amostras e conferir manualmente municípios selecionados.
Testar estabilidade de endpoint, chaves, filtros, anos e totais. Questões serão
resolvidas uma fonte por vez; nenhuma suposição será incorporada silenciosamente.

**Saída:** relatório por fonte, amostra bruta, mapeamento de variáveis e decisão
`apta`, `apta com ressalvas` ou `inapta`.

### Etapa 4 — infraestrutura e contrato de dados

Criar pacote, ambiente reproduzível, configurações, logs, contratos de esquema,
testes e integração contínua. Definir manifesto de execução com versões de
código, configuração e entradas.

**Saída:** esqueleto executável e pipeline-piloto de ponta a ponta.

### Etapa 5 — coleta e harmonização

Construir um adaptador por fonte, guardar respostas brutas e metadados, normalizar
tipos e ligar ao cadastro municipal. Executar incrementalmente e gerar alertas
para mudanças de esquema ou cobertura.

**Saída:** camada `raw`, tabelas `interim` e logs auditáveis.

### Etapa 6 — construção e qualidade dos indicadores

Aplicar fórmulas aprovadas, denominadores e regras temporais. Validar faixas,
duplicidades, valores faltantes, extremos e consistência com totais publicados.
Comparar distribuições por UF e porte sem corrigir diferenças reais apenas por
parecerem incomuns.

**Saída:** camada `processed`, relatório de qualidade e aprovação de cada indicador.

### Etapa 7 — padronização

Depois de decisão metodológica baseada nas distribuições observadas, executar o
método aprovado, verificar direção e casos degenerados e gerar diagnósticos
antes/depois. Comparar alternativas pertinentes na análise de sensibilidade,
sem antecipar nesta fase quais métodos serão definitivos.

**Saída:** pontuações de 0 a 100, marcadores de tratamento e análise de sensibilidade.

### Etapa 8 — pesos, eixos e índice geral

Aplicar os pesos, limiares e forma de agregação que vierem a ser aprovados após
a Etapa 2; calcular e publicar cobertura efetiva. Comparar as referências
provisórias de pesos iguais e média aritmética com cenários alternativos na
análise de sensibilidade.

**Saída:** notas por eixo e geral, composição dos pesos e relatório de robustez.

### Etapa 9 — validação substantiva e auditoria

Investigar resultados inesperados, revisar amostras contra as fontes, realizar
revisão de código e obter avaliação de especialistas. Comparar o índice com
variáveis externas que não fizeram parte dele, sem confundir associação com
validação causal.

**Saída:** checklist assinado, pendências resolvidas e versão candidata.

### Etapa 10 — publicação

Publicar tabelas em formatos abertos, catálogo, metodologia, cobertura, data de
corte, limitações e changelog. Rankings sempre virão acompanhados das notas e
componentes; casas decimais excessivas não sugerirão falsa precisão.

**Saída:** release versionada, relatório, dicionário de dados e artefatos reproduzíveis.

### Etapa 11 — manutenção

Monitorar fontes, registrar quebras, atualizar a edição em branch própria e
reexecutar testes. Uma mudança metodológica relevante gera nova versão e, quando
possível, recálculo histórico para preservar comparabilidade.

**Saída:** calendário de atualização, responsáveis e protocolo de incidentes.

## 11. Garantia de qualidade e critérios de aceite

Testes unitários cobrirão fórmulas, inversão, limites e pesos; testes de integração
usarão amostras congeladas; testes de dados verificarão esquema, unicidade,
domínios, cobertura e variações anormais. A integração contínua não dependerá
das APIs externas: chamadas reais ocorrerão em rotina controlada, enquanto os
testes comuns usarão fixtures.

Uma edição só poderá ser publicada quando:

- todos os municípios elegíveis estiverem representados ou justificados;
- todas as fichas e fontes estiverem aprovadas e versionadas;
- cada indicador cumprir os limiares de cobertura e qualidade;
- direções e fórmulas tiverem revisão independente;
- pesos somarem 1 nos níveis aplicáveis;
- pontuações respeitarem os intervalos esperados;
- análises de sensibilidade e casos extremos estiverem documentados;
- o pipeline puder ser reproduzido em ambiente limpo;
- limitações e dados ausentes estiverem visíveis no produto final.

## 12. Governança das decisões

Cada decisão metodológica será um registro curto contendo contexto, opções,
escolha, justificativa, consequências, autor, revisores e data. Mudanças serão
feitas por revisão de código e vinculadas a uma edição. Papéis mínimos: gestão
do projeto prioriza e aceita entregas; responsável metodológico aprova conceitos;
engenharia mantém coletores e pipeline; revisão de dados confere qualidade; e
revisão externa avalia clareza e vieses.

O plano operacional é deliberadamente sequencial: as Etapas 0 e 1 estão
concluídas; na Etapa 2 revisaremos um eixo e um indicador por vez. As verificações externas orientarão o código de coleta, e
os resultados observados poderão devolver um indicador à revisão antes que ele
entre no índice.

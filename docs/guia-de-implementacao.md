# ICE Sul — guia de implementação

## 1. Propósito e resultado esperado

O ICE Sul será um índice municipal multidimensional para comparar condições
associadas ao desenvolvimento dos municípios do Paraná, de Santa Catarina e do
Rio Grande do Sul. O projeto transformará dados públicos de diferentes fontes
em indicadores comparáveis, os organizará em eixos temáticos e produzirá
pontuações por eixo e uma pontuação sintética geral.

O produto não será apenas um ranking. Ele deverá permitir:

- comparar municípios, eixos e indicadores em um mesmo período de referência;
- localizar forças, fragilidades e lacunas de dados de cada município;
- reproduzir cada resultado a partir das fontes originais;
- distinguir dado observado, dado tratado e pontuação calculada;
- atualizar a base sem refazer manualmente toda a análise;
- testar escolhas metodológicas e medir quanto elas alteram os resultados.

Cada edição terá versão, data de corte e metodologia congeladas. Alterações de
fonte, conceito, cobertura ou cálculo serão registradas, evitando que números
de edições diferentes pareçam comparáveis quando não forem.

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

O índice terá quatro níveis:

1. **variável de origem:** campo extraído da fonte;
2. **indicador:** medida interpretável, já tratada (por exemplo, taxa por
   100 mil habitantes);
3. **eixo:** agregado temático de indicadores relacionados;
4. **índice geral:** agregado dos eixos.

Os eixos e seus nomes serão definidos na etapa metodológica. Uma proposta
inicial para discussão é: **capital humano; dinamismo econômico; infraestrutura
e conectividade; instituições e ambiente de negócios; qualidade de vida e
sustentabilidade**. Essa taxonomia é hipótese de trabalho, não uma decisão já
tomada. A revisão deve evitar eixos sobrepostos e garantir que cada um represente
uma dimensão defensável.

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

## 7. Padronização dos indicadores

Indicadores têm unidades e amplitudes incompatíveis. A opção inicial equilibrada
será **winsorizar e aplicar min–max robusto**, sempre no conjunto completo dos
municípios dos três estados:

1. definir limites inferior e superior pelos percentis 2,5 e 97,5 de cada
   indicador (parâmetros configuráveis);
2. limitar valores fora desses pontos aos respectivos limites, sem apagar o
   valor bruto;
3. aplicar `100 × (x − limite_inferior) / (limite_superior − limite_inferior)`;
4. para indicadores negativos, inverter a escala: `100 − pontuação`;
5. limitar o resultado a `[0, 100]` e registrar todos os valores afetados.

Essa solução mantém leitura intuitiva, reduz a influência desproporcional de
extremos e não pressupõe distribuição normal. Se os limites forem iguais, o
indicador não tem poder discriminante naquela edição e será retirado, em vez de
receber uma pontuação arbitrária.

Alternativas que serão testadas na análise de sensibilidade:

- **min–max simples:** mais transparente, porém muito sensível a extremos;
- **escore-z:** preserva distâncias em desvios-padrão, mas é menos intuitivo e
  sensível a assimetria;
- **escore-z robusto** por mediana e desvio absoluto mediano: resistente a
  extremos, embora menos familiar ao público;
- **postos ou percentis:** muito robustos e fáceis de comparar, mas apagam a
  magnitude das diferenças e podem gerar muitos empates;
- **transformação prévia** (log, raiz ou Box–Cox) seguida de z-score/min–max:
  útil para distribuições muito assimétricas, ao custo de mais decisões.

Compararemos correlações, mudanças de posição, estabilidade por porte municipal
e casos com maiores divergências. O método inicial só será confirmado depois
desses testes; indicadores com distribuição peculiar poderão ter regra própria,
explicitamente documentada.

## 8. Agregação, pesos e pontuações

Inicialmente, cada indicador terá **peso igual dentro do seu eixo**, e cada eixo
terá **peso igual no índice geral**. Assim, nenhum tema dominará apenas porque
possui mais indicadores. Dentro de um eixo, a pontuação será a média ponderada
dos indicadores válidos; o índice geral será a média ponderada dos eixos.

Essa é uma adoção inicial razoável: é transparente, reproduzível e evita afirmar
uma precisão normativa que ainda não possuímos. Ela não significa que todos os
temas tenham necessariamente a mesma importância social.

Serão discutidas e testadas estas alternativas:

- pesos normativos definidos por especialistas e partes interessadas;
- pesos derivados de consulta pública ou método multicritério (como AHP);
- pesos empíricos por análise de componentes principais ou análise fatorial;
- pesos por variabilidade/entropia, que privilegiam poder discriminante;
- pesos ligados a resultados externos, com validação fora da amostra;
- média geométrica, que reduz compensação total entre dimensões, em lugar da
  média aritmética.

Métodos empíricos não serão tratados como automaticamente objetivos: eles
dependem da amostra e podem valorizar variação, não relevância. A análise de
sensibilidade comparará pesos iguais com pelo menos um cenário normativo e um
empírico, observando correlação de pontuações, mudanças de quintil e municípios
mais afetados.

Para dados ausentes, a regra preliminar será calcular o eixo somente se o
município atingir uma cobertura mínima de peso (a definir). Os pesos dos itens
disponíveis poderão ser renormalizados dentro do eixo, com a cobertura publicada
ao lado da nota. Um eixo sem cobertura mínima torna o índice geral indisponível;
não receberá zero.

## 9. Estrutura do repositório

```text
ice-sul/
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

### Etapa 0 — decisões metodológicas preliminares

Registrar e aprovar, antes do cálculo:

1. objetivo, público e usos que o índice pode e não pode ter;
2. unidade de análise e território (município e três UFs);
3. ano da primeira edição, data de corte e defasagem máxima aceitável;
4. tratamento de períodos diferentes e disponibilidade de séries;
5. eixos, definições e fronteiras conceituais;
6. critérios de entrada, reserva e exclusão de indicadores;
7. unidade de cada indicador, direção desejável e denominadores;
8. cobertura mínima por indicador, município e eixo;
9. significado de zero, ausente, não aplicável e dado suprimido;
10. política de imputação e renormalização na presença de ausentes;
11. tratamento de municípios pequenos e medidas voláteis (médias móveis,
    agregação de anos ou modelos de suavização);
12. regra de extremos e parâmetros de winsorização;
13. população usada para padronizar e se haverá comparação apenas regional;
14. método de padronização e inversão de direção;
15. pesos intraeixo e entre eixos e forma de agregação;
16. precisão, arredondamento, empates, ordenação e faixas de desempenho;
17. testes de robustez e critérios para aceitar o método;
18. política de revisão retroativa, versionamento e comparabilidade entre edições;
19. licença, privacidade, ética, comunicação de incerteza e governança;
20. formatos de publicação e protocolo de auditoria/revisão externa.

**Saída:** documento de escopo, glossário e registros de decisão aprovados.

### Etapa 1 — cadastro dos municípios

Implementar a extração oficial, construir o cadastro canônico e testar chaves,
UFs, duplicidades e contagens. Criar tabela de aliases somente para fontes que
não forneçam código IBGE.

**Saída:** `municipios` versionado, relatório de validação e teste automatizado.

### Etapa 2 — inventário e revisão dos indicadores

Produzir uma lista ampla de candidatos, preencher fichas, localizar fontes
primárias e avaliar mérito, redundância, cobertura e viabilidade. Montar uma
matriz `eixo × conceito × indicador` para revelar lacunas e excesso de medidas.

**Saída:** catálogo com parecer e conjunto provisório aprovado.

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

Executar o método robusto inicial, verificar direção e casos degenerados e gerar
diagnósticos antes/depois. Rodar min–max, z-score robusto e percentis como
cenários alternativos.

**Saída:** pontuações de 0 a 100, marcadores de tratamento e análise de sensibilidade.

### Etapa 8 — pesos, eixos e índice geral

Aplicar pesos iguais dentro dos eixos e pesos iguais entre eixos; calcular
cobertura efetiva e impedir notas abaixo do limiar. Comparar cenários de peso e,
se justificável, média geométrica.

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

O plano operacional é deliberadamente sequencial: começaremos pelas decisões da
Etapa 0; depois construiremos a lista municipal; em seguida revisaremos um eixo
e uma fonte por vez. As verificações externas orientarão o código de coleta, e
os resultados observados poderão devolver um indicador à revisão antes que ele
entre no índice.

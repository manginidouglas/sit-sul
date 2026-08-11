# Decisões metodológicas — Mercado

## Escopo e efeito da decisão

Este registro encerra a **revisão substantiva** do eixo Mercado na Etapa 2.
Foram aprovados condicionalmente dois indicadores do núcleo e aprovados três
indicadores da camada diagnóstica. `Aprovado` autoriza a futura verificação da
fonte e coleta no papel indicado; não define peso, normalização, agregação nem
permanência na nota. Nenhum estudo, coleta ou cálculo municipal foi realizado.

O núcleo reúne condições elegíveis para a pontuação futura. Os diagnósticos ficam
fora da pontuação conforme a governança normativa das
[decisões metodológicas gerais](../decisoes-metodologicas-preliminares.md): os de
contexto caracterizam a estrutura observada sem direção normativa geral; os de
resultado apoiam validação e acompanhamento sem autorizar inferência causal.

## Indicadores do núcleo

### MER-01 — Massa de renda domiciliar acessível

**Problema conceitual e escolha.** O indicador mede a escala do mercado consumidor
final economicamente acessível, não apenas a renda contida no município. A renda
municipal corrente será estimada preservando a posição relativa do município em
sua UF observada no Censo 2022 e atualizando o nível pela PNAD Contínua da UF:

`RDPC_estimado_m,t = (RDPC_Censo_m,2022 / RDPC_Censo_UF,2022) × RDPC_PNAD_UF,t`

A massa corrente será `MassaRenda_m,t = RDPC_estimado_m,t × Populacao_m,t`, com
estimativa populacional municipal do IBGE. A medida candidata de acesso é:

`MER-01_i = soma_j [MassaRenda_j,t × f(tempo_ij)]`

A função `f()` **não está congelada**. As fontes preferenciais são Censo
Demográfico 2022, PNAD Contínua, estimativas anuais de população municipal e uma
rede viária/solução de roteamento ainda a documentar. A direção é positiva.

**Alternativas não adotadas.** A PNAD sozinha foi rejeitada como fonte municipal
para os 1.191 municípios. O Censo sozinho é viável, mas excessivamente defasado.
RAIS ou CEMPRE como substitutos foram rejeitados por mudarem o conceito de renda
domiciliar. Um fator de atualização nacional único é inferior à atualização
separada por UF. Corte rígido de acessibilidade não foi preferido porque cria
descontinuidade artificial; há preferência por decaimento contínuo, condicionada
a estudo.

**Limitações e estudos obrigatórios.** A hipótese de posição relativa constante e
a acessibilidade precisam ser validadas. O backtest usará, no mínimo, Curitiba,
Florianópolis e Porto Alegre: partirá da posição relativa no Censo 2022,
projetará ano recente pela PNAD da UF, comparará com a observação da própria PNAD
para a capital, registrará erros absolutos e relativos e avaliará a
defensabilidade da hipótese. Massa salarial/atividade formal da RAIS/CEMPRE será
usada apenas como diagnóstico de mudanças desde 2022, sem incorporação automática
à fórmula.

O estudo de acessibilidade comparará funções e horizontes explícitos de 30, 60,
90 e 120 minutos, incluindo alternativas contínuas, e mostrará efeitos em
municípios metropolitanos, médios, pequenos próximos a polos, pequenos remotos e
de fronteira. Somente depois poderá ser congelada `f()`.

### MER-02 — Emprego formal privado acessível

**Problema conceitual e escolha.** O indicador representa a escala do mercado
empresarial formal economicamente acessível. A proxy preferencial é o emprego
formal **privado** da RAIS, em direção positiva:

`MER-02_i = soma_j [EmpregoFormalPrivado_j × f(tempo_ij)]`

Deve-se preferir a mesma família metodológica de acessibilidade de MER-01, salvo
justificativa empírica explícita.

**Limitação.** Emprego formal aproxima escala empresarial, não demanda B2B
efetiva. Atividades intensivas em capital podem ter grande escala econômica e
poucos empregados.

**Alternativas e estudo obrigatório.** Antes da coleta, serão comparados (1)
emprego formal privado da RAIS, (2) estabelecimentos privados ativos do CNPJ/RFB
e (3) PIB municipal do IBGE como benchmark geral. O estudo comparará distribuições
e rankings, identificará municípios industriais ou agroindustriais em que o
emprego pareça subestimar a escala, verificará sensibilidade a grande número de
microempresas/MEIs e documentará a separação entre emprego privado e público.
As três proxies não serão combinadas arbitrariamente sem nova decisão
metodológica.

## Regra territorial comum à acessibilidade de mercado

> A fronteira da Região Sul limita o universo avaliado, não o universo de recursos econômicos acessíveis.

Em MER-01 e MER-02, `i` pertence aos 1.191 municípios ranqueados de PR, SC e RS,
mas `j` pode pertencer a **qualquer município brasileiro**. Sua contribuição
depende do tempo de deslocamento e da função de acessibilidade; a massa econômica
não será truncada nas fronteiras dos três estados.

### Estudo transversal de mercados internacionais

Argentina, Paraguai e Uruguai podem constituir mercados acessíveis a municípios
fronteiriços, mas não serão incorporados automaticamente nem formarão um
indicador separado. O estudo pré-coleta verificará comparabilidade de população e
renda, emprego/atividade empresarial, unidade territorial, tempos de deslocamento
e passagens de fronteira. Ele responderá:

1. há cobertura comparável?
2. a unidade geográfica é compatível?
3. renda e atividade são conceitualmente comparáveis?
4. o custo temporal da fronteira pode ser representado sem precisão fictícia?
5. a inclusão altera materialmente os resultados dos municípios fronteiriços?

Se a incorporação não for viável, a fronteira internacional será registrada como
limitação, sem improvisação de fórmula.

## Camada diagnóstica

### MER-DIAG-01 — Diversificação setorial do emprego formal

Aprovou-se como **diagnóstico de contexto**, em direção neutra, a referência
`1 - soma(p_s²)` a partir da RAIS. Ela poderá apoiar perfis econômicos, identificação
de polos especializados, tipologias, módulos setoriais e contextualização de
mercado. Não será transformada em “diversificação acessível” nesta etapa.

Não integra o núcleo porque não existe relação monotônica geral entre
diversificação e melhor ambiente: diversidade pode ampliar variedade e
resiliência, enquanto especialização pode produzir fornecedores especializados,
mão de obra específica, conhecimento acumulado e economias de aglomeração.

### MER-DIAG-02 — Densidade de estabelecimentos ativos

Aprovou-se como **diagnóstico de contexto**, em direção neutra, usando Dados
Abertos do CNPJ/RFB e preservando inicialmente a fórmula já inventariada:

`1000 × estabelecimentos ativos / população de 18 a 64 anos`

Mudança de denominador deverá voltar à revisão metodológica. A medida poderá
caracterizar a profundidade do tecido empresarial, contextualizar, apoiar
tipologias e investigar divergências entre condições do SIT e a estrutura
observada. Não integra o núcleo porque também é resultado da trajetória econômica,
não distingue adequadamente porte, pode ser dominada por MEIs e endereços
cadastrais e criaria circularidade na nota.

### MER-DIAG-03 — Crescimento real do PIB municipal

Aprovou-se como **diagnóstico de resultado**, em direção positiva, a fórmula
candidata já registrada:

`100 × (PIB_t/deflator_t)/(PIB_t-k/deflator_t-k) - 100`

A fonte será IBGE — PIB dos Municípios/SIDRA; janela e deflacionamento ficam para
a verificação específica. A direção interpreta o resultado econômico, mas não o
leva à pontuação. O indicador servirá à validação externa, acompanhamento
longitudinal, associação entre condições em `t` e resultados posteriores e
identificação de lacunas. Não integra o núcleo porque mede resultado e geraria
circularidade. Associação não será interpretada como causalidade.

## Lacunas avaliadas e não incluídas

### Dinamismo do mercado

É relevante, mas foi classificado como resultado, não condição do núcleo. O
crescimento real do PIB permanece diagnóstico de resultado. Não serão criados
nesta etapa indicadores de crescimento populacional ou de renda no núcleo.

### Composição da demanda

Idade, nível de renda, urbanização, composição industrial, estrutura rural e
perfil setorial podem ser decisivos para empreendimentos específicos, mas não têm
direção universal em um índice geral. Não entram agora no núcleo; podem apoiar
futuros módulos setoriais.

## Encerramento

A revisão substantiva de Mercado está encerrada. Permanecem os backtests, análises
de sensibilidade, comparação de proxies, estudo da função de acessibilidade e
estudo transfronteiriço, todos anteriores à coleta definitiva. Limitação de fonte
que impeça a implementação decidida deverá ser registrada e devolvida à revisão
metodológica, sem fórmula alternativa improvisada. Não foram definidos pesos,
normalização, agregação, nota ou ranking.

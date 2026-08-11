# Decisões metodológicas — Infraestrutura e Conectividade

## Escopo e efeito da decisão

Este registro encerra a **revisão substantiva** do eixo na Etapa 2. Foram
selecionados 11 indicadores para avançar à verificação detalhada das fontes e à
coleta posterior. `Aprovado` não significa peso definido, normalização escolhida
ou permanência irrevogável no índice final. Nenhum estudo, coleta ou cálculo
municipal foi realizado nesta decisão.

Os seis candidatos genéricos do inventário inicial foram substituídos pela
decomposição abaixo para evitar dupla contagem e ambiguidade. O catálogo contém
somente as versões vigentes; este documento e o histórico Git preservam a
transição.

## Conectividade digital

### INF-DIG-01 — Densidade de acessos de banda larga fixa ≥ 100 Mbps

Aprovou-se `100 × acessos convencionais de internet fixa SCM com velocidade
contratada ≥ 100 Mbps / população residente`, em acessos por 100 habitantes e
direção positiva. Linhas dedicadas, M2M e produtos que não sejam acesso
convencional ficam fora. O numerador será Anatel/SCM, o denominador será a
população oficial do IBGE adotada na edição, e a chave será o código IBGE de sete
dígitos. Será usado e registrado o mês mais recente disponível até o corte.
Zero explicitamente observado é zero; ausência na extração é `NA` até
investigação.

**Alternativas não adotadas:** o total genérico de acessos, sem limiar de
velocidade, foi considerado insuficiente para caracterizar alta velocidade; o
candidato antigo “Acessos de banda larga fixa” não permanece em paralelo. Não se
adotou número absoluto, inadequado à comparação de portes, nem ausência como
zero. A unidade domiciliar não foi improvisada porque a fonte registra acessos.

Antes da coleta serão conferidos os 1.191 municípios, unidade de velocidade,
filtros de internet, dupla contagem, totais publicados e mudanças de esquema.

### INF-DIG-02 — Participação da fibra óptica

Aprovou-se `100 × acessos de internet fixa por fibra / total de acessos de
internet fixa`, direção positiva, usando o mesmo mês do INF-DIG-01. Denominador
zero resulta em `NA`. A medida representa a tecnologia contratada, não cobertura
territorial.

**Alternativas não adotadas:** fibra não será inferida pelo limiar de velocidade,
pois velocidade e tecnologia não são equivalentes; tampouco será tratada como
percentual do território. As categorias/códigos oficiais, suas mudanças e a
consistência aritmética precisam ser documentadas antes da coleta.

### INF-DIG-03 — Competitividade do mercado de banda larga fixa

Aprovou-se `1 - HHI`, com `HHI = soma(s_i²)` e participações calculadas sobre
todos os acessos de internet fixa SCM do município. A escala é de 0 a 1 e a
direção positiva. Prestador único produz zero; mercado não observado produz
`NA`; participações residuais não serão eliminadas.

**Alternativas não adotadas:** contagem simples de prestadores ignora suas
participações; restringir o mercado a acessos ≥ 100 Mbps alteraria o mercado
relevante; excluir pequenos prestadores arbitrariamente distorceria o HHI. Não se
decidiu entre CNPJ e grupo econômico: a unidade seguirá a metodologia corrente
da Anatel, após verificação. Uma amostra será comparada às medidas publicadas
pela agência.

### INF-DIG-04 — População coberta por 4G ou superior

Aprovou-se `100 × população residente em áreas cobertas por 4G ou tecnologia
superior / população residente total`, direção positiva, preferindo a variável
municipal elementar oficial do Índice Brasileiro de Conectividade. Será usado o
vintage mais recente disponível até o corte. Ausência não será interpretada como
falta de cobertura.

**Alternativas não adotadas:** não haverá indicador 5G separado nesta etapa; 5G
pode ser variável auxiliar. Não se fará reconstrução geoespacial se o valor
municipal oficial adequado estiver disponível. Cobertura populacional não será
interpretada como cobertura da área, qualidade ou adoção.

### INF-DIG-05 — Área agrícola elegível coberta por 4G/5G

Aprovou-se `100 × área passível de uso agrícola coberta por 4G/5G / área total
passível de uso agrícola`, direção positiva, preferindo o componente municipal
de conectividade rural da Anatel. Município sem área elegível recebe `NA` por
não aplicabilidade.

**Alternativas não adotadas:** zero não representa corretamente município sem
área elegível; cobertura de todo o território diluiria o conceito rural
economicamente relevante; a medida não será apresentada como velocidade,
qualidade ou adoção. Fonte elementar, versão, método e definição da área ainda
serão verificados.

## Confiabilidade energética

### INF-ENE-01 (DEC) e INF-ENE-02 (FEC)

DEC anual, em horas equivalentes por unidade consumidora, e FEC anual, em número
equivalente de interrupções por unidade consumidora, foram aprovados como dois
indicadores negativos. A fonte é ANEEL — Indicadores Coletivos de Continuidade,
com territorialização pelo IndQual Município.

**Alternativas não adotadas:** o candidato genérico “Continuidade do fornecimento
elétrico” foi decomposto porque duração e frequência são dimensões distintas. Não
será usada automaticamente média simples dos conjuntos elétricos, que não
coincidem necessariamente com municípios. Antes da coleta é obrigatório verificar
valor municipal ponderado pelas unidades consumidoras atendidas. Sem pesos
municipais defensáveis, a limitação será registrada e a questão voltará à revisão
metodológica, sem fórmula improvisada.

## Acessibilidade logística rodoviária

### INF-LOG-01 — Tempo até malha pavimentada estruturante

Aprovou-se, em direção negativa, o menor tempo pela rede viária entre a **sede
municipal** e segmento elegível. A hipótese inicial é rodovia federal ou estadual
pavimentada, com malha DNIT PNV/SNV e rede roteável cuja fonte, versão, algoritmo
e parâmetros serão registrados.

**Alternativas não adotadas:** presença de rodovia dentro do município e distância
em linha reta não medem o acesso pela rede; centroide geográfico não representa a
origem administrativa e populacional escolhida; somente rodovia federal pode
omitir eixos estaduais relevantes. A hipótese “federais + estaduais pavimentadas
≈ estruturante” não foi congelada: será testada com casos concretos da Região Sul
antes da coleta definitiva.

## Acessibilidade e conectividade aérea

### INF-LOG-02 — Tempo até aeroporto com serviço regular

Aprovou-se o menor tempo rodoviário entre a sede e aeroporto com operação
comercial regular efetivamente observada, em direção negativa. A janela inicial é
12 meses. Cadastro de aeródromos e estatísticas de transporte aéreo da ANAC serão
combinados.

**Alternativas não adotadas:** cadastro físico, existência de pista ou aeroporto
sem operação recente não bastam; distância linear e centroide não substituem o
tempo rodoviário desde a sede.

### INF-LOG-03 — Conectividade aérea acessível

Aprovou-se substantivamente um indicador positivo de intensidade e diversidade
do serviço acessível, mas **a fórmula não está congelada**. Entorno significa o
conjunto de aeroportos alcançáveis por tempo rodoviário desde a sede, não
município vizinho, região administrativa ou distância em linha reta.

O estudo obrigatório comparará: (1) partidas regulares anuais; (2) destinos
regulares distintos; e (3) combinação de frequência e diversidade. Também testará
contribuição simultânea de vários aeroportos, negativamente ponderada pelo tempo,
limites de 90, 120 e 180 minutos (120 é apenas hipótese inicial) e alternativas
simples de ponderação. Uma contagem isolada não foi congelada porque pode ignorar
frequência, diversidade ou aeroportos alternativos. O resultado voltará à revisão
metodológica antes da fórmula definitiva.

## Acessibilidade logística portuária

### INF-LOG-04 — Tempo até instalação portuária de carga elegível

Aprovou-se, em direção negativa, o menor tempo rodoviário entre a sede e
instalação com movimentação comercial efetiva em janela recente, inicialmente 12
meses. Geografia e operação/perfil serão obtidos, respectivamente, das informações
geográficas e do Estatístico Aquaviário da ANTAQ.

**Alternativas ainda em comparação, não congeladas:** (1) somente portos
organizados ativos; (2) portos organizados mais terminais privados com carga geral
ou conteinerizada; (3) portos organizados mais TUPs com movimentação comercial
relevante, qualquer que seja o perfil, excluídas instalações claramente cativas
ou especializadas. Contar todo cadastro físico foi rejeitado porque inclui
instalações inativas ou inadequadas à acessibilidade portuária genérica. Restringir
já o universo a uma das três regras também foi rejeitado sem estudo de casos da
Região Sul. O universo será congelado somente após essa comparação.

## Pendências e encerramento

A revisão substantiva deste eixo está encerrada. Permanecem apenas as verificações
e estudos pré-coleta explicitados nas fichas: esquema e categorias da Anatel;
unidade empresarial do HHI; territorialização de DEC/FEC; hipótese rodoviária;
elegibilidade e fórmula aeroportuária; e universo portuário. Eles não autorizam
alterar silenciosamente conceitos ou fórmulas. Não se decidiu cobertura mínima,
tratamento de extremos, normalização, pesos, agregação ou nota do SIT.

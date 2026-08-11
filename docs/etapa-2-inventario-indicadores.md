# Etapa 2 — relatório do inventário inicial

## Escopo e método desta rodada

Esta primeira rodada partiu dos seis eixos normativos e, para cada um, definiu
fenômenos relevantes antes de procurar proxies. Foram mapeados 26 candidatos e
fontes públicas primárias plausíveis (IBGE, RFB/Redesim, Siconfi, Anatel, Aneel,
DNIT, ANAC, Antaq, Banco Central, BNDES, MTE, Inep, CAPES, CNPq e INPI).

O resultado está em [`config/indicadores.yml`](../config/indicadores.yml), arquivo
YAML legível por máquina (deliberadamente escrito no subconjunto JSON de YAML).
Ele registra conceito, interpretação, direção, fórmula, numerador/denominador,
território, fonte e URL, temporalidade, cobertura esperada, comparabilidade,
reprodutibilidade, custo, comportamento em municípios pequenos, redundâncias,
limitações, riscos, status e parecer. A
[matriz eixo × conceito × indicador](indicadores/matriz-conceitual.md) oferece a
visão transversal.

As URLs são pontos de entrada institucionais candidatos, não atestados de que a
variável já foi localizada ou validada. Endpoint, tabela, licença, períodos,
chaves, cobertura observada e estabilidade ainda exigem a verificação individual
das Etapas 2 e 3. Não houve coleta em escala, imputação, normalização, pesos,
agregação ou cálculo de ranking.

## Achados

### Lacunas principais

- **Ambiente regulatório:** não foi identificada ainda uma base nacional
  municipal uniforme para digitalização, licenciamento, fiscalização e prazo de
  pagamento. Arrecadação não substitui uma medida de carga legal ou burocracia.
- **Acesso a capital:** presença física é observável, mas não demonstra oferta,
  preço ou aprovação de crédito; o local contábil de saldos pode divergir do
  tomador.
- **Inovação:** ativos científicos e resultados formais são observáveis, porém a
  interação universidade–empresa e inovação não patenteada continuam mal medidas.
- **Acessibilidade:** os conceitos são fortes, mas dependem de uma futura rede de
  deslocamento comum, origens e funções de decaimento documentadas.

### Redundâncias a investigar

- banda larga fixa e cobertura móvel são relacionadas, embora meçam canais
  distintos;
- agência geral e cooperativa de crédito podem duplicar acesso presencial;
- pós-graduação e pesquisadores acessíveis compartilham infraestrutura científica;
- escolaridade, emprego qualificado e formação técnica podem refletir parcelas
  sobrepostas do capital humano;
- os vários modos logísticos não devem virar contagem automática de ativos.

Correlação futura será diagnóstico, não motivo automático de exclusão: primeiro
será verificado se os conceitos são distintos.

### Disponibilidade e municípios pequenos

Censo Demográfico oferece cobertura territorial forte, mas baixa frequência.
Registros administrativos são mais frequentes, porém podem ter supressões,
quebras e local de registro diferente do fenômeno. Eventos como patentes,
desembolsos e concluintes podem produzir zeros e volatilidade excessivos; foram
sinalizados para janelas plurianuais, acessibilidade ou reserva, nunca imputação.
Nenhum limiar quantitativo de cobertura foi antecipado.

### Candidatos promissores

Banda larga fixa, cobertura móvel e escolaridade têm conceito transversal e
fontes nacionais conhecidas, ainda sujeitos a teste de denominadores, período e
qualidade. Tempos de acesso a rodovia, aeroporto, universidade e pós-graduação
são conceitualmente promissores porque reconhecem o entorno, mas exigirão prova
de conceito geoespacial reproduzível.

### Candidatos problemáticos

Carga tributária aproximada por arrecadação pode premiar baixa fiscalização;
crédito municipal pode refletir contabilização bancária; patentes e desembolsos
são raros e setoriais. Crescimento do PIB e densidade empresarial são resultados
associados e ficaram em reserva, sem entrada automática na pontuação.

## Ordem proposta para a revisão humana

Recomenda-se começar por **Infraestrutura e conectividade**, um indicador por
vez. O eixo combina fontes nacionais plausíveis, condições transversais e o caso
metodológico decisivo de distinguir estoque local de acesso territorial. A ordem
sugerida para discussão é: banda larga fixa; cobertura móvel; continuidade de
energia; acesso rodoviário; acesso aeroportuário; acesso portuário.

Essa recomendação escolhe apenas o ponto de partida. Não aprova candidatos nem
antecipa sua ponderação. A tarefa deve parar aqui para revisão humana progressiva.

## Atualização posterior — revisão substantiva de Infraestrutura e Conectividade

Após o inventário inicial descrito acima, foi concluída a revisão substantiva do
eixo **Infraestrutura e Conectividade**. A decomposição resultante contém 11
indicadores com status `aprovado`, no sentido estrito de estarem autorizados a
avançar à verificação detalhada das fontes e, depois, à coleta. A aprovação não
define peso, normalização ou permanência irrevogável no índice final.

Permanecem condicionantes e estudos pré-coleta: territorialização ponderada do
DEC e do FEC; adequação da hipótese de malha rodoviária estruturante; elegibilidade
e conectividade de aeroportos, inclusive fórmula e limites do entorno; e universo
de instalações portuárias de carga. Esses estudos serão realizados com a
verificação das fontes, antes da coleta definitiva, e não foram executados nesta
atualização.

A trilha completa das escolhas, das alternativas consideradas e das razões para
não selecioná-las está em
[`docs/indicadores/decisoes-infraestrutura-conectividade.md`](indicadores/decisoes-infraestrutura-conectividade.md).
Esta atualização não realizou coleta municipal, imputação, normalização,
ponderação, agregação, nota de eixo ou cálculo do SIT. Os demais eixos permanecem
no estágio anteriormente registrado e não foram submetidos a revisão substantiva
nesta rodada.

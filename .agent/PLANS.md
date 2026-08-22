# ExecPlans do SIT

Um ExecPlan é um plano de execução para tarefas longas ou incertas. Ele existe para ajudar o agente a concluir a mudança inteira com evidência verificável, não para adicionar cerimônia a tarefas simples.

## Quando usar

Crie e mantenha um ExecPlan quando a tarefa envolver um ou mais destes casos:

- pesquisa externa seguida de implementação;
- coleta ou processamento real de dados grandes;
- mudança em vários componentes;
- refatoração relevante;
- dependências ou formatos ainda não confirmados;
- execução que pode exigir recuperação de rede, disco ou estado parcial;
- trabalho provavelmente superior a uma tarefa curta e localizada.

Não crie ExecPlan para correções pequenas, renomeações simples ou mudanças cuja implementação e validação sejam óbvias.

## Onde manter

Durante a tarefa, mantenha um arquivo de trabalho em `.agent/execplans/<slug-da-tarefa>.md` ou em outro caminho explicitamente pedido pelo usuário.

O ExecPlan não precisa entrar no PR final. Versione-o apenas se tiver valor durável de arquitetura, decisão ou auditoria; caso contrário, remova-o do diff antes da entrega.

## Princípios

O plano deve ser autossuficiente para alguém que tenha apenas o working tree atual e o próprio ExecPlan.

Não copie para o plano o conteúdo do `AGENTS.md` ou de documentos normativos. Referencie-os por caminho e registre apenas as implicações específicas para a tarefa.

Descreva resultados observáveis. Prefira “a execução produz 1.191 IDs únicos e todos os portões ficam verdadeiros” a prescrever uma classe, função ou algoritmo específico, salvo quando essa escolha já for parte do contrato.

O plano é vivo. Atualize-o quando surgirem novas evidências. Não preserve uma etapa ou hipótese que já foi refutada apenas porque estava no plano inicial.

A execução deve continuar enquanto houver um próximo passo viável. Um bloqueio parcial não encerra automaticamente a tarefa: registre a evidência, tente alternativas compatíveis com o contrato e avance no que não depender do bloqueio.

## Estrutura mínima

### 1. Objetivo e aceitação

Explique, em poucas linhas:

- qual estado final a tarefa deve produzir;
- quem/qual componente depende desse resultado;
- quais evidências tornam o trabalho aceitável.

Critérios de aceitação devem ser verificáveis por comando, teste, produto ou inspeção concreta.

### 2. Contexto e invariantes

Registre apenas o que é específico desta tarefa:

- branch/PR/base relevantes;
- fonte e período/snapshot;
- arquivos/componentes principais;
- restrições metodológicas que não podem mudar;
- limites de escrita ou autorização especiais.

Confirme estado mutável — SHAs, endpoints, versões, disponibilidade — antes de tratá-lo como fato.

### 3. Estado inicial

Antes de implementar, sintetize o que realmente existe:

- comportamento atual;
- testes atuais;
- artefatos já presentes;
- falhas reproduzidas;
- dependências já disponíveis ou ausentes.

Não confunda descrição do PR com estado efetivo do código.

### 4. Marcos de execução

Divida o trabalho em poucos marcos orientados a resultado. Cada marco deve terminar com uma verificação.

Exemplo genérico:

1. confirmar fonte/schema e congelar contrato;
2. corrigir coletor/transformação;
3. ampliar regressões offline;
4. executar dados reais;
5. validar QA e produtos;
6. limpar Git, publicar e conferir o PR.

Evite listas de microações óbvias. O agente pode escolher a implementação mais adequada dentro dos invariantes.

### 5. Progresso

Mantenha uma checklist curta, por exemplo:

- [x] fonte confirmada;
- [x] falha atual reproduzida;
- [ ] execução real concluída;
- [ ] suíte completa verde;
- [ ] branch publicada.

Atualize durante a execução.

### 6. Descobertas e surpresas

Registre fatos encontrados que mudem o caminho planejado, com evidência suficiente para serem rechecados depois.

Exemplos:

- endpoint oficial usa padrão de nomes diferente;
- cadastro posterior ao corte precisa ser tratado como revisão;
- um campo documentado tem domínio diferente no raw real;
- volume real excede o espaço disponível.

Não enterre descobertas importantes apenas em logs de terminal.

### 7. Decisões

Quando houver mais de uma solução plausível, registre sucintamente:

- decisão tomada;
- razão;
- alternativa rejeitada relevante;
- consequência para compatibilidade, QA ou reproducibilidade.

Não use esta seção para decisões triviais de estilo.

### 8. Validação e portões

Liste os comandos e resultados necessários para demonstrar aceitação. Inclua, conforme o caso:

- testes direcionados;
- suíte completa;
- compilação/lint/checks estáticos;
- execução real;
- reconciliações;
- sanity checks;
- inspeção do diff e histórico Git.

Um teste unitário verde não substitui execução real quando a tarefa exige provar fonte, cobertura ou materialização.

### 9. Recuperação e idempotência

Para tarefas com efeitos duráveis ou arquivos grandes, registre como repetir a execução sem corromper estado:

- raws existentes;
- downloads parciais;
- staging/promoção;
- rollback;
- scratch temporário;
- reexecução após falha.

A tarefa deve, sempre que razoável, poder ser reiniciada com segurança.

### 10. Resultado final

Ao terminar, atualize o ExecPlan para refletir o que realmente aconteceu:

- resultado produzido;
- diferenças em relação ao plano inicial;
- validações executadas;
- limitações que continuam reais;
- branch/SHA/PR final, quando aplicável.

Se o trabalho terminar bloqueado, deixe explícitos a evidência do bloqueio e o próximo passo executável. Não rotule como concluída uma implementação que não passou pelos critérios de aceitação.

# SIT — instruções para agentes de código

Este repositório implementa o Sistema de Inteligência Territorial (SIT). Use este arquivo como mapa operacional; a metodologia e os contratos detalhados permanecem nos documentos versionados do projeto.

## Antes de modificar

Leia primeiro, no estado atual da branch:

- `docs/guia-de-implementacao.md`;
- `docs/mvp-demo-2026/contratos-agentes.md`;
- `docs/mvp-demo-2026/fontes-e-periodos.md`;
- `docs/mvp-demo-2026/metodologia-experimental.md`;
- a ficha/configuração do indicador ou fonte que estiver sendo alterado.

Se uma tarefa mencionar PR, branch, SHA, período ou endpoint antigo, verifique o estado atual antes de agir. Não trate valores históricos do prompt como fonte de verdade quando puderem ter mudado.

## Autonomia e escopo

Resolva a tarefa de ponta a ponta sempre que for viável: investigar, implementar, executar, validar e deixar o PR/branch no estado solicitado. Não pare em análise ou em testes unitários se o critério de aceitação exigir execução real.

Cada fonte deve permanecer, por padrão, no seu próprio território:

- `src/ice_sul/extract/<fonte>.py`;
- `src/ice_sul/transform/<fonte>.py`;
- `tests/test_<fonte>.py` e fixtures da fonte;
- `data/raw/<fonte>/...`;
- `data/interim/<fonte>/...`;
- `reports/quality/mvp-demo-2026/<fonte>/...`.

Não altere scoring central, configuração global, documentação de outra fonte ou código compartilhado salvo necessidade real. Se uma mudança compartilhada for incontornável, mantenha-a mínima e explique por que foi necessária.

## ExecPlans

Para tarefas complexas — por exemplo pesquisa externa + implementação + execução real, refatorações relevantes, mudanças em vários componentes ou trabalho com alta incerteza operacional — use um ExecPlan conforme `.agent/PLANS.md`.

O ExecPlan é um documento de trabalho vivo. Ele deve orientar a execução e registrar descobertas e decisões; não deve virar um segundo manual do repositório nem substituir a implementação.

## Contrato de coleta e proveniência

Coletores devem obedecer ao contrato compartilhado em `src/ice_sul/extract/contracts.py` e ao registry existente.

Use fontes públicas primárias sempre que disponíveis. Para a edição `mvp-demo-2026`, respeite a data de corte e o período definidos na documentação da fonte; não substitua silenciosamente um snapshot ou período por outro mais recente.

Raw é imutável. Arquivos grandes não entram no Git. Preserve evidência suficiente para reproduzir e auditar a coleta conforme `contratos-agentes.md`, incluindo URL/parâmetros, período/snapshot, horário UTC, status HTTP, URL final/redirects, tipo de conteúdo, tamanhos, SHA-256, caminho lógico e versão/licença quando disponíveis.

Downloads grandes devem ser seguros contra interrupção. Um arquivo parcial ou uma execução reprovada não pode ser promovido silenciosamente a produto válido.

Nunca invente valores, cobertura, hashes, versões ou sucesso de coleta. Distinga claramente falha de fonte, ambiente, endpoint e validação usando os status padronizados.

## Território e saídas

O universo canônico da edição é `data/processed/2026/municipios.csv`. Quando uma transformação publicar observações municipais do SIT, preserve o código IBGE de sete dígitos e o contrato mínimo definido em `contratos-agentes.md`.

Ausência não vira zero. Correspondências territoriais por nome devem ser explícitas, auditáveis e testadas; não faça correções silenciosas.

## Validação

Antes de considerar uma tarefa concluída, execute as validações relevantes ao escopo. Como padrão para mudanças de fonte:

1. testes direcionados da fonte;
2. suíte completa `pytest -q`;
3. `python -m compileall -q src tests scripts` quando aplicável;
4. `git diff --check`;
5. execução ou smoke test real quando o critério da tarefa exigir dados reais;
6. QA e reconciliações do produto gerado.

Transforme bugs concretos encontrados durante revisão em testes de regressão sempre que possível, em vez de depender apenas de instruções textuais futuras.

Se alguma validação não puder ser executada, registre a evidência do bloqueio e execute a melhor verificação substituta possível. Não declare `success` se um portão crítico permanecer falso.

## Git e PRs

Respeite a branch de integração e a branch/PR indicadas na tarefa.

Ao corrigir um PR existente:

- atualize o mesmo PR/branch, salvo instrução contrária;
- reconstrua sobre a integração atual quando necessário, preservando backup do head remoto antes de reescrever histórico;
- prefira histórico linear;
- use `--force-with-lease`, nunca `--force` simples;
- não versione raws grandes, bancos scratch, `.part`, `egg-info` ou artefatos de ambiente;
- não faça merge, salvo autorização explícita.

Antes do push final, confira base/head, commits atrás/à frente, merges novos, arquivos do diff e working tree.

## Resposta final

Seja factual e curta. Informe:

- o que mudou;
- o que foi executado com dados reais;
- principais contagens/QA;
- testes executados;
- SHA/estado do push e do PR, quando aplicável;
- limitações realmente remanescentes.

Não repita todo o plano e não chame de concluído aquilo que ficou apenas preparado para execução posterior.

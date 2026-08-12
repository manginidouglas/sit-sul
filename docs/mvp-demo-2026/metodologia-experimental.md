# SIT — Demonstração Experimental 2026 | Infraestrutura e Mercado

> **Esta é uma demonstração experimental do Sistema de Inteligência Territorial (SIT), construída com os eixos Infraestrutura e Conectividade e Mercado. O SIT completo prevê seis eixos. Alguns parâmetros desta demonstração foram fixados provisoriamente para testar o funcionamento do sistema de ponta a ponta e não representam decisões metodológicas definitivas.**

## Escopo e estado desta entrega

Esta área isola a edição experimental da metodologia normativa. O código implementa, testa e congela a etapa **indicadores harmonizados → tratamento → scores → eixos → nota → ranking → exportação**. A coleta integral não foi declarada concluída: não se publicam valores, conclusões, ranking ou narrativa enquanto os 16 indicadores reais não passarem pela verificação técnica de `fontes-e-periodos.md`. Ausência não é substituída por zero.

O universo avaliado é o cadastro canônico de 1.191 municípios de PR, SC e RS, identificado pelo código IBGE de sete dígitos. MER-01 e MER-02 devem receber contribuições de todos os municípios brasileiros alcançáveis em até 360 minutos; países vizinhos ficam fora do MVP, limitação particularmente importante na fronteira.

## Contrato e execução

O ponto de entrada recebe CSV longo com `municipio_id`, `indicador_id`, `valor_bruto`, `periodo_referencia` e `flag_qualidade`. Campo vazio é ausente. Flags incluem `zero_observado`, `ausente`, `nao_aplicavel`, `suprimido_fonte`, `falha_roteamento` e `territorializacao_aproximada`.

```bash
sit-mvp-2026 --indicadores data/processed/mvp-demo-2026/indicadores.csv
```

O comando valida o universo, bloqueia duplicidades, aplica P1/P99 apenas a medidas sem limite natural, aplica `log1p` somente a MER-01/MER-02, normaliza min-max conforme a direção e interrompe a pontuação com `min=max`. Um eixo exige cobertura original mínima de 80%; pesos disponíveis são então renormalizados. A nota exige ambos os eixos.

## Fórmulas e produtos

* Competitividade digital: `1 - Σs²`, sem remover participações residuais.
* DEC/FEC: média pelos pesos município–conjunto; média simples só com flag explícita.
* Aeroportos: `Σ sqrt(F×D) × exp(-t/60)`, para `t ≤ 120`.
* Mercado: `Σ recurso × 2^(-t/60)`, incluindo o próprio município e truncando depois de 360 minutos.
* Diversificação: `1 - Σp²`; diagnósticos têm peso zero.

Os pesos ficam exclusivamente na configuração da edição. `data/output/mvp-demo-2026/municipios.csv` preserva bruto, tratado, score, flag, período, cobertura, eixos, nota e posições. Dashboard, relatório e fichas só devem ser materializados após qualidade, sanity checks e robustez; antes disso criariam narrativa sem base.

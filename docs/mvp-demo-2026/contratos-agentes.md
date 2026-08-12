# Contratos dos agentes — Onda 1

## Limites de escrita

Cada fonte ocupa `src/ice_sul/extract/<fonte>.py`, `src/ice_sul/transform/<fonte>.py`,
`tests/test_<fonte>.py`, `data/raw/<fonte>/...` e
`reports/quality/mvp-demo-2026/<fonte>...`. O agente não altera scoring central,
configuração global, coletor alheio, README ou metodologia de outro indicador.
Uma mudança compartilhada incontornável deve ser documentada, mínima e não pode
redesenhar silenciosamente a arquitetura.

## Interface e registry

O coletor implementa `Collector`, retorna `CollectionResult` e usa um dos status
`success`, `partial`, `blocked_source`, `blocked_environment`, `endpoint_review`,
`unavailable` ou `failed_validation`. A factory é incluída por uma chamada
localizada a `register_collector`; o orquestrador isola exceções e consolida as
evidências. HTTP 401/403 é bloqueio da fonte e não recebe retry cego. Retry com
backoff pode ocorrer dentro do adaptador para 429/502/503/504.

## Raw e manifesto

O raw é imutável. Cada artefato registra: fonte, URL, método, parâmetros,
período, timestamp UTC, status HTTP, URL final, redirects, content-type, tamanho,
SHA-256, caminho, licença quando disponível, versão/snapshot e validação feita.
Se houver compressão, registre separadamente tamanho transferido e tamanho da
representação persistida.

## Saída municipal e flags

Cada transformação produz ao menos `municipio_id`, `indicador_id`, `valor_bruto`,
`periodo_referencia` e `flag_qualidade`. Campos adicionais são permitidos. Flags
padronizadas: `observado`, `zero_observado`, `ausente`, `nao_aplicavel`,
`suprimido_fonte`, `falha_roteamento` e `territorializacao_aproximada`.

## Testes obrigatórios

Cada entrega cobre parsing, transformação, fórmula relevante, município conhecido,
erro/ausência e execução sem rede com fixture. Testes de rede são diagnósticos
separados; não substituem fixtures determinísticas.

## Decisões da Onda 0

`data/processed/2026/municipios.csv` é o snapshot canônico versionado. A edição
falha se ele estiver ausente ou se o universo não coincidir integralmente com seus
1.191 códigos, nomes e UFs. Na investigação de controle em 12/08/2026, a API do
IBGE devolveu gzip de aproximadamente 7.917 bytes cuja representação JSON
descomprimida tinha aproximadamente 170.538 bytes. A divergência vinha da medição
de camadas diferentes: `requests.content` descomprime automaticamente, enquanto a
captura anterior contabilizou os bytes gzip. O preflight agora registra ambos e
valida JSON, lista, 399 códigos paranaenses únicos e a presença de Curitiba.

# Camada ANTAQ — Onda 1

O materializador `python -m ice_sul.transform.antaq_materialize` processa as **1.179 linhas do universo cadastral completo** de `Portos.xlsx` (snapshot oficial ANTAQ de 06/05/2025) e gera `instalacoes_portuarias_avaliadas_2025.csv`. Cada linha recebe `elegivel`, `nao_elegivel`, `indeterminado` ou `fora_escopo_mvp`. `indeterminado` significa evidência insuficiente — nunca inexistência ou inelegibilidade.

A camada operacional versionada para a Onda 2 é `instalacoes_elegiveis_2025.csv`, derivada automaticamente do universo. A Onda 2 deve rotear somente `status_mvp == "elegivel"`; municípios não devem interpretar instalações indeterminadas como ausentes. O universo completo é saída derivada e pode ser regenerado a partir dos raws validados e da evidência versionada; seus totais, conflitos e casos manuais ficam registrados em `reports/quality/mvp-demo-2026/antaq/qa.json`.

A elegibilidade é parcial porque o bulk mensal detalhado permaneceu inacessível. Em especial, TUPs sem evidência oficial de natureza de carga ficam indeterminados, não negativos. Os valores do Anuário p. 19 comprovam apenas movimentação de **milho e soja**, não movimentação total.

### Codificação do cadastro

O `Portos.xlsx` deste snapshot contém caracteres de substituição U+FFFD no próprio XML. O pipeline valida que o XLSX está presente e usa os valores do `Portos.dbf` companheiro — com o mesmo número de linhas e bytes Windows-1252 preservados — para não apagar nem adivinhar acentos. Assim, nomes como Paranaguá, São Francisco do Sul, Itajaí, Vitória e Guarujá são materializados corretamente na origem.

### Coleta, conflito e coordenadas

Em clone limpo, execute `python -m ice_sul.extract.antaq` para obter e validar os raws pelo SHA-256 registrado e, depois, `python -m ice_sul.transform.antaq_materialize`. O ID ANTAQ conflitante `BRAM021` é preservado em dois registros com UIDs determinísticos (`BRAM021--terminal-de-uso-privado` e `BRAM021--tna`), ambos marcados como conflito e bloqueados para elegibilidade/routing. `coordenada_valida` mede apenas presença, numericidade e faixa; `ajuste_acesso_terrestre_onda2` permanece verdadeiro inclusive quando a coordenada está ausente, pois nenhum ponto foi descrito como portão rodoviário oficial.

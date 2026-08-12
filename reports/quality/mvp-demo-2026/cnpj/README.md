# CNPJ — MER-DIAG-02 (numerador)

## Fonte e snapshot

A fonte primária é **Receita Federal — Dados Abertos do CNPJ**, catálogo oficial
no Portal Brasileiro de Dados Abertos e índice bulk oficial
`https://dadosabertos.rfb.gov.br/CNPJ/dados_abertos_cnpj/`. O coletor exige um
snapshot mensal explícito (`YYYY-MM`), lê o índice e baixa todas as partes de
`Estabelecimentos`, além de `Simples` e `Municipios`. Não escolhe silenciosamente
o “mais recente”. Para a Onda 1, o snapshot pretendido é **2026-07**, último mês
integral anterior à data de corte de 2026-08-12.

Na execução deste ambiente em 2026-08-12, o catálogo oficial
`https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica-cnpj`
respondeu HTTP 200. Foram tentados o endereço legado
`https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/` (HTTP
404), o índice atual e seus diretórios `2026-07/` e `2026-06/` (HTTP 503 por
timeout do upstream). O PDF oficial do leiaute em
`https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf` respondeu HTTP 200.
Assim, o caminho correto foi identificado, mas o snapshot integral não é
versionado e não foi falsamente substituído por uma amostra. Execute:

```bash
python -m ice_sul.extract.cnpj --snapshot 2026-07
```

## Regras

* Unidade: CNPJ completo (`CNPJ básico + ordem + DV`), portanto cada filial é um
  estabelecimento e não se colapsam empresas-raiz.
* Ativo: campo **situação cadastral do estabelecimento = `02` (ATIVA)**.
* MEI: campo oficial **opção pelo MEI = `S`** do arquivo `Simples`, associado ao
  estabelecimento pelo CNPJ básico. Não se presume MEI pelo porte. Essa marca é
  a opção registrada no snapshot e pode ter defasagem cadastral própria.
* Território: código de município RFB do estabelecimento é ligado ao nome do
  arquivo oficial `Municipios`; nome normalizado + UF é então validado contra o
  cadastro canônico IBGE. Qualquer código ativo não ligado reprova a execução.

O CSV intermediário tem uma linha para cada município canônico (inclusive zero)
e traz ativos com MEI, sem MEI e MEIs. O denominador população 18–64 não é
calculado nesta onda.

## Volume, QA e recursos

Os ZIPs são lidos membro a membro, em streaming, sem extração. Raízes MEI e CNPJ
ativos são indexados em SQLite em disco; inserções usam lotes de 50 mil. A chave
primária CNPJ completo detecta duplicatas entre partes. O relatório JSON registra
snapshot, linhas lidas, ativos, raízes MEI, duplicatas e códigos municipais não
mapeados. A revisão de ordem de grandeza (capitais e municípios pequenos) deve
ser feita somente após o bulk concluir; não há contagens inventadas neste commit.

Exemplo da transformação:

```bash
python -m ice_sul.transform.cnpj \
  --snapshot 2026-07 \
  --estabelecimentos data/raw/cnpj/2026-07/Estabelecimentos*.zip \
  --simples data/raw/cnpj/2026-07/Simples.zip \
  --municipios data/raw/cnpj/2026-07/Municipios.zip \
  --output data/interim/cnpj/2026-07/numeradores.csv \
  --report reports/quality/mvp-demo-2026/cnpj/2026-07.json
```

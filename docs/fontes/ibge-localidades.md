# Cadastro de municípios — API de Localidades do IBGE

- **Órgão:** Instituto Brasileiro de Geografia e Estatística (IBGE).
- **Recurso:** API de Localidades, rota `estados/{UF}/municipios`.
- **URL:** <https://servicodados.ibge.gov.br/api/v1/localidades/estados/PR/municipios>
  (a sigla é substituída por `PR`, `SC` e `RS`).
- **Acesso:** JSON público, sem autenticação.
- **Data de corte da primeira configuração:** 7 de agosto de 2026.
- **Chave:** campo `id`, código IBGE municipal de sete dígitos.

O coletor salva separadamente a resposta original de cada UF e registra URL,
horário UTC, status HTTP, tamanho e SHA-256. As contagens esperadas são derivadas
das próprias respostas na execução, e não de constantes no código. A publicação
é bloqueada se houver chave vazia ou duplicada, código malformado, UF externa ao
universo, inconsistência entre sigla e código da UF, campo vigente obrigatório
vazio ou divergência de contagem.

Os recortes de mesorregião e microrregião são mantidos quando fornecidos, mas
são anuláveis por serem legados. Os recortes imediato e intermediário vigentes
são obrigatórios. O cadastro usa nomes apenas como atributos; integrações devem
usar `municipio_id`. Uma tabela de aliases não foi criada nesta etapa porque a
fonte oficial já oferece o código IBGE.

## Reprodução

```bash
python -m ice_sul.municipios --config config/edicoes/2026.yml
```

A execução produz `data/processed/2026/municipios.csv` e
`reports/quality/2026/municipios.json`. O diretório `data/raw` fica fora do Git;
o manifesto no relatório permite verificar cada cópia bruta.

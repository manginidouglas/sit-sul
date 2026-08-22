import math

from ice_sul.extract.ibge_mercado import RESOURCES
from ice_sul.transform.ibge_mercado import build_gdp, build_income, build_population_18_64, sidra_records


def row(localidade_id, valor, periodo="2025", classificacoes=None):
    return {"localidade_id": localidade_id, "localidade_nome": "x", "valor": valor,
            "periodo": periodo, "unidade": "Reais", "classificacoes": classificacoes or {}}


def test_recursos_congelam_tabelas_periodos_e_variaveis():
    assert [(r.table, r.period, r.variable) for r in RESOURCES] == [
        (10295, "2022", 13431), (10295, "2022", 13431), (7395, "2025", 4196),
        (6579, "2025", 9324), (9514, "2022", 93), (5938, "2021,2022,2023", 37),
        (6784, "2021,2022,2023", 9811),
    ]


def test_achata_resposta_sidra_e_preserva_codigo_como_texto():
    payload = [{"unidade": "Reais", "resultados": [{"classificacoes": [], "series": [
        {"localidade": {"id": "4100103", "nome": "Abatiá"}, "serie": {"2022": "1234.50"}}
    ]}]}]
    assert sidra_records(payload)[0] == {"localidade_id": "4100103", "localidade_nome": "Abatiá",
        "periodo": "2022", "valor": 1234.5, "unidade": "Reais", "classificacoes": {}}


def test_renda_estimada_e_massa_respeitam_formula_congelada():
    got = build_income([row("4100103", 1000, "2022")], [row("41", 2000, "2022")],
                       [row("41", 3000)], [row("4100103", 10000)])[0]
    assert got["rdpc_est_reais_mes"] == 1500
    assert got["massa_renda_reais_mes"] == 15_000_000


def test_populacao_18_64_aplica_participacao_censitaria_sem_arredondar():
    ages = [row("4100103", 600, "2022", {"287": {"93087": "20 a 24 anos"}}),
            row("4100103", 1000, "2022", {"287": {"100362": "Total"}})]
    got = build_population_18_64(ages, [row("4100103", 1100)])[0]
    assert got["participacao_18_64_censo"] == .6
    assert math.isclose(got["populacao_18_64_estimada_pessoas"], 660)


def test_pib_usa_deflator_implicito_nacional_encadeado_e_formula_do_projeto():
    pib = [row("4100103", 100, "2021"), row("4100103", 110, "2022"), row("4100103", 121, "2023")]
    deflator = [row("1", 5, "2021"), row("1", 10, "2022"), row("1", 10, "2023")]
    got = build_gdp(pib, deflator)[0]
    assert math.isclose(got["crescimento_real_acumulado_percentual"], 0, abs_tol=1e-12)

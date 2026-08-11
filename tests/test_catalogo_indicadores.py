import json
from pathlib import Path

CATALOGO = Path(__file__).parents[1] / "config" / "indicadores.yml"
OBRIGATORIOS = {
    "indicador_id", "nome", "eixo", "conceito", "descricao", "justificativa",
    "interpretacao", "natureza", "direcao", "unidade", "numerador",
    "denominador", "formula", "abordagem_territorial", "nivel_territorial",
    "fonte", "url_fonte", "periodicidade", "periodo_disponivel",
    "cobertura_esperada", "comparabilidade_pr_sc_rs",
    "comportamento_municipios_pequenos", "limitacoes", "status", "parecer",
}
INFRA_APROVADOS = {
    "INF-DIG-01", "INF-DIG-02", "INF-DIG-03", "INF-DIG-04", "INF-DIG-05",
    "INF-ENE-01", "INF-ENE-02", "INF-LOG-01", "INF-LOG-02", "INF-LOG-03",
    "INF-LOG-04",
}
INFRA_CONDICIONADOS = {
    "INF-ENE-01", "INF-ENE-02", "INF-LOG-01", "INF-LOG-02", "INF-LOG-03",
    "INF-LOG-04",
}


def carregar_catalogo():
    # JSON é um subconjunto válido de YAML; isso evita dependência só para validar o catálogo.
    return json.loads(CATALOGO.read_text(encoding="utf-8"))


def test_catalogo_tem_identificadores_unicos_e_campos_obrigatorios():
    catalogo = carregar_catalogo()
    ids = [item["indicador_id"] for item in catalogo["indicadores"]]
    assert len(ids) == len(set(ids))
    assert all(OBRIGATORIOS <= item.keys() for item in catalogo["indicadores"])


def test_catalogo_respeita_eixos_status_e_direcoes_controlados():
    catalogo = carregar_catalogo()
    eixos = set(catalogo["eixos"])
    status = set(catalogo["status_validos"])
    assert {item["eixo"] for item in catalogo["indicadores"]} == eixos
    assert all(item["status"] in status for item in catalogo["indicadores"])
    assert all(item["direcao"] in {"positiva", "negativa"} for item in catalogo["indicadores"])


def test_infraestrutura_tem_exatamente_os_11_indicadores_aprovados():
    catalogo = carregar_catalogo()
    infraestrutura = {
        item["indicador_id"]: item for item in catalogo["indicadores"]
        if item["eixo"] == "Infraestrutura e conectividade"
    }
    assert set(infraestrutura) == INFRA_APROVADOS
    assert all(item["status"] == "aprovado" for item in infraestrutura.values())


def test_indicadores_condicionados_registram_verificacoes_pre_coleta():
    catalogo = carregar_catalogo()
    por_id = {item["indicador_id"]: item for item in catalogo["indicadores"]}
    for indicador_id in INFRA_CONDICIONADOS:
        item = por_id[indicador_id]
        assert item.get("verificacoes_pre_coleta", "").strip()
        assert any(termo in item["parecer"].lower() for termo in ("condicionado", "condicionada"))

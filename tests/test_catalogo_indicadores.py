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
MERCADO_IDS = {
    "MER-01", "MER-02", "MER-DIAG-01", "MER-DIAG-02", "MER-DIAG-03",
}
MERCADO_NUCLEO = {"MER-01", "MER-02"}
MERCADO_DIAGNOSTICO_CONTEXTO = {"MER-DIAG-01", "MER-DIAG-02"}
MERCADO_DIAGNOSTICO_RESULTADO = {"MER-DIAG-03"}


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
    assert all(
        item["direcao"] in {"positiva", "negativa", "neutra"}
        for item in catalogo["indicadores"]
    )


def test_camadas_e_tipos_diagnosticos_controlados_e_sem_ambiguidade():
    catalogo = carregar_catalogo()
    classificados = [
        item for item in catalogo["indicadores"] if "camada" in item
    ]
    assert classificados
    assert all(item["camada"] in {"nucleo", "diagnostico"} for item in classificados)
    for item in classificados:
        if item["camada"] == "diagnostico":
            assert item.get("tipo_diagnostico") in {"contexto", "resultado"}
        else:
            assert "tipo_diagnostico" not in item


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


def test_mercado_tem_exatamente_a_estrutura_vigente():
    catalogo = carregar_catalogo()
    mercado = {
        item["indicador_id"]: item for item in catalogo["indicadores"]
        if item["eixo"] == "Mercado"
    }
    assert set(mercado) == MERCADO_IDS
    assert all(item["status"] == "aprovado" for item in mercado.values())
    assert {
        indicador_id for indicador_id, item in mercado.items()
        if item["camada"] == "nucleo"
    } == MERCADO_NUCLEO
    assert {
        indicador_id for indicador_id, item in mercado.items()
        if item.get("tipo_diagnostico") == "contexto"
    } == MERCADO_DIAGNOSTICO_CONTEXTO
    assert {
        indicador_id for indicador_id, item in mercado.items()
        if item.get("tipo_diagnostico") == "resultado"
    } == MERCADO_DIAGNOSTICO_RESULTADO


def test_nucleo_de_mercado_registra_estudos_pre_coleta():
    catalogo = carregar_catalogo()
    por_id = {item["indicador_id"]: item for item in catalogo["indicadores"]}
    for indicador_id in MERCADO_NUCLEO:
        assert por_id[indicador_id].get("verificacoes_pre_coleta", "").strip()


def test_candidatos_antigos_de_mercado_nao_permanecem_ativos():
    catalogo = carregar_catalogo()
    ids = {item["indicador_id"] for item in catalogo["indicadores"]}
    assert ids.isdisjoint({
        "merc_renda_acessivel", "merc_diversificacao",
        "merc_densidade_empresarial", "merc_pib_crescimento",
    })

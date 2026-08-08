import json
from pathlib import Path

CATALOGO = Path(__file__).parents[1] / "config" / "indicadores.yml"
OBRIGATORIOS = {
    "indicador_id", "nome", "eixo", "conceito", "descricao", "justificativa",
    "direcao", "unidade", "fonte", "url_fonte", "periodicidade",
    "periodo_disponivel", "cobertura_esperada", "formula", "denominador",
    "limitacoes", "status", "parecer",
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
    assert not any(item["status"] == "aprovado" for item in catalogo["indicadores"])

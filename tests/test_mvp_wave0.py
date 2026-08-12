import csv
import importlib.util
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest
import yaml

from ice_sul.extract.contracts import CollectionResult, CollectionStatus
from ice_sul.extract.orchestrator import CollectorValidationError, run_collectors
from ice_sul.mvp.robustness import compare_rankings, generate_robustness
from ice_sul.mvp.validate import validate_municipal_keys

PREFLIGHT_SPEC = importlib.util.spec_from_file_location(
    "network_preflight", Path("scripts/network_preflight.py")
)
assert PREFLIGHT_SPEC and PREFLIGHT_SPEC.loader
PREFLIGHT = importlib.util.module_from_spec(PREFLIGHT_SPEC)
PREFLIGHT_SPEC.loader.exec_module(PREFLIGHT)

CANONICAL = Path("data/processed/2026/municipios.csv")


def canonical_rows():
    with CANONICAL.open(encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda rows: rows.__setitem__(0, {**rows[0], "municipio_id": "9999999"}),
        lambda rows: rows.__setitem__(0, {**rows[0], "uf_sigla": "SC"}),
        lambda rows: rows.pop(),
        lambda rows: rows.append(
            {"municipio_id": "9999999", "municipio_nome": "X", "uf_sigla": "PR"}
        ),
        lambda rows: rows.append(dict(rows[0])),
    ],
)
def test_canonical_rejects_fictitious_wrong_uf_missing_extra_and_duplicate(mutation):
    reference = canonical_rows()
    candidate = [dict(row) for row in reference]
    mutation(candidate)
    with pytest.raises(ValueError):
        validate_municipal_keys(candidate, reference)


def test_canonical_accepts_exact_universe():
    rows = canonical_rows()
    validate_municipal_keys(rows, rows)


class FakeCollector:
    def __init__(self, source, action, calls):
        self.source, self.action, self.calls = source, action, calls

    def collect(self):
        self.calls.append(self.source)
        if isinstance(self.action, Exception):
            raise self.action
        return CollectionResult(self.source, self.action)


def test_orchestrator_isolates_http_and_validation_failures(tmp_path):
    calls = []
    collectors = [
        FakeCollector("ok", CollectionStatus.SUCCESS, calls),
        FakeCollector(
            "auth", HTTPError("url", 401, "unauthorized", {}, io.BytesIO()), calls
        ),
        FakeCollector(
            "temporary", HTTPError("url", 503, "busy", {}, io.BytesIO()), calls
        ),
        FakeCollector("invalid", CollectorValidationError("schema inválido"), calls),
        FakeCollector("after", CollectionStatus.SUCCESS, calls),
    ]
    result = run_collectors(collectors, tmp_path / "manifest.json")
    assert calls == ["ok", "auth", "temporary", "invalid", "after"]
    assert result.status == CollectionStatus.PARTIAL
    assert [item.status for item in result.results] == [
        CollectionStatus.SUCCESS,
        CollectionStatus.BLOCKED_SOURCE,
        CollectionStatus.UNAVAILABLE,
        CollectionStatus.FAILED_VALIDATION,
        CollectionStatus.SUCCESS,
    ]
    assert json.loads((tmp_path / "manifest.json").read_text())["status"] == "partial"


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (
            [CollectionStatus.SUCCESS, CollectionStatus.SUCCESS],
            CollectionStatus.SUCCESS,
        ),
        (
            [CollectionStatus.SUCCESS, CollectionStatus.UNAVAILABLE],
            CollectionStatus.PARTIAL,
        ),
        (
            [CollectionStatus.PARTIAL, CollectionStatus.FAILED_VALIDATION],
            CollectionStatus.PARTIAL,
        ),
        (
            [CollectionStatus.PARTIAL, CollectionStatus.PARTIAL],
            CollectionStatus.PARTIAL,
        ),
        (
            [CollectionStatus.BLOCKED_SOURCE, CollectionStatus.UNAVAILABLE],
            CollectionStatus.UNAVAILABLE,
        ),
    ],
)
def test_orchestrator_global_status_preserves_individual_statuses(statuses, expected):
    calls = []
    result = run_collectors(
        [
            FakeCollector(f"source-{index}", status, calls)
            for index, status in enumerate(statuses)
        ]
    )
    assert result.status == expected
    assert [item.status for item in result.results] == statuses


def test_ranking_comparison_separates_availability_from_ordinal_changes():
    result = compare_rankings(
        {"stable": 1, "left": 2, "moved": 25},
        {"stable": 2, "entered": 1, "moved": 21},
    )
    assert result["n_rankeados_baseline"] == 3
    assert result["n_rankeados_alternativo"] == 3
    assert result["entraram_no_ranking"] == ["entered"]
    assert result["sairam_do_ranking"] == ["left"]
    assert result["alteracoes_top20"] == {
        "entram": ["entered"],
        "saem": ["left"],
    }


def test_preflight_rejects_overwriting_immutable_raw(tmp_path):
    raw = tmp_path / "already-exists.json"
    raw.write_text("immutable", encoding="utf-8")
    with pytest.raises(FileExistsError, match="raw imutável já existe"):
        PREFLIGHT.execute(raw, tmp_path / "report.json", tmp_path / "manifest.json")
    assert raw.read_text(encoding="utf-8") == "immutable"


def test_all_robustness_scenarios_are_calculated(tmp_path):
    municipalities = canonical_rows()[:6]
    municipal_path = tmp_path / "municipios.csv"
    with municipal_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=municipalities[0])
        writer.writeheader()
        writer.writerows(municipalities)
    config = yaml.safe_load(Path("config/edicoes/mvp-demo-2026.yml").read_text())
    config["universo"]["municipios_esperados"] = len(municipalities)
    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml.safe_dump(config))
    observations = []
    infra_ids = [
        indicator
        for indicator, rule in config["indicadores"].items()
        if rule.get("eixo") == "infra"
    ]
    for index, municipality in enumerate(municipalities):
        for indicator in config["indicadores"]:
            # Distribuições deliberadamente não paralelas: outlier para R1,
            # assimetria de mercado para R2 e conflito de pesos para R3.
            if indicator == "INF-LOG-01":
                value = [0, 1, 2, 3, 4, 10000][index]
            elif indicator in infra_ids:
                value = [100, 80, 60, 40, 20, 0][index]
            elif indicator in {"MER-01", "MER-02"}:
                value = [0, 1, 3, 10, 100, 10000][index]
            else:
                value = index + 1
            observations.append(
                {
                    "municipio_id": municipality["municipio_id"],
                    "indicador_id": indicator,
                    "valor_bruto": value,
                    "periodo_referencia": "fixture",
                    "flag_qualidade": "observado",
                }
            )
    indicators_path = tmp_path / "indicators.csv"
    with indicators_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=observations[0])
        writer.writeheader()
        writer.writerows(observations)
    payload = generate_robustness(
        config_path,
        municipal_path,
        indicators_path,
        tmp_path / "output",
        municipal_path,
    )
    assert set(payload["cenarios"]) == {
        "baseline",
        "R1_sem_winsorizacao",
        "R2_sem_log",
        "R3_pesos_iguais_infra",
    }
    assert len(payload["comparacoes_com_baseline"]) == 3
    assert (tmp_path / "output" / "robustez.json").is_file()

    scenarios = payload["cenarios"]
    municipality_id = municipalities[1]["municipio_id"]
    assert (
        scenarios["baseline"][municipality_id]["nota_infra"]
        != scenarios["R1_sem_winsorizacao"][municipality_id]["nota_infra"]
    )
    assert (
        scenarios["baseline"][municipality_id]["nota_mercado"]
        != scenarios["R2_sem_log"][municipality_id]["nota_mercado"]
    )
    assert (
        scenarios["baseline"][municipality_id]["nota_infra"]
        != scenarios["R3_pesos_iguais_infra"][municipality_id]["nota_infra"]
    )

    baseline_parameters = json.loads(
        (tmp_path / "output/cenarios/baseline/parametros-score.json").read_text()
    )
    r1_parameters = json.loads(
        (
            tmp_path / "output/cenarios/R1_sem_winsorizacao/parametros-score.json"
        ).read_text()
    )
    assert baseline_parameters["INF-LOG-01"]["p99"] is not None
    assert r1_parameters["INF-LOG-01"]["p99"] is None

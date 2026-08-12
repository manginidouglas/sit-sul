import csv
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest
import yaml

from ice_sul.extract.contracts import CollectionResult, CollectionStatus
from ice_sul.extract.orchestrator import CollectorValidationError, run_collectors
from ice_sul.mvp.robustness import generate_robustness
from ice_sul.mvp.validate import validate_municipal_keys

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


def test_all_robustness_scenarios_are_calculated(tmp_path):
    municipalities = canonical_rows()[:4]
    municipal_path = tmp_path / "municipios.csv"
    with municipal_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=municipalities[0])
        writer.writeheader()
        writer.writerows(municipalities)
    config = yaml.safe_load(Path("config/edicoes/mvp-demo-2026.yml").read_text())
    config["universo"]["municipios_esperados"] = 4
    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml.safe_dump(config))
    observations = []
    for index, municipality in enumerate(municipalities, 1):
        for indicator in config["indicadores"]:
            observations.append(
                {
                    "municipio_id": municipality["municipio_id"],
                    "indicador_id": indicator,
                    "valor_bruto": index**3 + len(indicator),
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

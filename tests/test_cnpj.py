import csv
import hashlib
from http.client import IncompleteRead
import io
import json
import os
import zipfile
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

import pytest

from ice_sul.extract.cnpj import (
    CNPJCollector,
    CollectionValidationError,
    discover_snapshot,
    validate_topology,
)
from ice_sul.extract.contracts import CollectionStatus
from ice_sul.extract.orchestrator import run_collectors
from ice_sul.extract.registry import build_collectors
from ice_sul.transform.cnpj import (
    TransformationValidationError,
    build_numerators,
    classify_legal_nature,
    _record_failure,
    _recover_promotion,
    promote_outputs,
    validate_manifest,
)


def _zip_bytes(rows, member="fixture.csv"):
    text = io.StringIO(newline="")
    csv.writer(text, delimiter=";", lineterminator="\n").writerows(rows)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, text.getvalue().encode("latin-1"))
    return output.getvalue()


def _write_zip(path, rows, member="fixture.csv"):
    path.write_bytes(_zip_bytes(rows, member))


def _est(root, order, dv, status, uf, municipality):
    row = [""] * 30
    row[:3] = [root, order, dv]
    row[5], row[19], row[20] = status, uf, municipality
    return row


def _canonical(path):
    rows = []
    for uf, count, start in (("PR", 399, 4100000), ("SC", 295, 4200000), ("RS", 497, 4300000)):
        for index in range(count):
            rows.append(
                {
                    "municipio_id": str(start + index),
                    "municipio_nome": f"Municipio Comum" if index == 1 else f"M {uf} {index}",
                    "uf_sigla": uf,
                }
            )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def _fixture(tmp_path, establishments=None, simples=None):
    canonical = tmp_path / "canonical.csv"
    _canonical(canonical)
    establishments = establishments or [
        _est("11111111", "0001", "01", "02", "PR", "0001"),
        _est("11111111", "0002", "02", "2", "PR", "0001"),
        _est("22222222", "0001", "03", "02", "SC", "0002"),
        _est("33333333", "0001", "04", "02", "RS", "0003"),
        _est("99999999", "0001", "99", "08", "PR", "0001"),
    ]
    simples = simples or [
        ["11111111", "S", "", "", "S", "", ""],
        ["22222222", "S", "", "", "N", "", ""],
        ["33333333", "N", "", "", "", "", ""],
    ]
    resources = {
        "Municipios.zip": [["0001", "M PR 0"], ["0002", "M SC 0"], ["0003", "M RS 0"]],
        "Naturezas.zip": [["1015", "Orgao Publico"], ["2011", "Empresa Publica"], ["2038", "SEM"], ["2062", "Limitada"], ["3069", "Associacao"]],
        "Simples.zip": simples,
        "Empresas0.zip": [["11111111", "X", "2062"], ["22222222", "X", "2011"], ["33333333", "X", "3069"]],
        "Estabelecimentos0.zip": establishments,
    }
    artifacts = []
    for name, rows in resources.items():
        path = tmp_path / name
        _write_zip(path, rows)
        payload = path.read_bytes()
        with zipfile.ZipFile(path) as archive:
            uncompressed_bytes = sum(item.file_size for item in archive.infolist())
        artifacts.append(
            {
                "url": f"https://official/2026-07/{name}",
                "source": "cnpj",
                "method": "GET",
                "parameters": {},
                "final_url": f"https://official/2026-07/{name}",
                "http_status": 200,
                "name": name,
                "snapshot": "2026-07",
                "period_reference": "2026-07",
                "collected_at_utc": "2026-08-12T00:00:00+00:00",
                "path": str(path),
                "logical_path": str(path),
                "redirects": [],
                "content_type": "application/zip",
                "transferred_bytes": len(payload),
                "persisted_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "validated_at_utc": "2026-08-12T00:00:00+00:00",
                "zip_validation": "single-member-crc-ok",
                "uncompressed_bytes": uncompressed_bytes,
                "license": None,
                "license_status": "not_confirmed_in_official_material_reviewed",
            }
        )
    topology = {
        "Estabelecimentos": ["Estabelecimentos0.zip"],
        "Empresas": ["Empresas0.zip"],
        "Simples": ["Simples.zip"],
        "Municipios": ["Municipios.zip"],
        "Naturezas": ["Naturezas.zip"],
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "status": "complete",
                "source": "cnpj",
                "index_url": "https://official/2026-07/",
                "license": "fixture",
                "license_status": "fixture_only",
                "coverage_complete": True,
                "snapshot": "2026-07",
                "expected_artifact_count": len(artifacts),
                "topology": topology,
                "artifacts": artifacts,
            }
        ),
        encoding="utf-8",
    )
    return canonical, manifest


def _destinations(tmp_path):
    return {
        "output_csv": tmp_path / "out.csv",
        "bridge_csv": tmp_path / "bridge.csv",
        "report_json": tmp_path / "qa.json",
    }


def test_registry_builds_contract_collector():
    collector = build_collectors(["cnpj"])[0]
    assert isinstance(collector, CNPJCollector)
    assert collector.source == "cnpj"


def test_discovery_is_dynamic(monkeypatch):
    names = [
        "Estabelecimentos0.zip", "Estabelecimentos1.zip", "Empresas0.zip",
        "Empresas1.zip", "Empresas2.zip", "Simples.zip", "Municipios.zip", "Naturezas.zip",
    ]

    class Response:
        status, url, headers = 200, "https://official/2026-07/", Message()
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self): return "".join(f'<a href="{name}">x</a>' for name in names).encode()

    monkeypatch.setattr("ice_sul.extract.cnpj.urlopen", lambda *_a, **_k: Response())
    urls, _ = discover_snapshot("2026-07", base_url="https://official/")
    topology = validate_topology(urls)
    assert len(topology["Estabelecimentos"]) == 2
    assert len(topology["Empresas"]) == 3


@pytest.mark.parametrize(
    "names, message",
    [
        (["Estabelecimentos1.zip", "Empresas0.zip", "Simples.zip", "Municipios.zip", "Naturezas.zip"], "começar em 0"),
        (["Estabelecimentos0.zip", "Estabelecimentos2.zip", "Empresas0.zip", "Simples.zip", "Municipios.zip", "Naturezas.zip"], "contíguas"),
        (["Estabelecimentos0.zip", "Empresas0.zip", "Simples.zip", "Municipios.zip"], "ausentes"),
        (["Estabelecimentos0.zip", "Empresas0.zip", "Simples.zip", "Municipios.zip", "Naturezas.zip", "Naturezas.zip"], "duplicado"),
    ],
)
def test_topology_rejects_gaps_missing_singletons_and_duplicates(names, message):
    with pytest.raises(CollectionValidationError, match=message):
        validate_topology([f"https://official/{name}" for name in names])


def test_collector_returns_blocked_source_with_evidence(monkeypatch, tmp_path):
    error = HTTPError("https://official", 403, "forbidden", {}, None)
    monkeypatch.setattr("ice_sul.extract.cnpj.discover_snapshot", lambda *_a, **_k: (_ for _ in ()).throw(error))
    collector = CNPJCollector(destination=tmp_path / "raw", compact_manifest=tmp_path / "report.json", retries=0)
    result = collector.collect()
    assert result.status == CollectionStatus.BLOCKED_SOURCE
    assert json.loads((tmp_path / "report.json").read_text())["coverage_complete"] is False


def test_orchestrator_receives_collector_result_without_exception(monkeypatch, tmp_path):
    error = HTTPError("https://official", 503, "temporary", {}, None)
    monkeypatch.setattr(
        "ice_sul.extract.cnpj.discover_snapshot",
        lambda *_a, **_k: (_ for _ in ()).throw(error),
    )
    collector = CNPJCollector(
        destination=tmp_path / "raw",
        compact_manifest=tmp_path / "report.json",
        retries=0,
    )
    run = run_collectors([collector])
    assert run.results[0].status == CollectionStatus.UNAVAILABLE
    assert run.results[0].errors == ["HTTP Error 503: temporary"]


def test_valid_raw_is_reused_only_with_matching_manifest(tmp_path):
    collector = CNPJCollector(destination=tmp_path)
    target = tmp_path / "Simples.zip"
    _write_zip(target, [["x"]])
    entry = {"path": str(target), "persisted_bytes": target.stat().st_size, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    assert collector._reuse(target, entry)["reused"] is True
    entry["sha256"] = "0" * 64
    with pytest.raises(CollectionValidationError, match="diverge"):
        collector._reuse(target, entry)


def test_snapshot_derives_default_destination_and_honors_explicit_override(tmp_path):
    assert CNPJCollector(snapshot="2025-12").destination == Path("data/raw/cnpj/2025-12")
    assert CNPJCollector(snapshot="2025-12", destination=tmp_path).destination == tmp_path


class _Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.url = "https://official/resource.zip"
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = str(value)
    def __enter__(self): return self
    def __exit__(self, *_): return None


def test_resume_requires_validator_206_and_exact_content_range(monkeypatch, tmp_path):
    payload = _zip_bytes([["complete"]])
    target = tmp_path / "resource.zip"
    offset = 10
    (tmp_path / "resource.zip.part").write_bytes(payload[:offset])
    (tmp_path / "resource.zip.part.json").write_text(json.dumps({"etag": '"same"', "last_modified": None}))
    monkeypatch.setattr(
        "ice_sul.extract.cnpj.urlopen",
        lambda request, **_k: _Response(payload[offset:], 206, {"ETag": '"same"', "Content-Range": f"bytes {offset}-{len(payload)-1}/{len(payload)}", "Content-Length": len(payload)-offset}),
    )
    item = CNPJCollector(destination=tmp_path)._download_once("https://official/resource.zip", target)
    assert target.read_bytes() == payload
    assert item["resumed_from_bytes"] == offset


def test_server_ignoring_range_restarts_instead_of_appending(monkeypatch, tmp_path):
    payload = _zip_bytes([["complete"]])
    target = tmp_path / "resource.zip"
    (tmp_path / "resource.zip.part").write_bytes(b"old partial")
    (tmp_path / "resource.zip.part.json").write_text(json.dumps({"etag": '"old"', "last_modified": None}))
    monkeypatch.setattr(
        "ice_sul.extract.cnpj.urlopen",
        lambda request, **_k: _Response(payload, 200, {"ETag": '"new"', "Content-Length": len(payload)}),
    )
    CNPJCollector(destination=tmp_path)._download_once("https://official/resource.zip", target)
    assert target.read_bytes() == payload


def test_receipt_recovers_raw_promoted_before_manifest_checkpoint(monkeypatch, tmp_path):
    payload = _zip_bytes([["complete"]])
    url = "https://official/resource.zip"
    target = tmp_path / "resource.zip"
    monkeypatch.setattr(
        "ice_sul.extract.cnpj.urlopen",
        lambda *_a, **_k: _Response(payload, 200, {"ETag": '"v1"', "Content-Length": len(payload), "Content-Type": "application/zip"}),
    )
    first = CNPJCollector(destination=tmp_path)
    entry = first._download_once(url, target)  # simula queda antes de atualizar manifest.json
    assert {
        "source", "url", "method", "parameters", "snapshot", "period_reference",
        "collected_at_utc", "http_status", "final_url", "redirects", "content_type",
        "transferred_bytes", "persisted_bytes", "sha256", "logical_path", "license",
        "license_status", "zip_validation",
    } <= entry.keys()
    assert entry["license"] is None
    assert entry["license_status"] == "not_confirmed_in_official_material_reviewed"
    assert target.exists() and first._receipt_path(target).exists()
    monkeypatch.setattr(
        "ice_sul.extract.cnpj.urlopen",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("não deve baixar novamente")),
    )
    recovered = CNPJCollector(destination=tmp_path)._download(url, {"artifacts": []})
    assert recovered["reused"] is True
    assert target.read_bytes() == payload


def test_receipt_promotes_complete_validated_part_without_network(monkeypatch, tmp_path):
    payload = _zip_bytes([["complete"]])
    url = "https://official/resource.zip"
    target = tmp_path / "resource.zip"
    part = tmp_path / "resource.zip.part"
    part.write_bytes(payload)
    entry = {
        "url": url,
        "persisted_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    collector = CNPJCollector(destination=tmp_path)
    collector._receipt_path(target).write_text(
        json.dumps({"state": "validated_part", "entry": entry})
    )
    monkeypatch.setattr(
        "ice_sul.extract.cnpj.urlopen",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("rede proibida")),
    )
    recovered = collector._download(url, {"artifacts": []})
    assert recovered["reused"] is True
    assert target.read_bytes() == payload
    assert not part.exists()


class _InterruptedResponse(_Response):
    def __init__(self, first, error):
        super().__init__(b"", 200, {"ETag": '"v1"', "Content-Type": "application/zip"})
        self.first = first
        self.error = error
        self.calls = 0
    def read(self, _size=-1):
        self.calls += 1
        if self.calls == 1:
            return self.first
        raise self.error


@pytest.mark.parametrize(
    "error",
    [IncompleteRead(b"tail"), ConnectionResetError("reset")],
)
def test_stream_interruption_is_unavailable_and_preserves_partial(monkeypatch, tmp_path, error):
    monkeypatch.setattr(
        "ice_sul.extract.cnpj.discover_snapshot",
        lambda *_a, **_k: (
            [
                "https://official/Estabelecimentos0.zip", "https://official/Empresas0.zip",
                "https://official/Simples.zip", "https://official/Municipios.zip",
                "https://official/Naturezas.zip",
            ],
            {"index_url": "https://official/", "index_final_url": "https://official/", "index_http_status": 200},
        ),
    )
    monkeypatch.setattr(CNPJCollector, "_storage_preflight", lambda *_: {"test": True})
    monkeypatch.setattr(
        "ice_sul.extract.cnpj.urlopen",
        lambda *_a, **_k: _InterruptedResponse(b"partial", error),
    )
    result = CNPJCollector(destination=tmp_path / "raw", compact_manifest=tmp_path / "report.json", retries=0).collect()
    assert result.status == CollectionStatus.UNAVAILABLE
    partial = tmp_path / "raw" / "Estabelecimentos0.zip.part"
    assert partial.exists() and partial.stat().st_size >= len(b"partial")


def test_storage_preflight_blocks_known_oversized_bulk(monkeypatch, tmp_path):
    collector = CNPJCollector(destination=tmp_path / "raw")
    monkeypatch.setattr(collector, "_head_size", lambda _url: 100)
    usage = type("Usage", (), {"free": 1})()
    monkeypatch.setattr("ice_sul.extract.cnpj.shutil.disk_usage", lambda _path: usage)
    with pytest.raises(OSError, match="espaço insuficiente"):
        collector._storage_preflight(["https://official/a.zip"])


def test_storage_preflight_creates_cnpj_directories_on_clean_checkout(monkeypatch, tmp_path):
    destination = tmp_path / "data" / "raw" / "cnpj" / "2026-07"
    collector = CNPJCollector(destination=destination)
    monkeypatch.setattr(collector, "_head_size", lambda _url: None)
    evidence = collector._storage_preflight(["https://official/a.zip"])
    assert destination.is_dir()
    assert evidence["all_content_lengths_known"] is False


def test_invalid_zip_is_never_promoted(monkeypatch, tmp_path):
    monkeypatch.setattr("ice_sul.extract.cnpj.urlopen", lambda *_a, **_k: _Response(b"not zip", 200, {"Content-Length": 7, "ETag": '"x"'}))
    with pytest.raises(CollectionValidationError, match="ZIP inválido"):
        CNPJCollector(destination=tmp_path)._download_once("https://official/bad.zip", tmp_path / "bad.zip")
    assert not (tmp_path / "bad.zip").exists()


@pytest.mark.parametrize(
    "code, expected",
    [("101-5", "estatal_identificavel"), ("201-1", "estatal_identificavel"), ("203-8", "estatal_identificavel"), ("206-2", "nao_estatal_proxy"), ("306-9", "nao_estatal_proxy"), ("401-4", "nao_estatal_proxy"), ("501-0", "internacional_extraterritorial")],
)
def test_legal_nature_proxy_is_explicit(code, expected):
    assert classify_legal_nature(code) == expected


@pytest.mark.parametrize(
    "parts, valid",
    [
        (("12345678", "0001", "95"), True),
        (("00000000", "E08G", "12"), True),
        (("AB12CD34", "0001", "09"), True),
        (("AB12_D34", "0001", "09"), False),
        (("AB12CD34", "0001", "A9"), False),
    ],
)
def test_cnpj_legacy_and_alphanumeric_structure(parts, valid):
    from ice_sul.transform.cnpj import _valid_cnpj_parts
    assert _valid_cnpj_parts(*parts) is valid


@pytest.mark.parametrize("code", ["X2062", "2062Y", "20-62", " 2062"])
def test_legal_nature_malformed_values_are_not_silently_normalized(code):
    with pytest.raises(TransformationValidationError, match="inválida"):
        classify_legal_nature(code)


@pytest.mark.parametrize(
    "status, option, message",
    [("0002", "S", "situacao_cadastral_inesperada"), ("02", "s", "mei_inesperado")],
)
def test_unknown_domains_are_evidence_not_normalized(tmp_path, status, option, message):
    establishments = [_est("11111111", "0001", "01", status, "PR", "0001")]
    simples = [["11111111", "S", "", "", option, "", ""]]
    canonical, manifest = _fixture(
        tmp_path, establishments=establishments, simples=simples
    )
    with pytest.raises(TransformationValidationError, match=message):
        build_numerators(
            manifest_path=manifest,
            canonical_csv=canonical,
            snapshot="2026-07",
            **_destinations(tmp_path),
        )


def test_manifest_rejects_incomplete_hash_and_invalid_zip(tmp_path):
    _, manifest = _fixture(tmp_path)
    data = json.loads(manifest.read_text())
    data["coverage_complete"] = False
    manifest.write_text(json.dumps(data))
    with pytest.raises(TransformationValidationError, match="cobertura"):
        validate_manifest(manifest, "2026-07")
    data["coverage_complete"] = True
    data["artifacts"][0]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(data))
    with pytest.raises(TransformationValidationError, match="hash"):
        validate_manifest(manifest, "2026-07")


def test_artifact_provenance_contract_and_bounded_failure_samples(tmp_path):
    _, manifest = _fixture(tmp_path)
    _, paths = validate_manifest(manifest, "2026-07")
    assert set(paths) == {
        "Estabelecimentos0.zip", "Empresas0.zip", "Simples.zip",
        "Municipios.zip", "Naturezas.zip",
    }
    failures = {}
    for index in range(100):
        _record_failure(failures, "invalid", index)
    assert failures["invalid"]["count"] == 100
    assert failures["invalid"]["samples"] == list(range(20))


def test_end_to_end_preserves_filials_mei_blank_private_and_uf_context(tmp_path):
    canonical, manifest = _fixture(tmp_path)
    destinations = _destinations(tmp_path)
    qa = build_numerators(manifest_path=manifest, canonical_csv=canonical, snapshot="2026-07", **destinations)
    rows = {row["municipio_id"]: row for row in csv.DictReader(destinations["output_csv"].open())}
    assert len(rows) == 1191
    assert rows["4100000"]["estabelecimentos_ativos_total"] == "2"  # duas filiais
    assert rows["4100000"]["estabelecimentos_ativos_mei"] == "2"
    assert rows["4200000"]["estabelecimentos_ativos_nao_estatais_proxy"] == "0"
    assert rows["4300000"]["estabelecimentos_ativos_sem_mei_identificado"] == "1"  # branco/OUTROS
    assert qa["domains_observed"]["opcao_mei"] == {"S": 1, "N": 1, "BRANCO_OUTROS": 1}
    assert qa["totals"]["by_uf"]["PR"]["total"] == 2
    assert qa["totals"]["by_uf"]["SC"]["nao_estatal_proxy"] == 0
    assert qa["sanity_checks"]["by_uf"]["RS"]["lowest_nonzero"][0][
        "municipio_id"
    ] == "4300000"
    assert all(qa["gates"].values())
    bridge = list(csv.DictReader(destinations["bridge_csv"].open()))
    assert {(row["uf_observada"], row["codigo_municipio_rfb"]) for row in bridge} == {("PR", "0001"), ("SC", "0002"), ("RS", "0003")}


def test_national_join_tables_persist_only_roots_needed_by_active_south(tmp_path):
    canonical, manifest = _fixture(tmp_path)
    data = json.loads(manifest.read_text())
    by_name = {entry["name"]: entry for entry in data["artifacts"]}
    extras = [
        [f"{index:08d}", "S", "", "", "N", "", ""]
        for index in range(1000, 2000)
    ]
    extras_companies = [[f"{index:08d}", "X", "2062"] for index in range(1000, 2000)]
    for name, rows in (
        ("Simples.zip", [
            ["11111111", "S", "", "", "S", "", ""],
            ["22222222", "S", "", "", "N", "", ""],
            ["33333333", "N", "", "", "", "", ""],
            *extras,
        ]),
        ("Empresas0.zip", [
            ["11111111", "X", "2062"], ["22222222", "X", "2011"],
            ["33333333", "X", "3069"], *extras_companies,
        ]),
    ):
        path = tmp_path / name
        _write_zip(path, rows)
        entry = by_name[name]
        entry["persisted_bytes"] = path.stat().st_size
        entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with zipfile.ZipFile(path) as archive:
            entry["uncompressed_bytes"] = sum(item.file_size for item in archive.infolist())
    manifest.write_text(json.dumps(data))
    qa = build_numerators(
        manifest_path=manifest,
        canonical_csv=canonical,
        snapshot="2026-07",
        **_destinations(tmp_path),
    )
    assert qa["rows_read"]["linhas_simples_lidas"] == 1003
    assert qa["rows_read"]["linhas_simples_persistidas"] == 3
    assert qa["rows_read"]["linhas_empresas_lidas"] == 1003
    assert qa["rows_read"]["linhas_empresas_persistidas"] == 3


def test_end_to_end_counts_alphanumeric_order_without_numeric_coercion(tmp_path):
    establishments = [_est("11111111", "E08G", "12", "02", "PR", "0001")]
    canonical, manifest = _fixture(tmp_path, establishments=establishments)
    qa = build_numerators(
        manifest_path=manifest,
        canonical_csv=canonical,
        snapshot="2026-07",
        **_destinations(tmp_path),
    )
    assert qa["rows_read"]["cnpj_alfanumerico"] == 1
    assert qa["rows_read"].get("cnpj_numerico", 0) == 0


def test_same_name_in_other_ufs_does_not_cross_match(tmp_path):
    establishments = [_est("11111111", "0001", "01", "02", "SC", "0001")]
    canonical, manifest = _fixture(tmp_path, establishments=establishments, simples=[["11111111", "S", "", "", "N", "", ""]])
    # Código 0001 tem nome M PR 0 e não pode ser tentado como município de SC.
    with pytest.raises(TransformationValidationError, match="território"):
        build_numerators(manifest_path=manifest, canonical_csv=canonical, snapshot="2026-07", **_destinations(tmp_path))


def test_active_root_without_simples_is_absence_not_non_mei_or_zero(tmp_path):
    establishments = [_est("44444444", "0001", "01", "02", "PR", "0001")]
    canonical, manifest = _fixture(tmp_path, establishments=establishments)
    output = tmp_path / "out.csv"
    output.write_bytes(b"previous approved")
    destinations = _destinations(tmp_path)
    destinations["output_csv"] = output
    with pytest.raises(TransformationValidationError, match="sem join"):
        build_numerators(manifest_path=manifest, canonical_csv=canonical, snapshot="2026-07", **destinations)
    assert output.read_bytes() == b"previous approved"


def test_conflicting_duplicate_cnpj_blocks_publication(tmp_path):
    duplicate = [
        _est("11111111", "0001", "01", "02", "PR", "0001"),
        _est("11111111", "0001", "01", "02", "SC", "0002"),
    ]
    canonical, manifest = _fixture(tmp_path, establishments=duplicate)
    with pytest.raises(TransformationValidationError):
        build_numerators(manifest_path=manifest, canonical_csv=canonical, snapshot="2026-07", **_destinations(tmp_path))


def test_transaction_rolls_back_every_previous_output(tmp_path):
    destinations = {tmp_path / f"out-{index}.csv": tmp_path / f"stage-{index}.csv" for index in range(4)}
    for index, (destination, source) in enumerate(destinations.items()):
        destination.write_bytes(f"old-{index}".encode())
        source.write_bytes(f"new-{index}".encode())
    calls = 0
    def failing_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 6:  # quatro backups, uma promoção, falha na segunda promoção
            raise OSError("injected promotion failure")
        return os.replace(source, destination)
    with pytest.raises(OSError, match="injected"):
        promote_outputs(destinations, replace=failing_replace)
    assert [path.read_bytes() for path in destinations] == [f"old-{index}".encode() for index in range(4)]


def test_abrupt_promotion_is_recovered_from_durable_journal(tmp_path):
    staged = {
        tmp_path / f"out-{index}.csv": tmp_path / f"stage-{index}.csv"
        for index in range(3)
    }
    for index, (destination, source) in enumerate(staged.items()):
        destination.write_bytes(f"old-{index}".encode())
        source.write_bytes(f"new-{index}".encode())
    calls = 0

    class AbruptStop(BaseException):
        pass

    def abrupt_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 5:  # três backups, primeira promoção, queda na segunda
            raise AbruptStop()
        return os.replace(source, destination)

    with pytest.raises(AbruptStop):
        promote_outputs(staged, replace=abrupt_replace)
    journal = tmp_path / ".cnpj-promotion-journal.json"
    assert journal.exists()
    _recover_promotion(journal)
    assert [path.read_bytes() for path in staged] == [
        f"old-{index}".encode() for index in range(3)
    ]


def test_abrupt_stop_after_backup_move_is_recoverable(tmp_path):
    destination = tmp_path / "out.csv"
    source = tmp_path / "stage.csv"
    destination.write_bytes(b"old")
    source.write_bytes(b"new")

    class AbruptStop(BaseException):
        pass

    def move_then_stop(origin, target):
        os.replace(origin, target)
        raise AbruptStop()

    with pytest.raises(AbruptStop):
        promote_outputs({destination: source}, replace=move_then_stop)
    _recover_promotion(tmp_path / ".cnpj-promotion-journal.json")
    assert destination.read_bytes() == b"old"


def test_committed_generation_survives_abrupt_backup_cleanup(tmp_path):
    staged = {
        tmp_path / f"out-{index}.csv": tmp_path / f"stage-{index}.csv"
        for index in range(3)
    }
    for index, (destination, source) in enumerate(staged.items()):
        destination.write_bytes(f"old-{index}".encode())
        source.write_bytes(f"new-{index}".encode())
    removals = 0

    class AbruptStop(BaseException):
        pass

    def remove_then_stop(path):
        nonlocal removals
        removals += 1
        path.unlink(missing_ok=True)
        if removals == 2:
            raise AbruptStop()

    with pytest.raises(AbruptStop):
        promote_outputs(staged, remove=remove_then_stop)
    journal = tmp_path / ".cnpj-promotion-journal.json"
    assert json.loads(journal.read_text())["state"] == "committed"
    _recover_promotion(journal)
    assert [path.read_bytes() for path in staged] == [
        f"new-{index}".encode() for index in range(3)
    ]


def test_build_recovers_pending_publication_before_manifest_validation(tmp_path):
    output = tmp_path / "municipios.csv"
    bridge = tmp_path / "bridge.csv"
    quality = tmp_path / "qa.json"
    staged = {}
    for destination in (output, bridge, quality):
        destination.write_bytes(b"old-generation")
        source = tmp_path / f"stage-{destination.name}"
        source.write_bytes(b"new-generation")
        staged[destination] = source

    class AbruptStop(BaseException):
        pass

    calls = 0

    def abrupt_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 5:
            raise AbruptStop()
        return os.replace(source, destination)

    with pytest.raises(AbruptStop):
        promote_outputs(staged, replace=abrupt_replace)
    assert (tmp_path / ".cnpj-promotion-journal.json").exists()

    # A execução B falha antes de preflight/leitura/publicação, mas precisa ter
    # resolvido a transação A logo na entrada.
    with pytest.raises(FileNotFoundError):
        build_numerators(
            manifest_path=tmp_path / "manifest-missing.json",
            canonical_csv=tmp_path / "canonical.csv",
            output_csv=output,
            bridge_csv=bridge,
            report_json=quality,
            snapshot="2026-07",
        )
    assert not (tmp_path / ".cnpj-promotion-journal.json").exists()
    assert [path.read_bytes() for path in (output, bridge, quality)] == [
        b"old-generation",
        b"old-generation",
        b"old-generation",
    ]

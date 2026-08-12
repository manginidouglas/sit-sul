import csv
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).parents[1]
DOWNLOAD = ROOT / "scripts/routing/download_osm.sh"


def test_osm_download_is_immutable_and_promoted_only_after_validation(tmp_path):
    payload = b"controlled OSM fixture"
    served = tmp_path / "served"
    served.mkdir()
    (served / "snapshot.pbf").write_bytes(payload)
    handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(*args, directory=served, **kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    destination = tmp_path / "raw/snapshot.pbf"
    env = os.environ | {
        "OSM_SNAPSHOT_URL": f"http://127.0.0.1:{server.server_port}/snapshot.pbf",
        "OSM_SNAPSHOT_SIZE": str(len(payload)),
        "OSM_SNAPSHOT_MD5": hashlib.md5(payload).hexdigest(),  # noqa: S324 - mirrors official legacy checksum
        "OSM_SNAPSHOT_SHA256": hashlib.sha256(payload).hexdigest(),
    }
    try:
        first = subprocess.run([DOWNLOAD, destination], env=env, text=True, capture_output=True)
        assert first.returncode == 0 and destination.read_bytes() == payload and not Path(str(destination) + ".part").exists()
        valid_mtime = destination.stat().st_mtime_ns
        second = subprocess.run([DOWNLOAD, destination], env=env, text=True, capture_output=True)
        assert second.returncode == 0 and destination.stat().st_mtime_ns == valid_mtime
        destination.write_bytes(b"corrupt")
        invalid_mtime = destination.stat().st_mtime_ns
        third = subprocess.run([DOWNLOAD, destination], env=env, text=True, capture_output=True)
        assert third.returncode != 0 and destination.read_bytes() == b"corrupt"
        assert destination.stat().st_mtime_ns == invalid_mtime
        assert "refusing to replace" in third.stderr
    finally:
        server.shutdown()


def load_seats_module():
    spec = importlib.util.spec_from_file_location("build_municipal_seats", ROOT / "scripts/routing/build_municipal_seats.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_versioned_seats_match_canonical_exactly():
    with (ROOT / "data/interim/routing/municipal_seats_south_2022.csv").open(encoding="utf-8") as stream:
        seats = list(csv.DictReader(stream))
    with (ROOT / "data/processed/2026/municipios.csv").open(encoding="utf-8") as stream:
        canonical = list(csv.DictReader(stream))
    assert len(seats) == len({row["municipio_id"] for row in seats}) == 1191
    assert {(x["municipio_id"], x["municipio_nome"], x["uf_sigla"]) for x in seats} == {
        (x["municipio_id"], x["municipio_nome"], x["uf_sigla"]) for x in canonical
    }


def test_seat_validation_rejects_missing_extra_mismatch_and_duplicate(tmp_path):
    module = load_seats_module()
    module.CANONICAL = tmp_path / "municipios.csv"
    module.CANONICAL.write_text("municipio_id,municipio_nome,uf_sigla\n1,Alpha,PR\n2,Beta,SC\n", encoding="utf-8")
    good = [("1", "Alpha", "PR", -1, -2, "sede"), ("2", "Beta", "SC", -3, -4, "sede")]
    module.validate_against_canonical(good)
    for bad in [good[:1], good + [("3", "Gamma", "RS", 0, 0, "sede")],
                [("1", "Wrong", "PR", 0, 0, "sede"), good[1]], [good[0], good[0], good[1]]]:
        try:
            module.validate_against_canonical(bad)
        except RuntimeError:
            pass
        else:
            raise AssertionError("invalid municipal identities were accepted")

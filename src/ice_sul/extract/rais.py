"""Coletor Onda 1 para a distribuição oficial RAIS 2024 VINC_PUB."""

from __future__ import annotations

import json
import hashlib
from datetime import UTC, datetime
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ice_sul.extract.contracts import CollectionResult, CollectionStatus
from ice_sul.extract.http import download
from ice_sul.extract.registry import register_collector
from ice_sul.transform.rais import load_municipality_map, transform_archive

OFFICIAL_ROOT = "https://ftp.mtps.gov.br/pdet/microdados/RAIS/2024"
DE_PARA_URL = f"{OFFICIAL_ROOT}/De-Para%20Microdados.xlsx"
IBGE_MUNICIPALITIES_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios?orderBy=id"
UF_CODES = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()


@dataclass(frozen=True)
class RaisArchive:
    uf: str
    url: str

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def official_archives() -> list[RaisArchive]:
    return [RaisArchive(uf, f"{OFFICIAL_ROOT}/RAIS_VINC_PUB_{uf}.7z") for uf in UF_CODES]


def download_large(url: str, destination: Path, *, uf: str) -> dict[str, object]:
    """Transfere `.7z` em blocos, sem manter o arquivo RAIS inteiro em memória."""
    if destination.exists():
        raise FileExistsError(f"raw imutável já existe: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256(); size = 0
    try:
        with urlopen(Request(url, headers={"User-Agent": "SIT-mvp-demo-2026/1.0"}), timeout=180) as response, temporary.open("xb") as output:
            while chunk := response.read(8 * 1024 * 1024):
                output.write(chunk); digest.update(chunk); size += len(chunk)
            status, final_url = response.status, response.url
        if not size: raise ValueError("arquivo RAIS vazio")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "fonte": "MTE/PDET RAIS VINC_PUB", "url": url, "url_final": final_url,
        "status_http": status, "uf": uf, "periodo": "2024", "arquivo": str(destination),
        "tamanho": size, "sha256": digest.hexdigest(),
        "data_hora_utc": datetime.now(UTC).isoformat(), "validacao": "recebido_nao_vazio",
    }


@dataclass
class RaisCollector:
    """Implementa o contrato compartilhado sem esconder falhas de fonte/layout."""

    destination: Path = Path("data/raw/rais/2024")
    interim: Path = Path("data/interim/rais/2024")
    quality: Path = Path("reports/quality/mvp-demo-2026/rais")
    south_reference: Path = Path("data/processed/2026/municipios.csv")
    archives: list[RaisArchive] = field(default_factory=official_archives)
    source: str = "rais"

    def collect(self) -> CollectionResult:
        self.destination.mkdir(parents=True, exist_ok=True)
        entries: list[dict[str, object]] = []
        artifacts: list[str] = []
        warnings: list[str] = []
        # A planilha é evidência de layout e fica junto ao raw; não é inferida.
        de_para = self.destination / "De-Para Microdados.xlsx"
        try:
            ibge_json = self.destination / "municipios-ibge.json"
            if not ibge_json.exists():
                entries.append(download(IBGE_MUNICIPALITIES_URL, ibge_json, source="IBGE Localidades", indicators=["MER-02", "MER-DIAG-01"], period="2024", timeout=180))
            ibge_rows = json.loads(ibge_json.read_text(encoding="utf-8"))
            municipality_map = {}
            for item in ibge_rows:
                code = str(item["id"])
                if len(code) != 7 or code[:6] in municipality_map:
                    raise ValueError(f"cadastro IBGE nacional inválido/ambíguo: {code}")
                municipality_map[code[:6]] = code; municipality_map[code] = code
            south_map = load_municipality_map(self.south_reference)
            south_ids = sorted({value for key, value in south_map.items() if len(key) == 6})
            if not de_para.exists():
                entries.append(download(DE_PARA_URL, de_para, source="MTE/PDET RAIS 2024", indicators=["MER-02", "MER-DIAG-01"], period="2024", timeout=180))
            artifacts.append(str(de_para))
            results = []
            for spec in self.archives:
                archive = self.destination / spec.filename
                if not archive.exists():
                    entries.append(download_large(spec.url, archive, uf=spec.uf))
                artifacts.append(str(archive))
                result = transform_archive(
                    archive, file_uf=spec.uf, municipality_map=municipality_map, year=2024,
                    south_municipalities=[code for code in south_ids if {"41": "PR", "42": "SC", "43": "RS"}.get(code[:2]) == spec.uf],
                )
                results.append(result)
        except ModuleNotFoundError as exc:
            return CollectionResult(self.source, CollectionStatus.BLOCKED_ENVIRONMENT, artifacts, ["MER-02", "MER-DIAG-01"], entries, warnings, [str(exc)])
        except (HTTPError, URLError, TimeoutError) as exc:
            return CollectionResult(self.source, CollectionStatus.BLOCKED_SOURCE, artifacts, ["MER-02", "MER-DIAG-01"], entries, warnings, [str(exc)])
        except ValueError as exc:
            return CollectionResult(self.source, CollectionStatus.FAILED_VALIDATION, artifacts, ["MER-02", "MER-DIAG-01"], entries, warnings, [str(exc)])

        # Cada arquivo pertence a uma UF; portanto municípios não devem se repetir.
        private = [row for result in results for row in result.private_employment]
        diagnostic = [row for result in results for row in result.diversification]
        if len(private) != len({row["municipio_id"] for row in private}):
            raise ValueError("município repetido entre arquivos VINC_PUB de UF")
        if not private:
            return CollectionResult(self.source, CollectionStatus.FAILED_VALIDATION, artifacts, ["MER-02", "MER-DIAG-01"], entries, warnings, ["nenhum vínculo privado elegível foi produzido"])
        if len(diagnostic) != 1191 or len({row["municipio_id"] for row in diagnostic}) != 1191:
            return CollectionResult(self.source, CollectionStatus.FAILED_VALIDATION, artifacts, ["MER-02", "MER-DIAG-01"], entries, warnings, [f"contrato MER-DIAG-01 exige 1.191 municípios; obtidos {len(diagnostic)}"])
        self.interim.mkdir(parents=True, exist_ok=True); self.quality.mkdir(parents=True, exist_ok=True)
        import csv
        with (self.interim / "emprego_privado_municipal.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(private[0])); writer.writeheader(); writer.writerows(sorted(private, key=lambda row: row["municipio_id"]))
        with (self.interim / "mer_diag_01.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["municipio_id", "indicador_id", "valor_bruto", "periodo_referencia", "flag_qualidade"]); writer.writeheader(); writer.writerows(sorted(diagnostic, key=lambda row: row["municipio_id"]))
        qa = {
            "ano": 2024, "ufs_processadas": [spec.uf for spec in self.archives],
            "vinculos_lidos": sum(r.quality.get("vinculos_lidos", 0) for r in results),
            "vinculos_inativos_excluidos": sum(r.quality.get("vinculos_inativos_excluidos", 0) for r in results),
            "vinculos_administracao_publica_excluidos": sum(r.quality.get("vinculos_administracao_publica_excluidos", 0) for r in results),
            "vinculos_privados_elegiveis": sum(r.quality.get("vinculos_privados_elegiveis", 0) for r in results),
            "soma_municipal": sum(int(row["empregos_formais_privados"]) for row in private),
            "municipios_ligados": len(private),
            "codigos_nao_ligados": {spec.uf: r.quality["codigos_nao_ligados"] for spec, r in zip(self.archives, results) if r.quality["codigos_nao_ligados"]},
        }
        qa["reconciliacao_ok"] = qa["soma_municipal"] == qa["vinculos_privados_elegiveis"]
        qa_path = self.quality / "qa.json"; qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        artifacts += [str(self.interim / "emprego_privado_municipal.csv"), str(self.interim / "mer_diag_01.csv"), str(qa_path)]
        unmatched = sum(len(r.quality["codigos_nao_ligados"]) for r in results)
        status = CollectionStatus.PARTIAL if unmatched else CollectionStatus.SUCCESS
        if unmatched: warnings.append(f"{unmatched} códigos municipais RAIS não ligados")
        return CollectionResult(self.source, status, artifacts, ["MER-02", "MER-DIAG-01"], entries, warnings)


register_collector("rais", RaisCollector)

"""RAIS 2024: leitura do `.comt`, harmonização e agregações municipais."""

from __future__ import annotations

import csv
import json
import math
import re
import tempfile
import unicodedata
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping, TextIO


# Nomes confirmados na aba VINC_PUB do De-Para Microdados.xlsx da RAIS 2024.
# Os aliases antigos são somente compatibilidade, nunca a especificação primária.
ALIASES = {
    "municipio": (
        "municípiotrabcódigo", "municípiocódigo", "municipio ibge",
        "cod municipio", "cod mun trab",
    ),
    "cnae": ("cnae20classecódigo", "cnae 2.0 classe", "cnae 2.0 divisao", "cnae"),
    "natureza": ("naturezajurídicacódigo", "natureza jurídica", "natureza jur"),
    "ativo": ("indvínculoativo3112código", "vínculo ativo 31/12", "ativo 31/12"),
    "uf": ("uf", "sigla uf"),
}
UF_PREFIX = {
    "12": "AC", "27": "AL", "13": "AM", "16": "AP", "29": "BA", "23": "CE",
    "53": "DF", "32": "ES", "52": "GO", "21": "MA", "31": "MG", "50": "MS",
    "51": "MT", "15": "PA", "25": "PB", "26": "PE", "22": "PI", "41": "PR",
    "33": "RJ", "24": "RN", "11": "RO", "14": "RR", "43": "RS", "42": "SC",
    "28": "SE", "35": "SP", "17": "TO",
}


def _normal(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def resolve_columns(fieldnames: Iterable[str]) -> dict[str, str]:
    normalized = {_normal(name): name for name in fieldnames}
    result: dict[str, str] = {}
    for target, aliases in ALIASES.items():
        for alias in aliases:
            if _normal(alias) in normalized:
                result[target] = normalized[_normal(alias)]
                break
    missing = {"municipio", "cnae", "natureza", "ativo"} - result.keys()
    if missing:
        raise ValueError(f"colunas VINC_PUB RAIS 2024 ausentes: {sorted(missing)}")
    return result


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def cnae_division(value: object) -> str:
    digits = _digits(value)
    if len(digits) < 2 or not 1 <= int(digits[:2]) <= 99:
        raise ValueError(f"CNAE 2.0 inválida: {value!r}")
    return digits[:2]


def is_public_administration(cnae: object, legal_nature: object) -> bool:
    """Regra aprovada: CNAE divisão 84 OU Natureza Jurídica grupo 1."""
    return cnae_division(cnae) == "84" or _digits(legal_nature).startswith("1")


def load_municipality_map(reference_csv: Path) -> dict[str, str]:
    """Cria de-para explícito RAIS (6 dígitos) -> IBGE (7), sem calcular DV."""
    with reference_csv.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    mapping: dict[str, str] = {}
    for row in rows:
        ibge = str(row["municipio_id"]).strip()
        if not re.fullmatch(r"\d{7}", ibge):
            raise ValueError(f"municipio_id canônico inválido: {ibge!r}")
        rais = ibge[:6]  # chave explícita derivada do cadastro, sem completar DV.
        if rais in mapping and mapping[rais] != ibge:
            raise ValueError(f"chave RAIS ambígua no cadastro: {rais}")
        mapping[rais] = ibge
        mapping[ibge] = ibge
    return mapping


def _detect_encoding(path: Path) -> str:
    with path.open("rb") as stream:
        raw = stream.read(65536)
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            pass
    raise ValueError("encoding do .comt não é UTF-8 nem Windows-1252")


def read_comt(path: Path) -> tuple[csv.DictReader, TextIO, dict[str, str]]:
    """Abre o texto RAIS e detecta delimitador em conjunto estritamente permitido."""
    encoding = _detect_encoding(path)
    stream = path.open("r", encoding=encoding, newline="")
    sample = stream.read(65536)
    dialect = csv.Sniffer().sniff(sample, delimiters=";|\t")
    stream.seek(0)
    reader = csv.DictReader(stream, dialect=dialect)
    if not reader.fieldnames:
        raise ValueError(".comt sem cabeçalho")
    metadata = {"encoding": encoding, "delimitador": dialect.delimiter}
    return reader, stream, metadata


@contextmanager
def extracted_comt(archive: Path) -> Iterator[Path]:
    """Extrai controladamente um único VINC_PUB `.comt` de um `.7z`."""
    try:
        import py7zr
    except ModuleNotFoundError as exc:  # traduzido pelo orquestrador em blocked_environment
        raise ModuleNotFoundError("py7zr é necessário para abrir RAIS .7z") from exc
    if archive.suffix.lower() != ".7z":
        raise ValueError(f"arquivo RAIS não é .7z: {archive}")
    with py7zr.SevenZipFile(archive, mode="r") as seven:
        names = seven.getnames()
        candidates = [name for name in names if Path(name).suffix.lower() == ".comt"]
        if len(candidates) != 1:
            raise ValueError(f"esperado exatamente um .comt; encontrados: {candidates}")
        member = candidates[0]
        member_path = Path(member)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise ValueError(f"caminho inseguro no .7z: {member}")
        with tempfile.TemporaryDirectory(prefix="sit-rais-") as directory:
            seven.extract(path=directory, targets=[member])
            yield Path(directory) / member


@dataclass
class RaisResult:
    private_employment: list[dict[str, object]]
    diversification: list[dict[str, object]]
    quality: dict[str, object]


def transform_rows(
    rows: Iterable[Mapping[str, object]], *, columns: Mapping[str, str], year: int,
    file_uf: str, municipality_map: Mapping[str, str],
    south_municipalities: Iterable[str] = (), expected_south_count: int | None = None,
    provenance: str = "MTE/PDET RAIS 2024 VINC_PUB",
) -> RaisResult:
    totals: Counter[str] = Counter()
    sectors: dict[str, Counter[str]] = defaultdict(Counter)
    qa: Counter[str] = Counter()
    unmatched: Counter[str] = Counter()
    file_uf = file_uf.upper()
    for row in rows:
        qa["vinculos_lidos"] += 1
        if _digits(row[columns["ativo"]]) != "1":
            qa["vinculos_inativos_excluidos"] += 1
            continue
        raw_code = _digits(row[columns["municipio"]])
        code = municipality_map.get(raw_code)
        if code is None:
            unmatched[raw_code] += 1
            continue
        expected_uf = UF_PREFIX.get(code[:2])
        if expected_uf != file_uf:
            raise ValueError(f"UF do arquivo inconsistente para {raw_code}->{code}: {file_uf} != {expected_uf}")
        if "uf" in columns and str(row[columns["uf"]]).strip().upper() != file_uf:
            raise ValueError(f"UF da coluna diverge do metadado do arquivo: {raw_code}")
        division = cnae_division(row[columns["cnae"]])
        if is_public_administration(row[columns["cnae"]], row[columns["natureza"]]):
            qa["vinculos_administracao_publica_excluidos"] += 1
            continue
        totals[code] += 1
        sectors[code][division] += 1
        qa["vinculos_privados_elegiveis"] += 1
    south = list(south_municipalities)
    if len(south) != len(set(south)):
        raise ValueError("universo Sul contém códigos duplicados")
    if expected_south_count is not None and len(south) != expected_south_count:
        raise ValueError(f"cobertura Sul inválida: {len(south)} != {expected_south_count}")
    private = [{
        "municipio_id": code, "empregos_formais_privados": total,
        "periodo_referencia": str(year), "fonte": provenance,
    } for code, total in sorted(totals.items())]
    diagnostic = []
    for code in sorted(south):
        total = totals.get(code, 0)
        value = None if total == 0 else 1 - sum((n / total) ** 2 for n in sectors[code].values())
        diagnostic.append({
            "municipio_id": code, "indicador_id": "MER-DIAG-01",
            "valor_bruto": value, "periodo_referencia": str(year),
            "flag_qualidade": "ausente_sem_vinculo_privado" if value is None else "observado",
        })
    quality = {
        "ano": year, **dict(qa), "uf_processada": file_uf,
        "municipios_ligados": len(totals), "codigos_nao_ligados": dict(sorted(unmatched.items())),
        "municipios_nao_ligados": len(unmatched),
        "soma_municipal": sum(totals.values()),
        "reconciliacao_ok": sum(totals.values()) == qa["vinculos_privados_elegiveis"],
    }
    return RaisResult(private, diagnostic, quality)


def transform_archive(
    archive: Path, *, file_uf: str, municipality_map: Mapping[str, str], year: int = 2024,
    south_municipalities: Iterable[str] = (), expected_south_count: int | None = None,
) -> RaisResult:
    """Caminho end-to-end local: `.7z` -> `.comt` -> cabeçalho -> produtos."""
    with extracted_comt(archive) as comt:
        reader, stream, format_metadata = read_comt(comt)
        try:
            columns = resolve_columns(reader.fieldnames or [])
            result = transform_rows(
                reader, columns=columns, year=year, file_uf=file_uf,
                municipality_map=municipality_map, south_municipalities=south_municipalities,
                expected_south_count=expected_south_count,
                provenance=f"MTE/PDET RAIS {year} VINC_PUB; {archive.name}",
            )
        finally:
            stream.close()
    result.quality.update(format_metadata, arquivo=archive.name, membro_comt=comt.name)
    return result


def write_outputs(result: RaisResult, output_dir: Path, quality_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True); quality_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("emprego_privado_municipal.csv", result.private_employment), ("mer_diag_01.csv", result.diversification)):
        if not rows: raise ValueError(f"saída vazia: {name}")
        with (output_dir / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    (quality_dir / "qa.json").write_text(json.dumps(result.quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

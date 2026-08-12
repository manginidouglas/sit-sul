"""Construção municipal de emprego privado e diversificação a partir da RAIS."""

from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


ALIASES = {
    "ano": {"ano", "ano_rais", "ano referencia"},
    "municipio": {"municipio", "municipio ibge", "cod municipio", "cod mun trab"},
    "uf": {"uf", "sigla uf"},
    "cnae": {"cnae 2 0 classe", "cnae 2 0 divisao", "cnae", "cnae 20 classe"},
    "natureza": {"natureza juridica", "natureza estabelecimento", "natureza jur"},
    "ativo": {"vinculo ativo 31 12", "vinculo ativo", "ativo 31 12"},
    "empregos": {"empregos", "vinculos ativos", "estoque"},
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
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def resolve_columns(fieldnames: Iterable[str]) -> dict[str, str]:
    normalized = {_normal(name): name for name in fieldnames}
    result = {}
    for target, aliases in ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                result[target] = normalized[alias]
                break
    required = {"municipio", "uf", "cnae", "natureza"}
    missing = required - result.keys()
    if missing:
        raise ValueError(f"colunas RAIS ausentes: {sorted(missing)}")
    if "ativo" not in result and "empregos" not in result:
        raise ValueError("é necessário vínculo ativo em 31/12 ou estoque agregado")
    return result


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or "").split(",")[0])


def cnae_division(value: object) -> str:
    digits = _digits(value)
    if len(digits) < 2:
        raise ValueError(f"CNAE inválida: {value!r}")
    division = digits[:2]
    if not 1 <= int(division) <= 99:
        raise ValueError(f"divisão CNAE impossível: {division}")
    return division


def is_public_administration(cnae: object, legal_nature: object) -> bool:
    """Exclui divisão 84 ou natureza do grupo CONCLA 1 (Administração Pública)."""

    nature = _digits(legal_nature)
    return cnae_division(cnae) == "84" or nature.startswith("1")


@dataclass
class RaisResult:
    private_employment: list[dict[str, object]]
    diversification: list[dict[str, object]]
    quality: dict[str, object]


def transform_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    columns: Mapping[str, str],
    year: int,
    municipality_map: Mapping[str, str] | None = None,
    south_municipalities: Iterable[str] = (),
    expected_south_count: int | None = None,
) -> RaisResult:
    """Agrega vínculos ativos elegíveis; aceita também estoque oficial agregado."""

    totals: Counter[str] = Counter()
    sectors: dict[str, Counter[str]] = defaultdict(Counter)
    qa: Counter[str] = Counter()
    seen_ufs: dict[str, str] = {}
    for row in rows:
        qa["linhas_lidas"] += 1
        if "ano" in columns and int(str(row[columns["ano"]]).strip()) != year:
            raise ValueError("arquivo contém ano diferente do solicitado")
        if "ativo" in columns and _digits(row[columns["ativo"]]) not in {"1", "01"}:
            qa["vinculos_nao_ativos_descartados"] += 1
            continue
        raw_code = _digits(row[columns["municipio"]])
        code = municipality_map.get(raw_code, raw_code) if municipality_map else raw_code
        if not re.fullmatch(r"\d{7}", code):
            raise ValueError(f"código municipal não harmonizado: {raw_code!r}")
        uf = str(row[columns["uf"]]).strip().upper()
        expected_uf = UF_PREFIX.get(code[:2])
        if uf != expected_uf:
            raise ValueError(f"UF inconsistente para {code}: {uf!r} != {expected_uf!r}")
        if code in seen_ufs and seen_ufs[code] != uf:
            raise ValueError(f"município associado a UFs distintas: {code}")
        seen_ufs[code] = uf
        division = cnae_division(row[columns["cnae"]])
        quantity = 1
        if "empregos" in columns:
            raw_quantity = str(row[columns["empregos"]]).strip().replace(".", "").replace(",", ".")
            number = float(raw_quantity)
            if number < 0 or not number.is_integer() or not math.isfinite(number):
                raise ValueError(f"estoque de empregos impossível: {raw_quantity!r}")
            quantity = int(number)
        if is_public_administration(row[columns["cnae"]], row[columns["natureza"]]):
            qa["empregos_publicos_excluidos"] += quantity
            continue
        totals[code] += quantity
        sectors[code][division] += quantity
        qa["empregos_privados_elegiveis"] += quantity

    private = [
        {"municipio_id": code, "ano": year, "empregos_formais_privados": total}
        for code, total in sorted(totals.items())
    ]
    south = list(south_municipalities)
    if len(south) != len(set(south)):
        raise ValueError("universo Sul contém códigos municipais duplicados")
    if expected_south_count is not None and len(south) != expected_south_count:
        raise ValueError(
            f"cobertura municipal Sul inválida: {len(south)} != {expected_south_count}"
        )
    diagnostics = []
    for code in sorted(south):
        total = totals.get(code, 0)
        value = None if total == 0 else 1 - sum((n / total) ** 2 for n in sectors[code].values())
        diagnostics.append(
            {"municipio_id": code, "indicador_id": "MER-DIAG-01", "ano": year, "valor": value}
        )
    qa.update(
        municipios_privado=len(totals),
        municipios_diagnostico=len(diagnostics),
        municipios_diagnostico_na=sum(item["valor"] is None for item in diagnostics),
        duplicidades_emprego_privado=0,
        duplicidades_diagnostico=0,
    )
    return RaisResult(private, diagnostics, {"ano": year, **dict(qa)})


def write_outputs(result: RaisResult, output_dir: Path, quality_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    quality_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("emprego_privado_municipal.csv", result.private_employment), ("mer_diag_01.csv", result.diversification)):
        if not rows:
            raise ValueError(f"saída vazia: {name}")
        with (output_dir / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
    (quality_dir / "qa.json").write_text(json.dumps(result.quality, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

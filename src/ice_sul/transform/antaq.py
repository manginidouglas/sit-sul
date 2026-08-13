"""Elegibilidade congelada de instalações portuárias para o INF-LOG-04."""
from __future__ import annotations

import calendar
import csv
import re
import unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

OUTPUT_FIELDS = (
    "instalacao_id", "nome", "tipo", "latitude", "longitude", "movimentacao_t",
    "natureza_carga", "elegivel", "justificativa", "periodo_inicio", "periodo_fim",
    "ajuste_acesso_terrestre_onda2",
)
GENERAL = "carga geral"
CONTAINER = "carga conteinerizada"


def _key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"[^a-z0-9]+", " ", text.encode("ascii", "ignore").decode().lower()).strip()


def _month(value: str) -> date:
    match = re.fullmatch(r"(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?", value.strip())
    if not match:
        raise ValueError(f"período inválido: {value!r}")
    return date(int(match.group(1)), int(match.group(2)), 1)


def _decimal(value: object) -> Decimal:
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"movimentação inválida: {value!r}") from exc
    if number < 0:
        raise ValueError("movimentação não pode ser negativa")
    return number


def _nature(value: object) -> str:
    normalized = _key(value)
    if "conteiner" in normalized or "container" in normalized:
        return CONTAINER
    if "carga geral" in normalized or normalized in {"geral", "carga geral solta"}:
        return GENERAL
    if "granel" in normalized or "bulk" in normalized:
        return "granel"
    return normalized or "não informada"


def _type(value: object) -> str:
    normalized = _key(value)
    if normalized in {"porto", "porto organizado", "publico", "publica"}:
        return "porto organizado"
    if normalized in {"tup", "terminal de uso privado", "instalacao privada", "privado", "privada"}:
        return "TUP"
    raise ValueError(f"tipo de instalação desconhecido: {value!r}")


def latest_complete_window(movements: list[dict[str, object]], *, cutoff: date = date(2026, 8, 12)) -> tuple[date, date]:
    """Retorna os 12 meses encerrados no último mês completo presente até o corte."""
    available = sorted({_month(str(row["periodo"])) for row in movements})
    cutoff_month = date(cutoff.year, cutoff.month, 1)
    complete = [month for month in available if month < cutoff_month]
    if not complete:
        raise ValueError("nenhum mês completo disponível até a data de corte")
    end_month = complete[-1]
    start_month = date(end_month.year - 1, end_month.month + 1, 1) if end_month.month < 12 else date(end_month.year, 1, 1)
    end = date(end_month.year, end_month.month, calendar.monthrange(end_month.year, end_month.month)[1])
    return start_month, end


def build_eligible_installations(
    installations: list[dict[str, object]], movements: list[dict[str, object]],
    *, cutoff: date = date(2026, 8, 12), require_contiguous_months: bool = True,
) -> list[dict[str, object]]:
    """Combina cadastro e carga, agrega duplicatas por ID e aplica a regra do MVP."""
    start, end = latest_complete_window(movements, cutoff=cutoff)
    months = sorted({_month(str(row["periodo"])) for row in movements if start <= _month(str(row["periodo"])) <= end})
    if require_contiguous_months and len(months) != 12:
        raise ValueError(f"janela incompleta: esperados 12 meses, encontrados {len(months)}")

    registry: dict[str, dict[str, object]] = {}
    for row in installations:
        identifier = str(row.get("instalacao_id", "")).strip()
        if not identifier:
            raise ValueError("instalação sem identificador")
        normalized = {
            "instalacao_id": identifier, "nome": str(row.get("nome", "")).strip(),
            "tipo": _type(row.get("tipo")), "latitude": str(row.get("latitude", "")).strip(),
            "longitude": str(row.get("longitude", "")).strip(),
            "ajuste": _key(row.get("referencia_coordenada")) not in {"acesso terrestre", "portao rodoviario"},
        }
        if not normalized["nome"] or not normalized["latitude"] or not normalized["longitude"]:
            raise ValueError(f"cadastro incompleto para {identifier}")
        try:
            lat, lon = float(normalized["latitude"]), float(normalized["longitude"])
        except ValueError as exc:
            raise ValueError(f"coordenada inválida para {identifier}") from exc
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"coordenada fora da faixa para {identifier}")
        previous = registry.get(identifier)
        if previous and previous != normalized:
            raise ValueError(f"duplicidade cadastral conflitante: {identifier}")
        registry[identifier] = normalized

    totals: dict[str, Decimal] = defaultdict(Decimal)
    natures: dict[str, set[str]] = defaultdict(set)
    for row in movements:
        month = _month(str(row["periodo"]))
        if not start <= month <= end:
            continue
        identifier = str(row.get("instalacao_id", "")).strip()
        if identifier not in registry:
            raise ValueError(f"movimentação sem cadastro: {identifier}")
        amount = _decimal(row.get("movimentacao_t", 0))
        if amount > 0:
            totals[identifier] += amount
            natures[identifier].add(_nature(row.get("natureza_carga")))

    result = []
    for identifier, item in sorted(registry.items()):
        amount, kinds = totals[identifier], natures[identifier]
        if amount == 0:
            eligible, reason = False, "cadastro físico sem movimentação efetiva na janela"
        elif item["tipo"] == "porto organizado":
            eligible, reason = True, "porto organizado com movimentação efetiva de carga na janela"
        elif kinds & {GENERAL, CONTAINER}:
            eligible, reason = True, "TUP com movimentação efetiva de carga geral e/ou conteinerizada"
        else:
            eligible, reason = False, "TUP exclusivamente graneleiro/bulk, sem carga geral ou conteinerizada compatível"
        result.append({
            "instalacao_id": identifier, "nome": item["nome"], "tipo": item["tipo"],
            "latitude": item["latitude"], "longitude": item["longitude"],
            "movimentacao_t": format(amount, "f"), "natureza_carga": " | ".join(sorted(kinds)) or "sem movimentação",
            "elegivel": eligible, "justificativa": reason, "periodo_inicio": start.isoformat(),
            "periodo_fim": end.isoformat(), "ajuste_acesso_terrestre_onda2": item["ajuste"],
        })
    return result


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS)
        writer.writeheader(); writer.writerows(rows)


def read_antaq_installations(path: Path) -> list[dict[str, object]]:
    """Lê o XLSX oficial ``Portos.xlsx`` diretamente do ZIP geográfico ANTAQ.

    O leitor é intencionalmente stdlib-only e valida os nomes reais do snapshot
    de 06/05/2025, em vez de impor ao raw o schema interno.
    """
    import io
    import xml.etree.ElementTree as ET
    import zipfile

    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    with zipfile.ZipFile(path) as outer:
        xlsx_name = next((n for n in outer.namelist() if n.lower().endswith("portos.xlsx")), None)
        if not xlsx_name:
            raise ValueError("ZIP ANTAQ sem Portos.xlsx")
        payload = io.BytesIO(outer.read(xlsx_name))
    with zipfile.ZipFile(payload) as book:
        shared = []
        if "xl/sharedStrings.xml" in book.namelist():
            root = ET.fromstring(book.read("xl/sharedStrings.xml"))
            shared = ["".join(si.itertext()).strip() for si in root.findall("m:si", ns)]
        sheet = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
        rows = []
        for xml_row in sheet.findall(".//m:sheetData/m:row", ns):
            values = []
            for cell in xml_row.findall("m:c", ns):
                letters = re.match(r"[A-Z]+", cell.get("r", "A")).group()
                column = 0
                for letter in letters: column = column * 26 + ord(letter) - 64
                while len(values) < column - 1: values.append("")
                value = cell.find("m:v", ns)
                text = "" if value is None else value.text or ""
                if cell.get("t") == "s": text = shared[int(text)]
                elif cell.get("t") == "inlineStr": text = "".join(cell.itertext()).strip()
                values.append(text)
            rows.append(values)
    required = {"cdi_tuaria", "nome", "tipo", "estado", "cidade", "latitude", "longitude", "fonte"}
    headers = rows[0]
    if not required <= set(headers):
        raise ValueError(f"schema Portos.xlsx inesperado: ausentes {sorted(required - set(headers))}")
    result = []
    for values in rows[1:]:
        raw = dict(zip(headers, values))
        if not raw.get("cdi_tuaria") or not raw.get("nome"): continue
        clean_coord = lambda value: str(value).replace("°", "").replace("�", "").strip()
        result.append({
            "instalacao_id": raw["cdi_tuaria"].strip(), "nome": raw["nome"].strip(" �"),
            "tipo": raw["tipo"], "uf": raw.get("estado", ""), "municipio": raw.get("cidade", ""),
            "latitude": clean_coord(raw["latitude"]), "longitude": clean_coord(raw["longitude"]),
            "referencia_coordenada": "ponto da camada geográfica ANTAQ; natureza não especificada",
            "fonte_cadastro": raw.get("fonte", "ANTAQ"),
        })
    return result


def read_antaq_movements(path: Path) -> list[dict[str, object]]:
    """Lê evidências tabulares transcritas do Anuário ANTAQ 2025.

    O TSV preserva o texto/valor publicado e a página. Valores ``mi t`` são
    convertidos programaticamente em toneladas. Não se infere carga ausente.
    """
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    required = {"instalacao_id", "nome_publicado", "valor_publicado", "unidade", "natureza_carga", "pagina"}
    if not rows or not required <= set(rows[0]):
        raise ValueError("schema da evidência do Anuário 2025 inesperado")
    result = []
    for row in rows:
        multiplier = Decimal("1000000") if row["unidade"] == "mi t" else Decimal("1")
        result.append({"instalacao_id": row["instalacao_id"], "nome_publicado": row["nome_publicado"], "periodo": "2025-12", "movimentacao_t": str(_decimal(row["valor_publicado"]) * multiplier), "natureza_carga": row["natureza_carga"], "pagina_fonte": row["pagina"]})
    return result

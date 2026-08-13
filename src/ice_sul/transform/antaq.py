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


def _read_dbf(payload: bytes) -> list[dict[str, str]]:
    """Lê dBASE do snapshot com a codificação Windows-1252 preservada pela ANTAQ."""
    count = int.from_bytes(payload[4:8], "little")
    header_length = int.from_bytes(payload[8:10], "little")
    record_length = int.from_bytes(payload[10:12], "little")
    fields = []
    for offset in range(32, header_length - 1, 32):
        descriptor = payload[offset:offset + 32]
        name = descriptor[:11].split(b"\0", 1)[0].decode("ascii")
        fields.append((name, descriptor[16]))
    rows = []
    for index in range(count):
        record = payload[header_length + index * record_length:header_length + (index + 1) * record_length]
        if len(record) != record_length:
            raise ValueError("DBF Portos.dbf truncado")
        if record[:1] == b"*":
            continue
        cursor, row = 1, {}
        for name, width in fields:
            raw = record[cursor:cursor + width]
            cursor += width
            # Portos.dbf não declara code page no header, mas seus bytes (á=E1,
            # í=ED, ó=F3) são Windows-1252/Latin-1. Ao contrário do XLSX,
            # preservam os caracteres que este snapshot gravou como U+FFFD.
            row[name] = raw.decode("cp1252").strip()
        rows.append(row)
    return rows


def read_antaq_installations(path: Path) -> list[dict[str, object]]:
    """Lê o cadastro oficial do ZIP e preserva corretamente seus caracteres.

    ``Portos.xlsx`` é validado como parte obrigatória do recurso oficial. Neste
    vintage, porém, o próprio XML do XLSX contém U+FFFD em textos acentuados.
    O ``Portos.dbf`` companheiro contém as mesmas 1.179 linhas e preserva os
    bytes Windows-1252; ele é usado para os valores, sem tentar adivinhar letras
    perdidas nem aplicar substituições pontuais.
    """
    import io
    import xml.etree.ElementTree as ET
    import zipfile

    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as outer:
        xlsx_name = next((name for name in outer.namelist() if name.lower().endswith("portos.xlsx")), None)
        dbf_name = next((name for name in outer.namelist() if name.lower().endswith("portos.dbf")), None)
        if not xlsx_name:
            raise ValueError("ZIP ANTAQ sem Portos.xlsx")
        if not dbf_name:
            raise ValueError("ZIP ANTAQ sem Portos.dbf necessário para preservar encoding")
        xlsx_payload = io.BytesIO(outer.read(xlsx_name))
        dbf_rows = _read_dbf(outer.read(dbf_name))
    with zipfile.ZipFile(xlsx_payload) as book:
        shared_root = ET.fromstring(book.read("xl/sharedStrings.xml"))
        shared = ["".join(item.itertext()).strip() for item in shared_root.findall("m:si", ns)]
        sheet = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
        first_row = sheet.find(".//m:sheetData/m:row", ns)
        headers = []
        for cell in first_row.findall("m:c", ns):
            value = cell.find("m:v", ns)
            headers.append(shared[int(value.text)])
    required = {"cdi_tuaria", "nome", "tipo", "estado", "cidade", "latitude", "longitude", "fonte"}
    if not required <= set(headers) or not required <= set(dbf_rows[0]):
        raise ValueError(f"schema oficial inesperado: ausentes {sorted(required - set(headers))}")
    if len(dbf_rows) != len(sheet.findall(".//m:sheetData/m:row", ns)) - 1:
        raise ValueError("XLSX e DBF divergem em número de linhas")
    result = []
    for raw in dbf_rows:
        if not raw.get("cdi_tuaria") or not raw.get("nome"):
            continue
        clean_coord = lambda value: str(value).removesuffix("°").strip()
        clean_text = lambda value: str(value).rstrip("\xa0° ").strip()
        result.append({
            "instalacao_id": raw["cdi_tuaria"].strip(), "nome": clean_text(raw["nome"]),
            "tipo": clean_text(raw["tipo"]), "uf": clean_text(raw.get("estado", "")),
            "municipio": clean_text(raw.get("cidade", "")),
            "latitude": clean_coord(raw["latitude"]), "longitude": clean_coord(raw["longitude"]),
            "referencia_coordenada": "ponto da camada geográfica ANTAQ; natureza não especificada",
            "fonte_cadastro": clean_text(raw.get("fonte", "ANTAQ")),
        })
    return result

def read_antaq_movements(path: Path) -> list[dict[str, object]]:
    """Lê evidência anual oficial sem fingir que o consolidado é dezembro."""
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    required = {
        "instalacao_id", "nome_publicado", "valor_publicado", "unidade",
        "escopo_movimentacao_evidenciada", "natureza_carga_evidenciada",
        "tipo_evidencia", "fonte_movimentacao", "url", "pagina_ou_referencia",
        "periodo_inicio", "periodo_fim", "coletado_em",
    }
    if not rows or not required <= set(rows[0]):
        raise ValueError("schema da evidência anual ANTAQ inesperado")
    result = []
    for row in rows:
        multiplier = Decimal("1000000") if row["unidade"] == "mi t" else Decimal("1")
        amount = str(_decimal(row["valor_publicado"]) * multiplier) if row["valor_publicado"].strip() else ""
        result.append({**row, "movimentacao_evidenciada_t": amount})
    return result


def _category(official_type: object) -> str:
    normalized = _key(official_type)
    if normalized == "porto organizado":
        return "porto_organizado"
    if normalized == "terminal de uso privado":
        return "tup"
    return "fora_escopo_mvp"


def _valid_coordinate(latitude: object, longitude: object) -> bool:
    try:
        lat, lon = float(str(latitude)), float(str(longitude))
    except ValueError:
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180


def evaluate_annual_installations(
    installations: list[dict[str, object]], evidence: list[dict[str, object]],
    *, vintage: str = "2025-05-06",
) -> list[dict[str, object]]:
    """Classifica o universo cadastral sem converter ausência em inelegibilidade."""
    evidence_by_id = {str(item["instalacao_id"]): item for item in evidence}
    id_counts = defaultdict(int)
    for item in installations:
        id_counts[str(item["instalacao_id"])] += 1
    known_ids = set(id_counts)
    orphan = sorted(set(evidence_by_id) - known_ids)
    if orphan:
        raise ValueError(f"evidência sem cadastro: {', '.join(orphan)}")
    evaluated = []
    for item in installations:
        identifier = str(item["instalacao_id"])
        conflict = id_counts[identifier] > 1
        suffix = _key(item["tipo"]).replace(" ", "-")
        uid = f"{identifier}--{suffix}" if conflict else identifier
        category = _category(item["tipo"])
        proof = evidence_by_id.get(identifier) if not conflict else None
        amount = _decimal(proof["movimentacao_evidenciada_t"]) if proof and proof["movimentacao_evidenciada_t"] else None
        nature = _nature(proof["natureza_carga_evidenciada"]) if proof else None
        evidence_type = _key(proof["tipo_evidencia"]) if proof else ""
        if conflict:
            status, reason = "indeterminado", "ID ANTAQ conflitante; registros preservados e bloqueados para elegibilidade/routing"
        elif category == "fora_escopo_mvp":
            status, reason = "fora_escopo_mvp", "categoria oficial fora do escopo do MVP genérico"
        elif not proof:
            status, reason = "indeterminado", "sem evidência oficial recuperável suficiente; ausência não implica inelegibilidade"
        elif category == "porto_organizado" and proof and (amount is None or amount > 0) and "positiva" in evidence_type:
            status, reason = "elegivel", "porto organizado com evidência oficial positiva de movimentação em 2025"
        elif category == "porto_organizado" and "ausencia" in evidence_type:
            status, reason = "nao_elegivel", "evidência oficial explícita de ausência de movimentação em 2025"
        elif category == "tup" and amount > 0 and nature in {GENERAL, CONTAINER}:
            status, reason = "elegivel", "TUP com evidência oficial de carga geral e/ou conteinerizada"
        elif category == "tup" and amount > 0 and nature == "granel" and "exclusiv" in evidence_type:
            status, reason = "nao_elegivel", "TUP com evidência suficiente de movimentação exclusivamente graneleira/bulk"
        else:
            status, reason = "indeterminado", "evidência oficial insuficiente para aplicar com segurança a regra do MVP"
        valid = _valid_coordinate(item.get("latitude"), item.get("longitude"))
        evaluated.append({
            "instalacao_uid": uid, "instalacao_id_antaq": identifier, "nome": item["nome"], "tipo_oficial": item["tipo"],
            "categoria_mvp": category, "uf": item.get("uf", ""), "municipio": item.get("municipio", ""),
            "latitude": item.get("latitude", ""), "longitude": item.get("longitude", ""),
            "fonte_coordenada": item.get("fonte_cadastro", "ANTAQ"), "coordenada_valida": valid,
            "conflito_cadastral": conflict, "status_mvp": status,
            "justificativa_status": reason,
            "movimentacao_evidenciada_t": proof["movimentacao_evidenciada_t"] if proof else "",
            "escopo_movimentacao_evidenciada": proof["escopo_movimentacao_evidenciada"] if proof else "",
            "natureza_carga_evidenciada": proof["natureza_carga_evidenciada"] if proof else "",
            "fonte_movimentacao": proof["fonte_movimentacao"] if proof else "",
            "pagina_ou_referencia": proof["pagina_ou_referencia"] if proof else "",
            "periodo_inicio": proof["periodo_inicio"] if proof else "2025-01-01",
            "periodo_fim": proof["periodo_fim"] if proof else "2025-12-31",
            "vintage_cadastro": vintage,
            "ajuste_acesso_terrestre_onda2": True,
        })
    return evaluated

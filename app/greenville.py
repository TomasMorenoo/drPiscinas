import re
import unicodedata


_SECTOR_SIMPLE_RE = re.compile(r"^\s*([A-Z])\s*$", re.IGNORECASE)
_SECTOR_LEGACY_RE = re.compile(r"\(([A-Z])\)\s*$", re.IGNORECASE)
_LOTE_CON_SECTOR_RE = re.compile(r"^\s*([A-Z])(?:\s+|[-/]\s*|(?=\d))(.+?)\s*$", re.IGNORECASE)


def _normalizar(value):
    texto = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).strip().casefold()


def es_greenville(nombre):
    return _normalizar(nombre) == "greenville"


def codigo_barrio_greenville(nombre):
    texto = (nombre or "").strip()
    match = _SECTOR_SIMPLE_RE.fullmatch(texto) or _SECTOR_LEGACY_RE.search(texto)
    return match.group(1).upper() if match else None


def separar_sector_lote(numero):
    texto = (numero or "").strip()
    match = _LOTE_CON_SECTOR_RE.fullmatch(texto)
    if not match:
        return None, texto
    return match.group(1).upper(), match.group(2).strip()


def lote_tiene_sector(numero):
    sector, _ = separar_sector_lote(numero)
    return sector is not None

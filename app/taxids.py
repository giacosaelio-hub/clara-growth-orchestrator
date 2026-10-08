"""Chequeo de formato de IDs fiscales para los mercados de Clara. Solo formato y dígito verificador: no prueba
que la empresa exista (eso sería una consulta al ente fiscal o a un proveedor de datos en producción).

- Brasil, CNPJ: 14 caracteres. Desde julio de 2026 los primeros 12 pueden ser letras o números. Los 2 últimos
  son dígitos verificadores (módulo 11, las letras valen su código ASCII menos 48).
- México, RFC: 12 caracteres para una empresa (persona moral): 3 letras, una fecha de 6 dígitos y 3 de homoclave.
  13 caracteres es una persona física.
- Colombia, NIT: 9 dígitos más 1 dígito verificador (módulo 11 con los pesos primos de la DIAN).
"""
import re
from datetime import datetime


def _clean(value: str) -> str:
    return re.sub(r"[.\-/\s]", "", value or "").upper()


def cnpj_check_digits(base12: str) -> str:
    def digit(chars, weights):
        total = sum((ord(c) - 48) * w for c, w in zip(chars, weights))
        r = total % 11
        return "0" if r < 2 else str(11 - r)
    d1 = digit(base12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = digit(base12 + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return d1 + d2


def valid_cnpj(value: str) -> bool:
    v = _clean(value)
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", v) or len(set(v)) == 1:
        return False
    return cnpj_check_digits(v[:12]) == v[12:]


def valid_rfc_company(value: str) -> bool:
    v = _clean(value)
    m = re.fullmatch(r"([A-ZÑ&]{3})(\d{6})([A-Z0-9]{3})", v)
    if not m:
        return False
    try:
        datetime.strptime(m.group(2), "%y%m%d")
    except ValueError:
        return False
    return True


NIT_WEIGHTS = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]


def nit_check_digit(base9: str) -> str:
    total = sum(int(d) * w for d, w in zip(reversed(base9), NIT_WEIGHTS))
    r = total % 11
    return str(r if r < 2 else 11 - r)


def valid_nit(value: str) -> bool:
    v = _clean(value)
    if not re.fullmatch(r"\d{10}", v):
        return False
    return nit_check_digit(v[:9]) == v[9]


def format_tax_id(value: str | None, countries: list[str]) -> str | None:
    """Una sola forma de guardar un ID, escriba lo que escriba el usuario (con o sin puntos, barras o guiones)."""
    if not value:
        return None
    v = _clean(value)
    if "BR" in countries and len(v) == 14:
        return f"{v[:2]}.{v[2:5]}.{v[5:8]}/{v[8:12]}-{v[12:]}"
    if "CO" in countries and len(v) == 10 and v.isdigit():
        return f"{v[:3]}.{v[3:6]}.{v[6:9]}-{v[9]}"
    return v


VALIDATORS = {"BR": valid_cnpj, "MX": valid_rfc_company, "CO": valid_nit}


def valid_for_markets(tax_id: str, countries: list[str]) -> bool:
    """True si el ID es válido para al menos una de las entidades de la cuenta en los mercados de Clara."""
    return any(VALIDATORS[c](tax_id) for c in countries if c in VALIDATORS)

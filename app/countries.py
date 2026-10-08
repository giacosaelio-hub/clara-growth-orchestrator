"""Nombres de países como los escribe la gente -> códigos ISO 3166 de dos letras.

La lista ISO completa viene de pycountry (249 países). Se agregan nombres en español y portugués para
América Latina y los mercados más comunes, porque así los escriben los usuarios de la región de Clara.
Lo que no es un país ("LATAM", "Canada and LATAM", "xyz") se informa como desconocido, nunca se adivina.
"""
import unicodedata

import pycountry


def _key(value: str) -> str:
    v = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(c for c in v if not unicodedata.combining(c)).replace(".", "")


EXTRA = {
    "BR": ["brasil"], "MX": ["mejico"], "AR": ["arg"], "US": ["usa", "eeuu", "eua", "estados unidos", "united states"],
    "ES": ["espana"], "DE": ["alemania", "alemanha"], "GB": ["uk", "reino unido", "inglaterra"], "CA": ["canada"],
    "PE": ["peru"], "PA": ["panama"], "DO": ["republica dominicana"], "BF": ["burkina faso"],
    "FR": ["francia", "franca"], "IT": ["italia"], "CN": ["china"], "JP": ["japon", "japao"],
    "CH": ["suiza", "suica"], "NL": ["paises bajos", "holanda", "paises baixos"], "PT": ["portugal"],
}

LOOKUP: dict[str, str] = {}
for c in pycountry.countries:
    for name in (c.name, getattr(c, "common_name", None), getattr(c, "official_name", None), c.alpha_2, c.alpha_3):
        if name:
            LOOKUP[_key(name)] = c.alpha_2
for code, names in EXTRA.items():
    for n in names:
        LOOKUP[_key(n)] = code


def to_code(value: str) -> str | None:
    """Código ISO de un país escrito a mano, o None si no es un país."""
    return LOOKUP.get(_key(str(value))) if str(value).strip() else None


def normalize_countries(values) -> list[str]:
    """Países conocidos como códigos ISO, sin duplicados. Los desconocidos se descartan (ver unknown_countries)."""
    out = []
    for v in values or []:
        code = to_code(v)
        if code and code not in out:
            out.append(code)
    return out


def unknown_countries(values) -> list[str]:
    return [str(v) for v in values or [] if str(v).strip() and not to_code(v)]


def country_names() -> list[str]:
    return sorted(c.name for c in pycountry.countries)

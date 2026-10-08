"""Builds data/seed_accounts.json: 30 real companies from Brazil, Mexico and Colombia.

Companies are real and public. Everything about the PEOPLE is invented: names and email addresses are
fictional, and outreach is a mock, so no message is ever sent. Some contacts use personal domains
(Gmail, Yahoo, Hotmail), as many Latin American companies do. Employee counts are rough public orders
of magnitude. Tax IDs are fictitious, with the right format and a valid check digit, never real numbers.
CRM flags (customer, AE, opt-out, last outreach) are simulated to exercise every rule.
Magalu and Aviatur appear as clients on Clara's public website, so they enter as existing customers.
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.taxids import cnpj_check_digits, nit_check_digit  # noqa: E402

A = []
rng = random.Random(2026)  # fixed seed: the same fictitious IDs every run


def fake_tax_id(country: str, name: str) -> str:
    """Fictitious IDs with the right format and a valid check digit. Never a real company's number."""
    if country == "BR":
        base = "".join(str(rng.randint(0, 9)) for _ in range(8)) + "0001"
        v = base + cnpj_check_digits(base)
        return f"{v[:2]}.{v[2:5]}.{v[5:8]}/{v[8:12]}-{v[12:]}"
    if country == "MX":
        letters = "".join(ch for ch in name.upper() if ch.isalpha())[:3].ljust(3, "X")
        return f"{letters}{rng.randint(90, 99):02d}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}" +             "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789") for _ in range(3))
    if country == "CO":
        base = str(rng.randint(800000000, 901999999))
        return f"{base[:3]}.{base[3:6]}.{base[6:]}-{nit_check_digit(base)}"
    return "30-" + "".join(str(rng.randint(0, 9)) for _ in range(8)) + "-9"   # Argentina: outside Clara's markets


def acc(aid, name, countries, employees, industry, contact, lang, tax=True, legal="company", crm=None, expect=""):
    A.append({
        "account_id": aid,
        "account": {"name": name, "tax_id": fake_tax_id(next((x for x in countries if x in ("BR", "MX", "CO")), countries[0]), name) if tax else None, "entity_countries": countries,
                    "employees": employees, "industry": industry, "legal_type": legal},
        "contact": contact and {**contact, "language": lang},
        "crm": crm or {},
        "expected": expect,
    })


def c(user, domain, name, title):
    return {"email": f"{user}@{domain}", "name": name, "title": title}


# --- eligible: CONTACT (11) ---
acc("br-loggi", "Loggi", ["BR"], 3000, "logistics", c("marina.costa", "loggi.com", "Marina Costa", "Gerente Financeira"), "pt", expect="CONTACT")
acc("br-hering", "Cia. Hering", ["BR"], 5000, "fashion_retail", c("rafael.lima", "hering.com.br", "Rafael Lima", "Controller"), "pt", expect="CONTACT")
acc("br-petz", "Petz", ["BR"], 5000, "pet_retail", c("paula.ribeiro", "petz.com.br", "Paula Ribeiro", "Diretora Financeira"), "pt", expect="CONTACT")
acc("br-arezzo", "Arezzo&Co", ["BR"], 5000, "fashion_retail", c("thiago.alves", "arezzo.com.br", "Thiago Alves", "Gerente de Contas a Pagar"), "pt", expect="CONTACT")
acc("br-movida", "Movida", ["BR"], 5000, "car_rental", c("anamendes.movida", "gmail.com", "Ana Mendes", "Gerente Financeira"), "pt", expect="CONTACT")
acc("mx-cinepolis", "Cinépolis", ["MX", "BR", "CO"], 10000, "entertainment", c("lucia.hernandez", "cinepolis.com", "Lucía Hernández", "Directora de Finanzas"), "es", expect="CONTACT")
acc("mx-liverpool", "El Puerto de Liverpool", ["MX"], 10000, "department_stores", c("jorge.ramirez", "liverpool.com.mx", "Jorge Ramírez", "Gerente de Tesorería"), "es", expect="CONTACT")
acc("co-alpina", "Alpina", ["CO"], 5000, "food_manufacturing", c("camilo.rojas", "alpina.com", "Camilo Rojas", "Jefe de Compras"), "es", expect="CONTACT")
acc("co-postobon", "Postobón", ["CO"], 10000, "beverages", c("dvelez_postobon", "yahoo.com", "Daniela Vélez", "Gerente Administrativa"), "es", expect="CONTACT")
acc("co-procafecol", "Procafecol (Juan Valdez)", ["CO"], 2000, "coffee_retail", c("andres.gomez", "juanvaldezcafe.com", "Andrés Gómez", "Director Financiero"), "es", expect="CONTACT")
acc("ar-globant", "Globant (origen argentino)", ["AR", "BR", "MX", "CO"], 20000, "software", c("sofia.pereyra", "globant.com", "Sofía Pereyra", "Finance Manager LATAM"), "es",
    expect="CONTACT (Argentine company with entities in Brazil, Mexico and Colombia)")

# --- more eligible accounts, for volume (4) ---
acc("br-raiadrogasil", "Raia Drogasil", ["BR"], 50000, "pharmacy_retail", c("fernanda.lopes", "rd.com.br", "Fernanda Lopes", "Gerente de Despesas"), "pt", expect="CONTACT")
acc("mx-bimbo", "Grupo Bimbo", ["MX", "BR", "CO"], 100000, "food_manufacturing", c("alejandro.cruz", "grupobimbo.com", "Alejandro Cruz", "Gerente de Viajes y Gastos"), "es", expect="CONTACT")
acc("co-corona", "Organización Corona", ["CO"], 10000, "building_materials", c("sebastian.arango", "corona.co", "Sebastián Arango", "Director Financiero"), "es", expect="CONTACT")
acc("co-exito", "Grupo Éxito", ["CO"], 40000, "retail", c("valentina.ospina", "grupo-exito.com", "Valentina Ospina", "Jefe de Cuentas por Pagar"), "es", expect="CONTACT")

# --- invalid tax ID: right length, wrong check digit (1) ---
acc("br-totvs", "TOTVS", ["BR"], 9000, "software", c("lucas.martins", "totvs.com.br", "Lucas Martins", "Controller"), "pt",
    expect="ENRICH (CNPJ with a wrong check digit)")

# --- public Clara customers: SUPPRESS R1 (2) ---
acc("br-magalu", "Magazine Luiza (Magalu)", ["BR"], 30000, "retail", c("joana.silva", "magazineluiza.com.br", "Joana Silva", "Gerente Financeira"), "pt",
    crm={"is_customer": 1, "stage": "customer"}, expect="SUPPRESS R1 (Clara customer, listed on clara.com)")
acc("co-aviatur", "Aviatur", ["CO"], 2000, "travel", c("laura.castro", "aviatur.com", "Laura Castro", "Directora Financiera"), "es",
    crm={"is_customer": 1, "stage": "customer", "assigned_ae": "valeria.ae@clara.com"}, expect="SUPPRESS R1 (Clara customer, listed on clara.com)")

# --- owned by an AE: SUPPRESS R2 (2) ---
acc("mx-rappi", "Rappi", ["CO", "MX", "BR"], 5000, "delivery_platform", c("ricardo.luna", "rappi.com", "Ricardo Luna", "Head of Finance"), "es",
    crm={"has_open_opportunity": 1, "assigned_ae": "bruno.ae@clara.com"}, expect="SUPPRESS R2 (open opportunity)")
acc("co-frisby", "Frisby", ["CO"], 3000, "restaurants", c("felipeduarte.frisby", "hotmail.com", "Felipe Duarte", "Gerente Financiero"), "es",
    crm={"assigned_ae": "mariana.ae@clara.com"}, expect="SUPPRESS R2 (assigned AE)")

# --- opted out: SUPPRESS R3 (2) ---
acc("co-servientrega", "Servientrega", ["CO"], 10000, "logistics", c("natalia.mejia", "servientrega.com", "Natalia Mejía", "Jefe de Tesorería"), "es",
    crm={"contact_opted_out": 1}, expect="SUPPRESS R3 (contact opted out)")
acc("mx-lacomer", "La Comer", ["MX"], 10000, "supermarkets", c("carlos.ortiz", "lacomer.com.mx", "Carlos Ortiz", "Contralor"), "es",
    crm={"do_not_contact": 1}, expect="SUPPRESS R3 (do-not-contact)")

# --- missing data: ENRICH (3) ---
acc("br-cocobambu", "Coco Bambu", ["BR"], 5000, "restaurants", c("diegorocha.cocobambu", "gmail.com", "Diego Rocha", "Gerente Financeiro"), "pt", tax=False,
    expect="ENRICH (no CNPJ yet)")
acc("mx-herdez", "Grupo Herdez", ["MX"], 10000, "food_manufacturing", {"email": "contacto@herdez.com.mx", "name": "", "title": ""}, "es",
    expect="ENRICH (generic inbox, no name or title)")
acc("co-crepes", "Crepes & Waffles", ["CO"], 5000, "restaurants", None, "es", expect="ENRICH (no contact at all)")

# --- outside the ICP: SUPPRESS R6 (3) ---
acc("ar-laanonima", "La Anónima", ["AR"], 10000, "supermarkets", c("martin.diaz", "laanonima.com.ar", "Martín Díaz", "CFO"), "es",
    expect="SUPPRESS R6 (Argentina only, no entity in BR, MX or CO)")
acc("br-bancointer", "Banco Inter", ["BR"], 3000, "banking", c("elena.ruiz", "bancointer.com.br", "Elena Ruiz", "Diretora de Compras"), "pt",
    expect="SUPPRESS R6 (bank: excluded industry)")
acc("br-correios", "Correios", ["BR"], 80000, "postal_services", c("roberto.nunes", "correios.com.br", "Roberto Nunes", "Gerente de Compras"), "pt", legal="public_sector",
    expect="SUPPRESS R6 (state-owned: buys through public procurement, not outbound)")

# --- contacted recently: WAIT R7 (2) ---
acc("br-drconsulta", "Dr. Consulta", ["BR"], 2000, "healthcare", c("carla.mendes", "drconsulta.com", "Carla Mendes", "Gerente Financeira"), "pt",
    crm={"last_outreach_at": "2026-10-01T10:00:00+00:00", "stage": "contacted"}, expect="WAIT R7 (contacted 5 days ago)")
acc("mx-fahorro", "Farmacias del Ahorro", ["MX"], 10000, "pharmacy_retail", c("elena.soto", "fahorro.com", "Elena Soto", "Gerente de Compras"), "es",
    crm={"last_outreach_at": "2026-09-30T10:00:00+00:00", "stage": "contacted"}, expect="WAIT R7 (contacted 6 days ago)")

# break the check digit of TOTVS on purpose: the format looks right, the number is not
t = next(x for x in A if x["account_id"] == "br-totvs")["account"]
t["tax_id"] = t["tax_id"][:-1] + str((int(t["tax_id"][-1]) + 1) % 10)

assert len(A) == 30, len(A)
out = Path(__file__).resolve().parent.parent / "data" / "seed_accounts.json"
out.write_text(json.dumps(A, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {len(A)} accounts to {out}")

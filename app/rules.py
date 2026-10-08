"""Reglas de negocio fijas. Acá no hay IA, a propósito."""
import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from app.models import Decision, ReplyInterpretation
from app.taxids import valid_for_markets

ICP = json.loads((Path(__file__).resolve().parent.parent / "config" / "icp.json").read_text(encoding="utf-8"))
# nombre@dominio.tld, con dominios de varios niveles (empresa.com.br, empresa.com.mx, empresa.co)
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,24}$")


def normalize(text: str) -> str:
    """Minúsculas, sin acentos ni puntuación, espacios simples."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_personal_email(email: str) -> bool:
    return email.split("@")[-1].lower() in ICP["personal_email_domains"]


GENERIC_WORDS = {"grupo", "group", "cia", "companhia", "compania", "sa", "ltda", "sas", "cv", "de", "del", "la", "el", "los",
                 "las", "do", "da", "dos", "das", "y", "e", "and", "the", "inc", "corp", "origen", "argentino",
                 "organizacion", "organizacao", "holding", "co"}


def email_matches_company(email: str, company: str) -> bool:
    """¿El dominio del mail corporativo se parece a la empresa? coca-cola.com para Nivea no.
    Chequea palabras del nombre e iniciales (rd.com.br para Raia Drogasil). Los dominios personales no se chequean acá."""
    label = normalize(email.split("@")[-1].split(".")[0]).replace(" ", "")
    words = [w for w in normalize(company).split() if w not in GENERIC_WORDS]
    if any(len(w) >= 3 and (w in label or label in w) for w in words):
        return True
    return len(words) > 1 and "".join(w[0] for w in words) == label


def missing_fields(account: dict, contact: dict | None) -> list[str]:
    """Datos que el sistema necesita antes de contactar a alguien. Se permite un mail personal."""
    missing = []
    if not contact or not EMAIL_RE.match(contact.get("email") or ""):
        missing.append("valid_email")
    if not contact or not contact.get("name"):
        missing.append("contact_name")
    if not contact or not contact.get("title"):
        missing.append("contact_title")
    if not contact or not contact.get("language"):
        missing.append("contact_language")
    email = (contact or {}).get("email") or ""
    if EMAIL_RE.match(email) and not is_personal_email(email) and account.get("name")             and not email_matches_company(email, account["name"]):
        missing.append(f"a contact from this company (the email domain {email.split('@')[-1]} "
                       f"does not look like {account['name']})")
    if not account.get("tax_id"):
        missing.append("tax_id")
    elif set(account.get("entity_countries") or []) & set(ICP["markets"]) and             not valid_for_markets(account["tax_id"], account["entity_countries"]):
        missing.append("valid_tax_id (wrong format or check digit)")
    if not account.get("entity_countries"):
        missing.append("entity_countries")
    # Tamaño e industria NO son obligatorios: ayudan a priorizar, pero si faltan nunca bloquean una cuenta.
    return missing


def outside_icp(account: dict) -> str | None:
    if not set(account["entity_countries"]) & set(ICP["markets"]):
        return (f"no legal entity in {', '.join(ICP['markets'])}; kept for future markets "
                f"({', '.join(account['entity_countries']) or 'unknown'})")
    if account.get("industry") in ICP["excluded_industries"]:
        return f"excluded industry ({account['industry']})"
    if account.get("legal_type") in ICP["excluded_legal_types"]:
        return f"excluded legal type ({account['legal_type']})"
    return None


def has_unsubscribe_request(text: str) -> bool:
    clean = f" {normalize(text)} "
    return any(f" {normalize(p)} " in clean for p in ICP["unsubscribe_phrases"])


def has_injection_attempt(text: str) -> bool:
    clean = f" {normalize(text)} "
    return any(f" {normalize(p)} " in clean for p in ICP["injection_markers"])


def ownership_rules(account: dict, contact: dict | None, replied: bool) -> Decision | None:
    """Reglas 1 a 3: clientes, cuentas de un AE, bajas."""
    if account["is_customer"]:
        return Decision(kind="SUPPRESS", rule="R1_customer", reason="account is already a customer",
                        notify_ae=replied and bool(account.get("assigned_ae")))
    if account["has_open_opportunity"] or account.get("assigned_ae"):
        return Decision(kind="SUPPRESS", rule="R2_owned_by_ae",
                        reason="open opportunity or assigned AE: the AE owns the relationship",
                        notify_ae=replied)
    if account["do_not_contact"] or (contact and contact["opted_out"]):
        return Decision(kind="SUPPRESS", rule="R3_opted_out", reason="contact opted out or account on do-not-contact")
    return None


def decide_targeted(account: dict, contact: dict | None, now: datetime) -> Decision:
    """Próxima mejor acción para una cuenta que acaba de entrar a la lista de prospección."""
    owned = ownership_rules(account, contact, replied=False)
    if owned:
        return owned
    missing = missing_fields(account, contact)
    if missing:
        return Decision(kind="ENRICH", rule="R5_missing_data", reason="missing: " + ", ".join(missing))
    out = outside_icp(account)
    if out:
        return Decision(kind="SUPPRESS", rule="R6_outside_icp", reason=out)
    if account.get("last_outreach_at"):
        last = datetime.fromisoformat(account["last_outreach_at"])
        if now - last < timedelta(days=ICP["contact_cooldown_days"]):
            return Decision(kind="WAIT", rule="R7_cooldown",
                            reason=f"contacted less than {ICP['contact_cooldown_days']} days ago")
    reason = "eligible account inside the ICP"
    if contact and is_personal_email(contact["email"]):
        reason += " (personal email domain: the SDR confirms it belongs to the company)"
    return Decision(kind="CONTACT", rule="R8_eligible", reason=reason)


def decide_reply_pre_ai(account: dict, contact: dict | None, text: str) -> Decision | None:
    """Reglas que corren antes de que la IA vea una respuesta."""
    owned = ownership_rules(account, contact, replied=True)
    if owned:
        return owned
    if has_unsubscribe_request(text):
        return Decision(kind="SUPPRESS", rule="R4_unsubscribe", reason="the prospect asked to stop", opt_out=True)
    if has_injection_attempt(text):
        return Decision(kind="HUMAN_REVIEW", rule="R4b_injection",
                        reason="reply contains instructions aimed at the AI: a person reads it")
    return None


def decide_from_ai(ai: ReplyInterpretation | None, failure: str | None) -> Decision:
    """Convierte una salida validada de la IA en una decisión. Todo lo dudoso va a una persona."""
    if ai is None:
        return Decision(kind="HUMAN_REVIEW", rule="AI_rejected", reason=failure or "AI output rejected")
    mapping = {
        "interested": ("HANDOFF", "prospect is interested"),
        "not_now": ("WAIT", "prospect asked to talk later"),
        "referral": ("ENRICH", "prospect referred another contact"),
        "not_interested": ("SUPPRESS", "prospect is not interested"),
        "question": ("HUMAN_REVIEW", "prospect asked a question for the SDR"),
        "unclear": ("HUMAN_REVIEW", "reply is ambiguous"),
    }
    kind, reason = mapping[ai.intent]
    return Decision(kind=kind, rule=f"AI_{ai.intent}", reason=reason)

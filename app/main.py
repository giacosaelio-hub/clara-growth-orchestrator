"""API del webhook y consola de demo.

    py -m uvicorn app.main:app --port 8000      y después abrir http://localhost:8000
"""
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import db
from app.actions import ActionRunner
from app.ai import MockLLM, GeminiLLM
from app.countries import country_names, normalize_countries, unknown_countries
from app.integrations import MockCRM, MockEnrichment, MockOutreach
from app.models import Event
from app.orchestrator import Orchestrator

SAO_PAULO = timezone(timedelta(hours=-3), "America/Sao_Paulo")   # Brasil no tiene horario de verano desde 2019
ROOT = Path(__file__).resolve().parent.parent
conn = db.connect(os.environ.get("DB_PATH", str(ROOT / "data" / "state.db")))
# Sin clave de Gemini toda respuesta va a revisión humana: lo seguro por defecto, nunca adivinar.
llm = GeminiLLM() if os.environ.get("GEMINI_API_KEY") else MockLLM()
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
# Los endpoints de demo pueden borrar la base, por eso solo existen con DEMO_MODE activado (por defecto en local).
DEMO_MODE = os.environ.get("DEMO_MODE", "1") == "1"
outreach = MockOutreach()
runner = ActionRunner(conn, outreach, MockCRM(), MockEnrichment())
orchestrator = Orchestrator(conn, llm, runner, clock=lambda: datetime.now(SAO_PAULO))

app = FastAPI(title="Clara Growth Orchestration System")




def now_iso():
    """Las fechas llevan su zona horaria (-03:00), así se comparan bien con eventos de cualquier zona."""
    return datetime.now(SAO_PAULO).isoformat(timespec="seconds")


# ---------------- webhook ----------------

@app.post("/events")
def receive_event(event: Event, x_webhook_secret: str | None = Header(default=None)):
    # En producción se verificaría una firma HMAC por proveedor. Acá alcanza con una clave compartida.
    # compare_digest tarda lo mismo si falla el primer o el último carácter (no se filtra nada por el tiempo).
    if WEBHOOK_SECRET and not hmac.compare_digest(x_webhook_secret or "", WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="invalid webhook secret")
    return orchestrator.handle(event)


# ---------------- API de lectura ----------------

@app.get("/api/accounts")
def list_accounts():
    rows = conn.execute("""
        SELECT a.account_id, a.name, a.entity_countries, a.employees, a.industry, a.legal_type, a.tax_id, a.stage,
               a.is_customer, a.has_open_opportunity, a.assigned_ae, a.do_not_contact, a.last_outreach_at,
               c.email, c.name AS contact_name, c.language, c.personal_email, c.opted_out,
               l.decision, l.rule, l.reason, l.action_status
        FROM accounts a
        LEFT JOIN contacts c ON c.email = (SELECT email FROM contacts WHERE account_id = a.account_id ORDER BY rowid DESC LIMIT 1)
        LEFT JOIN audit_log l ON l.id = (SELECT MAX(id) FROM audit_log WHERE account_id = a.account_id)
        ORDER BY a.account_id""").fetchall()
    return [dict(r) for r in rows]


@app.get("/api/status")
def status():
    return {"llm": getattr(llm, "model", "fake (no GEMINI_API_KEY: replies go to human review)"),
            "demo_mode": DEMO_MODE, "webhook_secret": bool(WEBHOOK_SECRET)}


def _attempts(key):
    return [dict(r) for r in conn.execute(
        "SELECT attempt, outcome, detail FROM action_attempts WHERE idempotency_key = ? ORDER BY id", (key,))]


@app.get("/api/actions")
def actions_log(limit: int = 200):
    rows = conn.execute("""
        SELECT x.idempotency_key, x.account_id, a.name, x.action, x.status, x.attempts, x.last_error, x.updated_at
        FROM actions x LEFT JOIN accounts a ON a.account_id = x.account_id
        ORDER BY x.rowid DESC LIMIT ?""", (min(limit, 500),)).fetchall()
    return [{**dict(r), "log": _attempts(r["idempotency_key"])} for r in rows]


@app.get("/api/rule-counts")
def rule_counts():
    """Cuántas decisiones tomó cada regla en toda la auditoría (sin las empresas de prueba del paso 6)."""
    return {r["rule"]: r["n"] for r in conn.execute(
        "SELECT rule, COUNT(*) n FROM audit_log WHERE account_id NOT LIKE 'test-%' GROUP BY rule")}


@app.get("/api/future-markets")
def future_markets():
    """Las empresas fuera de los mercados de Clara se guardan, así Growth puede llegar a ellas si Clara se expande."""
    out = {}
    for r in conn.execute("SELECT account_id, name, entity_countries FROM accounts"):
        for c in json.loads(r["entity_countries"] or "[]"):
            if c not in ("BR", "MX", "CO"):
                out.setdefault(c, []).append(r["name"])
    return out


@app.get("/api/audit")
def audit_log(limit: int = 60):
    return [dict(r) for r in conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (min(limit, 500),))]


@app.get("/accounts/{account_id}")
def account_state(account_id: str):
    return {
        "account": db.get_account(conn, account_id),
        "audit": [dict(r) for r in conn.execute("SELECT * FROM audit_log WHERE account_id = ? ORDER BY id", (account_id,))],
    }


@app.get("/review-queue")
def review_queue():
    return [dict(r) for r in conn.execute("SELECT * FROM audit_log WHERE decision = 'HUMAN_REVIEW' ORDER BY id DESC")]


# ---------------- consola de demo ----------------

@app.get("/")
def console():
    return FileResponse(ROOT / "app" / "static" / "index.html")


def _demo_only():
    if not DEMO_MODE:
        raise HTTPException(status_code=404)


def _seed():
    return json.loads((ROOT / "data" / "seed_accounts.json").read_text(encoding="utf-8"))


@app.post("/api/demo/reset")
def demo_reset():
    """Borra el estado y carga la foto simulada del CRM (clientes, AEs, bajas, contactos recientes)."""
    _demo_only()
    for table in ("audit_log", "action_attempts", "actions", "processed_events", "contacts", "accounts"):
        conn.execute(f"DELETE FROM {table}")
    for s in _seed():
        crm = dict(s["crm"])
        opted = crm.pop("contact_opted_out", 0)
        db.upsert_account(conn, {"account_id": s["account_id"], **s["account"], "stage": "target", **crm})
        if s["contact"]:
            db.upsert_contact(conn, {**s["contact"], "account_id": s["account_id"], "opted_out": opted})
    conn.commit()
    return {"status": "reset", "accounts": len(_seed())}


@app.post("/api/demo/target-all")
def demo_target_all():
    """Simula que el CRM manda las 30 cuentas a la lista de prospección."""
    _demo_only()
    out = []
    for s in _seed():
        ev = Event(event_id=f"tgt-{s['account_id']}", type="account_targeted", occurred_at=now_iso(),
                   account_id=s["account_id"], contact_email=(s["contact"] or {}).get("email"),
                   payload={"account": s["account"], "contact": s["contact"]})
        out.append({**orchestrator.handle(ev), "expected": s["expected"]})
    return out


@app.post("/api/demo/duplicate")
def demo_duplicate():
    """El CRM manda el mismo evento dos veces. Empresa de prueba propia, borrada en cada clic, así el resultado nunca se acumula."""
    _demo_only()
    aid = "test-duplicate"
    _wipe_test_account(aid)
    ev = Event(event_id=f"tgt-{aid}", type="account_targeted", occurred_at=now_iso(), account_id=aid,
               contact_email=f"finanzas@{aid}.example",
               payload={"account": {"name": "Test company (CRM sends the event twice)",
                                    "tax_id": "DUP950814" + uuid.uuid4().hex[:3].upper(), "entity_countries": ["MX"],
                                    "employees": 200, "industry": "retail", "legal_type": "company"},
                        "contact": {"email": f"finanzas@{aid}.example", "name": "Test", "title": "CFO", "language": "es"}})
    first = orchestrator.handle(ev)
    orchestrator.handle(ev)      # exactamente el mismo evento, por segunda vez
    sent = conn.execute("SELECT COUNT(*) FROM actions WHERE account_id = ? AND action = 'send_email' AND status = 'done'",
                        (aid,)).fetchone()[0]
    history = [dict(r) for r in conn.execute(
        "SELECT id, created_at, decision, rule, reason FROM audit_log WHERE event_id = ? ORDER BY id", (ev.event_id,))]
    return {**first, "name": "Test company (CRM sends the event twice)", "event_id": ev.event_id,
            "emails_sent_to_account": sent, "original": history[0], "this_copy": history[-1],
            "copies_received": len(history)}


def _wipe_test_account(aid):
    keys = [r[0] for r in conn.execute("SELECT idempotency_key FROM actions WHERE account_id = ?", (aid,))]
    for k in keys:
        conn.execute("DELETE FROM action_attempts WHERE idempotency_key = ?", (k,))
        outreach.sent.pop(k, None)
    for table in ("actions", "audit_log", "processed_events", "contacts", "accounts"):
        conn.execute(f"DELETE FROM {table} WHERE account_id = ?", (aid,))
    conn.commit()


@app.post("/api/demo/failure/{mode}")
def demo_failure(mode: str):
    """mode = timeout (resultado incierto, recuperado) o down (el proveedor falla 3 veces)."""
    _demo_only()
    if mode not in ("timeout", "down"):
        raise HTTPException(status_code=400)
    outreach.failures = ["timeout"] if mode == "timeout" else ["server_error"] * 3
    aid = f"test-{mode}"
    label = "email provider times out" if mode == "timeout" else "email provider is down"
    n = 1
    # La misma empresa de prueba en cada clic: se borra la corrida anterior, así el escenario arranca limpio y nada se acumula.
    _wipe_test_account(aid)
    ev = Event(event_id=f"tgt-{aid}", type="account_targeted", occurred_at=now_iso(), account_id=aid,
               contact_email=f"finanzas@{aid}.example",
               payload={"account": {"name": f"Test company ({label})", "tax_id": "FAL950814" + uuid.uuid4().hex[:3].upper(),
                                    "entity_countries": ["MX"],
                                    "employees": 200, "industry": "retail", "legal_type": "company"},
                        "contact": {"email": f"finanzas@{aid}.example", "name": "Test", "title": "CFO", "language": "es"}})
    res = orchestrator.handle(ev)
    act = dict(conn.execute("SELECT idempotency_key, attempts, status, last_error FROM actions WHERE account_id = ?", (aid,)).fetchone())
    return {**res, "name": f"Test company ({label})", "action": act, "log": _attempts(act["idempotency_key"]),
            "emails_delivered": len([k for k in outreach.sent if k.startswith(aid)])}


class CompanyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    entity_countries: list[str] = Field(default_factory=list, max_length=10)
    tax_id: str | None = Field(default=None, max_length=30)
    employees: int | None = Field(default=None, ge=0, le=5_000_000)
    industry: str | None = Field(default=None, max_length=60)
    legal_type: str = Field(default="company", max_length=30)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_title: str | None = Field(default=None, max_length=120)
    contact_email: str | None = Field(default=None, max_length=200)
    contact_language: str | None = Field(default=None, max_length=5)


@app.get("/api/countries")
def countries():
    return country_names()


@app.post("/api/demo/target-one")
def demo_target_one(c: CompanyIn):
    """Probar cualquier empresa: la consola arma el mismo evento que mandaría el CRM."""
    _demo_only()
    unknown = unknown_countries(c.entity_countries)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Not a country: {', '.join(unknown)}. Write one country per comma, "
                                                    f"for example: Argentina, Chile.")
    slug = "".join(ch for ch in c.name.lower() if ch.isalnum())[:24] or "company"
    codes = normalize_countries(c.entity_countries)
    country = (codes[0] if codes else "xx").lower()
    contact = {"email": c.contact_email, "name": c.contact_name, "title": c.contact_title,
               "language": c.contact_language} if c.contact_email else None
    event = {"event_id": f"try-{uuid.uuid4().hex[:8]}", "type": "account_targeted", "occurred_at": now_iso(),
             "account_id": f"{country}-{slug}", "contact_email": c.contact_email,
             "payload": {"account": {"name": c.name, "tax_id": c.tax_id, "entity_countries": codes,
                                     "employees": c.employees, "industry": c.industry, "legal_type": c.legal_type},
                         "contact": contact}}
    return {"event_sent": event, "result": orchestrator.handle(Event(**event))}


class ReplyIn(BaseModel):
    account_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=4000)


@app.post("/api/demo/reply")
def demo_reply(body: ReplyIn):
    """Simula la respuesta de un prospecto. El texto pasa por las reglas y, si hace falta, por el modelo real."""
    _demo_only()
    contact = conn.execute("SELECT email FROM contacts WHERE account_id = ? LIMIT 1", (body.account_id,)).fetchone()
    ev = Event(event_id=f"rep-{uuid.uuid4().hex[:8]}", type="reply_received", occurred_at=now_iso(),
               account_id=body.account_id, contact_email=contact["email"] if contact else None,
               payload={"text": body.text})
    return orchestrator.handle(ev)

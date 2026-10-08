"""event -> state -> rules -> AI -> decision -> action -> audit"""
import json
from datetime import datetime, timedelta, timezone

from app import db, rules
from app.countries import normalize_countries
from app.taxids import format_tax_id
from app.ai import interpret
from app.models import Decision, Event

# Campos que un evento entrante puede escribir. Las banderas de dueño (is_customer, assigned_ae,
# do_not_contact...) solo vienen de la sincronización con el CRM, nunca de un webhook.
FIRMOGRAPHIC_FIELDS = ("name", "tax_id", "entity_countries", "employees", "industry", "legal_type")


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Orchestrator:
    def __init__(self, conn, llm, runner, clock=lambda: datetime.now(timezone.utc)):
        self.conn, self.llm, self.runner, self.clock = conn, llm, runner, clock

    def handle(self, event: Event) -> dict:
        now = self.clock()

        # Reservar el evento antes de hacer nada. Si llegan dos copias al mismo tiempo,
        # solo un insert funciona, así que solo se procesa una copia.
        claimed = self.conn.execute(
            "INSERT OR IGNORE INTO processed_events (event_id, type, account_id, received_at, outcome)"
            " VALUES (?, ?, ?, ?, 'processing')",
            (event.event_id, event.type, event.account_id, now.isoformat()),
        ).rowcount
        self.conn.commit()
        if not claimed:
            reason = "duplicate event: this event_id was already processed, nothing done"
            db.audit(self.conn, event.event_id, event.account_id, "IGNORE", "duplicate_event", reason, None,
                     "no_external_call", now.isoformat())
            self.conn.commit()
            return {"event_id": event.event_id, "account_id": event.account_id, "decision": "IGNORE",
                    "rule": "duplicate_event", "reason": reason, "action_status": "no_external_call", "ai": None}

        account = db.get_account(self.conn, event.account_id)
        if account is None and event.type != "account_targeted":
            return self._close(event, event.account_id, Decision(
                kind="HUMAN_REVIEW", rule="unknown_account", reason="event for an account we do not know"), None, None, now)

        # Desordenado: un evento más viejo no puede pisar un estado más nuevo.
        if account and account.get("last_event_at") and parse_ts(event.occurred_at) < parse_ts(account["last_event_at"]):
            return self._close(event, account["account_id"], Decision(
                kind="IGNORE", rule="stale_event", reason="event older than the account's last event"), None, None, now)

        if event.type == "account_targeted":
            twin = self._same_company(event) if account is None else None
            if twin:
                return self._close(event, event.account_id, Decision(
                    kind="HUMAN_REVIEW", rule="R0_duplicate_company",
                    reason=f"same tax ID as {twin['name']} ({twin['account_id']}): merge the records in the CRM"),
                    None, None, now)
            account = self._apply_targeted_payload(event)
        contact = db.get_contact(self.conn, event.contact_email) if event.contact_email else None

        ai_output = None
        if event.type == "account_targeted":
            decision = rules.decide_targeted(account, contact, now)
        elif event.type == "reply_received":
            text = event.payload.get("text", "")
            decision = rules.decide_reply_pre_ai(account, contact, text)
            if decision is None:
                ai, failure, raw = interpret(self.llm, text)
                ai_output = ai.model_dump() if ai else {"rejected": failure, "raw": raw}
                ai_output["model"] = getattr(self.llm, "model", "mock")
                decision = rules.decide_from_ai(ai, failure)
        else:  # meeting_booked
            decision = rules.ownership_rules(account, contact, replied=True) or Decision(
                kind="HANDOFF", rule="meeting_booked", reason="prospect booked a meeting")

        status = self._act(event, account, contact, decision, ai_output, now)
        return self._close(event, account["account_id"], decision, ai_output, status, now)

    # ---------- acciones y estado ----------

    def _act(self, event, account, contact, d: Decision, ai_output, now) -> str:
        aid = account["account_id"]
        state = {"last_event_at": event.occurred_at}
        status = "no_external_call"

        if d.kind == "CONTACT":
            status = self.runner.run(aid, "send_email", event.event_id, {
                "to": contact["email"], "language": contact["language"], "template": "first_touch"})
            if self._ok(status):
                state.update(stage="contacted", last_outreach_at=now.isoformat())
        elif d.kind == "HANDOFF":
            status = self.runner.run(aid, "create_ae_task", event.event_id, {
                "contact": event.contact_email, "summary": d.reason, "ai": ai_output})
            if self._ok(status):
                state.update(stage="handed_off")
        elif d.kind == "ENRICH":
            status = self.runner.run(aid, "request_enrichment", event.event_id, {"reason": d.reason})
        elif d.kind == "WAIT":
            if d.rule == "R7_cooldown":
                follow_up = parse_ts(account["last_outreach_at"]) + timedelta(days=rules.ICP["contact_cooldown_days"])
            else:
                follow_up = now + timedelta(days=30)
                state.update(stage="engaged")
            state.update(next_follow_up_at=follow_up.isoformat())
        elif d.kind == "SUPPRESS":
            if d.rule not in ("R1_customer", "R2_owned_by_ae"):
                state.update(stage="suppressed")
            if d.opt_out and contact:
                self.conn.execute("UPDATE contacts SET opted_out = 1 WHERE email = ?", (contact["email"],))
            if d.notify_ae:
                status = self.runner.run(aid, "notify_ae", event.event_id, {
                    "ae": account.get("assigned_ae"), "contact": event.contact_email,
                    "text": event.payload.get("text")})
        elif d.kind == "HUMAN_REVIEW" and event.type == "reply_received":
            state.update(stage="engaged")

        # Una acción externa que falló en todos los reintentos va a una persona.
        if status == "failed":
            d.reason += " | action failed after retries"
            d.kind = "HUMAN_REVIEW"
        db.update_account(self.conn, aid, **state)
        return status

    @staticmethod
    def _ok(status):
        return status in ("done", "already_done")

    def _close(self, event, account_id, d: Decision, ai_output, status, now):
        self.conn.execute("UPDATE processed_events SET outcome = ? WHERE event_id = ?", (d.kind, event.event_id))
        db.audit(self.conn, event.event_id, account_id, d.kind, d.rule, d.reason, ai_output, status, now.isoformat())
        self.conn.commit()
        return {"event_id": event.event_id, "account_id": account_id, "decision": d.kind, "rule": d.rule,
                "reason": d.reason, "action_status": status, "ai": ai_output}

    @staticmethod
    def _clean_account(raw: dict) -> dict:
        acc = {k: v for k, v in (raw or {}).items() if k in FIRMOGRAPHIC_FIELDS}
        acc["entity_countries"] = normalize_countries(acc.get("entity_countries"))
        acc["tax_id"] = format_tax_id(acc.get("tax_id"), acc["entity_countries"])
        return acc

    def _same_company(self, event):
        """Un account_id nuevo con un ID fiscal que ya tiene otra cuenta es la misma empresa cargada dos veces."""
        tax = self._clean_account(event.payload.get("account")).get("tax_id")
        if not tax:
            return None
        countries = set(self._clean_account(event.payload.get("account"))["entity_countries"])
        # el mismo número solo es la misma empresa dentro del mismo país
        for row in self.conn.execute("SELECT account_id, name, entity_countries FROM accounts WHERE tax_id = ?", (tax,)):
            if countries & set(json.loads(row["entity_countries"] or "[]")):
                return {"account_id": row["account_id"], "name": row["name"]}
        return None

    def _apply_targeted_payload(self, event):
        acc = self._clean_account(event.payload.get("account"))
        db.upsert_account(self.conn, {"account_id": event.account_id, **acc})
        c = event.payload.get("contact")
        if c and c.get("email"):
            existing = db.get_contact(self.conn, c["email"]) or {}
            db.upsert_contact(self.conn, {
                "email": c["email"], "account_id": event.account_id, "name": c.get("name"),
                "title": c.get("title"), "language": c.get("language"), "linkedin_url": c.get("linkedin_url"),
                "personal_email": int(rules.is_personal_email(c["email"])),
                "opted_out": existing.get("opted_out", 0),
            })
        return db.get_account(self.conn, event.account_id)

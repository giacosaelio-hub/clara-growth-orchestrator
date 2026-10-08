"""Plays the role of Clara's CRM and outreach tool against the running server.

    py scripts/send_events.py --load-crm      # 1) copy the CRM snapshot into the server's database
    py scripts/send_events.py                 # 2) send events to http://localhost:8000/events
"""
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app import db  # noqa: E402

URL = os.environ.get("API_URL", "http://localhost:8000")
HEADERS = {"X-Webhook-Secret": os.environ["WEBHOOK_SECRET"]} if os.environ.get("WEBHOOK_SECRET") else {}
SEED = json.loads((ROOT / "data" / "seed_accounts.json").read_text(encoding="utf-8"))


def load_crm():
    conn = db.connect(str(ROOT / "data" / "state.db"))
    for s in SEED:
        crm = dict(s["crm"])
        opted = crm.pop("contact_opted_out", 0)
        if crm or opted:
            db.upsert_account(conn, {"account_id": s["account_id"], **s["account"], **crm})
            if s["contact"]:
                db.upsert_contact(conn, {**s["contact"], "account_id": s["account_id"], "opted_out": opted})
    conn.commit()
    print("CRM snapshot loaded")


def post(event):
    r = httpx.post(f"{URL}/events", json=event, headers=HEADERS, timeout=60)
    out = r.json()
    print(f"{r.status_code} {event['event_id']:<10} {out.get('account_id', ''):<20} {out.get('decision'):<13} {out.get('reason', '')[:70]}")


def main():
    if "--load-crm" in sys.argv:
        return load_crm()
    pick = {s["account_id"]: s for s in SEED}
    for i, aid in enumerate(["br-loggi", "mx-liverpool", "br-magalu", "ar-laanonima", "co-crepes"]):
        s = pick[aid]
        post({"event_id": f"srv-t{i}", "type": "account_targeted", "occurred_at": f"2026-10-06T18:{i:02d}:00Z",
              "account_id": aid, "contact_email": (s["contact"] or {}).get("email"),
              "payload": {"account": s["account"], "contact": s["contact"]}})
    # the same webhook delivered twice
    s = pick["br-loggi"]
    post({"event_id": "srv-t0", "type": "account_targeted", "occurred_at": "2026-10-06T18:00:00Z",
          "account_id": "br-loggi", "contact_email": s["contact"]["email"],
          "payload": {"account": s["account"], "contact": s["contact"]}})
    # a real reply, interpreted by Gemini
    post({"event_id": "srv-r1", "type": "reply_received", "occurred_at": "2026-10-06T18:30:00Z",
          "account_id": "br-loggi", "contact_email": s["contact"]["email"],
          "payload": {"text": "Oi, aqui é a Marina. Tenho interesse, hoje os gastos dos entregadores são todos em planilha. Podemos falar quinta às 10h?"}})
    print(f"\nstate of br-loggi: {URL}/accounts/br-loggi   review queue: {URL}/review-queue   docs: {URL}/docs")


if __name__ == "__main__":
    main()

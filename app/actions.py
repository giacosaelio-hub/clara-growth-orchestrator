"""Ejecuta acciones externas con clave de idempotencia y reintentos."""
import json
import time
from datetime import datetime, timedelta, timezone

from app.integrations import TransientError, UncertainOutcome

MAX_ATTEMPTS = 3


def _now():
    return datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec="seconds")   # Hora de São Paulo, como en la demo


class ActionRunner:
    def __init__(self, conn, outreach, crm, enrichment, sleep=time.sleep, base_delay=0.5):
        self.conn, self.sleep, self.base_delay = conn, sleep, base_delay
        self.handlers = {
            "send_email": (outreach.send_email, outreach.get_status),
            "create_ae_task": (crm.create_ae_task, None),
            "notify_ae": (crm.notify_ae, None),
            "request_enrichment": (enrichment.request, None),
        }

    def run(self, account_id: str, action: str, event_id: str, payload: dict) -> str:
        """Devuelve done | failed | already_done."""
        key = f"{account_id}:{action}:{event_id}"
        row = self.conn.execute("SELECT status FROM actions WHERE idempotency_key = ?", (key,)).fetchone()
        if row and row["status"] == "done":
            self._log(key, 0, "skipped_already_done", "this action was already done: nothing sent")
            return "already_done"
        self.conn.execute(
            "INSERT OR IGNORE INTO actions (idempotency_key, account_id, action, payload, status, updated_at)"
            " VALUES (?, ?, ?, ?, 'pending', ?)",
            (key, account_id, action, json.dumps(payload, ensure_ascii=False), _now()),
        )
        call, check = self.handlers[action]
        last_error = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            # después de un timeout no sabemos si salió: preguntar antes de volver a enviar
            if attempt > 1 and check and check(key) == "sent":
                self._log(key, attempt, "confirmed_sent", "asked the provider before retrying: it had gone out, not sent again")
                return self._finish(key, "done", attempt - 1, "confirmed after uncertain outcome")
            try:
                call(key, payload)
                self._log(key, attempt, "sent", "ok")
                return self._finish(key, "done", attempt, None)
            except (TransientError, UncertainOutcome) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self._log(key, attempt, "timeout" if isinstance(exc, UncertainOutcome) else "error", str(exc))
                self._finish(key, "pending", attempt, last_error)
                if attempt < MAX_ATTEMPTS:
                    delay = self.base_delay * 2 ** (attempt - 1)
                    self._log(key, attempt, "wait", f"waited {delay} s before trying again")
                    self.sleep(delay)
        return self._finish(key, "failed", MAX_ATTEMPTS, last_error)

    def _log(self, key, attempt, outcome, detail):
        self.conn.execute("INSERT INTO action_attempts (idempotency_key, attempt, outcome, detail, at) VALUES (?, ?, ?, ?, ?)",
                          (key, attempt, outcome, detail, _now()))

    def _finish(self, key, status, attempts, error):
        self.conn.execute(
            "UPDATE actions SET status = ?, attempts = ?, last_error = ?, updated_at = ? WHERE idempotency_key = ?",
            (status, attempts, error, _now(), key),
        )
        return status

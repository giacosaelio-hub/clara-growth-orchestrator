"""Integraciones simuladas: versiones de prueba de la herramienta de envío, el CRM y el proveedor de enriquecimiento de Clara.

Se comportan como APIs reales, fallas incluidas, pero nada sale de la computadora.
"""


class TransientError(Exception):
    """Vale la pena reintentar: límite de velocidad, error del servidor."""


class UncertainOutcome(Exception):
    """Timeout: el pedido puede haberse ejecutado o no."""


class MockOutreach:
    def __init__(self, failures: list[str] | None = None):
        # failures es un guion, por ejemplo ["timeout", "rate_limit"]: se consume una falla por llamada
        self.failures = list(failures or [])
        self.sent: dict[str, dict] = {}

    def send_email(self, key: str, payload: dict) -> dict:
        mode = self.failures.pop(0) if self.failures else None
        if mode == "rate_limit":
            raise TransientError("429 rate limited")
        if mode == "server_error":
            raise TransientError("503 service unavailable")
        if mode == "timeout":
            self.sent[key] = payload          # el proveedor sí lo envió, solo que nunca nos llegó la respuesta
            raise UncertainOutcome("request timed out")
        self.sent[key] = payload
        return {"status": "sent", "key": key}

    def get_status(self, key: str) -> str | None:
        return "sent" if key in self.sent else None


class MockCRM:
    def __init__(self):
        self.tasks: dict[str, dict] = {}
        self.notes: dict[str, dict] = {}

    def create_ae_task(self, key: str, payload: dict) -> dict:
        self.tasks[key] = payload
        return {"status": "created", "key": key}

    def notify_ae(self, key: str, payload: dict) -> dict:
        self.notes[key] = payload
        return {"status": "notified", "key": key}


class MockEnrichment:
    def __init__(self):
        self.requests: dict[str, dict] = {}

    def request(self, key: str, payload: dict) -> dict:
        self.requests[key] = payload
        return {"status": "queued", "key": key}

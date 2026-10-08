"""Contratos del evento y de la salida de la IA."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

EventType = Literal["account_targeted", "reply_received", "meeting_booked"]


class Event(BaseModel):
    event_id: str
    type: EventType
    occurred_at: str                      # ISO 8601, UTC
    account_id: str
    contact_email: Optional[str] = None
    payload: dict = Field(default_factory=dict)


class Qualification(BaseModel):
    timeline: Optional[str] = None
    current_tool: Optional[str] = None
    decision_maker: Optional[bool] = None
    referral_contact: Optional[str] = None
    meeting_requested: Optional[bool] = None
    meeting_time: Optional[str] = None


class ReplyInterpretation(BaseModel):
    """Lo que el LLM tiene que devolver cuando lee la respuesta de un prospecto."""
    intent: Literal["interested", "not_now", "referral", "question", "not_interested", "unclear"]
    confidence: float = Field(ge=0, le=1)
    language: Literal["es", "pt", "en", "other"]
    qualification: Qualification = Field(default_factory=Qualification)
    evidence: str = Field(min_length=1)


class Decision(BaseModel):
    kind: Literal["CONTACT", "WAIT", "ENRICH", "SUPPRESS", "HANDOFF", "HUMAN_REVIEW", "IGNORE"]
    rule: str
    reason: str
    opt_out: bool = False
    notify_ae: bool = False

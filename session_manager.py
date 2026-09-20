from __future__ import annotations
import uuid
from datetime import datetime, timezone

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

def new_session_id() -> str:
    return f"sess_{uuid.uuid4().hex}"

def ensure_session(chat: dict) -> dict:
    if not chat.get("session_id"):
        chat["session_id"] = new_session_id()
    chat.setdefault("session_started_at", utc_now())
    chat["session_updated_at"] = utc_now()
    return chat

from __future__ import annotations
from conversation_store import ensure_store, append_once, touch, now
from conversation_runtime import sanitize

def record_message(chat: dict, message_id: str, role: str, user_input: str, timestamp: str | None = None, request_id: str = "", round_id: str = "") -> dict:
    """Persist one application-owned message row and reconcile its lifecycle links.

    The row is keyed only by message_id.  Repeated Streamlit reruns therefore update
    linkage fields instead of creating a second logical message.  No provider prose
    participates in identity.
    """
    ensure_store(chat); touch(chat)
    mid = str(message_id or "").strip()
    if not mid:
        raise ValueError("message_id is required")
    row = {
        "message_id": mid,
        "conversation_id": str(chat.get("conversation_id")),
        "session_id": str(chat.get("session_id")),
        "role": sanitize(role, 30),
        "user_input": sanitize(user_input, 20000),
        "timestamp": timestamp or now(),
        "request_id": str(request_id or ""),
        "round_id": str(round_id or ""),
    }
    existing = next((x for x in chat["message_ledger_v24"] if str(x.get("message_id") or "") == mid), None)
    if existing is None:
        chat["message_ledger_v24"].append(row)
    else:
        # Preserve the original message timestamp/content; lifecycle linkage may be
        # filled in later once the authoritative round has been created.
        for key in ("conversation_id", "session_id", "role", "user_input"):
            existing[key] = row[key]
        if not existing.get("timestamp"):
            existing["timestamp"] = row["timestamp"]
        if request_id:
            existing["request_id"] = str(request_id)
        if round_id:
            existing["round_id"] = str(round_id)
        row = existing
    chat["message_ledger_v24"] = chat["message_ledger_v24"][-400:]
    return row

def message_ids(chat: dict) -> list[str]:
    ensure_store(chat)
    return [str(x.get("message_id")) for x in chat["message_ledger_v24"] if x.get("message_id")]

from __future__ import annotations
from conversation_store import ensure_store, append_once, touch, now
from conversation_runtime import sanitize

def record_message(chat: dict, message_id: str, role: str, user_input: str, timestamp: str | None = None, request_id: str = "", round_id: str = "") -> dict:
    ensure_store(chat); touch(chat)
    row = {"message_id": str(message_id), "conversation_id": str(chat.get("conversation_id")), "session_id": str(chat.get("session_id")), "role": sanitize(role, 30), "request_id": str(request_id or ""), "round_id": str(round_id or ""), "user_input": sanitize(user_input, 20000), "timestamp": timestamp or now()}
    existing = next((x for x in chat["message_ledger_v24"] if str(x.get("message_id") or "") == str(message_id)), None)
    if existing is not None:
        existing.update(row)
    else:
        append_once(chat["message_ledger_v24"], row, ("message_id",))
    # When the runtime explicitly supplies a request_id, preserve that already-
    # allocated identity in the canonical store. This is not identity invention:
    # the caller has supplied both Message and Request identifiers.
    if str(request_id or "").strip():
        from conversation_store import canonical_upsert_message, canonical_upsert_request
        canonical_upsert_message(chat, {
            "message_id": str(message_id), "request_id": str(request_id),
            "conversation_id": str(chat.get("conversation_id") or ""),
            "session_id": str(chat.get("session_id") or ""), "role": sanitize(role, 30),
            "created_at": row["timestamp"],
        })
        canonical_upsert_request(chat, {
            "request_id": str(request_id), "message_id": str(message_id),
            "conversation_id": str(chat.get("conversation_id") or ""),
            "session_id": str(chat.get("session_id") or ""), "state": "RUNNING",
            "created_at": row["timestamp"],
        })
    return row

def message_ids(chat: dict) -> list[str]:
    ensure_store(chat)
    return [str(x.get("message_id")) for x in chat["message_ledger_v24"] if x.get("message_id")]

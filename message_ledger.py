from __future__ import annotations
from conversation_store import ensure_store, append_once, touch, now, canonical_upsert_message, canonical_upsert_request
from conversation_runtime import sanitize

def record_message(chat: dict, message_id: str, role: str, user_input: str, timestamp: str | None = None, request_id: str = "", round_id: str = "") -> dict:
    ensure_store(chat); touch(chat)
    row = {"message_id": str(message_id), "conversation_id": str(chat.get("conversation_id")), "session_id": str(chat.get("session_id")), "role": sanitize(role, 30), "request_id": str(request_id or ""), "round_id": str(round_id or ""), "user_input": sanitize(user_input, 20000), "timestamp": timestamp or now()}
    append_once(chat["message_ledger_v24"], row, ("message_id",))
    existing_ledger = next((x for x in chat["message_ledger_v24"] if str(x.get("message_id") or "") == str(message_id)), None)
    if existing_ledger is not None:
        if str(request_id or "").strip(): existing_ledger["request_id"] = str(request_id)
        if str(round_id or "").strip(): existing_ledger["round_id"] = str(round_id)
    # Message/request identity is created at the lifecycle write boundary, not
    # reconstructed by an audit.  The request_id is explicit caller-owned
    # identity; this write therefore cannot invent a request.
    if str(request_id or "").strip():
        canonical_upsert_message(chat, {
            "message_id": str(message_id), "conversation_id": row["conversation_id"],
            "session_id": row["session_id"], "role": row["role"],
            "request_id": str(request_id), "created_at": row["timestamp"],
        })
        canonical_upsert_request(chat, {
            "request_id": str(request_id), "message_id": str(message_id),
            "conversation_id": row["conversation_id"], "session_id": row["session_id"],
        })
        if str(round_id or "").strip():
            existing = next((x for x in chat["message_ledger_v24"] if str(x.get("message_id") or "") == str(message_id)), None)
            if existing is not None:
                existing["round_id"] = str(round_id)
    return row

def message_ids(chat: dict) -> list[str]:
    ensure_store(chat)
    return [str(x.get("message_id")) for x in chat["message_ledger_v24"] if x.get("message_id")]

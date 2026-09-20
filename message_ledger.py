from __future__ import annotations
from conversation_store import ensure_store, append_once, touch, now
from conversation_runtime import sanitize

def record_message(chat: dict, message_id: str, role: str, user_input: str, timestamp: str | None = None) -> dict:
    ensure_store(chat); touch(chat)
    row = {"message_id": str(message_id), "conversation_id": str(chat.get("conversation_id")), "session_id": str(chat.get("session_id")), "role": sanitize(role, 30), "user_input": sanitize(user_input, 20000), "timestamp": timestamp or now()}
    append_once(chat["message_ledger_v24"], row, ("message_id",))
    return row

def message_ids(chat: dict) -> list[str]:
    ensure_store(chat)
    return [str(x.get("message_id")) for x in chat["message_ledger_v24"] if x.get("message_id")]

from __future__ import annotations
from conversation_store import ensure_store, touch

def migrate_chat(chat: dict) -> dict:
    ensure_store(chat); touch(chat)
    # Import pre-V24 messages only as ledger metadata. Do not duplicate content into provider state.
    existing={str(x.get("message_id")) for x in chat.get("message_ledger_v24",[]) if isinstance(x,dict)}
    for msg in chat.get("messages",[]):
        if not isinstance(msg,dict): continue
        mid=str(msg.get("id") or "")
        if mid and mid not in existing:
            chat["message_ledger_v24"].append({"message_id":mid,"conversation_id":chat.get("conversation_id"),"session_id":chat.get("session_id"),"role":str(msg.get("role") or ""),"user_input":"","timestamp":str(msg.get("created_at") or chat.get("created_at") or "")})
    return chat

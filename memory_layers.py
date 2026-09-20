from __future__ import annotations
import hashlib
from conversation_store import ensure_store, touch
from conversation_runtime import sanitize

def update_memory(chat: dict, message_id: str, user_text: str, context_digest: str = "") -> None:
    ensure_store(chat); touch(chat)
    clean=sanitize(user_text,20000)
    chat["memory_l0"]={"message_id":str(message_id),"text":clean,"updated_at":chat["updated_at_v24"]}
    ids=list(chat["memory_l1"].get("message_ids",[]));
    if message_id not in ids: ids.append(str(message_id))
    chat["memory_l1"]={"message_ids":ids[-200:],"context_digest":context_digest or hashlib.sha256(clean.encode()).hexdigest()[:32],"updated_at":chat["updated_at_v24"]}
    # L2 stores references/summaries, never credentials or raw provider payloads.
    chat["memory_l2"]={"items":[{"message_id":str(message_id),"summary":clean[:1000]}][-200:] if not chat["memory_l2"].get("items") else (chat["memory_l2"]["items"]+[ {"message_id":str(message_id),"summary":clean[:1000]}])[-200:]}

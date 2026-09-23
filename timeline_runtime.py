from __future__ import annotations
from conversation_store import ensure_store, append_once, touch, now

def event(chat: dict, request_id: str, message_id: str, event_type: str, **meta) -> dict:
    ensure_store(chat); touch(chat)
    row={"event_id":f"evt_{__import__('uuid').uuid4().hex}","timestamp":now(),"conversation_id":chat.get("conversation_id"),"session_id":chat.get("session_id"),"message_id":str(message_id),"request_id":str(request_id),"event_type":str(event_type)}
    row.update({k:v for k,v in meta.items() if k not in ("api_key","authorization","token","secret")})
    chat["timeline_ledger_v24"].append(row); chat["timeline_ledger_v24"]=chat["timeline_ledger_v24"][-5000:]
    return row

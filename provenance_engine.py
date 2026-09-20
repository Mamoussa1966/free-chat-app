from __future__ import annotations
from conversation_store import ensure_store, append_once, touch

def record_result(chat: dict, result: dict, message_id: str, round_id: str) -> list[dict]:
    ensure_store(chat); touch(chat)
    rows=[]
    for ev in result.get("runtime_execution_events") or result.get("attempt_telemetry") or []:
        if not isinstance(ev, dict): continue
        attempt=int(ev.get("attempt") or 0)
        if attempt <= 0: continue
        row={"conversation_id":chat.get("conversation_id"),"session_id":chat.get("session_id"),"message_id":str(message_id),"round_id":str(round_id),"request_id":str(result.get("request_id") or ""),"provider":str(result.get("name") or result.get("seat") or ""),"seat":str(result.get("seat") or ""),"model":str(ev.get("model") or result.get("executed_model") or ""),"attempt":attempt,"status":str(ev.get("status") or result.get("status") or ""),"classification":str(ev.get("classification") or ""),"cascade_action":str(ev.get("cascade_action") or "")}
        row["provenance_key"]=f"{row['request_id']}:{row['round_id']}:{row['seat']}:{attempt}"
        append_once(chat["provenance_ledger_v24"],row,("provenance_key",)); rows.append(row)
    return rows

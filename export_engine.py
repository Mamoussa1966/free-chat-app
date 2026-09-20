from __future__ import annotations
import json
from conversation_store import authoritative_snapshot

def export_conversation(chat: dict) -> str:
    return json.dumps(authoritative_snapshot(chat), ensure_ascii=False, indent=2, sort_keys=True)

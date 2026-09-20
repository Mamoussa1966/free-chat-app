from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

SCHEMA_VERSION = "v24-conversation-ledger/v1"

@dataclass
class ConversationRecord:
    conversation_id: str
    session_id: str
    created_at: str
    updated_at: str

@dataclass
class MessageRecord:
    message_id: str
    conversation_id: str
    session_id: str
    role: str
    user_input: str
    timestamp: str

@dataclass
class RoundRecord:
    round_id: str
    message_id: str
    request_id: str
    round_no: int
    status: str
    created_at: str
    finished_at: str = ""

@dataclass
class RequestRecordV24:
    request_id: str
    conversation_id: str
    session_id: str
    message_id: str
    round_id: str
    provider: str
    seat: str
    model: str
    status: str

@dataclass
class BridgeRecord:
    bridge_id: str
    request_id: str
    round_id: str
    status: str

@dataclass
class ResultRecord:
    result_id: str
    request_id: str
    message_id: str
    provider: str
    seat: str
    model: str
    status: str
    provenance_count: int

def as_public_dict(obj: Any) -> dict[str, Any]:
    return asdict(obj) if hasattr(obj, "__dataclass_fields__") else dict(obj or {})

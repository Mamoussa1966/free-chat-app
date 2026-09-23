from collections.abc import Mapping
from conversation_store import ensure_store, canonical_create_lifecycle, load_canonical_snapshot, canonical_history_hash
from conversation_v25_runtime import authoritative_audit

class SessionStateLike(Mapping):
    def __init__(self, data): self._data = data
    def __getitem__(self, key): return self._data[key]
    def __iter__(self): return iter(self._data)
    def __len__(self): return len(self._data)
    def get(self, key, default=None): return self._data.get(key, default)

def _chat():
    c={"conversation_id":"conv-hash", "session_id":"sess-hash"}
    ensure_store(c); return c

def _row(i):
    mid=f"M{i}"; rid=f"R{i}"; oid=f"O{i}"; ts=f"2026-09-23T00:0{i}:00Z"
    return (
      {"message_id":mid,"conversation_id":"conv-hash","session_id":"sess-hash","role":"user","request_id":rid,"created_at":ts},
      {"request_id":rid,"conversation_id":"conv-hash","session_id":"sess-hash","message_id":mid,"created_at":ts,"state":"COMPLETED"},
      {"round_id":oid,"conversation_id":"conv-hash","session_id":"sess-hash","message_id":mid,"request_id":rid,"round":1,"created_at":ts,"status":"COMPLETED"})

def test_hotfix122_canonical_hash_matches_with_mapping_session_state():
    plain = {}
    chat=_chat()
    for i in (1,2): canonical_create_lifecycle(chat,*_row(i),plain)
    # Recreate the real rerun boundary with a Mapping-like SessionState.
    ss=SessionStateLike(plain)
    snap=load_canonical_snapshot(chat, ss)
    assert snap is not None
    assert snap["canonical_history_hash"] == canonical_history_hash(snap)
    audit=authoritative_audit(chat, ss)
    assert audit["canonical_transport_hash_matches"] is True

def test_hotfix122_hash_mismatch_is_not_passed():
    plain = {}
    chat=_chat(); canonical_create_lifecycle(chat,*_row(1),plain)
    bucket=plain["v26_3_canonical_conversation_store"]["conv-hash"]
    bucket["history_hash"]="0"*64
    ss=SessionStateLike(plain)
    audit=authoritative_audit(chat, ss)
    assert audit["canonical_transport_hash_matches"] is False

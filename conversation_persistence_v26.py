from __future__ import annotations
import copy
from conversation_store import now

SCHEMA = "v26.3.3-canonical-conversation-record-persistence/v4"
MAX_MESSAGES = 1000
MAX_REQUESTS = 1000
MAX_ROUNDS = 2000


def _s(v):
    return str(v or "").strip()


def ensure_persistence_store(session_state):
    store = session_state.setdefault("v26_3_conversation_persistence", {})
    if not isinstance(store, dict):
        store = {}
        session_state["v26_3_conversation_persistence"] = store
    return store


def _bucket(store, conversation_id):
    cid = _s(conversation_id)
    if not cid:
        return None
    row = store.setdefault(cid, {
        "schema": SCHEMA,
        "conversation_id": cid,
        "messages": [],
        "requests": [],
        "rounds": [],
    })
    for key in ("messages", "requests", "rounds"):
        if not isinstance(row.get(key), list):
            row[key] = []
    return row


def _append_unique(rows, row, keys):
    identity = tuple(_s(row.get(k)) for k in keys)
    if not all(identity):
        return False
    for old in rows:
        if tuple(_s(old.get(k)) for k in keys) == identity:
            # Preserve the original identity record, but allow lifecycle fields to
            # become richer without changing identity.
            # Never let a later row rewrite an established identity binding.
            # A changed Message→Request binding is an explicit conflict.
            if _s(old.get("request_id")) and _s(row.get("request_id")) and _s(old.get("request_id")) != _s(row.get("request_id")):
                old["identity_conflict"] = True
                return False
            for k, v in row.items():
                if v not in (None, "", [], {}):
                    old[k] = copy.deepcopy(v)
            return False
    rows.append(copy.deepcopy(row))
    return True


def _chat_bucket(chat):
    """Canonical durable-in-object persistence attached to conversation_record.

    `chat` is the application-owned canonical Conversation object held inside the
    conversation collection.  The historical ledger MUST live inside that object,
    not only in Streamlit session_state.  The legacy top-level field is retained as
    a compatibility mirror, never as the authoritative source.
    """
    cid = _s(chat.get("conversation_id"))
    if not cid:
        return None
    record = chat.setdefault("conversation_record", {})
    if not isinstance(record, dict):
        record = {}
        chat["conversation_record"] = record
    root = record.setdefault("v26_3_conversation_persistence", {})
    if not isinstance(root, dict):
        root = {}
        record["v26_3_conversation_persistence"] = root
    row = root.setdefault(cid, {"schema": SCHEMA, "conversation_id": cid, "messages": [], "requests": [], "rounds": []})
    if not isinstance(row, dict):
        row = {"schema": SCHEMA, "conversation_id": cid, "messages": [], "requests": [], "rounds": []}
        root[cid] = row
    for key in ("messages", "requests", "rounds"):
        if not isinstance(row.get(key), list):
            row[key] = []
    # Keep the former location synchronized for compatibility, but it is never read
    # as authoritative historical state.
    legacy_root = chat.setdefault("v26_3_conversation_persistence", {})
    if isinstance(legacy_root, dict):
        legacy_root[cid] = row
    return row


def _merge_bucket(dst, src):
    if not isinstance(src, dict):
        return
    for key, keys in (("messages", ("message_id",)), ("requests", ("request_id",)), ("rounds", ("round_id",))):
        for item in src.get(key, []) if isinstance(src.get(key), list) else []:
            if isinstance(item, dict):
                _append_unique(dst[key], item, keys)


def persist_identity(chat, session_state, *, message=None, request=None, round_row=None):
    """Append identity to BOTH canonical chat persistence and session mirror.

    The chat-embedded ledger is authoritative. session_state is only a mirror for
    compatibility/hydration; neither source mints IDs or consults provider prose.
    """
    canonical = _chat_bucket(chat)
    if canonical is None:
        return
    if isinstance(message, dict):
        _append_unique(canonical["messages"], message, ("message_id",))
    if isinstance(request, dict):
        _append_unique(canonical["requests"], request, ("request_id",))
    if isinstance(round_row, dict):
        _append_unique(canonical["rounds"], round_row, ("round_id",))
    for key, limit in (("messages", MAX_MESSAGES), ("requests", MAX_REQUESTS), ("rounds", MAX_ROUNDS)):
        canonical[key] = canonical[key][-limit:]

    mirror = _bucket(ensure_persistence_store(session_state), chat.get("conversation_id"))
    _merge_bucket(mirror, canonical)



def get_authoritative_bucket(chat, session_state=None):
    """Read the canonical Conversation object's durable historical ledger only.

    session_state is intentionally NOT an authoritative fallback.  A missing
    canonical record is therefore NOT_PROVEN rather than reconstructed from a
    narrower/current source.
    """
    cid = _s(chat.get("conversation_id"))
    if not cid:
        return {"schema": SCHEMA, "conversation_id": "", "messages": [], "requests": [], "rounds": []}
    record = chat.get("conversation_record") if isinstance(chat, dict) else None
    root = record.get("v26_3_conversation_persistence") if isinstance(record, dict) else None
    bucket = root.get(cid) if isinstance(root, dict) else None
    if isinstance(bucket, dict):
        for key in ("messages", "requests", "rounds"):
            if not isinstance(bucket.get(key), list):
                bucket[key] = []
        return bucket
    return {"schema": SCHEMA, "conversation_id": cid, "messages": [], "requests": [], "rounds": []}


def authoritative_history(chat, session_state):
    bucket = get_authoritative_bucket(chat, session_state)
    return {
        "schema": SCHEMA,
        "source": "V26.3.2_CANONICAL_CONVERSATION_OBJECT_PERSISTENCE",
        "conversation_id": _s(chat.get("conversation_id")) or "NOT_PROVEN",
        "messages": [copy.deepcopy(x) for x in bucket.get("messages", []) if isinstance(x, dict)],
        "requests": [copy.deepcopy(x) for x in bucket.get("requests", []) if isinstance(x, dict)],
        "rounds": [copy.deepcopy(x) for x in bucket.get("rounds", []) if isinstance(x, dict)],
    }


def snapshot_chat_identity(chat, session_state):
    """Persist the complete application-owned Conversation identity before audit.

    V26.3.4 closes the gap exposed by the two-message runtime test: HOTFIX145's
    canonical chat object contains the user-facing Message records even when a
    narrower request ledger has already been reduced to the current Request.
    Those records are application-owned (not provider prose), so they are valid
    identity evidence. Existing request/round records are preferred; no IDs are
    minted here. A request is copied from an existing application-owned record
    only when its explicit request_id is already bound to a persisted Message.
    """
    ensure_persistence_store(session_state)
    _chat_bucket(chat)

    # 1) HOTFIX145 canonical message ledger.
    for row in chat.get("message_ledger", []):
        if isinstance(row, dict) and _s(row.get("message_id")) and _s(row.get("request_id")):
            persist_identity(chat, session_state, message=row)

    # 2) Canonical user Message objects. This is the critical historical bridge:
    # the UI/history may retain both Messages while request_records is current-only.
    for row in chat.get("messages", []):
        if not isinstance(row, dict) or str(row.get("role") or "").lower() != "user":
            continue
        mid = _s(row.get("id") or row.get("message_id"))
        rid = _s(row.get("request_id"))
        if not mid or not rid:
            continue
        persist_identity(chat, session_state, message={
            "message_id": mid,
            "conversation_id": _s(row.get("conversation_id")) or _s(chat.get("conversation_id")),
            "session_id": _s(row.get("session_id")) or _s(chat.get("session_id")),
            "role": "user",
            "request_id": rid,
            "created_at": row.get("created_at") or now(),
        })

    # 3) Request identity: prefer the real lifecycle/request record. If a historical
    # user Message has an explicit request_id but request_records has been narrowed,
    # use an already-existing application-owned V24 request ledger row as evidence.
    request_rows = []
    request_rows.extend([x for x in chat.get("request_records", []) if isinstance(x, dict)])
    request_rows.extend([x for x in chat.get("request_ledger_v24", []) if isinstance(x, dict)])
    seen = set()
    for row in request_rows:
        rid = _s(row.get("request_id"))
        if not rid or rid in seen:
            continue
        seen.add(rid)
        bound_mid = _s(row.get("message_id"))
        if not bound_mid:
            bound_mid = next((_s(m.get("message_id")) for m in chat.get("message_ledger", [])
                              if isinstance(m, dict) and _s(m.get("request_id")) == rid), "")
        if not bound_mid:
            bound_mid = next((_s(m.get("id") or m.get("message_id")) for m in chat.get("messages", [])
                              if isinstance(m, dict) and str(m.get("role") or "").lower() == "user" and _s(m.get("request_id")) == rid), "")
        if not bound_mid:
            continue
        out = copy.deepcopy(row)
        out["request_id"] = rid
        out["message_id"] = bound_mid
        out.setdefault("conversation_id", _s(chat.get("conversation_id")))
        out.setdefault("session_id", _s(chat.get("session_id")))
        persist_identity(chat, session_state, request=out)

    # 4) Real HOTFIX145 Round records. Never synthesize a round_id.
    for row in chat.get("round_ledger", []):
        if isinstance(row, dict) and _s(row.get("round_id")) and _s(row.get("request_id")) and _s(row.get("message_id")):
            persist_identity(chat, session_state, round_row=row)


def hydrate_chat_identity(chat, session_state=None):
    bucket = get_authoritative_bucket(chat, session_state)
    if bucket is None:
        return chat

    # Hydration is additive and identity-preserving. Existing application-owned
    # records win only when they have the same identity; conflicts are retained.
    def merge(rows, incoming, keys):
        by_key = {tuple(_s(x.get(k)) for k in keys): x for x in rows if isinstance(x, dict)}
        for item in incoming:
            if not isinstance(item, dict):
                continue
            ident = tuple(_s(item.get(k)) for k in keys)
            if not all(ident):
                continue
            old = by_key.get(ident)
            if old is None:
                rows.append(copy.deepcopy(item))
                by_key[ident] = rows[-1]
            else:
                for k, v in item.items():
                    if v not in (None, "", [], {}):
                        old[k] = copy.deepcopy(v)
        return rows

    chat.setdefault("message_ledger", [])
    chat.setdefault("request_records", [])
    chat.setdefault("round_ledger", [])
    merge(chat["message_ledger"], bucket["messages"], ("message_id",))
    merge(chat["request_records"], bucket["requests"], ("request_id",))
    merge(chat["round_ledger"], bucket["rounds"], ("round_id",))
    return chat


def persistence_audit(chat, session_state):
    bucket = get_authoritative_bucket(chat, session_state) or {"messages": [], "requests": [], "rounds": []}
    return {
        "schema": SCHEMA,
        "source": "APPLICATION_OWNED_CANONICAL_CONVERSATION_PERSISTENCE",
        "conversation_id": _s(chat.get("conversation_id")) or "NOT_PROVEN",
        "persisted_message_count": len(bucket.get("messages", [])),
        "persisted_request_count": len(bucket.get("requests", [])),
        "persisted_round_count": len(bucket.get("rounds", [])),
    }

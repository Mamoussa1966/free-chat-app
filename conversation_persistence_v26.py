from __future__ import annotations
import copy

SCHEMA = "v26.3.2-authoritative-conversation-persistence/v3"
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
    """Canonical per-conversation persistence embedded in the active chat object.

    This is deliberately separate from Streamlit session_state: reruns/hydration may
    reconstruct session_state, but the canonical Conversation object must carry its
    historical Message→Request→Round chain with it.
    """
    cid = _s(chat.get("conversation_id"))
    if not cid:
        return None
    root = chat.setdefault("v26_3_conversation_persistence", {})
    if not isinstance(root, dict):
        root = {}
        chat["v26_3_conversation_persistence"] = root
    row = root.setdefault(cid, {"schema": SCHEMA, "conversation_id": cid, "messages": [], "requests": [], "rounds": []})
    for key in ("messages", "requests", "rounds"):
        if not isinstance(row.get(key), list):
            row[key] = []
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



def get_authoritative_bucket(chat, session_state):
    """Return canonical historical persistence; session_state is fallback mirror only."""
    canonical = _chat_bucket(chat)
    if canonical is not None and (canonical.get("messages") or canonical.get("requests") or canonical.get("rounds")):
        return canonical
    mirror = _bucket(ensure_persistence_store(session_state), chat.get("conversation_id"))
    if canonical is not None and mirror is not None:
        _merge_bucket(canonical, mirror)
        return canonical
    return canonical or {"schema": SCHEMA, "conversation_id": "", "messages": [], "requests": [], "rounds": []}


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
    ensure_persistence_store(session_state)
    _chat_bucket(chat)
    for row in chat.get("message_ledger", []):
        if isinstance(row, dict):
            persist_identity(chat, session_state, message=row)
    for row in chat.get("request_records", []):
        if isinstance(row, dict):
            persist_identity(chat, session_state, request=row)
    for row in chat.get("round_ledger", []):
        if isinstance(row, dict):
            persist_identity(chat, session_state, round_row=row)


def hydrate_chat_identity(chat, session_state):
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

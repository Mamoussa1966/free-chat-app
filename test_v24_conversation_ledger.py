from conversation_store import ensure_store, authoritative_snapshot
from message_ledger import record_message
from memory_layers import update_memory
from provenance_engine import record_result
from timeline_runtime import event
from conversation_migrations import migrate_chat


def chat():
    c={"id":"c1","conversation_id":"conv_1","session_id":"sess_1","created_at":"now","messages":[]}
    ensure_store(c); migrate_chat(c); return c


def test_two_messages_same_conversation_unique_message_ids():
    c=chat(); record_message(c,"m1","user","hello"); record_message(c,"m2","user","second")
    assert c["conversation_id"] == "conv_1"
    assert c["session_id"] == "sess_1"
    assert [x["message_id"] for x in c["message_ledger_v24"]] == ["m1","m2"]
    assert len({x["message_id"] for x in c["message_ledger_v24"]}) == 2


def test_provenance_is_application_owned_and_request_scoped():
    c=chat(); record_message(c,"m1","user","x")
    result={"request_id":"r1","name":"Gemini","seat":"gemini","status":"SUCCESS","executed_model":"gemini-x","runtime_execution_events":[{"attempt":1,"model":"gemini-x","status":"SUCCESS","classification":"SUCCESS","cascade_action":"SUCCESS"}]}
    rows=record_result(c,result,"m1","conv_1:r1:r1")
    assert len(rows)==1
    assert rows[0]["request_id"]=="r1"
    assert rows[0]["message_id"]=="m1"
    assert "api_key" not in str(rows).lower()


def test_memory_layers_keep_bridge_separate():
    c=chat(); update_memory(c,"m1","hello bridge text")
    assert c["memory_l0"]["message_id"]=="m1"
    assert "bridge_state" not in c["memory_l0"]
    assert "bridge_state" not in c["memory_l1"]


def test_authoritative_snapshot_has_separate_ledgers():
    c=chat(); record_message(c,"m1","user","hello"); event(c,"r1","m1","REQUEST_CREATED",status="REQUEST_CREATED")
    snap=authoritative_snapshot(c)
    assert snap["conversation_id"]=="conv_1"
    assert len(snap["messages"])==1
    assert len(snap["timeline"])==1

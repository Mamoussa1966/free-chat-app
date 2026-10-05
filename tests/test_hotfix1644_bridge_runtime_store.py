import main
from conversation_v25_runtime import authoritative_audit


def test_runtime_evidence_record_is_application_owned_and_provider_free():
    b = main.SharedContextBridge(request_id="req-1644", round_no=1, application_owned_test=True)
    tgt=type("Seat", (), {"room_slot": 2, "key":"gemini", "name":"Gemini"})()
    b.seed_application_state("BRIDGE_RESULT", "CANARY-1644", source="DeepSeek", source_seat=7)
    b.attest_source_execution(True, "APPLICATION_TEST_CONTROL")
    b.commit(tgt); b.barrier()
    b._record_bridge_event("SOURCE_EXECUTION", seat=7, provider="DeepSeek", status="SUCCESS")
    b._record_bridge_event("WRITE", seat=7, provider="DeepSeek", status="RECORDED")
    b._record_bridge_event("VALIDATE", seat=7, provider="DeepSeek", status="PASS")
    b._record_bridge_event("COMMIT", seat=7, provider="DeepSeek", status="PASS")
    b._record_bridge_event("BARRIER", seat=7, provider="Application", status="PASS")
    b._record_bridge_event("TARGET_DISPATCH", seat=2, provider="Gemini", status="ACCEPTED")
    b._record_bridge_event("TARGET_RESPONSE", seat=2, provider="Gemini", status="SUCCESS")
    b.read("BRIDGE_RESULT", tgt); b._record_bridge_event("READ", seat=2, provider="Application", status="PASS")
    b._record_bridge_event("MATCH", seat=2, provider="Application", status="PASS")
    b.seal_runtime_audit(user_prompt="safe")
    r=b.runtime_evidence_record()
    required={"request_id","round_id","bridge_id_hash","source_execution_proven","write_status","validate_status","commit_status","barrier_status","target_dispatch_status","target_response_status","read_status","schema_validation_status","match_status","user_prompt_contains_value","gemini_input_prompt_contains_value","runtime_http_payload_attested","runtime_http_payload_contains_value","runtime_http_payload_contains_bridge_key","gemini_received_sanitized_representation_only","terminal_state"}
    assert required <= set(r)
    assert r["request_id"] == "req-1644" and r["bridge_id"] == "[REDACTED]"


def test_final_audit_prefers_runtime_evidence_store_over_provider_output():
    chat={"conversation_id":"c","session_id":"s","conversation_record":{"messages":[{"message_id":"m1","request_id":"r1","role":"user"},{"message_id":"m2","request_id":"r2","role":"user"}],"requests":[{"request_id":"r1","message_id":"m1","canonical_round_base":1},{"request_id":"r2","message_id":"m2","canonical_round_base":2}],"rounds":[{"round_id":"c:r1:r1","message_id":"m1","request_id":"r1","round":1,"ordinal":1},{"round_id":"c:r2:r2","message_id":"m2","request_id":"r2","round":2,"ordinal":2}]},"request_records":[],"bridge_runtime_evidence_store":{"r1":{"bridge_id_hash":"h1","write_status":"PASS","terminal_state":"COMMITTED"},"r2":{"bridge_id_hash":"h2","write_status":"PASS","terminal_state":"COMMITTED"}}}
    session={"v26_3_canonical_conversation_store":{"c":{"record":dict(chat["conversation_record"]),"history_hash":"h","revision":1}}}
    a=authoritative_audit(chat, session)
    assert a["bridge_evidence_source"] == "APPLICATION_OWNED_BRIDGE_RUNTIME_EVIDENCE_STORE"
    assert a["bridge_lifecycle_message_1"]["bridge_id_hash"] == "h1"
    assert a["bridge_lifecycle_message_2"]["bridge_id_hash"] == "h2"

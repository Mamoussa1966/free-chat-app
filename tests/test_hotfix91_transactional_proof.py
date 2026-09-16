from main import SharedContextBridge

class Seat:
    def __init__(self, key, room_slot, name):
        self.key=key; self.room_slot=room_slot; self.name=name

def result(seat, content):
    return {"status":"SUCCESS","seat":seat.key,"model":"m","executed_model":"m","content":content,"round":1}

def test_hotfix91_transactional_proof_audit_redacts_values_and_proves_path():
    ds=Seat("deepseek",7,"DeepSeek"); ge=Seat("gemini",2,"Gemini")
    b=SharedContextBridge(request_id="req-91", round_no=1)
    user="HOTFIX91 BRIDGE TRANSACTION TEST"
    b.record_provider_input(ds, user)
    value="X9pLm2Qa7Vr4Ts8Z"
    b.append_agent_output(ds, result(ds, f"BRIDGE_WRITE: BRIDGE_RESULT = {value}"))
    b.commit(ge); b.barrier()
    gp=b.prompt_snapshot(ge); b.record_provider_input(ge,gp)
    assert value not in gp
    resolution=b.consume_read_requests(ge, result(ge,"BRIDGE_READ: BRIDGE_RESULT"))
    assert resolution["status"]=="RESOLVED"
    audit=b.transaction_audit(user_prompt=user)
    assert audit["WRITE"]=="PASS"
    assert audit["VALIDATE"]=="PASS"
    assert audit["COMMIT"]=="PASS"
    assert audit["BARRIER"]=="PASS"
    assert audit["READ"]=="PASS"
    assert audit["SCHEMA_VALIDATION"]=="PASS"
    assert audit["MATCH"]=="PASS"
    assert audit["USER_PROMPT_CONTAINS_VALUE"]=="NO"
    assert audit["GEMINI_INPUT_PROMPT_CONTAINS_VALUE"]=="NO"
    assert audit["BRIDGE_STATE_CONTAINS_VALUE"]=="YES"
    assert audit["SOURCE_VALUE"]=="[REDACTED]" and audit["TARGET_VALUE"]=="[REDACTED]"
    assert audit["SOURCE"]=="DeepSeek / Seat 7" and audit["TARGET"]=="Gemini / Seat 2"

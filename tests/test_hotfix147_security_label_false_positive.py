from production_platform import security_audit, conversation_persistence_audit


def test_security_does_not_treat_audit_label_in_user_prose_as_raw_payload():
    chat = {"messages": [{"role": "user", "content": "NO_RAW_PROVIDER_PAYLOADS_IN_HISTORY"}]}
    report = security_audit([chat])
    assert report["status"] == "PASS"
    assert report["checks"]["NO_RAW_PROVIDER_PAYLOADS_IN_HISTORY"] is True


def test_persistence_does_not_treat_audit_label_in_user_prose_as_raw_payload():
    chat = {"id": "c", "messages": [{"role": "user", "content": "NO_RAW_PROVIDER_PAYLOADS_IN_HISTORY"}], "request_records": []}
    report = conversation_persistence_audit(chat, "")
    assert report["forbidden_data"]["RAW_PROVIDER_PAYLOADS"] is False
    assert report["forbidden_data"]["SENSITIVE_DIAGNOSTICS"] is False

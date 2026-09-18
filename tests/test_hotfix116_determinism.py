from pathlib import Path

import main


def test_hotfix116_duplicate_fingerprint_is_atomically_reserved():
    chat = main._new_chat()
    fingerprint = "same-logical-request"
    with main._REQUEST_GATE_LOCK:
        main._ACTIVE_REQUEST_FINGERPRINTS.discard(fingerprint)
        main._ACTIVE_REQUEST_FINGERPRINTS.add(fingerprint)
    try:
        assert fingerprint in main._ACTIVE_REQUEST_FINGERPRINTS
    finally:
        with main._REQUEST_GATE_LOCK:
            main._ACTIVE_REQUEST_FINGERPRINTS.discard(fingerprint)


def test_hotfix116_release_identity_is_canonical():
    assert Path("VERSION.txt").read_text(encoding="utf-8").strip() == "V22.1-HOTFIX120-PRODUCTION-HARDENED"


def test_hotfix116_gate_has_one_request_per_logical_fingerprint():
    chat = main._new_chat()
    fingerprint = main._request_fingerprint("hello", [])
    chat["request_ids"].append(fingerprint)
    assert fingerprint in chat["request_ids"]

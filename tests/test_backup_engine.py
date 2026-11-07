from __future__ import annotations

import copy
import hashlib
import json

import pytest

from backup_engine import (
    BACKUP_SCHEMA,
    build_conversation_backup,
    serialize_conversation_backup,
    verify_conversation_backup,
)


def _chat(conversation_id: str = "conversation-1") -> dict:
    message = {
        "message_id": "message-1",
        "conversation_id": conversation_id,
        "session_id": "session-1",
        "role": "user",
        "request_id": "request-1",
        "created_at": "2026-11-06T00:00:00Z",
        "content": "hello from the canonical conversation",
    }
    request = {
        "request_id": "request-1",
        "conversation_id": conversation_id,
        "session_id": "session-1",
        "message_id": "message-1",
        "created_at": "2026-11-06T00:00:00Z",
        "state": "COMPLETED",
    }
    round_record = {
        "round_id": "round-1",
        "conversation_id": conversation_id,
        "session_id": "session-1",
        "message_id": "message-1",
        "request_id": "request-1",
        "round": 1,
        "created_at": "2026-11-06T00:00:01Z",
        "status": "COMPLETED",
    }
    return {
        "id": conversation_id,
        "conversation_id": conversation_id,
        "session_id": "session-1",
        "title": "QA Conversation",
        "messages": [{"role": "user", "content": "hello from the canonical conversation"}],
        "conversation_record": {
            "conversation_id": conversation_id,
            "session_id": "session-1",
            "messages": [message],
            "requests": [request],
            "rounds": [round_record],
        },
        "message_ledger_v24": [message],
        "request_ledger_v24": [request],
        "round_ledger_v24": [round_record],
        "bridge_ledger_v24": [],
        "result_ledger_v24": [],
        "provenance_ledger_v24": [],
        "timeline_ledger_v24": [],
        "api_key_setting": "NOT_FOR_EXPORT",
        "voice_audio_store": {"pending": b"binary voice bytes"},
    }


def test_backup_bundle_contains_canonical_history_and_sha256_integrity():
    document = build_conversation_backup(
        [_chat()],
        source="test",
        exported_at="2026-11-06T10:00:00Z",
    )

    assert document["schema"] == BACKUP_SCHEMA
    assert document["conversation_count"] == 1
    assert document["conversations"][0]["conversation_id"] == "conversation-1"
    assert document["conversations"][0]["canonical_history_sha256"]
    assert document["media"]["binary_attachments_included"] is False
    assert document["media"]["voice_recording_blobs_included"] is False
    assert document["restore"]["automatic_restore_supported"] is False
    assert verify_conversation_backup(document) is True


def test_backup_checksum_detects_content_tampering():
    document = build_conversation_backup([_chat()])
    document["conversations"][0]["snapshot"]["canonical_conversation_record"]["messages"][0]["content"] = "tampered"

    assert verify_conversation_backup(document) is False


def test_backup_does_not_mutate_the_live_chat_or_include_unrelated_secrets_and_binary_state():
    chat = _chat()
    original = copy.deepcopy(chat)
    document = build_conversation_backup([chat])
    serialized = serialize_conversation_backup(document)

    assert chat == original
    assert "NOT_FOR_EXPORT" not in serialized
    assert "binary voice bytes" not in serialized
    assert "api_key_setting" not in serialized
    assert document["secrets"]["provider_credentials_from_application_settings_included"] is False
    assert document["secrets"]["user_entered_sensitive_text_may_be_present"] is True


def test_backup_serialization_is_utf8_json_and_integrity_verifies_after_round_trip():
    document = build_conversation_backup([_chat()])
    payload = serialize_conversation_backup(document)
    loaded = json.loads(payload)

    assert loaded["schema"] == BACKUP_SCHEMA
    assert verify_conversation_backup(loaded) is True
    assert hashlib.sha256(
        json.dumps(
            {key: value for key, value in loaded.items() if key != "integrity"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest() == loaded["integrity"]["payload_sha256"]


def test_backup_preserves_the_sanitized_presentation_state_supplied_by_supabase():
    chat = _chat()
    chat["_backup_presentation_state"] = {
        "title": "Saved title",
        "request_ids": ["request-1"],
        "history_identity_ledger": [{"request_id": "request-1", "status": "COMPLETED"}],
        "result_keys": ["request-1:gemini"],
        "bridge_ledger_v24": [],
    }

    document = build_conversation_backup([chat])
    exported = document["conversations"][0]["stored_presentation_state"]

    assert exported["title"] == "Saved title"
    assert exported["request_ids"] == ["request-1"]
    assert exported["result_keys"] == ["request-1:gemini"]
    assert exported["bridge_ledger_v24"] == []
    assert verify_conversation_backup(document) is True


def test_backup_marks_possible_truncation_at_the_repository_row_limit():
    document = build_conversation_backup(
        [_chat()],
        possible_truncation=True,
    )
    assert document["limits"]["maximum_conversations_per_export"] == 500
    assert document["limits"]["possible_truncation"] is True


def test_backup_rejects_duplicate_conversation_ids():
    with pytest.raises(ValueError, match="duplicate conversation_id"):
        build_conversation_backup([_chat("same"), _chat("same")])


def test_backup_rejects_a_missing_canonical_conversation_id():
    chat = _chat()
    chat["conversation_id"] = ""
    with pytest.raises(ValueError, match="conversation_id"):
        build_conversation_backup([chat])


def test_backup_rejects_more_than_the_documented_row_limit_before_export():
    chats = [{}] * 501
    with pytest.raises(ValueError, match="500 conversations"):
        build_conversation_backup(chats)

from __future__ import annotations

from types import SimpleNamespace

import main


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def _install_state(monkeypatch, values):
    state = SessionState(values)
    monkeypatch.setattr(main, "st", SimpleNamespace(session_state=state))
    return state


def test_deleting_one_conversation_removes_its_audio_and_orphans_but_keeps_other_chats(monkeypatch):
    state = _install_state(monkeypatch, {
        "chats": [
            {
                "id": "chat-b",
                "messages": [{"id": "voice-b", "voice": True}],
            }
        ],
        "voice_audio_store": {
            "voice-a": b"deleted-chat-a-audio",
            "voice-b": b"keep-chat-b-audio",
            "orphan": b"orphaned-audio",
        },
        "voice_fingerprints": {"chat-a": "fingerprint-a", "chat-b": "fingerprint-b"},
        "last_voice_transcription": {"chat_id": "chat-a", "text": "old transcript"},
        "pending_voice_recording": {"chat_id": "chat-a", "audio_bytes": b"pending-a"},
        "last_voice_error": "old error",
        "voice_nonce": 4,
    })

    main._cleanup_voice_media_after_chat_delete([{"id": "chat-a"}])

    assert state["voice_audio_store"] == {"voice-b": b"keep-chat-b-audio"}
    assert state["voice_fingerprints"] == {"chat-b": "fingerprint-b"}
    assert state["last_voice_transcription"] == {}
    assert state["pending_voice_recording"] == {}
    assert state["last_voice_error"] == ""
    assert state["voice_nonce"] == 5


def test_deleting_another_conversation_preserves_unrelated_pending_voice_state(monkeypatch):
    state = _install_state(monkeypatch, {
        "chats": [
            {
                "id": "chat-b",
                "messages": [{"id": "voice-b", "voice": True}],
            }
        ],
        "voice_audio_store": {"voice-b": b"keep-chat-b-audio"},
        "voice_fingerprints": {"chat-a": "fingerprint-a", "chat-b": "fingerprint-b"},
        "last_voice_transcription": {"chat_id": "chat-b", "text": "keep transcript"},
        "pending_voice_recording": {"chat_id": "chat-b", "audio_bytes": b"pending-b"},
        "last_voice_error": "old error",
        "voice_nonce": 8,
    })

    main._cleanup_voice_media_after_chat_delete([{"id": "chat-a"}])

    assert state["voice_audio_store"] == {"voice-b": b"keep-chat-b-audio"}
    assert state["voice_fingerprints"] == {"chat-b": "fingerprint-b"}
    assert state["last_voice_transcription"] == {"chat_id": "chat-b", "text": "keep transcript"}
    assert state["pending_voice_recording"] == {"chat_id": "chat-b", "audio_bytes": b"pending-b"}
    assert state["last_voice_error"] == ""
    assert state["voice_nonce"] == 9


def test_clear_all_removes_every_voice_blob_and_recorder_state(monkeypatch):
    state = _install_state(monkeypatch, {
        "chats": [{"id": "fresh-chat", "messages": []}],
        "voice_audio_store": {"voice-a": b"audio-a", "voice-b": b"audio-b"},
        "voice_fingerprints": {"chat-a": "a", "chat-b": "b"},
        "last_voice_transcription": {"chat_id": "chat-a", "text": "old transcript"},
        "pending_voice_recording": {"chat_id": "chat-b", "audio_bytes": b"pending"},
        "last_voice_error": "old error",
        "voice_nonce": 11,
    })

    main._cleanup_voice_media_after_chat_delete(
        [{"id": "chat-a"}, {"id": "chat-b"}],
        clear_all=True,
    )

    assert state["voice_audio_store"] == {}
    assert state["voice_fingerprints"] == {}
    assert state["last_voice_transcription"] == {}
    assert state["pending_voice_recording"] == {}
    assert state["last_voice_error"] == ""
    assert state["voice_nonce"] == 12

from main import _clear_voice_state_for_chats


def test_deleting_one_chat_clears_its_audio_but_preserves_other_chats():
    state = {
        "voice_audio_store": {"msg-a": b"audio-a", "msg-b": b"audio-b"},
        "voice_fingerprints": {"chat-a": {"fingerprint-a"}, "chat-b": {"fingerprint-b"}},
        "voice_nonce": 4,
        "last_voice_transcription": {"chat_id": "chat-a", "text": "old transcript"},
        "last_voice_error": "old error",
    }
    chats = [
        {
            "id": "chat-a",
            "messages": [
                {"id": "msg-a", "voice": True, "voice_audio_key": "msg-a"},
            ],
        }
    ]

    deleted_keys = _clear_voice_state_for_chats(chats, state)

    assert deleted_keys == {"msg-a"}
    assert state["voice_audio_store"] == {"msg-b": b"audio-b"}
    assert state["voice_fingerprints"] == {"chat-b": {"fingerprint-b"}}
    assert state["voice_nonce"] == 5
    assert state["last_voice_transcription"] == {}
    assert state["last_voice_error"] == ""


def test_deleting_chat_resets_unsent_audio_input_preview():
    # A recording in st.audio_input is not in voice_audio_store until submitted.
    state = {
        "voice_audio_store": {},
        "voice_fingerprints": {},
        "voice_nonce": 2,
        "last_voice_transcription": {},
        "last_voice_error": "",
    }

    _clear_voice_state_for_chats([{"id": "chat-a", "messages": []}], state)

    assert state["voice_audio_store"] == {}
    assert state["voice_nonce"] == 3


def test_clearing_all_chats_removes_all_message_linked_voice_audio():
    state = {
        "voice_audio_store": {"msg-a": b"audio-a", "msg-b": b"audio-b"},
        "voice_fingerprints": {"chat-a": {"a"}, "chat-b": {"b"}},
        "voice_nonce": 0,
        "last_voice_transcription": {"chat_id": "chat-b", "text": "transcript"},
        "last_voice_error": "old error",
    }
    chats = [
        {"id": "chat-a", "messages": [{"id": "msg-a", "voice": True}]},
        {"id": "chat-b", "messages": [{"id": "msg-b", "voice": True}]},
    ]

    _clear_voice_state_for_chats(chats, state)

    assert state["voice_audio_store"] == {}
    assert state["voice_fingerprints"] == {}
    assert state["voice_nonce"] == 1
    assert state["last_voice_transcription"] == {}
    assert state["last_voice_error"] == ""

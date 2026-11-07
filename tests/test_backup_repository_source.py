from __future__ import annotations

from types import SimpleNamespace

import pytest

import main
from conversation_repository import AccountIdentity, OwnedConversationSnapshot, ConversationRepositoryError


OWNER = AccountIdentity(
    issuer="https://backup-test.supabase.co/auth/v1",
    subject="00000000-0000-4000-8000-000000000001",
)
OTHER_OWNER = AccountIdentity(
    issuer="https://backup-test.supabase.co/auth/v1",
    subject="00000000-0000-4000-8000-000000000002",
)


def _snapshot(conversation_id: str, owner: AccountIdentity = OWNER):
    return OwnedConversationSnapshot(
        owner,
        {
            "conversation_id": conversation_id,
            "session_id": f"session-{conversation_id}",
            "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
            "messages": [],
            "requests": [],
            "rounds": [],
            "_streamlit_state": {
                "title": f"Title {conversation_id}",
                "created_at": "2026-11-06T00:00:00Z",
                "messages": [{"role": "user", "content": "private conversation text"}],
                "request_records": [{"request_id": f"request-{conversation_id}"}],
                "request_ids": [f"request-{conversation_id}"],
                "history_identity_ledger": [{"message_id": f"message-{conversation_id}"}],
                "result_keys": [f"result-{conversation_id}"],
                "bridge_ledger_v24": [],
            },
        },
    )


class ReadOnlyRepository:
    def __init__(self, owner, rows):
        self.owner = owner
        self.rows = rows
        self.list_calls = []
        self.load_calls = []
        self.write_calls = []

    def list_ids(self, owner, *, limit):
        self.list_calls.append((owner, limit))
        assert owner == self.owner
        return [snapshot.conversation_id for snapshot in self.rows][:limit]

    def load(self, owner, conversation_id):
        self.load_calls.append((owner, conversation_id))
        assert owner == self.owner
        return next(
            (row for row in self.rows if row.conversation_id == conversation_id),
            None,
        )


def _enable_supabase(monkeypatch, repo, *, authenticated=True):
    monkeypatch.setattr(main, "get_supabase_config", lambda _st: ("https://backup-test.supabase.co", "publishable", True))
    monkeypatch.setattr(main, "is_supabase_auth_active", lambda _st: authenticated)
    monkeypatch.setattr(main, "_supabase_identity_and_repository", lambda: (OWNER, repo))


def test_remote_backup_reads_only_the_current_owner_and_preserves_sanitized_view(monkeypatch):
    repository = ReadOnlyRepository(OWNER, [_snapshot("conversation-1")])
    _enable_supabase(monkeypatch, repository)

    chats, source, truncated = main._collect_conversation_backup_source()

    assert source == "supabase_authenticated_owner"
    assert truncated is False
    assert [chat["conversation_id"] for chat in chats] == ["conversation-1"]
    assert chats[0]["_backup_presentation_state"]["request_ids"] == ["request-conversation-1"]
    assert chats[0]["_backup_presentation_state"]["result_keys"] == ["result-conversation-1"]
    assert repository.list_calls == [(OWNER, main.MAX_BACKUP_CONVERSATIONS)]
    assert repository.load_calls == [(OWNER, "conversation-1")]
    assert repository.write_calls == []


def test_remote_backup_fails_closed_when_any_row_is_not_owned_by_the_current_user(monkeypatch):
    repository = ReadOnlyRepository(OWNER, [_snapshot("foreign-conversation", OTHER_OWNER)])
    _enable_supabase(monkeypatch, repository)

    with pytest.raises(ConversationRepositoryError, match="التحقق من ملكية"):
        main._collect_conversation_backup_source()

    assert repository.load_calls == [(OWNER, "foreign-conversation")]
    assert repository.write_calls == []


def test_remote_backup_requires_a_verified_authenticated_session(monkeypatch):
    repository = ReadOnlyRepository(OWNER, [_snapshot("conversation-1")])
    _enable_supabase(monkeypatch, repository, authenticated=False)

    with pytest.raises(ConversationRepositoryError, match="تسجيل الدخول"):
        main._collect_conversation_backup_source()

    assert repository.list_calls == []
    assert repository.load_calls == []


def test_remote_backup_marks_the_configured_row_limit_as_possibly_truncated(monkeypatch):
    monkeypatch.setattr(main, "MAX_BACKUP_CONVERSATIONS", 2)
    repository = ReadOnlyRepository(
        OWNER,
        [_snapshot("conversation-1"), _snapshot("conversation-2")],
    )
    _enable_supabase(monkeypatch, repository)

    chats, source, truncated = main._collect_conversation_backup_source()

    assert len(chats) == 2
    assert source == "supabase_authenticated_owner"
    assert truncated is True
    assert repository.list_calls == [(OWNER, 2)]


def test_backup_ui_discloses_remote_or_session_only_source():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "مصدر النسخة: سجلات Supabase المملوكة للحساب المسجّل دخوله." in source
    assert "ذاكرة الجلسة الحالية فقط؛ هذه ليست نسخة سحابية دائمة" in source


def test_backup_restore_ui_warns_that_sha256_is_not_source_authentication():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "لا تثبت هوية مصدره" in source
    assert "مصدر موثوق" in source


def test_local_backup_source_is_a_defensive_copy_and_is_labeled_as_session_only(monkeypatch):
    chat = {
        "conversation_id": "local-conversation",
        "messages": [{"role": "user", "content": "current session only"}],
    }
    fake_streamlit = SimpleNamespace(session_state={"chats": [chat]})
    monkeypatch.setattr(main, "st", fake_streamlit)
    monkeypatch.setattr(main, "get_supabase_config", lambda _st: ("", "", False))

    chats, source, truncated = main._collect_conversation_backup_source()

    assert source == "streamlit_session_cache"
    assert truncated is False
    assert chats[0]["conversation_id"] == chat["conversation_id"]
    assert chats[0] is not chat
    assert chats[0]["messages"] is not chat["messages"]
    assert chats[0]["_backup_presentation_state"]["messages"] == chat["messages"]
    assert "_backup_presentation_state" not in chat

def test_backup_restore_ui_explains_auth_and_rls_database_storage():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "restore_supabase_auth_enabled" in source
    assert "ستُدرج المحادثات في جدول قاعدة البيانات مع تطبيق سياسات RLS" in source
    assert "يلزم تفعيل Supabase Storage" not in source


"""Private, file-backed adapter for the canonical conversation repository.

This adapter is a real local-filesystem implementation for staged validation.
It is deliberately NOT wired into the Streamlit app and is NOT a claim of
production durability: host-local files may be ephemeral and are not a
replacement for a database with durable volumes, backups, and server-side
authorization policies. The caller must construct AccountIdentity only after
verifying the identity-provider result.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import threading
from contextlib import contextmanager
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - production hosting target is POSIX/Linux
    fcntl = None  # type: ignore[assignment]

from conversation_repository import (
    AccountIdentity,
    ConversationIdentityConflict,
    ConversationOwnershipError,
    ConversationRepositoryError,
    OwnedConversationSnapshot,
)

FILE_REPOSITORY_SCHEMA = "ai-council-file-conversation-repository/v1"
_ID_FIELDS = {
    "messages": ("message_id", ("conversation_id", "session_id", "role", "request_id", "created_at")),
    "requests": ("request_id", ("conversation_id", "session_id", "message_id")),
    "rounds": ("round_id", ("conversation_id", "session_id", "message_id", "request_id", "round")),
}
_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _thread_lock_for(lock_path: Path) -> threading.RLock:
    key = str(lock_path)
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[key] = lock
        return lock


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _identity_rows(record: dict, collection: str, id_field: str, fields: tuple[str, ...]) -> dict[str, tuple]:
    rows: dict[str, tuple] = {}
    for row in record.get(collection, []):
        if not isinstance(row, dict):
            raise ConversationRepositoryError("canonical identity record is malformed")
        identity = str(row.get(id_field) or "").strip()
        if identity:
            rows[identity] = tuple(row.get(field) for field in fields)
    return rows


def _assert_identity_history_preserved(
    previous: dict, candidate: dict
) -> None:
    for collection, (id_field, fields) in _ID_FIELDS.items():
        old_rows = _identity_rows(previous, collection, id_field, fields)
        new_rows = _identity_rows(candidate, collection, id_field, fields)
        if not set(old_rows).issubset(new_rows):
            raise ConversationIdentityConflict(
                f"canonical {collection} history cannot be silently removed"
            )
        if any(new_rows[identity] != values for identity, values in old_rows.items()):
            raise ConversationIdentityConflict(
                f"canonical {collection} identity binding cannot be rewritten"
            )


def _owner_payload(owner: AccountIdentity) -> dict[str, str]:
    return {"issuer": owner.issuer, "subject": owner.subject}


def _payload_without_checksum(
    owner: AccountIdentity, conversation_id: str, canonical_record: dict
) -> dict:
    return {
        "schema": FILE_REPOSITORY_SCHEMA,
        "conversation_id": conversation_id,
        "owner": _owner_payload(owner),
        "canonical_record": canonical_record,
    }


def _checksum(payload: dict) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class FileConversationRepository:
    """Atomic local-file adapter implementing ConversationRepository.

    Each conversation is stored in a SHA-256-named JSON file (never a
    user-controlled path). Writes use a temporary file plus atomic replace,
    flush/fsync, owner and canonical-history checks, and a POSIX advisory lock
    shared across threads and processes using the same repository directory.
    Files are private to the current OS user (directory mode 0700, files 0600).

    This is suitable for adapter/contract verification or an explicitly
    persistent local volume. It is not safe to treat an ephemeral app filesystem
    as cross-restart storage, and it does not provide encryption at rest,
    replication, backups, or multi-host transactions.
    """

    def __init__(self, data_dir: str | os.PathLike[str]) -> None:
        if fcntl is None:
            raise ConversationRepositoryError(
                "file repository requires POSIX advisory file locking"
            )
        raw_root = Path(data_dir).expanduser()
        if raw_root.is_symlink():
            raise ConversationRepositoryError("repository directory must not be a symlink")
        try:
            raw_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if raw_root.is_symlink() or not raw_root.is_dir():
                raise ConversationRepositoryError("repository path must be a real directory")
            # data_dir is expected to be a dedicated, app-owned directory.
            os.chmod(raw_root, 0o700)
            self._root = raw_root.resolve(strict=True)
            self._lock_path = self._root / ".repository.lock"
            lock_fd = os.open(
                self._lock_path,
                os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            try:
                os.fchmod(lock_fd, 0o600)
            finally:
                os.close(lock_fd)
        except ConversationRepositoryError:
            raise
        except OSError as exc:
            raise ConversationRepositoryError("repository directory is not available") from exc
        self._thread_lock = _thread_lock_for(self._lock_path)

    @staticmethod
    def _validate_owner(owner: AccountIdentity) -> None:
        if not isinstance(owner, AccountIdentity):
            raise ValueError("owner must be an AccountIdentity from a verified identity flow")

    @staticmethod
    def _validate_conversation_id(conversation_id: str) -> str:
        if not isinstance(conversation_id, str):
            raise ValueError("conversation_id must be a string")
        value = conversation_id.strip()
        if not value or len(value) > 1024 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("conversation_id is invalid")
        return value

    def _path_for(self, conversation_id: str) -> Path:
        digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()
        return self._root / f"{digest}.json"

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        if fcntl is None:  # defensive if monkeypatched/unavailable at runtime
            raise ConversationRepositoryError("repository locking is unavailable")
        with self._thread_lock:
            try:
                fd = os.open(
                    self._lock_path,
                    os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                )
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                    yield
                finally:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    finally:
                        os.close(fd)
            except ConversationRepositoryError:
                raise
            except OSError as exc:
                raise ConversationRepositoryError("repository lock could not be acquired") from exc

    def _read_file(self, path: Path, expected_id: str | None = None) -> OwnedConversationSnapshot | None:
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file():
            raise ConversationRepositoryError("stored conversation record is not a regular file")
        try:
            raw = path.read_text(encoding="utf-8")
            envelope = json.loads(raw)
            if not isinstance(envelope, dict) or envelope.get("schema") != FILE_REPOSITORY_SCHEMA:
                raise ValueError("unsupported record schema")
            conversation_id = self._validate_conversation_id(envelope.get("conversation_id"))
            if expected_id is not None and conversation_id != expected_id:
                raise ValueError("record identifier does not match its storage key")
            if path != self._path_for(conversation_id):
                raise ValueError("record is stored under an invalid key")
            owner_payload = envelope.get("owner")
            if not isinstance(owner_payload, dict):
                raise ValueError("owner envelope is invalid")
            owner = AccountIdentity(owner_payload.get("issuer"), owner_payload.get("subject"))
            record = envelope.get("canonical_record")
            if not isinstance(record, dict):
                raise ValueError("canonical record is invalid")
            expected_checksum = _checksum(
                _payload_without_checksum(owner, conversation_id, record)
            )
            actual_checksum = envelope.get("checksum")
            if not isinstance(actual_checksum, str) or not hmac.compare_digest(
                expected_checksum, actual_checksum
            ):
                raise ValueError("record checksum mismatch")
            snapshot = OwnedConversationSnapshot(owner, record)
            if snapshot.conversation_id != conversation_id:
                raise ValueError("canonical conversation identity mismatch")
            return snapshot
        except ConversationRepositoryError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ConversationRepositoryError("stored conversation record is invalid or unreadable") from exc

    def _write_atomic(self, path: Path, snapshot: OwnedConversationSnapshot) -> None:
        record = snapshot.canonical_record
        payload = _payload_without_checksum(snapshot.owner, snapshot.conversation_id, record)
        envelope = dict(payload)
        envelope["checksum"] = _checksum(payload)
        encoded = (_canonical_json(envelope) + "\n").encode("utf-8")
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".tmp-", suffix=".json", dir=self._root, delete=False
            ) as temp:
                temp_name = temp.name
                os.chmod(temp_name, 0o600)
                temp.write(encoded)
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(temp_name, path)
            temp_name = None
            directory_fd = os.open(self._root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise ConversationRepositoryError("conversation snapshot could not be committed") from exc
        finally:
            if temp_name:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass

    def save(self, snapshot: OwnedConversationSnapshot) -> None:
        if not isinstance(snapshot, OwnedConversationSnapshot):
            raise ValueError("snapshot must be an OwnedConversationSnapshot")
        self._validate_owner(snapshot.owner)
        conversation_id = self._validate_conversation_id(snapshot.conversation_id)
        if conversation_id != snapshot.conversation_id:
            raise ValueError("snapshot conversation_id must already be normalized")
        path = self._path_for(conversation_id)
        with self._exclusive_lock():
            existing = self._read_file(path, expected_id=conversation_id)
            if existing is not None:
                if existing.owner != snapshot.owner:
                    raise ConversationOwnershipError("conversation owner mismatch")
                previous_record = existing.canonical_record
                candidate_record = snapshot.canonical_record
                _assert_identity_history_preserved(previous_record, candidate_record)
                if previous_record == candidate_record:
                    return
            self._write_atomic(path, snapshot)

    def load(self, owner: AccountIdentity, conversation_id: str) -> OwnedConversationSnapshot | None:
        self._validate_owner(owner)
        conversation_id = self._validate_conversation_id(conversation_id)
        with self._exclusive_lock():
            snapshot = self._read_file(self._path_for(conversation_id), expected_id=conversation_id)
            if snapshot is None or snapshot.owner != owner:
                return None
            return OwnedConversationSnapshot(snapshot.owner, snapshot.canonical_record)

    def list_ids(self, owner: AccountIdentity, *, limit: int = 50) -> list[str]:
        self._validate_owner(owner)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")
        with self._exclusive_lock():
            owned: list[str] = []
            try:
                paths = sorted(self._root.glob("*.json"))
            except OSError as exc:
                raise ConversationRepositoryError("conversation records could not be listed") from exc
            for path in paths:
                snapshot = self._read_file(path)
                if snapshot is not None and snapshot.owner == owner:
                    owned.append(snapshot.conversation_id)
            return sorted(owned)[:limit]

    def delete(self, owner: AccountIdentity, conversation_id: str) -> bool:
        self._validate_owner(owner)
        conversation_id = self._validate_conversation_id(conversation_id)
        path = self._path_for(conversation_id)
        with self._exclusive_lock():
            snapshot = self._read_file(path, expected_id=conversation_id)
            if snapshot is None or snapshot.owner != owner:
                return False
            try:
                path.unlink()
                directory_fd = os.open(self._root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError as exc:
                raise ConversationRepositoryError("conversation snapshot could not be deleted") from exc
            return True

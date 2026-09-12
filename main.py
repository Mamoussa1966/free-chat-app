from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import html
import json
import re
import time
import uuid

import streamlit as st
from streamlit.components.v1 import html as components_html

from attachment_utils import normalize_uploaded_files, public_metadata
from providers import SEATS, VERSION as PROVIDER_VERSION, call_seat, capture_credentials, capture_model_candidates, configured_count, diagnostic_seat, model_config_fingerprint, model_config_sources, transcribe_audio_gemini

APP_VERSION = PROVIDER_VERSION
MAX_VOICE_BYTES = 8 * 1024 * 1024
MAX_STORED_VOICE_ITEMS = 10
MAX_STORED_VOICE_BYTES = 40 * 1024 * 1024
MAX_ROUNDS = 4
MAX_EXECUTION_SECONDS = 180
MAX_PROMPT_CHARS = 20_000
MAX_CHAT_MESSAGES = 200
MAX_REQUEST_IDS = 50
MAX_WORKERS = 5
ERROR_DISPLAY_TTL_SECONDS = 60


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _new_chat() -> dict:
    return {
        "id": uuid.uuid4().hex,
        "title": "محادثة جديدة",
        "created_at": _now(),
        "messages": [],
        "request_ids": [],
        "request_records": [],
        "history_identity_ledger": [],
        "result_keys": [],
    }


def _ensure_chat_identity_state(chat: dict) -> None:
    chat.setdefault("request_ids", [])
    chat.setdefault("request_records", [])
    chat.setdefault("history_identity_ledger", [])
    chat.setdefault("result_keys", [])


def _request_display_number(chat: dict, request_id: str) -> int | None:
    _ensure_chat_identity_state(chat)
    for index, record in enumerate(chat.get("request_records", []), start=1):
        if isinstance(record, dict) and record.get("request_id") == request_id:
            return index
    return None


def _history_identity_keys(chat: dict) -> set[tuple[str, int, str]]:
    _ensure_chat_identity_state(chat)
    keys: set[tuple[str, int, str]] = set()
    for raw in chat.get("history_identity_ledger", []):
        if isinstance(raw, (list, tuple)) and len(raw) == 3:
            try:
                request_id, round_no, seat_key = str(raw[0]).strip(), int(raw[1]), str(raw[2]).strip()
            except (TypeError, ValueError):
                continue
            if request_id and round_no > 0 and seat_key:
                keys.add((request_id, round_no, seat_key))
    # Backward-compatible reconstruction for histories created before the ledger existed.
    for message in chat.get("messages", []):
        if message.get("role") != "assistant":
            continue
        request_id = str(message.get("request_id") or "").strip()
        seat = str(message.get("seat_key") or "").strip()
        if not seat:
            seat = next((str(s.key) for s in SEATS if s.name == message.get("seat")), "")
        try:
            round_no = int(message.get("round"))
        except (TypeError, ValueError):
            continue
        if request_id and seat and round_no > 0:
            keys.add((request_id, round_no, seat))
    return keys


def _assert_unique_history_identity(chat: dict, request_id: str, round_no: int, seat_key: str) -> None:
    request_id = str(request_id).strip()
    seat_key = str(seat_key).strip()
    try:
        round_no = int(round_no)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid history identity round: {round_no!r}") from exc
    if not request_id or round_no <= 0 or not seat_key:
        raise RuntimeError(
            f"Invalid history identity: request_id={request_id!r}, round={round_no!r}, seat={seat_key!r}"
        )
    key = (request_id, round_no, seat_key)
    existing = _history_identity_keys(chat)
    if key in existing:
        raise RuntimeError(f"Duplicate history identity invariant: {key!r}")
    chat["history_identity_ledger"].append([request_id, round_no, seat_key])


def _init_state() -> None:
    defaults = {"rounds": 1, "folder_nonce": 0, "voice_nonce": 0, "last_results": [], "last_diagnostics": [], "voice_fingerprints": {}, "voice_audio_store": {}, "last_voice_error": ""}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if "chats" not in st.session_state or not isinstance(st.session_state.chats, list):
        chat = _new_chat()
        st.session_state.chats = [chat]
        st.session_state.active_chat_id = chat["id"]


def _active_chat() -> dict:
    for chat in st.session_state.chats:
        if isinstance(chat, dict) and chat.get("id") == st.session_state.get("active_chat_id"):
            chat.setdefault("messages", [])
            chat.setdefault("title", "محادثة جديدة")
            chat.setdefault("created_at", _now())
            _ensure_chat_identity_state(chat)
            return chat
    chat = _new_chat()
    st.session_state.chats.insert(0, chat)
    st.session_state.active_chat_id = chat["id"]
    return chat


def _prune_voice_store() -> None:
    store = st.session_state.get("voice_audio_store") or {}
    if not isinstance(store, dict):
        st.session_state.voice_audio_store = {}
        return
    kept: list[tuple[str, bytes]] = []
    total = 0
    for key, value in reversed(list(store.items())):
        try:
            blob = bytes(value or b"")
        except Exception:
            continue
        if len(kept) >= MAX_STORED_VOICE_ITEMS or total + len(blob) > MAX_STORED_VOICE_BYTES:
            continue
        kept.append((key, blob))
        total += len(blob)
    st.session_state.voice_audio_store = dict(reversed(kept))


def _title_from_prompt(prompt: str) -> str:
    clean = re.sub(r"\s+", " ", str(prompt or "")).strip()
    return clean[:48] + ("…" if len(clean) > 48 else "") or "محادثة جديدة"


def _shared_context(chat: dict, exclude_message_id: str | None = None, max_chars: int = 30_000) -> str:
    lines: list[str] = []
    for item in chat.get("messages", [])[-MAX_CHAT_MESSAGES:]:
        if exclude_message_id and item.get("id") == exclude_message_id:
            continue
        role = item.get("role")
        if role == "user":
            text = str(item.get("content", "")).strip()
            if text:
                lines.append(f"USER HISTORICAL DATA:\n{text}")
            attachment_context = str(item.get("attachment_context", "")).strip()
            if attachment_context:
                lines.append(f"USER ATTACHMENT METADATA (UNTRUSTED DATA):\n{attachment_context}")
        elif role == "assistant":
            text = str(item.get("content", "")).strip()
            if text:
                lines.append(f"{item.get('seat', 'AI')} [OFFICIAL API] HISTORICAL OUTPUT:\n{text}")
    return "\n\n".join(lines)[-max_chars:]


def _worker_failure(seat, exc: Exception, model_candidates: dict | None = None, request_id: str = "", round_no: int = 0) -> dict:
    models = tuple((model_candidates or {}).get(seat.key) or ())
    return {"seat": seat.key, "name": seat.name, "label": seat.label, "status": "FAILED", "mode": "internal", "model": models[0] if models else "", "content": "", "error": f"class=internal_worker_error; {exc.__class__.__name__}", "latency": 0.0, "attempted_models": [], "official_authenticated": False, "request_id": request_id, "round": round_no}


def _history_attempt_summaries(details: list[dict]) -> list[dict]:
    """Persist only compact, non-sensitive classifications in visible History."""
    allowed = {
        "MODEL_UNAVAILABLE", "QUOTA_EXCEEDED", "RATE_LIMITED",
        "AUTHENTICATION_ERROR", "API_ERROR", "NETWORK_ERROR",
        "TIMEOUT", "UNKNOWN",
    }
    summaries: list[dict] = []
    for detail in details or []:
        classification = str(detail.get("classification") or "UNKNOWN").strip().upper()
        if classification not in allowed:
            classification = "UNKNOWN"
        summary = {
            "attempt": detail.get("attempt"),
            "model": str(detail.get("model") or "").strip(),
            "status_code": detail.get("status_code"),
            "classification": classification,
            "retryable": bool(detail.get("retryable", False)),
        }
        # The timestamp is runtime metadata used only for the 60-second UI TTL.
        # Do not synthesize it here: real provider attempts stamp it at creation time.
        if "_display_created_at" in detail:
            try:
                summary["created_at_epoch"] = float(detail.get("_display_created_at"))
            except (TypeError, ValueError):
                pass
        summaries.append(summary)
    return summaries


def _attempt_display_remaining(detail: dict, now: float | None = None) -> float:
    """Return remaining UI visibility time; never expose or mutate raw provider errors."""
    try:
        created = float(detail.get("created_at_epoch", 0))
    except (TypeError, ValueError):
        return 0.0
    current = time.time() if now is None else float(now)
    return max(0.0, ERROR_DISPLAY_TTL_SECONDS - (current - created))


def _render_temporary_attempt_diagnostic(detail: dict) -> None:
    """Render a compact attempt error for 60 seconds, without exposing raw provider payloads."""
    model = str(detail.get("model") or "").strip()
    classification = str(detail.get("classification") or "UNKNOWN").strip().upper()
    code = detail.get("status_code")
    code_text = f" · HTTP {code}" if code else ""
    remaining = _attempt_display_remaining(detail)
    if remaining <= 0:
        return
    safe_text = html.escape(
        f"Attempt #{detail.get('attempt', '?')} · {model} · ❌ FAILED{code_text} · {classification}"
    )
    height = 32
    components_html(
        f"""<div id=\"attempt-error\" style=\"font-family:sans-serif;font-size:13px;padding:4px 0;\">{safe_text}</div>
<script>
const el=document.getElementById('attempt-error');
setTimeout(()=>{{ if(el) el.remove(); }}, {int(remaining * 1000)});
</script>""",
        height=height,
    )


def _run_round(user_prompt: str, chat: dict, round_no: int, credentials: dict, attachments: list[dict], model_candidates: dict, current_user_message_id: str, deadline: float, request_id: str) -> list[dict]:
    snapshot = _shared_context(chat, exclude_message_id=current_user_message_id)
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(SEATS)), thread_name_prefix="council") as pool:
        futures = {
            pool.submit(call_seat, seat, user_prompt, snapshot, round_no, False, credentials.get(seat.key), attachments, model_candidates.get(seat.key), deadline, request_id): seat
            for seat in SEATS
        }
        for future in as_completed(futures):
            seat = futures[future]
            try:
                results[seat.key] = future.result()
            except Exception as exc:
                results[seat.key] = _worker_failure(seat, exc, model_candidates, request_id, round_no)
    for seat in SEATS:
        results.setdefault(seat.key, _worker_failure(seat, TimeoutError("round deadline exceeded"), model_candidates, request_id, round_no))
    return [results[seat.key] for seat in SEATS]


def _run_council(user_prompt: str, chat: dict, rounds: int, credentials: dict, attachments: list[dict], model_candidates: dict, current_user_message_id: str, request_id: str) -> list[dict]:
    deadline = time.monotonic() + MAX_EXECUTION_SECONDS
    all_results: list[dict] = []
    total_rounds = max(1, min(int(rounds), MAX_ROUNDS))
    for round_no in range(1, total_rounds + 1):
        if time.monotonic() >= deadline:
            break
        round_results = _run_round(user_prompt, chat, round_no, credentials, attachments, model_candidates, current_user_message_id, deadline, request_id)
        seen_keys = set()
        for result in round_results:
            result["request_id"] = request_id
            result["round"] = round_no
            seat_key = str(result.get("seat") or "")
            result_key = f"{request_id}:{round_no}:{seat_key}"
            result["result_key"] = result_key
            identity_key = (str(request_id), int(round_no), seat_key)
            if identity_key in seen_keys:
                raise RuntimeError(f"Duplicate council result invariant violated: {identity_key!r}")
            _assert_unique_history_identity(chat, request_id, round_no, seat_key)
            seen_keys.add(identity_key)
            all_results.append(result)
            if result.get("status") == "SUCCESS" and result.get("content"):
                executed_model = str(result.get("executed_model") or "").strip()
                result_model = str(result.get("model") or "").strip()
                attempted_models = [str(m).strip() for m in result.get("attempted_models", []) if str(m).strip()]
                if not executed_model or result_model != executed_model:
                    raise RuntimeError(f"Execution identity invariant violated: {result_model!r} != {executed_model!r}")
                if attempted_models and attempted_models[-1] != executed_model:
                    raise RuntimeError(f"Cascade identity invariant violated: {attempted_models!r} -> {executed_model!r}")
                chat["messages"].append({"role": "assistant", "id": uuid.uuid4().hex, "seat": result["name"], "seat_key": seat_key, "label": result["label"], "content": result["content"], "round": round_no, "mode": "official", "model": executed_model, "executed_model": executed_model, "attempted_models": attempted_models, "attempt_diagnostics": _history_attempt_summaries(result.get("attempt_diagnostics", []) or []), "request_id": request_id, "result_key": result_key, "created_at": _now()})
        keys = set(chat.get("result_keys", []))
        keys.update(f"{request_id}:{round_no}:{r.get('seat', '')}" for r in round_results)
        chat["result_keys"] = list(keys)[-MAX_CHAT_MESSAGES:]
        chat["messages"] = chat["messages"][-MAX_CHAT_MESSAGES:]
    return all_results


def _run_provider_diagnostics(credentials: dict, model_candidates: dict) -> list[dict]:
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(SEATS)), thread_name_prefix="diagnostic") as pool:
        futures = {pool.submit(diagnostic_seat, seat, credentials.get(seat.key), model_candidates.get(seat.key)): seat for seat in SEATS}
        for future in as_completed(futures):
            seat = futures[future]
            try:
                results[seat.key] = future.result()
            except Exception as exc:
                results[seat.key] = _worker_failure(seat, exc, model_candidates, request_id="diagnostic", round_no=0)
    return [results[seat.key] for seat in SEATS]


def _render_sidebar(rounds: int, credentials: dict, model_candidates: dict) -> int:
    with st.sidebar:
        st.header("⚙️ إعدادات المجلس")
        rounds = st.slider("عدد الجولات", 1, MAX_ROUNDS, max(1, min(rounds, MAX_ROUNDS)), 1)
        st.session_state.rounds = rounds
        st.caption("🆓 Free API Cascade: Free #1 → Free #10 لكل مزود. لا Local Engine ولا Paid fallback.")
        st.divider()
        st.subheader("🔬 تشخيص المزودين")
        st.caption("API رسمي فقط؛ لا Local Engine ولا نموذج تلقائي.")
        if st.button("🔍 فحص المزودين الخمسة الآن", use_container_width=True):
            with st.spinner("تشخيص المزودين بالتوازي…"):
                st.session_state.last_diagnostics = _run_provider_diagnostics(credentials, model_candidates)
            st.rerun()
        st.divider()
        chat = _active_chat()
        st.subheader("💬 المحادثة الحالية")
        st.caption(f"اسم المحادثة: {chat['title']}")
        rename = st.text_input("إعادة تسمية", value="", key="rename_chat_input")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 حفظ الاسم", use_container_width=True) and rename.strip():
                chat["title"] = rename.strip()[:80]
                st.rerun()
        with c2:
            if st.button("➕ جديد", use_container_width=True):
                new_chat = _new_chat()
                st.session_state.chats.insert(0, new_chat)
                st.session_state.active_chat_id = new_chat["id"]
                st.session_state.last_results = []
                st.session_state.last_diagnostics = []
                st.rerun()
        st.divider()
        st.subheader("📚 السجل")
        for item in list(st.session_state.chats)[:30]:
            if st.button(f"{'🟢' if item['id'] == st.session_state.active_chat_id else '⚪'} {item.get('title', 'محادثة')}", key=f"load_{item['id']}", use_container_width=True):
                st.session_state.active_chat_id = item["id"]
                st.session_state.last_results = []
                st.rerun()
            st.caption(f"{len(item.get('messages', []))} رسالة • {item.get('created_at', '')}")
        c3, c4 = st.columns(2)
        with c3:
            if st.button("🗑️ حذف الحالية", use_container_width=True):
                if len(st.session_state.chats) == 1:
                    fresh = _new_chat()
                    st.session_state.chats = [fresh]
                    st.session_state.active_chat_id = fresh["id"]
                else:
                    st.session_state.chats = [x for x in st.session_state.chats if x.get("id") != chat["id"]]
                    st.session_state.active_chat_id = st.session_state.chats[0]["id"]
                st.session_state.last_results = []
                st.rerun()
        with c4:
            if st.button("🧹 مسح الكل", use_container_width=True):
                fresh = _new_chat()
                st.session_state.chats = [fresh]
                st.session_state.active_chat_id = fresh["id"]
                st.session_state.last_results = []
                st.session_state.last_diagnostics = []
                st.rerun()
        st.divider()
        st.subheader("🔌 الاعتمادات والنماذج")
        for seat in SEATS:
            models = tuple(model_candidates.get(seat.key) or ())
            st.markdown(f"{'🟢' if credentials.get(seat.key) else '⚪'} **{seat.name}**")
            st.caption("Free cascade: " + " → ".join(f"#{i+1} `{m}`" for i, m in enumerate(models)) if models else "Free cascade: غير مُكوّن — أضف *_FREE_MODELS")
        st.caption(f"اعتمادات موجودة: {configured_count(credentials)}/5")
        st.caption(f"Model config fingerprint: `{model_config_fingerprint(model_candidates)}`")
        sources = model_config_sources()
        source_text = " • ".join(f"{seat.name}: {sources.get(seat.key, 'missing')}" for seat in SEATS)
        st.caption(f"مصدر إعداد النماذج: {source_text}")
        st.caption("Streamlit Secrets لها الأولوية؛ Environment Variables تُستخدم فقط عند غياب Secret غير الفارغ.")
        st.caption("وجود المفتاح لا يثبت Free Tier أو quota.")
        st.caption("المفاتيح لا تظهر في الواجهة ولا تدخل History.")
    return rounds


def _voice_player(text: str, label: str = "🔊 استمع") -> None:
    from streamlit.components.v1 import html as components_html
    safe_text = json.dumps(str(text or ""), ensure_ascii=False)
    safe_label = html.escape(label, quote=True)
    components_html(f"<button id='speakBtn' style='padding:6px 10px'>{safe_label}</button><script>const b=document.getElementById('speakBtn'),t={safe_text};b.onclick=()=>{{if(!('speechSynthesis' in window))return;window.speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(t);u.lang=/[\\u0600-\\u06FF]/.test(t)?'ar-SA':'en-US';window.speechSynthesis.speak(u);}};</script>", height=44)


def _render_user_room(chat: dict, credentials: dict, model_candidates: dict):
    voice_submission = None
    with st.container(height=500, border=True):
        st.subheader("👤 أنت")
        user_messages = [m for m in chat.get("messages", []) if m.get("role") == "user"]
        if not user_messages:
            st.caption("اكتب رسالة أو سجّل صوتًا أو أرفق ملفات.")
        st.markdown("**🎙️ صوت داخل الغرفة**")
        st.caption("التفريغ يستخدم Gemini فقط عند وجود نموذج تفريغ صريح.")
        audio = st.audio_input("🎙️ تسجيل رسالة صوتية", sample_rate=16000, key=f"voice_input_{st.session_state.voice_nonce}")
        if audio:
            audio_bytes = bytes(audio.getvalue())
            mime = str(getattr(audio, "type", None) or "audio/wav")
            st.audio(audio_bytes, format=mime)
            if st.button("🎤 إرسال الصوت للمجلس", type="primary", use_container_width=True, key=f"send_voice_{st.session_state.voice_nonce}"):
                fingerprint = hashlib.sha256(audio_bytes).hexdigest()
                seen = st.session_state.voice_fingerprints.get(chat["id"], set())
                if len(audio_bytes) > MAX_VOICE_BYTES:
                    st.error("الرسالة الصوتية أكبر من الحد المسموح 8 MB.")
                elif fingerprint in seen:
                    st.warning("هذه الرسالة الصوتية تم إرسالها بالفعل.")
                else:
                    with st.spinner("تحويل الصوت إلى نص عبر Gemini…"):
                        transcription = transcribe_audio_gemini(audio_bytes, mime, credentials.get("gemini"), model_candidates.get("gemini"))
                    if transcription.get("status") == "SUCCESS" and transcription.get("text", "").strip():
                        st.session_state.last_voice_error = ""
                        voice_submission = (transcription["text"].strip(), audio_bytes, mime, fingerprint)
                    else:
                        st.session_state.last_voice_error = str(transcription.get("error", "unknown error"))
                        st.error(f"تعذر تحويل الصوت: {st.session_state.last_voice_error}")
        if st.session_state.get("last_voice_error"):
            with st.expander("⚠️ آخر خطأ في تحويل الصوت"):
                st.code(st.session_state.last_voice_error)
        st.divider()
        for message in user_messages:
            with st.chat_message("user"):
                st.write(message.get("content", ""))
                if message.get("voice"):
                    st.caption("🎙️ رسالة صوتية — تم تحويلها إلى نص.")
                    blob = st.session_state.get("voice_audio_store", {}).get(message.get("voice_audio_key"))
                    if blob:
                        st.audio(blob, format=message.get("voice_mime", "audio/wav"))
                for attachment in message.get("attachments", []):
                    st.caption(f"📎 {attachment.get('name', 'attachment')} · {attachment.get('mime', 'file')} · {attachment.get('size', 0)} bytes")
    return voice_submission


def _render_ai_room(chat: dict, seat, model_candidates: dict) -> None:
    with st.container(height=500, border=True):
        st.subheader(seat.label)
        models = tuple(model_candidates.get(seat.key) or ())
        st.caption("Free #1 → " + f"`{models[0]}`" if models else "لا يوجد Free API model مُكوّن")
        messages = [m for m in chat.get("messages", []) if m.get("seat") == seat.name]
        if not messages:
            st.caption("بانتظار أول جولة…")
            return
        for message in messages:
            displayed_model = str(message.get("model") or "").strip()
            executed_model = str(message.get("executed_model") or "").strip()
            attempted_models = [str(m).strip() for m in message.get("attempted_models", []) if str(m).strip()]
            if message.get("mode") == "official":
                if not executed_model or displayed_model != executed_model:
                    st.error("⚠️ Execution identity mismatch: النموذج المعروض لا يطابق النموذج المنفذ.")
                    continue
                if attempted_models and attempted_models[-1] != executed_model:
                    st.error("⚠️ Cascade identity mismatch: آخر محاولة لا تطابق النموذج المنفذ.")
                    continue
            request_id = str(message.get("request_id") or "").strip()
            request_no = _request_display_number(chat, request_id) if request_id else None
            prefix = f"Request {request_no} · " if request_no is not None else ""
            st.markdown(f"**{prefix}Round {message.get('round', '?')} · 🟢 Official API · `{executed_model or displayed_model}`**")
            if attempted_models:
                st.caption("Cascade attempts: " + " → ".join(f"`{m}`" for m in attempted_models))
            for detail in message.get("attempt_diagnostics", []) or []:
                _render_temporary_attempt_diagnostic(detail)
            st.caption(f"Executed model: `{executed_model or displayed_model}`")
            st.markdown(message.get("content", ""))
            _voice_player(message.get("content", ""))
            st.divider()


def _render_six_rooms(chat: dict, model_candidates: dict, credentials: dict):
    rows = [(None, SEATS[0]), (SEATS[1], SEATS[2]), (SEATS[3], SEATS[4])]
    voice_submission = None
    for left, right in rows:
        cols = st.columns(2, gap="medium")
        with cols[0]:
            voice_submission = _render_user_room(chat, credentials, model_candidates) if left is None else _render_ai_room(chat, left, model_candidates)
        with cols[1]:
            _render_ai_room(chat, right, model_candidates)
    return voice_submission


def _result_error_classification(result: dict) -> str:
    details = result.get("attempt_diagnostics", []) or []
    for detail in reversed(details):
        value = str(detail.get("classification") or "").strip().upper()
        if value in {
            "MODEL_UNAVAILABLE", "QUOTA_EXCEEDED", "RATE_LIMITED",
            "AUTHENTICATION_ERROR", "API_ERROR", "NETWORK_ERROR",
            "TIMEOUT", "UNKNOWN",
        }:
            return value
    raw = str(result.get("error") or "")
    match = re.search(r"(?:^|[;\s])class=([A-Za-z0-9_:-]+)", raw, flags=re.IGNORECASE)
    if match:
        internal = match.group(1)
        try:
            from providers import _canonical_error_classification
            return _canonical_error_classification(internal)
        except Exception:
            pass
    status = result.get("status_code")
    return "AUTHENTICATION_ERROR" if status in (401, 403) else "UNKNOWN"


def _render_result_line(result: dict, diagnostic_only: bool = False) -> None:
    status = result.get("status")
    if status == "SUCCESS":
        st.success(f"{'🟢' if diagnostic_only else '✅'} {result['label']} — Official API — `{(result.get('executed_model') or result.get('model', ''))}` — {result['latency']}s")
    elif status == "NO_FREE_MODEL_CONFIGURED":
        st.warning(f"🟡 {result['label']} — لا يوجد Free API model مُكوّن؛ لم يتم إرسال أي طلب.")
    elif status == "AUTHENTICATION_OK_NO_FREE_MODEL":
        st.warning(f"🟡 {result['label']} — نقطة المصادقة قبلت المفتاح، لكن لا يوجد Free model مُكوّن.")
        st.caption("Classification: AUTHENTICATION_ERROR")
    else:
        with st.expander(f"🔴 {result.get('label', result.get('name', 'Provider'))} — Official API failed", expanded=diagnostic_only):
            st.write("Official API request failed; raw provider payload is not shown in the UI.")
            st.write("Attempted models:", ", ".join(result.get("attempted_models", [])) or "none")
            for detail in result.get("attempt_diagnostics", []) or []:
                model = str(detail.get("model") or "").strip()
                classification = str(detail.get("classification") or "UNKNOWN").strip().upper()
                code = detail.get("status_code")
                code_text = f" · HTTP {code}" if code else ""
                st.caption(f"Attempt #{detail.get('attempt', '?')} · `{model}` · ❌ FAILED{code_text} · {classification}")


def _render_diagnostics(results: list[dict], title: str = "🔎 نتائج الجولة") -> None:
    official = sum(r.get("status") == "SUCCESS" for r in results)
    failed = sum(r.get("status") == "FAILED" for r in results)
    st.subheader(title)
    st.info(f"{official} استجابات رسمية ناجحة • {failed} فشل • Local Engine: غير مستخدم")
    for result in results:
        _render_result_line(result)


def _render_provider_diagnostics(results: list[dict]) -> None:
    if not results:
        return
    st.subheader("🧪 الفحص المستقل للمزودين")
    for result in results:
        _render_result_line(result, diagnostic_only=True)


def _render_attachment_picker() -> list[dict]:
    with st.expander("📁 إرفاق مجلد", expanded=False):
        st.caption("الحد: 20 ملفًا / 25 MB إجمالًا.")
        folder = st.file_uploader("📁 اختر مجلدًا", accept_multiple_files="directory", key=f"chat_folder_{st.session_state.folder_nonce}")
    return list(folder or [])


def _submission_files(submission, folder_files: list[object]) -> list[dict] | None:
    files = list(getattr(submission, "files", []) or []) if submission is not None else []
    files.extend(folder_files)
    if not files:
        return []
    try:
        return normalize_uploaded_files(files)
    except ValueError as exc:
        st.error(str(exc))
        return None


def _request_fingerprint(prompt: str, attachments: list[dict]) -> str:
    h = hashlib.sha256()
    h.update(str(prompt).strip().encode("utf-8"))
    for attachment in attachments:
        h.update(str(attachment.get("name", "")).encode("utf-8"))
        h.update(str(attachment.get("mime", "")).encode("utf-8"))
        h.update(str(attachment.get("size", 0)).encode("ascii"))
        h.update(str(attachment.get("sha256", "")).encode("ascii"))
    return h.hexdigest()


def run_app() -> None:
    _init_state()
    credentials = capture_credentials()
    model_candidates = capture_model_candidates()
    rounds = _render_sidebar(st.session_state.rounds, credentials, model_candidates)
    chat = _active_chat()
    st.title("🏛️ AI Council — Six-Room Shared Context Arena")
    st.caption(f"{APP_VERSION} • المستخدم + خمسة مقاعد • Free Cascade #1→#10 • Provider: {PROVIDER_VERSION}")
    st.markdown("**العقد:** لا Local Engine، لا Paid fallback، ولا نموذج تلقائي. كل طلب رسمي يستخدم فقط النماذج الموجودة صراحةً في `*_FREE_MODELS`.")
    voice_submission = _render_six_rooms(chat, model_candidates, credentials)
    folder_files = _render_attachment_picker()
    submission = st.chat_input("اكتب موضوع النقاش أو أرفق صورة/ملف…", accept_file="multiple", file_type=None, max_upload_size=10, key="council_chat_input")
    prompt = ""
    attachments: list[dict] = []
    voice_audio = None
    voice_mime = "audio/wav"
    voice_fingerprint = ""
    if voice_submission:
        transcript, voice_audio, voice_mime, voice_fingerprint = voice_submission
        typed_prompt = (getattr(submission, "text", "") or "").strip() if submission is not None else ""
        prompt = f"{typed_prompt}\n\n[تفريغ الرسالة الصوتية]:\n{transcript}" if typed_prompt and transcript else (typed_prompt or transcript)
        attachments = _submission_files(submission, folder_files)
    elif submission:
        prompt = (getattr(submission, "text", "") or "").strip()
        attachments = _submission_files(submission, folder_files)
    if attachments is None:
        return
    if prompt or attachments:
        if not prompt:
            prompt = "حلّل المرفقات المرفقة واذكر أهم ما تحتويه."
        if len(prompt) > MAX_PROMPT_CHARS:
            st.error("الرسالة تتجاوز الحد المسموح 20,000 حرف.")
            return
        fingerprint = _request_fingerprint(prompt, attachments)
        if fingerprint in chat.get("request_ids", []):
            st.warning("تم تجاهل طلب مكرر مطابق تمامًا لطلب أُرسل في هذه المحادثة.")
            return
        if not chat["messages"]:
            chat["title"] = _title_from_prompt(prompt)
        user_message_id = uuid.uuid4().hex
        request_id = uuid.uuid4().hex
        _ensure_chat_identity_state(chat)
        chat["request_ids"] = chat["request_ids"][-MAX_REQUEST_IDS:]
        chat["request_ids"].append(fingerprint)
        chat["request_ids"] = chat["request_ids"][-MAX_REQUEST_IDS:]
        chat["request_records"].append({"request_id": request_id, "fingerprint": fingerprint, "rounds": rounds, "created_at": _now()})
        attachment_context = "\n".join(f"- {a.get('name')} ({a.get('mime')}, {a.get('size', 0)} bytes, sha256={a.get('sha256', '')})" for a in attachments)[:6000]
        request_no = _request_display_number(chat, request_id)
        chat["messages"].append({"role": "user", "id": user_message_id, "content": prompt, "attachments": public_metadata(attachments), "attachment_context": attachment_context, "request_id": request_id, "request_no": request_no, "created_at": _now()})
        if voice_audio is not None:
            chat["messages"][-1].update({"voice": True, "voice_audio_key": user_message_id, "voice_mime": voice_mime})
            st.session_state.voice_audio_store[user_message_id] = voice_audio
            _prune_voice_store()
            fingerprints = st.session_state.voice_fingerprints.setdefault(chat["id"], set())
            fingerprints.add(voice_fingerprint)
            st.session_state.voice_fingerprints[chat["id"]] = set(list(fingerprints)[-20:])
        st.session_state.last_diagnostics = []
        with st.spinner("المجلس السداسي ينفذ Free API Cascade بالتوازي…"):
            results = _run_council(prompt, chat, rounds, credentials, attachments, model_candidates, user_message_id, request_id)
        st.session_state.last_results = results
        st.session_state.folder_nonce += 1
        st.session_state.voice_nonce += 1
        st.rerun()
    if st.session_state.last_diagnostics:
        st.divider()
        _render_provider_diagnostics(st.session_state.last_diagnostics)
    if st.session_state.last_results:
        st.divider()
        _render_diagnostics(st.session_state.last_results)


if __name__ == "__main__":
    run_app()

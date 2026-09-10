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

from attachment_utils import normalize_uploaded_files, public_metadata
from providers import SEATS, VERSION as PROVIDER_VERSION, call_seat, capture_credentials, capture_model_candidates, configured_count, diagnostic_seat, transcribe_audio_gemini, get_model_config_diagnostic

APP_VERSION = "V22.1-FINAL-EXACT-NAMES-UPDATED-HARDENED-HOTFIX7"
MAX_VOICE_BYTES = 8 * 1024 * 1024
MAX_STORED_VOICE_ITEMS = 10
MAX_STORED_VOICE_BYTES = 40 * 1024 * 1024
MAX_ROUNDS = 4
MAX_EXECUTION_SECONDS = 180
MAX_PROMPT_CHARS = 20_000
MAX_CHAT_MESSAGES = 200
MAX_REQUEST_IDS = 50
MAX_WORKERS = 5


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _new_chat() -> dict:
    return {"id": uuid.uuid4().hex, "title": "محادثة جديدة", "created_at": _now(), "messages": [], "request_ids": []}


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
            chat.setdefault("request_ids", [])
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


def _worker_failure(seat, exc: Exception, model_candidates: dict | None = None) -> dict:
    models = tuple((model_candidates or {}).get(seat.key) or ())
    return {"seat": seat.key, "name": seat.name, "label": seat.label, "status": "FAILED", "mode": "internal", "model": models[0] if models else "", "content": "", "error": f"class=internal_worker_error; {exc.__class__.__name__}", "latency": 0.0, "attempted_models": [], "official_authenticated": False}


def _run_round(user_prompt: str, chat: dict, round_no: int, credentials: dict, attachments: list[dict], model_candidates: dict, current_user_message_id: str, deadline: float) -> list[dict]:
    snapshot = _shared_context(chat, exclude_message_id=current_user_message_id)
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(SEATS)), thread_name_prefix="council") as pool:
        futures = {
            pool.submit(call_seat, seat, user_prompt, snapshot, round_no, False, credentials.get(seat.key), attachments, model_candidates.get(seat.key), deadline): seat
            for seat in SEATS
        }
        for future in as_completed(futures):
            seat = futures[future]
            try:
                results[seat.key] = future.result()
            except Exception as exc:
                results[seat.key] = _worker_failure(seat, exc, model_candidates)
    for seat in SEATS:
        results.setdefault(seat.key, _worker_failure(seat, TimeoutError("round deadline exceeded"), model_candidates))
    return [results[seat.key] for seat in SEATS]


def _run_council(user_prompt: str, chat: dict, rounds: int, credentials: dict, attachments: list[dict], model_candidates: dict, current_user_message_id: str) -> list[dict]:
    deadline = time.monotonic() + MAX_EXECUTION_SECONDS
    all_results: list[dict] = []
    total_rounds = max(1, min(int(rounds), MAX_ROUNDS))
    for round_no in range(1, total_rounds + 1):
        if time.monotonic() >= deadline:
            break
        round_results = _run_round(user_prompt, chat, round_no, credentials, attachments, model_candidates, current_user_message_id, deadline)
        all_results.extend(round_results)
        for result in round_results:
            if result.get("status") == "SUCCESS" and result.get("content"):
                chat["messages"].append({"role": "assistant", "id": uuid.uuid4().hex, "seat": result["name"], "label": result["label"], "content": result["content"], "round": round_no, "mode": "official", "model": result.get("model", ""), "attempted_models": list(result.get("attempted_models", [])), "created_at": _now()})
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
                results[seat.key] = _worker_failure(seat, exc, model_candidates)
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
        st.caption("وجود المفتاح لا يثبت Free Tier أو quota.")
        gemini_cfg = get_model_config_diagnostic(next(s for s in SEATS if s.key == "gemini"))
        if gemini_cfg["invalid"]:
            st.error("GEMINI_FREE_MODELS موجود لكنه غير صالح. استخدم أسماء نماذج مفصولة بفواصل إنجليزية (,). لا يوجد fallback تلقائي.")
        elif gemini_cfg["configured"]:
            st.caption(f"Gemini config source: `{gemini_cfg['source']}` • {gemini_cfg['model_count']} model(s) loaded")
        else:
            st.caption("Gemini config source: `unset` • لا يوجد Free model configured")
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
            st.markdown(f"**Round {message.get('round', '?')} · 🟢 Official API · `{message.get('model', '')}`**")
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


def _render_result_line(result: dict, diagnostic_only: bool = False) -> None:
    status = result.get("status")
    if status == "SUCCESS":
        st.success(f"{'🟢' if diagnostic_only else '✅'} {result['label']} — Official API — `{result['model']}` — {result['latency']}s")
    elif status == "NO_FREE_MODEL_CONFIGURED":
        st.warning(f"🟡 {result['label']} — لا يوجد Free API model مُكوّن؛ لم يتم إرسال أي طلب.")
    elif status == "AUTHENTICATION_OK_NO_FREE_MODEL":
        st.warning(f"🟡 {result['label']} — نقطة المصادقة قبلت المفتاح، لكن لا يوجد Free model مُكوّن.")
        st.caption(result.get("error", ""))
    else:
        with st.expander(f"🔴 {result.get('label', result.get('name', 'Provider'))} — Official API failed", expanded=diagnostic_only):
            st.write(result.get("error") or "تعذر الحصول على رد رسمي.")
            st.write("Attempted models:", ", ".join(result.get("attempted_models", [])) or "none")


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
        chat.setdefault("request_ids", []).append(fingerprint)
        chat["request_ids"] = chat["request_ids"][-MAX_REQUEST_IDS:]
        attachment_context = "\n".join(f"- {a.get('name')} ({a.get('mime')}, {a.get('size', 0)} bytes, sha256={a.get('sha256', '')})" for a in attachments)[:6000]
        chat["messages"].append({"role": "user", "id": user_message_id, "content": prompt, "attachments": public_metadata(attachments), "attachment_context": attachment_context, "created_at": _now()})
        if voice_audio is not None:
            chat["messages"][-1].update({"voice": True, "voice_audio_key": user_message_id, "voice_mime": voice_mime})
            st.session_state.voice_audio_store[user_message_id] = voice_audio
            _prune_voice_store()
            fingerprints = st.session_state.voice_fingerprints.setdefault(chat["id"], set())
            fingerprints.add(voice_fingerprint)
            st.session_state.voice_fingerprints[chat["id"]] = set(list(fingerprints)[-20:])
        st.session_state.last_diagnostics = []
        with st.spinner("المجلس السداسي ينفذ Free API Cascade بالتوازي…"):
            results = _run_council(prompt, chat, rounds, credentials, attachments, model_candidates, user_message_id)
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

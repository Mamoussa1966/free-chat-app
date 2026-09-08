from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import html
import json
import re
import uuid

import streamlit as st

from attachment_utils import (
    normalize_uploaded_files,
    public_metadata,
)

from providers import (
    SEATS,
    VERSION as PROVIDER_VERSION,
    call_seat,
    capture_credentials,
    capture_model_candidates,
    configured_count,
    diagnostic_seat,
    transcribe_audio_gemini,
)


APP_VERSION = "V22.2-FREE-ONLY-HARDENED"

MAX_VOICE_BYTES = 8 * 1024 * 1024
MAX_STORED_VOICE_ITEMS = 10
MAX_STORED_VOICE_BYTES = 40 * 1024 * 1024


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")


def _new_chat() -> dict:
    return {
        "id": uuid.uuid4().hex,
        "title": "محادثة جديدة",
        "created_at": _now(),
        "messages": [],
    }


def _init_state() -> None:
    if "chats" not in st.session_state:
        chat = _new_chat()
        st.session_state.chats = [chat]
        st.session_state.active_chat_id = chat["id"]

    if "last_results" not in st.session_state:
        st.session_state.last_results = []

    if "last_diagnostics" not in st.session_state:
        st.session_state.last_diagnostics = []

    if "rounds" not in st.session_state:
        st.session_state.rounds = 1

    if "folder_nonce" not in st.session_state:
        st.session_state.folder_nonce = 0

    if "voice_nonce" not in st.session_state:
        st.session_state.voice_nonce = 0

    if "voice_fingerprints" not in st.session_state:
        st.session_state.voice_fingerprints = {}

    if "voice_audio_store" not in st.session_state:
        st.session_state.voice_audio_store = {}

    if "last_voice_error" not in st.session_state:
        st.session_state.last_voice_error = ""

    # Production invariant:
    # There is NO Local Engine path in V22.2.
    st.session_state.local_fallback = False


def _active_chat() -> dict:
    chats = st.session_state.get("chats")

    if not isinstance(chats, list):
        chats = []
        st.session_state.chats = chats

    active_id = st.session_state.get(
        "active_chat_id"
    )

    for chat in chats:
        if (
            isinstance(chat, dict)
            and chat.get("id") == active_id
        ):
            chat.setdefault(
                "messages",
                [],
            )
            chat.setdefault(
                "title",
                "محادثة جديدة",
            )
            chat.setdefault(
                "created_at",
                _now(),
            )
            return chat

    chat = _new_chat()
    chats.insert(0, chat)
    st.session_state.active_chat_id = chat["id"]

    return chat


def _prune_voice_store() -> None:
    store = (
        st.session_state.get(
            "voice_audio_store"
        )
        or {}
    )

    if not store:
        return

    total = 0
    kept = {}

    for key, data in reversed(
        list(store.items())
    ):
        blob = bytes(data or b"")

        if len(kept) >= MAX_STORED_VOICE_ITEMS:
            continue

        if (
            total + len(blob)
            > MAX_STORED_VOICE_BYTES
        ):
            continue

        kept[key] = blob
        total += len(blob)

    st.session_state.voice_audio_store = dict(
        reversed(list(kept.items()))
    )


def _title_from_prompt(prompt: str) -> str:
    clean = re.sub(
        r"\s+",
        " ",
        prompt,
    ).strip()

    if not clean:
        return "محادثة جديدة"

    return clean[:48] + (
        "…" if len(clean) > 48 else ""
    )


# ---------------------------------------------------------------------------
# Shared context
# ---------------------------------------------------------------------------

def _shared_context(
    chat: dict,
    exclude_message_id: str | None = None,
    max_chars: int = 30_000,
) -> str:
    lines = []

    for item in chat["messages"]:
        if (
            exclude_message_id
            and item.get("id")
            == exclude_message_id
        ):
            continue

        if item.get("role") == "user":
            text = str(
                item.get("content", "")
            ).strip()

            if text:
                lines.append(
                    "USER (historical context): "
                    f"{text}"
                )

            attachment_context = str(
                item.get(
                    "attachment_context",
                    "",
                )
            ).strip()

            if attachment_context:
                lines.append(
                    "USER ATTACHMENT CONTEXT "
                    "(untrusted): "
                    f"{attachment_context}"
                )

        elif item.get("role") == "assistant":
            source = (
                "OFFICIAL"
                if item.get("mode")
                == "official"
                else "FAILED"
            )

            text = str(
                item.get("content", "")
            ).strip()

            if text:
                lines.append(
                    f"{item.get('seat', 'AI')} "
                    f"[{source}]: {text}"
                )

    context = "\n\n".join(lines)

    return context[-max_chars:]


# ---------------------------------------------------------------------------
# Council execution
# ---------------------------------------------------------------------------

def _worker_failure(
    seat,
    exc: Exception,
    model_candidates: dict | None = None,
) -> dict:
    return {
        "seat": seat.key,
        "name": seat.name,
        "label": seat.label,
        "status": "FAILED",
        "mode": "internal",
        "model": "",
        "content": "",
        "error": (
            "class=internal_worker_error; "
            f"{exc.__class__.__name__}"
        ),
        "latency": 0,
        "attempted_models": [],
        "official_authenticated": False,
    }


def _run_round(
    user_prompt: str,
    chat: dict,
    round_no: int,
    credentials: dict,
    attachments: list[dict],
    model_candidates: dict,
    current_user_message_id: str,
) -> list[dict]:
    snapshot = _shared_context(
        chat,
        exclude_message_id=current_user_message_id,
    )

    results: dict[str, dict] = {}

    with ThreadPoolExecutor(
        max_workers=len(SEATS),
        thread_name_prefix="council",
    ) as pool:

        futures = {
            pool.submit(
                call_seat,
                seat,
                user_prompt,
                snapshot,
                round_no,
                False,  # Local Engine disabled.
                credentials.get(seat.key),
                attachments,
                model_candidates.get(seat.key),
            ): seat
            for seat in SEATS
        }

        for future in as_completed(futures):
            seat = futures[future]

            try:
                results[seat.key] = (
                    future.result()
                )
            except Exception as exc:
                results[seat.key] = (
                    _worker_failure(
                        seat,
                        exc,
                        model_candidates,
                    )
                )

    return [
        results[seat.key]
        for seat in SEATS
    ]


def _run_council(
    user_prompt: str,
    chat: dict,
    rounds: int,
    credentials: dict,
    attachments: list[dict],
    model_candidates: dict,
    current_user_message_id: str,
) -> list[dict]:
    all_results = []

    for round_no in range(
        1,
        rounds + 1,
    ):
        round_results = _run_round(
            user_prompt,
            chat,
            round_no,
            credentials,
            attachments,
            model_candidates,
            current_user_message_id,
        )

        all_results.extend(
            round_results
        )

        # Only successful official responses
        # enter historical context.
        for result in round_results:
            if (
                result["status"]
                == "SUCCESS"
                and result["content"]
            ):
                chat["messages"].append(
                    {
                        "role": "assistant",
                        "id": uuid.uuid4().hex,
                        "seat": result["name"],
                        "label": result["label"],
                        "content": result["content"],
                        "round": round_no,
                        "mode": result["mode"],
                        "model": result["model"],
                        "official_error": result.get(
                            "error"
                        ),
                        "attempted_models": list(
                            result.get(
                                "attempted_models",
                                [],
                            )
                        ),
                        "created_at": _now(),
                    }
                )

    return all_results


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def _run_provider_diagnostics(
    credentials: dict,
    model_candidates: dict,
) -> list[dict]:
    results: dict[str, dict] = {}

    with ThreadPoolExecutor(
        max_workers=len(SEATS),
        thread_name_prefix="diagnostic",
    ) as pool:

        futures = {
            pool.submit(
                diagnostic_seat,
                seat,
                credentials.get(seat.key),
                model_candidates.get(seat.key),
            ): seat
            for seat in SEATS
        }

        for future in as_completed(futures):
            seat = futures[future]

            try:
                results[seat.key] = (
                    future.result()
                )
            except Exception as exc:
                results[seat.key] = (
                    _worker_failure(
                        seat,
                        exc,
                        model_candidates,
                    )
                )

    return [
        results[seat.key]
        for seat in SEATS
    ]


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _render_sidebar(
    rounds: int,
    credentials: dict,
    model_candidates: dict,
) -> int:

    with st.sidebar:
        st.header(
            "⚙️ إعدادات المجلس"
        )

        rounds = st.slider(
            "عدد الجولات",
            1,
            4,
            rounds,
            1,
        )

        st.session_state.rounds = rounds

        st.caption(
            "🆓 Free API Cascade: حتى 10 نماذج "
            "مجانية لكل مزود."
        )

        st.caption(
            "🚫 Local Engine غير مستخدم."
        )

        st.caption(
            "🚫 لا يوجد نموذج مدفوع افتراضيًا."
        )

        st.divider()

        # ---------------------------------------------------------------
        # Diagnostics
        # ---------------------------------------------------------------

        st.subheader(
            "🔬 تشخيص المزودين"
        )

        st.caption(
            "يفحص كل API رسمي بشكل مستقل. "
            "لا يستخدم Local Engine ولا المرفقات."
        )

        if st.button(
            "🔍 فحص المزودين الخمسة الآن",
            use_container_width=True,
        ):
            with st.spinner(
                "تشخيص ChatGPT وGemini وClaude "
                "وGrok وKimi بالتوازي…"
            ):
                st.session_state.last_diagnostics = (
                    _run_provider_diagnostics(
                        credentials,
                        model_candidates,
                    )
                )

            st.rerun()

        st.divider()

        # ---------------------------------------------------------------
        # Current chat
        # ---------------------------------------------------------------

        st.subheader(
            "💬 المحادثة الحالية"
        )

        chat = _active_chat()

        st.caption(
            f"اسم المحادثة: {chat['title']}"
        )

        rename = st.text_input(
            "إعادة تسمية",
            value="",
            key="rename_chat_input",
        )

        c1, c2 = st.columns(2)

        with c1:
            if st.button(
                "💾 حفظ الاسم",
                use_container_width=True,
            ):
                if rename.strip():
                    chat["title"] = (
                        rename.strip()[:80]
                    )
                    st.rerun()

        with c2:
            if st.button(
                "➕ جديد",
                use_container_width=True,
            ):
                new_chat = _new_chat()

                st.session_state.chats.insert(
                    0,
                    new_chat,
                )

                st.session_state.active_chat_id = (
                    new_chat["id"]
                )

                st.session_state.last_results = []
                st.session_state.last_diagnostics = []

                st.rerun()

        st.divider()

        # ---------------------------------------------------------------
        # History
        # ---------------------------------------------------------------

        st.subheader("📚 السجل")

        for item in list(
            st.session_state.chats
        ):
            marker = (
                "🟢"
                if (
                    item["id"]
                    == st.session_state.active_chat_id
                )
                else "⚪"
            )

            if st.button(
                f"{marker} {item['title']}",
                key=f"load_{item['id']}",
                use_container_width=True,
            ):
                st.session_state.active_chat_id = (
                    item["id"]
                )

                st.session_state.last_results = []

                st.rerun()

            st.caption(
                f"{len(item['messages'])} رسالة • "
                f"{item['created_at']}"
            )

        c3, c4 = st.columns(2)

        with c3:
            if st.button(
                "🗑️ حذف الحالية",
                use_container_width=True,
            ):
                if (
                    len(st.session_state.chats)
                    == 1
                ):
                    fresh = _new_chat()

                    st.session_state.chats = [
                        fresh
                    ]

                    st.session_state.active_chat_id = (
                        fresh["id"]
                    )
                else:
                    st.session_state.chats = [
                        x
                        for x in st.session_state.chats
                        if x["id"]
                        != chat["id"]
                    ]

                    st.session_state.active_chat_id = (
                        st.session_state.chats[0]["id"]
                    )

                st.session_state.last_results = []

                st.rerun()

        with c4:
            if st.button(
                "🧹 مسح الكل",
                use_container_width=True,
            ):
                fresh = _new_chat()

                st.session_state.chats = [
                    fresh
                ]

                st.session_state.active_chat_id = (
                    fresh["id"]
                )

                st.session_state.last_results = []
                st.session_state.last_diagnostics = []

                st.rerun()

        st.divider()

        # ---------------------------------------------------------------
        # Credentials / Free Models
        # ---------------------------------------------------------------

        st.subheader(
            "🔌 الاعتمادات والنماذج"
        )

        for seat in SEATS:
            credential_exists = bool(
                credentials.get(seat.key)
            )

            models = (
                model_candidates.get(
                    seat.key
                )
                or ()
            )

            icon = (
                "🟢"
                if credential_exists
                else "⚪"
            )

            st.markdown(
                f"{icon} **{seat.name}**"
            )

            if models:
                st.caption(
                    "Free cascade: "
                    + " → ".join(
                        f"#{index + 1} `{model}`"
                        for index, model in enumerate(
                            models
                        )
                    )
                )
            else:
                st.caption(
                    "Free cascade: غير مُكوّن"
                )

        st.caption(
            f"اعتمادات موجودة: "
            f"{configured_count(credentials)}/5"
        )

        st.caption(
            "🔑 وجود المفتاح لا يثبت نجاح API "
            "ولا يثبت وجود Free quota."
        )

        st.caption(
            "المفاتيح لا تُعرض في الواجهة "
            "ولا تُحفظ في History."
        )

    return rounds


# ---------------------------------------------------------------------------
# Browser TTS
# ---------------------------------------------------------------------------

def _voice_player(
    text: str,
    label: str = "🔊 استمع",
) -> None:
    """
    Browser-side TTS.
    No audio is uploaded by this player.
    """
    from streamlit.components.v1 import (
        html as components_html,
    )

    safe_text = json.dumps(
        str(text or ""),
        ensure_ascii=False,
    )

    safe_label = html.escape(
        label,
        quote=True,
    )

    components_html(
        f"""
        <div style="font-family:sans-serif;margin:2px 0 8px 0;">
          <button
            id="speakBtn"
            style="
              padding:6px 10px;
              border-radius:8px;
              border:1px solid #888;
              background:transparent;
              cursor:pointer;
            "
          >
            {safe_label}
          </button>

          <script>
            const btn =
              document.getElementById('speakBtn');

            const text = {safe_text};

            btn.onclick = () => {{
              if (!('speechSynthesis' in window)) {{
                btn.textContent =
                  'المتصفح لا يدعم الصوت';
                return;
              }}

              window.speechSynthesis.cancel();

              const utterance =
                new SpeechSynthesisUtterance(text);

              utterance.lang =
                /[\\u0600-\\u06FF]/.test(text)
                  ? 'ar-SA'
                  : 'en-US';

              utterance.rate = 1.0;

              window.speechSynthesis.speak(
                utterance
              );
            }};
          </script>
        </div>
        """,
        height=48,
    )


# ---------------------------------------------------------------------------
# User room / voice
# ---------------------------------------------------------------------------

def _render_user_room(
    chat: dict,
    credentials: dict,
    model_candidates: dict,
) -> tuple[
    str,
    bytes,
    str,
    str,
] | None:

    del model_candidates

    voice_submission = None

    with st.container(
        height=500,
        border=True,
    ):
        st.subheader("👤 أنت")

        user_messages = [
            m
            for m in chat["messages"]
            if m.get("role") == "user"
        ]

        if not user_messages:
            st.caption(
                "اكتب رسالة أو سجّل رسالة صوتية، "
                "أو أرفق صورة/ملف/مجلد."
            )

        st.markdown(
            "**🎙️ صوت داخل الغرفة**"
        )

        st.caption(
            "سجّل رسالتك الصوتية ثم أرسلها للمجلس. "
            "سيتم تحويلها إلى نص عبر Gemini "
            "Transcribe قبل توزيعها على المقاعد."
        )

        audio = st.audio_input(
            "🎙️ تسجيل رسالة صوتية",
            sample_rate=16000,
            key=(
                f"voice_input_"
                f"{st.session_state.voice_nonce}"
            ),
        )

        if audio:
            audio_bytes = bytes(
                audio.getvalue()
            )

            mime = str(
                getattr(
                    audio,
                    "type",
                    None,
                )
                or "audio/wav"
            )

            st.audio(
                audio_bytes,
                format=mime,
            )

            if st.button(
                "🎤 إرسال الصوت للمجلس السداسي",
                type="primary",
                use_container_width=True,
                key=(
                    f"send_voice_"
                    f"{st.session_state.voice_nonce}"
                ),
            ):
                import hashlib

                fingerprint = hashlib.sha256(
                    audio_bytes
                ).hexdigest()

                if (
                    len(audio_bytes)
                    > MAX_VOICE_BYTES
                ):
                    st.error(
                        "الرسالة الصوتية أكبر "
                        "من الحد المسموح 8 MB."
                    )

                elif (
                    fingerprint
                    in st.session_state.voice_fingerprints.get(
                        chat["id"],
                        set(),
                    )
                ):
                    st.warning(
                        "هذه الرسالة الصوتية "
                        "تم إرسالها بالفعل."
                    )

                else:
                    with st.spinner(
                        "تحويل الصوت إلى نص عبر "
                        "Gemini Transcribe…"
                    ):
                        transcription = (
                            transcribe_audio_gemini(
                                audio_bytes,
                                mime,
                                credentials.get(
                                    "gemini"
                                ),
                                None,
                            )
                        )

                    if (
                        transcription["status"]
                        == "SUCCESS"
                    ):
                        text = (
                            transcription["text"]
                            .strip()
                        )

                        if text:
                            st.session_state.last_voice_error = ""
                            voice_submission = (
                                text,
                                audio_bytes,
                                mime,
                                fingerprint,
                            )
                        else:
                            st.error(
                                "تم التقاط الصوت، "
                                "لكن لم ينتج عنه نص صالح."
                            )

                    else:
                        st.session_state.last_voice_error = str(
                            transcription.get(
                                "error",
                                "unknown error",
                            )
                        )

                        st.error(
                            "تعذر تحويل الرسالة الصوتية "
                            "إلى نص عبر Gemini. "
                            f"{st.session_state.last_voice_error}"
                        )

        if st.session_state.get(
            "last_voice_error"
        ):
            with st.expander(
                "⚠️ آخر خطأ في تحويل الصوت",
                expanded=False,
            ):
                st.code(
                    st.session_state.last_voice_error
                )

        st.divider()

        for message in user_messages:
            with st.chat_message("user"):
                content = message.get(
                    "content",
                    "",
                )

                if content:
                    st.write(content)

                if message.get("voice"):
                    st.caption(
                        "🎙️ رسالة صوتية — تم "
                        "تحويلها إلى نص قبل إرسالها للمجلس."
                    )

                    key = message.get(
                        "voice_audio_key"
                    )

                    audio_bytes = (
                        st.session_state
                        .get(
                            "voice_audio_store",
                            {},
                        )
                        .get(key)
                    )

                    if audio_bytes:
                        st.audio(
                            audio_bytes,
                            format=message.get(
                                "voice_mime",
                                "audio/wav",
                            ),
                        )

                for attachment in message.get(
                    "attachments",
                    [],
                ):
                    st.caption(
                        f"📎 {attachment.get('name', 'attachment')} "
                        f"· {attachment.get('mime', 'file')} "
                        f"· {attachment.get('size', 0)} bytes"
                    )

    return voice_submission


# ---------------------------------------------------------------------------
# AI rooms
# ---------------------------------------------------------------------------

def _render_ai_room(
    chat: dict,
    seat,
    model_candidates: dict,
) -> None:

    with st.container(
        height=500,
        border=True,
    ):
        st.subheader(seat.label)

        models = (
            model_candidates.get(
                seat.key
            )
            or ()
        )

        if models:
            st.caption(
                "Free #1 → "
                f"`{models[0]}`"
            )
        else:
            st.caption(
                "لا يوجد Free API model "
                "مُكوّن لهذا المقعد"
            )

        messages = [
            m
            for m in chat["messages"]
            if m.get("seat")
            == seat.name
        ]

        if not messages:
            st.caption(
                "بانتظار أول جولة…"
            )
            return

        for message in messages:
            if (
                message.get("mode")
                == "official"
            ):
                st.markdown(
                    f"**Round "
                    f"{message.get('round', '?')} "
                    f"· 🟢 Official API · "
                    f"`{message.get('model', '')}`**"
                )
            else:
                st.markdown(
                    f"**Round "
                    f"{message.get('round', '?')} "
                    f"· 🔴 Official API failed**"
                )

                error = message.get(
                    "official_error"
                )

                if error:
                    with st.expander(
                        "سبب فشل سلسلة Free API",
                        expanded=False,
                    ):
                        st.code(error)

                        attempted = (
                            message.get(
                                "attempted_models"
                            )
                            or []
                        )

                        if attempted:
                            st.caption(
                                "النماذج التي تمت "
                                "محاولتها: "
                                + " → ".join(
                                    attempted
                                )
                            )

            response_text = message.get(
                "content",
                "",
            )

            if response_text:
                st.markdown(
                    response_text
                )
                _voice_player(
                    response_text
                )

            st.divider()


def _render_six_rooms(
    chat: dict,
    model_candidates: dict,
    credentials: dict,
) -> tuple[
    str,
    bytes,
    str,
    str,
] | None:

    rows = [
        (None, SEATS[0]),
        (SEATS[1], SEATS[2]),
        (SEATS[3], SEATS[4]),
    ]

    voice_submission = None

    for left, right in rows:
        cols = st.columns(
            2,
            gap="medium",
        )

        with cols[0]:
            if left is None:
                voice_submission = (
                    _render_user_room(
                        chat,
                        credentials,
                        model_candidates,
                    )
                )
            else:
                _render_ai_room(
                    chat,
                    left,
                    model_candidates,
                )

        with cols[1]:
            _render_ai_room(
                chat,
                right,
                model_candidates,
            )

    return voice_submission


# ---------------------------------------------------------------------------
# Result rendering
# ---------------------------------------------------------------------------

def _render_result_line(
    result: dict,
    diagnostic_only: bool = False,
) -> None:

    status = result.get(
        "status"
    )

    if status == "SUCCESS":
        prefix = (
            "🟢"
            if diagnostic_only
            else "✅"
        )

        st.success(
            f"{prefix} "
            f"{result['label']} — "
            f"Official API — "
            f"`{result['model']}` — "
            f"{result['latency']}s"
        )
        return

    if (
        status
        == "AUTHENTICATED_NO_FREE_MODEL"
    ):
        st.warning(
            f"🟡 {result['label']} — "
            "OpenAI authentication OK, "
            "but no Free API model is configured. "
            "No paid model is selected automatically."
        )

        with st.expander(
            "تفاصيل التشخيص",
            expanded=diagnostic_only,
        ):
            st.write(
                result.get("error")
                or "لا يوجد Free model."
            )

        return

    with st.expander(
        f"🔴 {result['label']} — "
        "Official API failed",
        expanded=diagnostic_only,
    ):
        st.write(
            result.get("error")
            or "تعذر الحصول على رد رسمي."
        )

        attempted = (
            result.get(
                "attempted_models",
                [],
            )
            or []
        )

        st.write(
            "Attempted models:",
            ", ".join(attempted)
            or "none",
        )


def _render_diagnostics(
    results: list[dict],
    title: str = "🔎 التشخيص والنتائج",
) -> None:

    official = sum(
        r.get("status")
        == "SUCCESS"
        for r in results
    )

    authenticated = sum(
        r.get(
            "official_authenticated"
        )
        is True
        for r in results
    )

    failed = sum(
        r.get("status")
        == "FAILED"
        for r in results
    )

    no_free = sum(
        r.get("status")
        == "AUTHENTICATED_NO_FREE_MODEL"
        for r in results
    )

    st.subheader(title)

    st.info(
        f"آخر عملية: "
        f"{official}/5 استجابات رسمية "
        f"• موثّق API: "
        f"{authenticated}/5 "
        f"• بدون Free model: "
        f"{no_free} "
        f"• فشل: "
        f"{failed} "
        f"• Local Engine: غير مستخدم"
    )

    for result in results:
        _render_result_line(result)


def _render_provider_diagnostics(
    results: list[dict],
) -> None:
    if not results:
        return

    st.subheader(
        "🧪 الفحص المستقل للمزودين"
    )

    st.caption(
        "هذا الاختبار لا يستخدم Local Engine؛ "
        "كل نتيجة هنا تخص API الرسمي مباشرة."
    )

    for result in results:
        _render_result_line(
            result,
            diagnostic_only=True,
        )


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------

def _render_attachment_picker() -> list[dict]:
    nonce = (
        st.session_state.folder_nonce
    )

    with st.expander(
        "📁 إرفاق مجلد",
        expanded=False,
    ):
        st.caption(
            "اختر مجلدًا كاملًا؛ ستُرسل ملفاته "
            "مع الرسالة التالية. الحد: "
            "20 ملفًا / 25 MB إجمالًا."
        )

        folder = st.file_uploader(
            "📁 اختر مجلدًا",
            accept_multiple_files="directory",
            key=f"chat_folder_{nonce}",
            help=(
                "يرفع الملفات الموجودة داخل "
                "المجلد ومجلداته الفرعية "
                "عندما يدعم المتصفح ذلك."
            ),
        )

    return list(folder or [])


def _submission_files(
    submission,
    folder_files: list[object],
) -> list[dict] | None:

    files = []

    if submission is not None:
        files.extend(
            list(
                getattr(
                    submission,
                    "files",
                    [],
                )
                or []
            )
        )

    files.extend(
        folder_files
    )

    if not files:
        return []

    try:
        return normalize_uploaded_files(
            files
        )
    except ValueError as exc:
        st.error(str(exc))
        return None


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

def run_app() -> None:
    _init_state()

    credentials = (
        capture_credentials()
    )

    model_candidates = (
        capture_model_candidates()
    )

    rounds = _render_sidebar(
        st.session_state.rounds,
        credentials,
        model_candidates,
    )

    chat = _active_chat()

    st.title(
        "🏛️ AI Council — "
        "Six-Room Shared Context Arena"
    )

    st.caption(
        f"{APP_VERSION} • "
        "المستخدم + خمسة مقاعد • "
        "سياق مشترك • "
        "استدعاءات متوازية • "
        f"Provider: {PROVIDER_VERSION}"
    )

    st.caption(
        "🔒 سياق الجولات السابقة يُوسم حسب المصدر، "
        "والطلب الحالي لا يُكرر داخل سياق الجولة "
        "الثانية وما بعدها."
    )

    st.markdown(
        "**العقد التشغيلي:** "
        "رسالة واحدة تُرسل بالتوازي إلى "
        "ChatGPT وGemini وClaude وGrok وKimi. "
        "كل مقعد يجرب Free #1 ثم Free #2 … "
        "حتى Free #10. "
        "**لا يوجد Local Engine ولا نموذج مدفوع "
        "افتراضيًا.**"
    )

    voice_submission = _render_six_rooms(
        chat,
        model_candidates,
        credentials,
    )

    folder_files = (
        _render_attachment_picker()
    )

    submission = st.chat_input(
        "اكتب موضوع النقاش أو أرفق صورة/ملف…",
        accept_file="multiple",
        file_type=None,
        max_upload_size=10,
        key="council_chat_input",
    )

    prompt = ""
    attachments = []
    voice_audio = None
    voice_mime = "audio/wav"
    voice_fingerprint = ""

    # ---------------------------------------------------------------
    # Voice + typed input
    # ---------------------------------------------------------------

    if voice_submission:
        (
            transcript,
            voice_audio,
            voice_mime,
            voice_fingerprint,
        ) = voice_submission

        typed_prompt = (
            (
                getattr(
                    submission,
                    "text",
                    "",
                )
                or ""
            ).strip()
            if submission is not None
            else ""
        )

        if (
            typed_prompt
            and transcript
        ):
            prompt = (
                f"{typed_prompt}\n\n"
                "[تفريغ الرسالة الصوتية]:\n"
                f"{transcript}"
            )
        else:
            prompt = (
                typed_prompt
                or transcript
            )

        attachments = (
            _submission_files(
                submission,
                folder_files,
            )
            if submission is not None
            else _submission_files(
                None,
                folder_files,
            )
        )

        if attachments is None:
            return

    elif submission:
        prompt = (
            getattr(
                submission,
                "text",
                "",
            )
            or ""
        ).strip()

        attachments = (
            _submission_files(
                submission,
                folder_files,
            )
        )

        if attachments is None:
            return

    # ---------------------------------------------------------------
    # Execute message
    # ---------------------------------------------------------------

    if prompt or attachments:
        if not prompt:
            prompt = (
                "حلّل المرفقات المرفقة "
                "واذكر أهم ما تحتويه."
            )

        if not chat["messages"]:
            chat["title"] = (
                _title_from_prompt(
                    prompt
                )
            )

        user_message_id = (
            uuid.uuid4().hex
        )

        attachment_context = "\n".join(
            f"- {a.get('name')} "
            f"({a.get('mime')}, "
            f"{a.get('size', 0)} bytes)"
            for a in attachments
        )[:6000]

        user_message = {
            "role": "user",
            "id": user_message_id,
            "content": prompt,
            "attachments": (
                public_metadata(
                    attachments
                )
            ),
            "attachment_context": (
                attachment_context
            ),
            "created_at": _now(),
        }

        if voice_audio is not None:
            user_message["voice"] = True
            user_message[
                "voice_audio_key"
            ] = user_message_id
            user_message[
                "voice_mime"
            ] = voice_mime

            store = (
                st.session_state.setdefault(
                    "voice_audio_store",
                    {},
                )
            )

            store[
                user_message_id
            ] = voice_audio

            _prune_voice_store()

        chat["messages"].append(
            user_message
        )

        st.session_state.last_diagnostics = []

        with st.spinner(
            "المجلس السداسي ينفذ الجولة "
            "بالتوازي…"
        ):
            results = _run_council(
                prompt,
                chat,
                rounds,
                credentials,
                attachments,
                model_candidates,
                user_message_id,
            )

        st.session_state.last_results = (
            results
        )

        if voice_fingerprint:
            fingerprints = (
                st.session_state.setdefault(
                    "voice_fingerprints",
                    {},
                )
            )

            chat_fingerprints = (
                fingerprints.setdefault(
                    chat["id"],
                    set(),
                )
            )

            chat_fingerprints.add(
                voice_fingerprint
            )

            # Bound replay history per chat.
            if len(
                chat_fingerprints
            ) > 20:
                fingerprints[
                    chat["id"]
                ] = set(
                    list(
                        chat_fingerprints
                    )[-20:]
                )

        st.session_state.folder_nonce += 1
        st.session_state.voice_nonce += 1

        st.rerun()

    # ---------------------------------------------------------------
    # Persistent diagnostics
    # ---------------------------------------------------------------

    if st.session_state.last_diagnostics:
        st.divider()

        _render_provider_diagnostics(
            st.session_state.last_diagnostics
        )

    # ---------------------------------------------------------------
    # Last council run
    # ---------------------------------------------------------------

    if st.session_state.last_results:
        st.divider()

        _render_diagnostics(
            st.session_state.last_results
        )


# ---------------------------------------------------------------------------
# Direct execution compatibility
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_app()

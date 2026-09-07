from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import html
import json
import re
import uuid

import streamlit as st

from attachment_utils import normalize_uploaded_files, public_metadata
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

APP_VERSION = "V21.18-SIX-ROOM-TEXT-VOICE-PROVIDER-CATALOG-HARDENED"
MAX_VOICE_BYTES = 8 * 1024 * 1024
MAX_STORED_VOICE_ITEMS = 10
MAX_STORED_VOICE_BYTES = 40 * 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


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

    if "local_fallback" not in st.session_state:
        st.session_state.local_fallback = True

    if "folder_nonce" not in st.session_state:
        st.session_state.folder_nonce = 0

    if "voice_nonce" not in st.session_state:
        st.session_state.voice_nonce = 0

    if "last_voice_fingerprint" not in st.session_state:
        st.session_state.last_voice_fingerprint = ""

    if "voice_audio_store" not in st.session_state:
        st.session_state.voice_audio_store = {}

    if "last_voice_error" not in st.session_state:
        st.session_state.last_voice_error = ""


def _active_chat() -> dict:
    for chat in st.session_state.chats:
        if chat["id"] == st.session_state.active_chat_id:
            return chat

    chat = _new_chat()
    st.session_state.chats.insert(0, chat)
    st.session_state.active_chat_id = chat["id"]
    return chat


def _prune_voice_store() -> None:
    store = st.session_state.get("voice_audio_store") or {}

    if not store:
        return

    total = 0
    kept = {}

    for key, data in reversed(list(store.items())):
        blob = bytes(data or b"")

        if len(kept) >= MAX_STORED_VOICE_ITEMS:
            continue

        if total + len(blob) > MAX_STORED_VOICE_BYTES:
            continue

        kept[key] = blob
        total += len(blob)

    st.session_state.voice_audio_store = dict(reversed(list(kept.items())))


def _title_from_prompt(prompt: str) -> str:
    clean = re.sub(r"\s+", " ", prompt).strip()
    return clean[:48] + ("…" if len(clean) > 48 else "") or "محادثة جديدة"


def _shared_context(
    chat: dict,
    exclude_message_id: str | None = None,
    max_chars: int = 30000,
) -> str:
    lines = []

    for item in chat["messages"]:
        if exclude_message_id and item.get("id") == exclude_message_id:
            continue

        if item.get("role") == "user":
            text = str(item.get("content", "")).strip()

            if text:
                lines.append(
                    f"USER (historical context): {text}"
                )

            attachment_context = str(
                item.get("attachment_context", "")
            ).strip()

            if attachment_context:
                lines.append(
                    "USER ATTACHMENT CONTEXT (untrusted): "
                    + attachment_context
                )

        elif item.get("role") == "assistant":
            source = (
                "OFFICIAL"
                if item.get("mode") == "official"
                else "LOCAL"
            )

            text = str(item.get("content", "")).strip()

            if text:
                lines.append(
                    f"{item.get('seat', 'AI')} [{source}]: {text}"
                )

    context = "\n\n".join(lines)

    return context[-max_chars:]


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
        "model": (
            model_candidates or {}
        ).get(
            seat.key,
            (seat.default_model,),
        )[0],
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
    local_fallback: bool,
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
                local_fallback,
                credentials.get(seat.key),
                attachments,
                model_candidates.get(seat.key),
            ): seat
            for seat in SEATS
        }

        for future in as_completed(futures):
            seat = futures[future]

            try:
                results[seat.key] = future.result()

            except Exception as exc:
                results[seat.key] = _worker_failure(
                    seat,
                    exc,
                    model_candidates,
                )

    return [
        results[seat.key]
        for seat in SEATS
    ]


def _run_council(
    user_prompt: str,
    chat: dict,
    rounds: int,
    local_fallback: bool,
    credentials: dict,
    attachments: list[dict],
    model_candidates: dict,
    current_user_message_id: str,
) -> list[dict]:

    all_results = []

    for round_no in range(1, rounds + 1):

        round_results = _run_round(
            user_prompt,
            chat,
            round_no,
            local_fallback,
            credentials,
            attachments,
            model_candidates,
            current_user_message_id,
        )

        all_results.extend(round_results)

        for result in round_results:

            if (
                result["status"] in ("SUCCESS", "LOCAL")
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
                        "official_error": result.get("error"),
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
                results[seat.key] = future.result()

            except Exception as exc:
                results[seat.key] = _worker_failure(
                    seat,
                    exc,
                    model_candidates,
                )

    return [
        results[seat.key]
        for seat in SEATS
    ]


def _render_sidebar(
    rounds: int,
    local_fallback: bool,
    credentials: dict,
    model_candidates: dict,
) -> tuple[int, bool]:

    with st.sidebar:

        st.header("⚙️ إعدادات المجلس")

        rounds = st.slider(
            "عدد الجولات",
            1,
            4,
            rounds,
            1,
        )

        local_fallback = st.checkbox(
            "تفعيل Local Engine كبديل محلي معلن",
            value=local_fallback,
        )

        st.session_state.rounds = rounds
        st.session_state.local_fallback = local_fallback

        st.divider()

        st.subheader("🔬 تشخيص المزودين")

        st.caption(
            "يفحص كل API رسمي بشكل مستقل برسالة اختبار صغيرة، "
            "بدون Local Engine وبدون مرفقات."
        )

        if st.button(
            "🔍 فحص المزودين الخمسة الآن",
            use_container_width=True,
        ):

            with st.spinner(
                "تشخيص ChatGPT وGemini وClaude وGrok وKimi بالتوازي…"
            ):
                st.session_state.last_diagnostics = (
                    _run_provider_diagnostics(
                        credentials,
                        model_candidates,
                    )
                )

            st.rerun()

        st.divider()

        st.subheader("💬 المحادثة الحالية")

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
                    chat["title"] = rename.strip()[:80]
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

        st.subheader("📚 السجل")

        for item in list(st.session_state.chats):

            label = item["title"]

            if item["id"] == st.session_state.active_chat_id:
                label = "🟢 " + label

            if st.button(
                label,
                key=f"load_chat_{item['id']}",
                use_container_width=True,
            ):

                st.session_state.active_chat_id = item["id"]
                st.session_state.last_results = []
                st.session_state.last_diagnostics = []

                st.rerun()

        st.divider()

        if st.button(
            "🗑️ حذف المحادثة الحالية",
            use_container_width=True,
        ):

            current_id = st.session_state.active_chat_id

            st.session_state.chats = [
                item
                for item in st.session_state.chats
                if item["id"] != current_id
            ]

            if not st.session_state.chats:
                new_chat = _new_chat()
                st.session_state.chats = [new_chat]
                st.session_state.active_chat_id = new_chat["id"]

            else:
                st.session_state.active_chat_id = (
                    st.session_state.chats[0]["id"]
                )

            st.session_state.last_results = []
            st.session_state.last_diagnostics = []

            st.rerun()

        if st.button(
            "🧹 مسح السجل بالكامل",
            use_container_width=True,
        ):

            new_chat = _new_chat()

            st.session_state.chats = [new_chat]
            st.session_state.active_chat_id = new_chat["id"]

            st.session_state.last_results = []
            st.session_state.last_diagnostics = []

            st.rerun()

        st.divider()

        configured = configured_count(credentials)

        st.metric(
            "المزودون المهيؤون",
            f"{configured}/5",
        )

        st.caption(
            "مفاتيح API تُقرأ من Secrets فقط ولا تُعرض في الواجهة."
        )

    return rounds, local_fallback


def _voice_player(text: str) -> None:

    if not text:
        return

    safe_text = html.escape(
        text[:12000]
    )

    component = f"""
    <div style="margin: 6px 0;">
        <button
            onclick="speechSynthesis.cancel();
            speechSynthesis.speak(
                new SpeechSynthesisUtterance(
                    document.getElementById('tts_text').innerText
                )
            );"
        >
            🔊 قراءة الرد
        </button>

        <span
            id="tts_text"
            style="display:none;"
        >
            {safe_text}
        </span>
    </div>
    """

    st.components.v1.html(
        component,
        height=45,
    )


def _render_user_room(
    chat: dict,
    credentials: dict,
    model_candidates: dict,
) -> tuple[str, bytes, str, str] | None:

    with st.container(
        height=500,
        border=True,
    ):

        st.subheader("👤 المستخدم")

        user_messages = [
            m
            for m in chat["messages"]
            if m.get("role") == "user"
        ]

        if not user_messages:
            st.caption(
                "اكتب رسالة في صندوق الإدخال أسفل المجلس."
            )

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
                        "🎙️ رسالة صوتية — تم تحويلها إلى نص "
                        "قبل إرسالها للمجلس."
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
                        f"📎 "
                        f"{attachment.get('name', 'attachment')} · "
                        f"{attachment.get('mime', 'file')} · "
                        f"{attachment.get('size', 0)} bytes"
                    )

        st.divider()

        st.subheader("🎙️ رسالة

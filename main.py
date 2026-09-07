from __future__ import annotations

from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from datetime import datetime, timezone
import os

import streamlit as st

from providers import (
    SEATS,
    call_seat,
    get_seat_config,
)


APP_VERSION = "V21.3.1-FINAL-SYNTAX-SAFE"

MAX_CONTEXT_CHARS = 50000
MAX_HISTORY_CHATS = 100
MAX_VISIBLE_HISTORY = 20


# ---------------------------------------------------------------------------
# Time / chat helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def _default_title() -> str:
    return "محادثة جديدة"


def _make_chat() -> dict:
    now = _now()

    return {
        "id": (
            now
            .replace(":", "")
            .replace("+00:00", "Z")
        ),
        "title": _default_title(),
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }


def _ensure_state() -> None:

    if (
        "chat" not in st.session_state
        or not isinstance(
            st.session_state.chat,
            dict,
        )
    ):
        st.session_state.chat = _make_chat()

    if (
        "history_chats" not in st.session_state
        or not isinstance(
            st.session_state.history_chats,
            list,
        )
    ):
        st.session_state.history_chats = []


def _context(
    messages: list[dict],
    max_chars: int = MAX_CONTEXT_CHARS,
) -> str:

    chunks: list[str] = []

    for item in messages:

        sender = str(
            item.get(
                "sender",
                "Unknown",
            )
        )

        content = str(
            item.get(
                "content",
                "",
            )
        )

        if content:
            chunks.append(
                f"{sender}: {content}"
            )

    text = "\n\n".join(chunks)

    return text[-max_chars:]


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def _credential_state() -> dict[str, dict]:

    state: dict[str, dict] = {}

    for seat in SEATS:

        try:
            state[seat.name] = get_seat_config(
                seat
            )

        except Exception:
            state[seat.name] = {
                "credential": None,
                "workspace_id": None,
            }

    return state


# ---------------------------------------------------------------------------
# Chat persistence in session
# ---------------------------------------------------------------------------

def _has_chat_content(
    chat: dict,
) -> bool:

    messages = chat.get(
        "messages",
        [],
    )

    return bool(messages) or (
        chat.get("title")
        not in (
            None,
            "",
            _default_title(),
        )
    )


def _save_current_chat() -> None:

    chat = dict(
        st.session_state.chat
    )

    chat["messages"] = list(
        st.session_state.chat.get(
            "messages",
            [],
        )
    )

    chat["updated_at"] = _now()

    if not _has_chat_content(chat):

        st.session_state.history_chats = [
            item
            for item in st.session_state.history_chats
            if item.get("id")
            != chat.get("id")
        ]

        return

    existing = [
        item
        for item in st.session_state.history_chats
        if item.get("id")
        != chat.get("id")
    ]

    existing.insert(
        0,
        chat,
    )

    st.session_state.history_chats = (
        existing[:MAX_HISTORY_CHATS]
    )


def _set_title(
    title: str,
) -> bool:

    cleaned = " ".join(
        (title or "").split()
    ).strip()[:120]

    if not cleaned:
        return False

    st.session_state.chat["title"] = cleaned

    st.session_state.chat[
        "updated_at"
    ] = _now()

    _save_current_chat()

    return True


def _new_chat() -> None:
    _save_current_chat()

    st.session_state.chat = _make_chat()


def _load_chat(
    chat: dict,
) -> None:

    fallback = _make_chat()

    st.session_state.chat = {
        "id": chat.get(
            "id",
            fallback["id"],
        ),
        "title": (
            chat.get("title")
            or _default_title()
        ),
        "created_at": chat.get(
            "created_at",
            _now(),
        ),
        "updated_at": chat.get(
            "updated_at",
            _now(),
        ),
        "messages": list(
            chat.get(
                "messages",
                [],
            )
        ),
    }


def _clear_current_chat() -> None:

    st.session_state.chat[
        "messages"
    ] = []

    st.session_state.chat[
        "title"
    ] = _default_title()

    st.session_state.chat[
        "updated_at"
    ] = _now()

    _save_current_chat()


def _auto_title_from_prompt(
    prompt: str,
) -> None:

    if (
        st.session_state.chat["title"]
        != _default_title()
    ):
        return

    title = " ".join(
        prompt.split()
    ).strip()

    if title:
        st.session_state.chat[
            "title"
        ] = title[:80]


# ---------------------------------------------------------------------------
# Council execution
# ---------------------------------------------------------------------------

def run_room(
    user_prompt: str,
    messages: list[dict],
    rounds: int,
    local_fallback: bool,
) -> list[dict]:

    results: list[dict] = []

    working_messages = list(
        messages
    )

    credentials = _credential_state()

    rounds = max(
        1,
        min(
            int(rounds),
            4,
        ),
    )

    for round_no in range(
        1,
        rounds + 1,
    ):

        snapshot = _context(
            working_messages
        )

        round_results: list[dict] = []

        with ThreadPoolExecutor(
            max_workers=len(SEATS)
        ) as pool:

            futures = {
                pool.submit(
                    call_seat,
                    seat,
                    user_prompt,
                    snapshot,
                    round_no,
                    local_fallback,
                    credentials.get(
                        seat.name,
                        {},
                    ).get(
                        "credential"
                    ),
                    credentials.get(
                        seat.name,
                        {},
                    ).get(
                        "workspace_id"
                    ),
                ): seat
                for seat in SEATS
            }

            for future in as_completed(
                futures
            ):

                seat = futures[future]

                try:
                    result = future.result()

                except Exception as exc:

                    result = {
                        "seat": seat.name,
                        "label": (
                            f"❌ {seat.name} "
                            "— Worker Error"
                        ),
                        "provider": (
                            seat.provider_id
                        ),
                        "model": (
                            seat.default_model
                        ),
                        "status": "FAILED",
                        "mode": "NONE",
                        "round": round_no,
                        "content": (
                            "حدث خطأ داخلي أثناء "
                            f"تشغيل مقعد {seat.name}."
                        ),
                        "error": str(exc)[:1200],
                    }

                round_results.append(
                    result
                )

        order = {
            seat.name: index
            for index, seat in enumerate(
                SEATS
            )
        }

        round_results.sort(
            key=lambda item: order.get(
                item.get("seat"),
                999,
            )
        )

        for item in round_results:

            if (
                item.get("status")
                == "SUCCESS"
            ):

                working_messages.append(
                    {
                        "sender": item.get(
                            "label",
                            item.get(
                                "seat",
                                "Unknown",
                            ),
                        ),
                        "content": item.get(
                            "content",
                            "",
                        ),
                    }
                )

            results.append(item)

    return results


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _render_sidebar() -> tuple[int, bool]:

    with st.sidebar:

        st.header(
            "⚙️ إعدادات المجلس"
        )

        st.subheader(
            "📝 اسم المحادثة"
        )

        chat_id = str(
            st.session_state.chat.get(
                "id",
                "new",
            )
        )

        title_hash = abs(
            hash(
                st.session_state.chat.get(
                    "title",
                    "",
                )
            )
        )

        title_widget_key = (
            "title_draft_"
            f"{chat_id}_"
            f"{title_hash}"
        )

        title_value = st.text_input(
            "الاسم",
            value=(
                st.session_state.chat.get(
                    "title",
                    _default_title(),
                )
            ),
            key=title_widget_key,
            label_visibility="collapsed",
        )

        if st.button(
            "💾 حفظ اسم المحادثة",
            use_container_width=True,
        ):

            if _set_title(
                title_value
            ):
                st.success(
                    "تم حفظ اسم المحادثة."
                )

            else:
                st.warning(
                    "اكتب اسمًا صالحًا للمحادثة."
                )

        col1, col2 = st.columns(2)

        with col1:

            if st.button(
                "🆕 جديدة",
                use_container_width=True,
            ):
                _new_chat()
                st.rerun()

        with col2:

            if st.button(
                "🗑️ مسح",
                use_container_width=True,
            ):
                _clear_current_chat()
                st.rerun()

        rounds = st.slider(
            "عدد الجولات",
            1,
            4,
            2,
        )

        local_fallback = st.checkbox(
            "تفعيل Local Engine كبديل محلي معلن",
            value=False,
        )

        st.divider()

        st.subheader(
            "المقاعد الرسمية"
        )

        credentials = _credential_state()

        configured_count = 0

        for seat in SEATS:

            configured = bool(
                credentials.get(
                    seat.name,
                    {},
                ).get(
                    "credential"
                )
            )

            if configured:
                configured_count += 1

            icon = (
                "🔑"
                if configured
                else "⚪"
            )

            st.write(
                f"{icon} {seat.name}"
            )

            st.caption(
                f"Model: {seat.default_model}"
            )

        st.caption(
            "الاعتمادات المكوّنة: "
            f"{configured_count}/{len(SEATS)}"
        )

        st.caption(
            "🔑 تعني وجود اعتماد في البيئة فقط؛ "
            "ولا تعني نجاح API."
        )

        st.caption(
            "Local Engine مستقل ولا ينتحل "
            "هوية أي مزود رسمي."
        )

        st.divider()

        st.subheader(
            "📚 History"
        )

        if not st.session_state.history_chats:

            st.caption(
                "لا توجد محادثات محفوظة بعد."
            )

        else:

            for saved in (
                st.session_state.history_chats[
                    :MAX_VISIBLE_HISTORY
                ]
            ):

                title = (
                    saved.get("title")
                    or _default_title()
                )

                label = title[:45]

                if st.button(
                    label,
                    key=f"load_{saved.get('id')}",
                    use_container_width=True,
                ):

                    _load_chat(saved)
                    st.rerun()

    return (
        rounds,
        local_fallback,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_result(
    item: dict,
) -> None:

    label = item.get(
        "label",
        item.get(
            "seat",
            "Unknown",
        ),
    )

    content = item.get(
        "content",
        "",
    )

    with st.chat_message(
        "assistant"
    ):

        st.markdown(
            f"**{label}**\n\n{content}"
        )

    error = item.get(
        "error",
        "",
    )

    if error:

        with st.expander(
            "تفاصيل حالة "
            f"{item.get('seat', 'المقعد')}"
        ):

            if (
                item.get("mode")
                == "LOCAL_FALLBACK"
            ):
                st.info(error)

            else:
                st.warning(error)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

def run_app() -> None:

    _ensure_state()

    st.title(
        "🏛️ AI Council — Shared Context Arena"
    )

    st.caption(
        f"{APP_VERSION} • "
        "المستخدم + خمسة مقاعد أصلية • "
        "سياق مشترك • جولات متزامنة"
    )

    st.caption(
        "المحادثة الحالية: "
        f"**{st.session_state.chat['title']}**"
    )

    rounds, local_fallback = (
        _render_sidebar()
    )

    messages = (
        st.session_state.chat.get(
            "messages",
            [],
        )
    )

    for item in messages:

        role = (
            "user"
            if item.get("role")
            == "user"
            else "assistant"
        )

        with st.chat_message(role):

            st.markdown(
                f"**{item.get('sender', '')}**"
                "\n\n"
                f"{item.get('content', '')}"
            )

    prompt = st.chat_input(
        "اكتب موضوع النقاش على المجلس..."
    )

    if not prompt:
        return

    prompt = prompt.strip()

    if not prompt:
        return

    _auto_title_from_prompt(
        prompt
    )

    st.session_state.chat[
        "messages"
    ].append(
        {
            "role": "user",
            "sender": "👤 أنت",
            "content": prompt,
        }
    )

    st.session_state.chat[
        "updated_at"
    ] = _now()

    with st.chat_message(
        "user"
    ):

        st.markdown(
            f"**👤 أنت**\n\n{prompt}"
        )

    with st.spinner(
        "المجلس يناقش..."
    ):

        results = run_room(
            prompt,
            st.session_state.chat[
                "messages"
            ],
            rounds,
            local_fallback,
        )

    success_count = sum(
        item.get("status")
        == "SUCCESS"
        for item in results
    )

    official_count = sum(
        item.get("mode")
        == "OFFICIAL_API"
        for item in results
    )

    fallback_count = sum(
        item.get("mode")
        == "LOCAL_FALLBACK"
        for item in results
    )

    if results:

        st.info(
            f"نتائج هذه العملية: "
            f"{success_count}/{len(results)} ناجحة • "
            f"رسمي: {official_count} • "
            f"محلي: {fallback_count}"
        )

    for item in results:

        label = item.get(
            "label",
            item.get(
                "seat",
                "Unknown",
            ),
        )

        content = item.get(
            "content",
            "",
        )

        st.session_state.chat[
            "messages"
        ].append(
            {
                "role": "assistant",
                "sender": label,
                "content": content,
            }
        )

        _render_result(item)

    st.session_state.chat[
        "updated_at"
    ] = _now()

    _save_current_chat()

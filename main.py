from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import uuid

import streamlit as st

from providers import (
    PROVIDERS,
    SEATS,
    call_seat,
    get_model_candidates,
    get_seat_credential,
)


APP_VERSION = "V21.5-CONTRACT-HARDENED"

MAX_CONTEXT_CHARS = 50000
MAX_HISTORY_ITEMS = 120

DEFAULT_CHAT_TITLE = "محادثة جديدة"


def _now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def _new_chat(
    title: str = DEFAULT_CHAT_TITLE,
) -> dict:

    now = _now_iso()

    return {
        "id": uuid.uuid4().hex,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }


def _ensure_chat_state() -> None:

    if (
        "chats" not in st.session_state
        or not isinstance(
            st.session_state.chats,
            dict,
        )
    ):

        chat = _new_chat()

        st.session_state.chats = {
            chat["id"]: chat
        }

        st.session_state.current_chat_id = (
            chat["id"]
        )

    if (
        "current_chat_id"
        not in st.session_state
        or st.session_state.current_chat_id
        not in st.session_state.chats
    ):

        newest = sorted(
            st.session_state.chats.values(),
            key=lambda item: item.get(
                "updated_at",
                "",
            ),
            reverse=True,
        )

        if newest:

            st.session_state.current_chat_id = (
                newest[0]["id"]
            )

        else:

            chat = _new_chat()

            st.session_state.chats = {
                chat["id"]: chat
            }

            st.session_state.current_chat_id = (
                chat["id"]
            )


def _current_chat() -> dict:

    _ensure_chat_state()

    return st.session_state.chats[
        st.session_state.current_chat_id
    ]


def _touch(chat: dict) -> None:
    chat["updated_at"] = _now_iso()


def _trim_messages(
    messages: list[dict],
) -> list[dict]:

    if len(messages) <= MAX_HISTORY_ITEMS:
        return messages

    return messages[
        -MAX_HISTORY_ITEMS:
    ]


def _context(
    history: list[dict],
    max_chars: int = MAX_CONTEXT_CHARS,
) -> str:

    chunks = []

    for item in history:

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

        chunks.append(
            f"{sender}: {content}"
        )

    return "\n\n".join(chunks)[
        -max_chars:
    ]


def _safe_key_fragment(
    value: str,
) -> str:

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:12]


def _configured(seat) -> bool:
    return bool(
        get_seat_credential(seat)
    )


def _auto_title(
    prompt: str,
) -> str:

    clean = " ".join(
        str(prompt).split()
    )

    if len(clean) <= 54:
        return clean or DEFAULT_CHAT_TITLE

    return (
        clean[:54].rstrip()
        + "…"
    )


def _format_time(
    value: str,
) -> str:

    try:

        dt = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

        return dt.astimezone().strftime(
            "%Y-%m-%d %H:%M"
        )

    except Exception:

        return value[:16]


def _create_new_chat() -> None:

    chat = _new_chat()

    st.session_state.chats[
        chat["id"]
    ] = chat

    st.session_state.current_chat_id = (
        chat["id"]
    )


def _delete_chat(
    chat_id: str,
) -> None:

    st.session_state.chats.pop(
        chat_id,
        None,
    )

    if not st.session_state.chats:

        _create_new_chat()

        return

    if (
        st.session_state.current_chat_id
        == chat_id
    ):

        newest = max(
            st.session_state.chats.values(),
            key=lambda item: item.get(
                "updated_at",
                "",
            ),
        )

        st.session_state.current_chat_id = (
            newest["id"]
        )


def _clear_all_chats() -> None:

    chat = _new_chat()

    st.session_state.chats = {
        chat["id"]: chat
    }

    st.session_state.current_chat_id = (
        chat["id"]
    )


def _render_history_manager() -> None:

    chat = _current_chat()

    title_key = (
        "chat_title_"
        + _safe_key_fragment(
            chat["id"]
            + "|"
            + chat.get(
                "title",
                "",
            )
        )
    )

    st.subheader(
        "💬 المحادثة الحالية"
    )

    title_value = st.text_input(
        "اسم المحادثة",
        value=chat.get(
            "title",
            DEFAULT_CHAT_TITLE,
        ),
        key=title_key,
        max_chars=120,
    )

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "💾 حفظ الاسم",
            use_container_width=True,
            key="save_chat_title",
        ):

            clean_title = (
                " ".join(
                    title_value.split()
                ).strip()
                or DEFAULT_CHAT_TITLE
            )

            chat["title"] = clean_title

            _touch(chat)

            st.success(
                "تم حفظ اسم المحادثة."
            )

            st.rerun()

    with col2:

        if st.button(
            "🆕 محادثة جديدة",
            use_container_width=True,
            key="new_chat",
        ):

            _create_new_chat()

            st.rerun()

    st.divider()

    st.subheader(
        "📚 السجل"
    )

    saved = sorted(
        st.session_state.chats.values(),
        key=lambda item: item.get(
            "updated_at",
            "",
        ),
        reverse=True,
    )

    if not saved:

        st.caption(
            "لا توجد محادثات محفوظة في هذه الجلسة."
        )

    else:

        for saved_chat in saved:

            cid = saved_chat["id"]

            is_current = (
                cid
                == st.session_state.current_chat_id
            )

            title = (
                saved_chat.get("title")
                or DEFAULT_CHAT_TITLE
            )

            message_count = len(
                saved_chat.get(
                    "messages",
                    [],
                )
            )

            marker = (
                "🟢"
                if is_current
                else "⚪"
            )

            st.markdown(
                f"{marker} **{title}**"
            )

            st.caption(
                f"{message_count} رسالة • "
                f"{_format_time(saved_chat.get('updated_at', ''))}"
            )

            c1, c2 = st.columns(2)

            with c1:

                if st.button(
                    "📂 استدعاء",
                    key=f"load_{cid}",
                    use_container_width=True,
                ):

                    st.session_state.current_chat_id = (
                        cid
                    )

                    st.rerun()

            with c2:

                if st.button(
                    "🗑️ حذف",
                    key=f"delete_{cid}",
                    use_container_width=True,
                ):

                    _delete_chat(cid)

                    st.rerun()

    st.divider()

    if st.button(
        "🧹 مسح كل السجل",
        use_container_width=True,
        key="clear_all_chats",
    ):

        _clear_all_chats()

        st.rerun()

    st.caption(
        "السجل الحالي محفوظ داخل جلسة Streamlit الحالية فقط. "
        "لا يتم تخزين مفاتيح API أو إرسال السجل إلى مزود خارجي."
    )


def run_room(
    user_prompt: str,
    history: list[dict],
    rounds: int,
    local_fallback: bool,
    model_overrides: dict[str, str] | None = None,
) -> list[dict]:

    results: list[dict] = []

    working_history = list(
        history
    )

    model_overrides = (
        model_overrides or {}
    )

    seat_snapshot = {}

    for seat in SEATS:

        candidates = (
            get_model_candidates(
                seat
            )
        )

        selected = (
            model_overrides.get(
                seat.name
            )
            or candidates[0]
        )

        seat_snapshot[
            seat.name
        ] = {
            "credential": get_seat_credential(
                seat
            ),
            "model": selected,
            "candidates": candidates,
        }

    order = {
        seat.name: index
        for index, seat in enumerate(
            SEATS
        )
    }

    for round_no in range(
        1,
        rounds + 1,
    ):

        snapshot = _context(
            working_history
        )

        round_results = []

        with ThreadPoolExecutor(
            max_workers=len(SEATS),
            thread_name_prefix="provider",
        ) as pool:

            futures = {
                pool.submit(
                    call_seat,
                    seat,
                    user_prompt,
                    snapshot,
                    round_no,
                    local_fallback,
                    seat_snapshot[
                        seat.name
                    ]["credential"],
                    seat_snapshot[
                        seat.name
                    ]["model"],
                ): seat
                for seat in SEATS
            }

            for future in as_completed(
                futures
            ):

                seat = futures[
                    future
                ]

                try:

                    round_results.append(
                        future.result()
                    )

                except Exception as exc:

                    round_results.append(
                        {
                            "seat": seat.name,
                            "status": "FAILED",
                            "mode": "INTERNAL",
                            "label": (
                                f"🔴 {seat.name} "
                                "— Internal failure"
                            ),
                            "model": (
                                seat_snapshot[
                                    seat.name
                                ]["model"]
                            ),
                            "content": (
                                "حدث فشل داخلي "
                                "معزول في هذا المقعد."
                            ),
                            "error": (
                                f"{exc.__class__.__name__}: "
                                f"{str(exc)[:500]}"
                            ),
                            "latency": 0.0,
                            "attempted_models": [],
                        }
                    )

        round_results.sort(
            key=lambda item:
            order.get(
                item.get(
                    "seat"
                ),
                999,
            )
        )

        for item in round_results:

            if (
                item.get("status")
                == "SUCCESS"
            ):

                working_history.append(
                    {
                        "sender": item[
                            "label"
                        ],
                        "content": item.get(
                            "content",
                            "",
                        ),
                    }
                )

            results.append(item)

    return results


def _render_result(
    item: dict,
) -> None:

    status = item.get(
        "status",
        "FAILED",
    )

    icon = (
        "✅"
        if status == "SUCCESS"
        else "❌"
    )

    label = item.get(
        "label",
        item.get(
            "seat",
            "Unknown",
        ),
    )

    model = item.get(
        "model",
        "unknown",
    )

    latency = item.get(
        "latency",
        0.0,
    )

    with st.chat_message(
        "assistant"
    ):

        st.markdown(
            f"**{icon} {label}**"
        )

        if status == "SUCCESS":

            st.markdown(
                item.get(
                    "content",
                    "",
                )
            )

        else:

            st.error(
                item.get(
                    "content",
                    "فشل غير محدد.",
                )
            )

        with st.expander(
            f"تفاصيل تشخيص {item.get('seat', 'المقعد')}",
            expanded=False,
        ):

            st.write(
                f"**Mode:** "
                f"`{item.get('mode', 'unknown')}`"
            )

            st.write(
                f"**Model:** `{model}`"
            )

            st.write(
                f"**Latency:** "
                f"`{latency:.2f}s`"
            )

            attempted = (
                item.get(
                    "attempted_models"
                )
                or []
            )

            if attempted:

                st.write(
                    "**Models tried:** "
                    f"`{', '.join(attempted)}`"
                )

            error = item.get(
                "error"
            )

            if error:

                st.code(
                    str(error),
                    language="text",
                )

            else:

                st.write(
                    "لا يوجد خطأ مسجل."
                )


def _render_contract_table() -> None:

    with st.expander(
        "🔍 عقود APIs الخمسة",
        expanded=False,
    ):

        rows = []

        for seat in SEATS:

            meta = PROVIDERS[
                seat.provider_id
            ]

            rows.append(
                {
                    "Seat": seat.name,
                    "Provider": seat.provider_id,
                    "Endpoint": meta[
                        "endpoint"
                    ],
                    "Kind": meta[
                        "kind"
                    ],
                    "Models": ", ".join(
                        get_model_candidates(
                            seat
                        )
                    ),
                    "Credential": (
                        "configured"
                        if _configured(
                            seat
                        )
                        else "missing"
                    ),
                }
            )

        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
        )

        st.caption(
            "تُعرض هنا عقود النقل البرمجية فقط. "
            "وجود المفتاح لا يعني أن الحساب يملك صلاحية أو رصيد النموذج."
        )


def _run_hello_diagnostic(
    local_fallback: bool,
) -> None:

    prompt = (
        "Hello. Return one short sentence "
        "confirming that this API contract "
        "can generate text."
    )

    with st.spinner(
        "اختبار Hello للمقاعد الخمسة..."
    ):

        results = run_room(
            prompt,
            [],
            1,
            local_fallback,
        )

    official_success = sum(
        1
        for item in results
        if (
            item.get("status")
            == "SUCCESS"
            and item.get("mode")
            == "OFFICIAL_API"
        )
    )

    local_success = sum(
        1
        for item in results
        if (
            item.get("status")
            == "SUCCESS"
            and item.get("mode")
            == "LOCAL_FALLBACK"
        )
    )

    st.info(
        f"اختبار Hello: "
        f"{official_success + local_success}/5 ناجحة • "
        f"رسمي: {official_success} • "
        f"محلي: {local_success}"
    )

    for item in results:
        _render_result(item)


def run_app() -> None:

    _ensure_chat_state()

    chat = _current_chat()

    st.title(
        "🏛️ AI Council — Shared Context Arena"
    )

    st.caption(
        f"{APP_VERSION} • "
        "المستخدم + خمسة مقاعد أصلية • "
        "سياق مشترك • API Contract Hardening"
    )

    with st.sidebar:

        st.header(
            "⚙️ إعدادات المجلس"
        )

        rounds = st.slider(
            "عدد الجولات",
            1,
            4,
            1,
        )

        local_fallback = st.checkbox(
            "تفعيل Local Engine "
            "كبديل محلي معلن",
            False,
        )

        st.divider()

        _render_history_manager()

        st.divider()

        st.subheader(
            "المقاعد الرسمية"
        )

        configured_count = 0

        for seat in SEATS:

            configured = _configured(
                seat
            )

            configured_count += int(
                configured
            )

            candidates = (
                get_model_candidates(
                    seat
                )
            )

            st.write(
                f"{'🔑' if configured else '⚪'} "
                f"{seat.name}"
            )

            st.caption(
                f"Primary: {candidates[0]}"
            )

            if len(candidates) > 1:

                st.caption(
                    "Fallback models: "
                    + ", ".join(
                        candidates[1:]
                    )
                )

        st.caption(
            f"الاعتمادات المكوّنة: "
            f"{configured_count}/{len(SEATS)}"
        )

        st.caption(
            "🔑 تعني وجود اعتماد في البيئة فقط؛ "
            "ولا تعني نجاح API أو وجود رصيد."
        )

        st.caption(
            "لا يتم عرض أو حفظ مفاتيح API. "
            "الأخطاء تُنقّى من الأسرار قبل عرضها."
        )

        st.caption(
            "Local Engine مستقل ولا ينتحل هوية "
            "أي مزود رسمي."
        )

        _render_contract_table()

        if st.button(
            "🔬 اختبار Hello للمقاعد الخمسة",
            use_container_width=True,
            key="hello_diagnostic",
        ):

            st.session_state[
                "run_hello_diagnostic"
            ] = True

            st.rerun()

    if st.session_state.pop(
        "run_hello_diagnostic",
        False,
    ):

        _run_hello_diagnostic(
            local_fallback
        )

    for item in chat.get(
        "messages",
        [],
    ):

        role = (
            "user"
            if item.get("role")
            == "user"
            else "assistant"
        )

        with st.chat_message(
            role
        ):

            st.markdown(
                f"**{item.get('sender', '')}**\n\n"
                f"{item.get('content', '')}"
            )

    prompt = st.chat_input(
        "اكتب موضوع النقاش على المجلس..."
    )

    if not prompt:
        return

    if (
        chat.get("title")
        == DEFAULT_CHAT_TITLE
    ):

        chat["title"] = _auto_title(
            prompt
        )

    chat["messages"].append(
        {
            "role": "user",
            "sender": "👤 أنت",
            "content": prompt,
        }
    )

    chat["messages"] = _trim_messages(
        chat["messages"]
    )

    _touch(chat)

    with st.chat_message(
        "user"
    ):

        st.markdown(
            f"**👤 أنت**\n\n{prompt}"
        )

    with st.spinner(
        "المجلس يفحص المقاعد الخمسة..."
    ):

        results = run_room(
            prompt,
            chat["messages"],
            rounds,
            local_fallback,
        )

    official_success = sum(
        1
        for item in results
        if (
            item.get("status")
            == "SUCCESS"
            and item.get("mode")
            == "OFFICIAL_API"
        )
    )

    local_success = sum(
        1
        for item in results
        if (
            item.get("status")
            == "SUCCESS"
            and item.get("mode")
            == "LOCAL_FALLBACK"
        )
    )

    total_success = (
        official_success
        + local_success
    )

    st.info(
        f"نتائج هذه العملية: "
        f"{total_success}/"
        f"{len(SEATS) * rounds} ناجحة • "
        f"رسمي: {official_success} • "
        f"محلي: {local_success}"
    )

    for item in results:

        if (
            item.get("status")
            == "SUCCESS"
        ):

            chat["messages"].append(
                {
                    "role": "assistant",
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

        _render_result(item)

    chat["messages"] = _trim_messages(
        chat["messages"]
    )

    _touch(chat)

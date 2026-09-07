from __future__ import annotations

from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from datetime import (
    datetime,
    timezone,
)
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
    configured_count,
    diagnostic_seat,
    get_model_candidates,
)


APP_VERSION = (
    "V21.9-SIX-ROOM-ATTACHMENTS-DIAGNOSTIC"
)


def _now() -> str:

    return datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M UTC"
    )


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

        st.session_state.chats = [
            chat
        ]

        st.session_state.active_chat_id = (
            chat["id"]
        )

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


def _active_chat() -> dict:

    for chat in st.session_state.chats:

        if (
            chat["id"]
            == st.session_state.active_chat_id
        ):
            return chat

    chat = _new_chat()

    st.session_state.chats.insert(
        0,
        chat,
    )

    st.session_state.active_chat_id = (
        chat["id"]
    )

    return chat


def _title_from_prompt(
    prompt: str,
) -> str:

    clean = re.sub(
        r"\s+",
        " ",
        prompt,
    ).strip()

    return (
        clean[:48]
        + (
            "…"
            if len(clean) > 48
            else ""
        )
        or "محادثة جديدة"
    )


def _shared_context(
    chat: dict,
    max_chars: int = 30000,
) -> str:

    lines = []

    for index, item in enumerate(
        chat["messages"]
    ):

        if (
            index
            == len(chat["messages"]) - 1
            and item.get("role")
            == "user"
        ):
            continue

        if item.get("role") == "user":

            lines.append(
                f"USER: "
                f"{item.get('content', '')}"
            )

        elif item.get("role") == "assistant":

            lines.append(
                f"{item.get('seat', 'AI')}: "
                f"{item.get('content', '')}"
            )

    return "\n\n".join(lines)[-max_chars:]


def _worker_failure(
    seat,
    exc: Exception,
) -> dict:

    return {
        "seat": seat.key,
        "name": seat.name,
        "label": seat.label,
        "status": "FAILED",
        "mode": "internal",
        "model": get_model_candidates(
            seat
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
) -> list[dict]:

    snapshot = _shared_context(
        chat
    )

    results: dict[
        str,
        dict,
    ] = {}

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
                credentials.get(
                    seat.key
                ),
                attachments,
            ): seat
            for seat in SEATS
        }

        for future in as_completed(
            futures
        ):

            seat = futures[future]

            try:

                results[
                    seat.key
                ] = future.result()

            except Exception as exc:

                results[
                    seat.key
                ] = _worker_failure(
                    seat,
                    exc,
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
            local_fallback,
            credentials,
            attachments,
        )

        all_results.extend(
            round_results
        )

        for result in round_results:

            if (
                result["status"]
                in (
                    "SUCCESS",
                    "LOCAL",
                )
                and result["content"]
            ):

                chat["messages"].append(
                    {
                        "role": "assistant",
                        "seat": result["name"],
                        "label": result["label"],
                        "content": result["content"],
                        "round": round_no,
                        "mode": result["mode"],
                        "model": result["model"],
                        "created_at": _now(),
                    }
                )

    return all_results


def _run_provider_diagnostics(
    credentials: dict,
) -> list[dict]:

    results: dict[
        str,
        dict,
    ] = {}

    with ThreadPoolExecutor(
        max_workers=len(SEATS),
        thread_name_prefix="diagnostic",
    ) as pool:

        futures = {
            pool.submit(
                diagnostic_seat,
                seat,
                credentials.get(
                    seat.key
                ),
            ): seat
            for seat in SEATS
        }

        for future in as_completed(
            futures
        ):

            seat = futures[future]

            try:

                results[
                    seat.key
                ] = future.result()

            except Exception as exc:

                results[
                    seat.key
                ] = _worker_failure(
                    seat,
                    exc,
                )

    return [
        results[seat.key]
        for seat in SEATS
    ]


def _render_sidebar(
    rounds: int,
    local_fallback: bool,
    credentials: dict,
) -> tuple[int, bool]:

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

        local_fallback = st.checkbox(
            "تفعيل Local Engine كبديل محلي معلن",
            value=local_fallback,
        )

        st.session_state.rounds = rounds
        st.session_state.local_fallback = (
            local_fallback
        )

        st.divider()

        st.subheader(
            "🔬 تشخيص المزودين"
        )

        st.caption(
            "يفحص كل API رسمي بشكل مستقل "
            "برسالة اختبار صغيرة، "
            "بدون Local Engine وبدون مرفقات."
        )

        if st.button(
            "🔍 فحص المزودين الخمسة الآن",
            use_container_width=True,
        ):

            with st.spinner(
                "تشخيص ChatGPT وGemini "
                "وClaude وGrok وKimi "
                "بالتوازي…"
            ):

                st.session_state.last_diagnostics = (
                    _run_provider_diagnostics(
                        credentials
                    )
                )

            st.rerun()

        st.divider()

        st.subheader(
            "💬 المحادثة الحالية"
        )

        chat = _active_chat()

        st.caption(
            f"اسم المحادثة: "
            f"{chat['title']}"
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

        st.subheader(
            "📚 السجل"
        )

        for item in list(
            st.session_state.chats
        ):

            if st.button(
                (
                    "🟢"
                    if item["id"]
                    == st.session_state.active_chat_id
                    else "⚪"
                )
                + " "
                + item["title"],
                key=f"load_{item['id']}",
                use_container_width=True,
            ):

                st.session_state.active_chat_id = (
                    item["id"]
                )

                st.session_state.last_results = []

                st.rerun()

            st.caption(
                f"{len(item['messages'])} رسالة "
                f"• {item['created_at']}"
            )

        c3, c4 = st.columns(2)

        with c3:

            if st.button(
                "🗑️ حذف الحالية",
                use_container_width=True,
            ):

                if len(
                    st.session_state.chats
                ) == 1:

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
                        for x
                        in st.session_state.chats
                        if x["id"]
                        != chat["id"]
                    ]

                    st.session_state.active_chat_id = (
                        st.session_state.chats[0][
                            "id"
                        ]
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

        st.subheader(
            "🔌 الاعتمادات والنماذج"
        )

        for seat in SEATS:

            models = get_model_candidates(
                seat
            )

            icon = (
                "🟢"
                if credentials.get(
                    seat.key
                )
                else "⚪"
            )

            st.markdown(
                f"{icon} **{seat.name}**"
            )

            st.caption(
                f"Primary: `{models[0]}`"
            )

            if len(models) > 1:

                st.caption(
                    "Fallback: "
                    + ", ".join(
                        f"`{m}`"
                        for m in models[1:]
                    )
                )

        st.caption(
            f"اعتمادات موجودة: "
            f"{configured_count(credentials)}/5"
        )

        st.caption(
            "🔑 وجود المفتاح لا يثبت نجاح API "
            "ولا وجود رصيد/ائتمان."
        )

        st.caption(
            "المفاتيح لا تُعرض في الواجهة "
            "ولا تُحفظ في History."
        )

    return (
        rounds,
        local_fallback,
    )


def _render_user_room(
    chat: dict,
) -> None:

    with st.container(
        height=500,
        border=True,
    ):

        st.subheader(
            "👤 أنت"
        )

        user_messages = [
            m
            for m
            in chat["messages"]
            if m.get("role")
            == "user"
        ]

        if not user_messages:

            st.caption(
                "اكتب رسالة أو أرفق "
                "صورة/ملف/مجلد "
                "من خانة الإدخال السفلية."
            )

        for message in user_messages:

            with st.chat_message(
                "user"
            ):

                content = message.get(
                    "content",
                    "",
                )

                if content:
                    st.write(content)

                for attachment in message.get(
                    "attachments",
                    [],
                ):

                    st.caption(
                        f"📎 "
                        f"{attachment.get('name', 'attachment')} "
                        f"· "
                        f"{attachment.get('mime', 'file')} "
                        f"· "
                        f"{attachment.get('size', 0)} bytes"
                    )


def _render_ai_room(
    chat: dict,
    seat,
) -> None:

    with st.container(
        height=500,
        border=True,
    ):

        st.subheader(
            seat.label
        )

        models = get_model_candidates(
            seat
        )

        st.caption(
            f"Primary: `{models[0]}`"
        )

        messages = [
            m
            for m
            in chat["messages"]
            if m.get("seat")
            == seat.name
        ]

        if not messages:

            st.caption(
                "بانتظار أول جولة…"
            )

            return

        for message in messages:

            badge = (
                "Official API"
                if message.get("mode")
                == "official"
                else "Local Engine"
            )

            st.markdown(
                f"**Round "
                f"{message.get('round', '?')} "
                f"· {badge} "
                f"· `{message.get('model', '')}`**"
            )

            st.markdown(
                message.get(
                    "content",
                    "",
                )
            )

            st.divider()


def _render_six_rooms(
    chat: dict,
) -> None:

    rows = [
        (None, SEATS[0]),
        (SEATS[1], SEATS[2]),
        (SEATS[3], SEATS[4]),
    ]

    for left, right in rows:

        cols = st.columns(
            2,
            gap="medium",
        )

        with cols[0]:

            (
                _render_user_room(chat)
                if left is None
                else _render_ai_room(
                    chat,
                    left,
                )
            )

        with cols[1]:

            _render_ai_room(
                chat,
                right,
            )


def _render_result_line(
    result: dict,
    diagnostic_only: bool = False,
) -> None:

    if result["status"] == "SUCCESS":

        prefix = (
            "🟢"
            if diagnostic_only
            else "✅"
        )

        st.success(
            f"{prefix} "
            f"{result['label']} "
            f"— Official API "
            f"— `{result['model']}` "
            f"— {result['latency']}s"
        )

        return

    with st.expander(
        f"🔴 "
        f"{result['label']} "
        f"— Official API failed",
        expanded=diagnostic_only,
    ):

        st.write(
            result.get("error")
            or "تعذر الحصول "
            "على رد رسمي."
        )

        st.write(
            "Attempted models:",
            ", ".join(
                result.get(
                    "attempted_models",
                    [],
                )
            )
            or "none",
        )


def _render_diagnostics(
    results: list[dict],
    title: str = "🔎 التشخيص والنتائج",
) -> None:

    official = sum(
        r["status"] == "SUCCESS"
        for r in results
    )

    local = sum(
        r["status"] == "LOCAL"
        for r in results
    )

    failed = sum(
        r["status"] == "FAILED"
        for r in results
    )

    st.subheader(title)

    st.info(
        f"آخر عملية: "
        f"{official + local}/5 استجابات "
        f"• رسمي: {official} "
        f"• محلي: {local} "
        f"• فشل: {failed}"
    )

    for result in results:

        if result["status"] == "SUCCESS":

            _render_result_line(
                result
            )

        elif result["status"] == "LOCAL":

            with st.expander(
                f"🟡 "
                f"{result['label']} "
                f"— Local Engine"
            ):

                st.write(
                    result.get("error")
                    or "تم استخدام "
                    "Local Engine."
                )

                st.write(
                    "Attempted models:",
                    ", ".join(
                        result.get(
                            "attempted_models",
                            [],
                        )
                    )
                    or "none",
                )

        else:

            _render_result_line(
                result
            )


def _render_provider_diagnostics(
    results: list[dict],
) -> None:

    if not results:
        return

    st.subheader(
        "🧪 الفحص المستقل للمزودين"
    )

    st.caption(
        "هذا الاختبار لا يستخدم "
        "Local Engine؛ كل نتيجة هنا "
        "تخص API الرسمي مباشرة."
    )

    for result in results:

        _render_result_line(
            result,
            diagnostic_only=True,
        )


def _render_attachment_picker() -> list[dict]:

    nonce = st.session_state.folder_nonce

    with st.expander(
        "📁 إرفاق مجلد",
        expanded=False,
    ):

        st.caption(
            "اختر مجلدًا كاملًا؛ "
            "ستُرسل ملفاته مع الرسالة التالية. "
            "الحد: 20 ملفًا / 25 MB إجمالًا."
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

    return list(
        folder or []
    )


def _submission_files(
    submission,
    folder_files: list[object],
) -> list[dict]:

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

        st.error(
            str(exc)
        )

        return []


def run_app() -> None:

    _init_state()

    credentials = capture_credentials()

    rounds, local_fallback = (
        _render_sidebar(
            st.session_state.rounds,
            st.session_state.local_fallback,
            credentials,
        )
    )

    chat = _active_chat()

    st.title(
        "🏛️ AI Council — "
        "Six-Room Shared Context Arena"
    )

    st.caption(
        f"{APP_VERSION} "
        "• المستخدم + خمسة مقاعد "
        "• سياق مشترك "
        "• استدعاءات متوازية "
        f"• Provider: {PROVIDER_VERSION}"
    )

    st.markdown(
        "**العقد التشغيلي:** "
        "رسالة واحدة تُرسل بالتوازي "
        "إلى ChatGPT وGemini وClaude "
        "وGrok وKimi. "
        "لا يظهر وسم Official API "
        "إلا بعد نجاح طلب API رسمي "
        "مصادق عليه."
    )

    _render_six_rooms(
        chat
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

    if submission:

        prompt = (
            getattr(
                submission,
                "text",
                "",
            )
            or ""
        ).strip()

        attachments = _submission_files(
            submission,
            folder_files,
        )

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

            chat["messages"].append(
                {
                    "role": "user",
                    "content": prompt,
                    "attachments":
                        public_metadata(
                            attachments
                        ),
                    "created_at": _now(),
                }
            )

            with st.spinner(
                "المجلس ينفذ الجولة "
                "بالتوازي…"
            ):

                results = _run_council(
                    prompt,
                    chat,
                    rounds,
                    local_fallback,
                    credentials,
                    attachments,
                )

            st.session_state.last_results = (
                results
            )

            st.session_state.folder_nonce += 1

            st.rerun()

    if st.session_state.last_diagnostics:

        st.divider()

        _render_provider_diagnostics(
            st.session_state.last_diagnostics
        )

    if st.session_state.last_results:

        st.divider()

        _render_diagnostics(
            st.session_state.last_results
        )

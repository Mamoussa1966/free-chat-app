from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib

import streamlit as st

from providers import (
    SEATS,
    call_seat,
    get_models,
    get_seat_credential,
)


APP_VERSION = "V21.4-FINAL-DIAGNOSTIC"

MAX_CONTEXT_CHARS = 50000


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

    return "\n\n".join(chunks)[-max_chars:]


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


def run_room(
    user_prompt: str,
    history: list[dict],
    rounds: int,
    local_fallback: bool,
) -> list[dict]:

    results: list[dict] = []

    working_history = list(history)

    # ---------------------------------------------------------
    # IMPORTANT:
    # Resolve secrets and models BEFORE worker threads.
    # Streamlit state is not accessed by provider workers.
    # ---------------------------------------------------------

    seat_snapshot = {
        seat.name: {
            "credential": (
                get_seat_credential(seat)
            ),
            "model": (
                get_models(seat)[0]
            ),
        }
        for seat in SEATS
    }

    # ---------------------------------------------------------
    # ROUND BARRIER
    # ---------------------------------------------------------

    for round_no in range(
        1,
        rounds + 1,
    ):

        snapshot = _context(
            working_history
        )

        round_results: list[dict] = []

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

                    # A single worker must NEVER
                    # terminate the entire council.
                    round_results.append(
                        {
                            "seat": seat.name,
                            "status": "FAILED",
                            "mode": "INTERNAL",
                            "label": (
                                f"🔴 {seat.name} "
                                "— Internal failure"
                            ),
                            "model": seat_snapshot[
                                seat.name
                            ]["model"],
                            "content": (
                                "حدث فشل داخلي "
                                "معزول في هذا المقعد."
                            ),
                            "error": (
                                f"{exc.__class__.__name__}: "
                                f"{str(exc)[:500]}"
                            ),
                            "latency": 0.0,
                        }
                    )

        # -----------------------------------------------------
        # Deterministic seat order
        # -----------------------------------------------------

        order = {
            seat.name: index
            for index, seat in enumerate(SEATS)
        }

        round_results.sort(
            key=lambda item: order.get(
                item.get("seat"),
                999,
            )
        )

        # -----------------------------------------------------
        # Commit round simultaneously
        # -----------------------------------------------------

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

        # -----------------------------------------------------
        # SAFE DIAGNOSTICS
        # -----------------------------------------------------

        with st.expander(
            (
                f"تفاصيل تشخيص "
                f"{item.get('seat', 'المقعد')}"
            ),
            expanded=False,
        ):

            st.write(
                f"**Mode:** "
                f"`{item.get('mode', 'unknown')}`"
            )

            st.write(
                f"**Model:** "
                f"`{model}`"
            )

            st.write(
                f"**Latency:** "
                f"`{latency:.2f}s`"
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


def run_app() -> None:

    st.title(
        "🏛️ AI Council — Shared Context Arena"
    )

    st.caption(
        f"{APP_VERSION} • "
        "المستخدم + خمسة مقاعد أصلية • "
        "سياق مشترك • "
        "تشخيص آمن للأخطاء"
    )

    if "history" not in st.session_state:
        st.session_state.history = []

    # =========================================================
    # SIDEBAR
    # =========================================================

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
            "تفعيل Local Engine كبديل محلي معلن",
            False,
        )

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

            model = get_models(
                seat
            )[0]

            st.write(
                f"{'🔑' if configured else '⚪'} "
                f"{seat.name}"
            )

            st.caption(
                f"Model: {model}"
            )

        st.caption(
            f"الاعتمادات المكوّنة: "
            f"{configured_count}/{len(SEATS)}"
        )

        st.caption(
            "🔑 تعني وجود اعتماد في البيئة فقط؛ "
            "ولا تعني نجاح API."
        )

        st.caption(
            "لا يتم عرض أو حفظ مفاتيح API. "
            "الأخطاء تُنقّى من الأسرار قبل عرضها."
        )

        st.caption(
            "Local Engine مستقل ولا ينتحل "
            "هوية أي مزود رسمي."
        )

    # =========================================================
    # HISTORY
    # =========================================================

    for item in st.session_state.history:

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
                f"**{item.get('sender', '')}**"
                f"\n\n"
                f"{item.get('content', '')}"
            )

    # =========================================================
    # INPUT
    # =========================================================

    prompt = st.chat_input(
        "اكتب موضوع النقاش على المجلس..."
    )

    if not prompt:
        return

    st.session_state.history.append(
        {
            "role": "user",
            "sender": "👤 أنت",
            "content": prompt,
        }
    )

    with st.chat_message("user"):

        st.markdown(
            f"**👤 أنت**\n\n{prompt}"
        )

    # =========================================================
    # EXECUTION
    # =========================================================

    with st.spinner(
        "المجلس يفحص المقاعد الخمسة..."
    ):

        results = run_room(
            prompt,
            st.session_state.history,
            rounds,
            local_fallback,
        )

    # =========================================================
    # SUMMARY
    # =========================================================

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

    total_expected = (
        len(SEATS)
        * rounds
    )

    st.info(
        f"نتائج هذه العملية: "
        f"{total_success}/{total_expected} ناجحة • "
        f"رسمي: {official_success} • "
        f"محلي: {local_success}"
    )

    # =========================================================
    # RESULTS
    # =========================================================

    for item in results:

        if (
            item.get("status")
            == "SUCCESS"
        ):

            st.session_state.history.append(
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

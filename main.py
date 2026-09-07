from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import os
import streamlit as st

from providers import SEATS, call_seat, get_seat_credential


APP_VERSION = "V20.0-MULTI-MODEL-VERIFICATION-GATED"


def _context(
    history: list[dict],
    max_chars: int = 50000,
) -> str:

    chunks: list[str] = []

    for item in history:
        chunks.append(
            f"{item.get('sender', 'Unknown')}: "
            f"{item.get('content', '')}"
        )

    text = "\n\n".join(chunks)

    return text[-max_chars:]


def _credential_map() -> dict[str, str | None]:
    """
    Resolve credentials in the Streamlit main thread.

    This prevents worker threads from accessing st.secrets.
    """

    credentials: dict[str, str | None] = {}

    for seat in SEATS:
        try:
            credentials[seat.name] = get_seat_credential(seat)
        except Exception:
            credentials[seat.name] = None

    return credentials


def _configured_seat(
    seat,
    credentials: dict[str, str | None],
) -> bool:

    return bool(credentials.get(seat.name))


def run_room(
    user_prompt: str,
    history: list[dict],
    rounds: int,
    local_fallback: bool,
) -> list[dict]:

    results: list[dict] = []

    working_history = list(history)

    credentials = _credential_map()

    for round_no in range(1, rounds + 1):

        # Barrier model:
        # every seat receives the same snapshot.
        snapshot = _context(working_history)

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
                    credentials.get(seat.name),
                ): seat
                for seat in SEATS
            }

            for future in as_completed(futures):

                seat = futures[future]

                try:
                    result = future.result()

                except Exception as exc:
                    result = {
                        "seat": seat.name,
                        "label": f"❌ {seat.name} — Worker Error",
                        "provider": seat.provider_id,
                        "model": seat.default_model,
                        "status": "FAILED",
                        "mode": "NONE",
                        "round": round_no,
                        "content": (
                            f"حدث خطأ داخلي أثناء تشغيل "
                            f"مقعد {seat.name}."
                        ),
                        "error": str(exc)[:1200],
                    }

                round_results.append(result)

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

        for item in round_results:

            if item.get("status") == "SUCCESS":
                working_history.append(
                    {
                        "sender": item.get(
                            "label",
                            item.get("seat", "Unknown"),
                        ),
                        "content": item.get(
                            "content",
                            "",
                        ),
                    }
                )

            results.append(item)

    return results


def run_app() -> None:

    st.title("🏛️ AI Council — Shared Context Arena")

    st.caption(
        f"{APP_VERSION} • "
        "خمسة مقاعد أصلية + سياق مشترك + جولات متزامنة"
    )

    if "history" not in st.session_state:
        st.session_state.history = []

    with st.sidebar:

        st.header("⚙️ إعدادات المجلس")

        rounds = st.slider(
            "عدد الجولات",
            min_value=1,
            max_value=4,
            value=2,
        )

        local_fallback = st.checkbox(
            "تفعيل Local Engine كبديل محلي معلن",
            value=False,
        )

        st.divider()

        st.subheader("المقاعد")

        credentials = _credential_map()

        for seat in SEATS:

            configured = _configured_seat(
                seat,
                credentials,
            )

            if configured:
                st.write(
                    f"🟢 {seat.name}"
                )
            else:
                st.write(
                    f"⚪ {seat.name}"
                )

            st.caption(
                f"Model: {seat.default_model}"
            )

        st.divider()

        st.caption(
            "المفاتيح لا تُعرض في الواجهة ولا تُحفظ في سجل المحادثة."
        )

        st.caption(
            "Local Engine مستقل عن النماذج التجارية ولا ينتحل هويتها."
        )

    # ---------------------------------------------------------------
    # Previous conversation
    # ---------------------------------------------------------------

    for item in st.session_state.history:

        role = (
            "user"
            if item.get("role") == "user"
            else "assistant"
        )

        with st.chat_message(role):

            st.markdown(
                f"**{item.get('sender', '')}**\n\n"
                f"{item.get('content', '')}"
            )

    # ---------------------------------------------------------------
    # User input
    # ---------------------------------------------------------------

    prompt = st.chat_input(
        "اكتب موضوع النقاش على المجلس..."
    )

    if not prompt:
        return

    prompt = prompt.strip()

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

    # ---------------------------------------------------------------
    # Council execution
    # ---------------------------------------------------------------

    with st.spinner(
        "المجلس يناقش..."
    ):

        results = run_room(
            prompt,
            st.session_state.history,
            rounds,
            local_fallback,
        )

    # ---------------------------------------------------------------
    # Results
    # ---------------------------------------------------------------

    for item in results:

        label = item.get(
            "label",
            item.get("seat", "Unknown"),
        )

        content = item.get(
            "content",
            "",
        )

        st.session_state.history.append(
            {
                "role": "assistant",
                "sender": label,
                "content": content,
            }
        )

        with st.chat_message("assistant"):

            st.markdown(
                f"**{label}**\n\n{content}"
            )

        error = item.get("error", "")

        if error:
            with st.expander(
                f"تفاصيل حالة {item.get('seat', 'المقعد')}"
            ):
                st.warning(
                    error
                )

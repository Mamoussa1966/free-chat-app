# -*- coding: utf-8 -*-
"""
AI Council V21 - Main Room Coordinator

Architecture:
    5 official AI providers:
        ChatGPT
        Gemini
        Claude
        Grok
        Kimi

    + Seat 6:
        Human user

Design goals:
    - Shared-context council
    - Round barrier
    - Concurrent provider execution
    - Provider failure isolation
    - No API secrets in UI
    - Compatible with providers.py:
          from providers import SEATS, call_seat
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

import streamlit as st

from providers import SEATS, call_seat


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_CONTEXT_CHARS = max(
    5_000,
    min(int(os.getenv("MAX_CONTEXT_CHARS", "50000")), 200_000),
)

MAX_ROUNDS = max(
    1,
    min(int(os.getenv("MAX_ROUNDS", "4")), 8),
)


# ---------------------------------------------------------------------------
# Context handling
# ---------------------------------------------------------------------------

def _safe_text(value: Any) -> str:
    """Convert arbitrary values to safe display/context text."""
    if value is None:
        return ""

    try:
        return str(value).strip()
    except Exception:
        return ""


def _context(
    history: List[Dict[str, Any]],
    max_chars: int = MAX_CONTEXT_CHARS,
) -> str:
    """
    Build a deterministic shared-context snapshot.

    The newest content is retained when the context exceeds the limit.
    """
    chunks: List[str] = []

    for item in history:
        if not isinstance(item, dict):
            continue

        sender = _safe_text(item.get("sender")) or "Unknown"
        content = _safe_text(item.get("content"))

        if not content:
            continue

        chunks.append(f"{sender}: {content}")

    text = "\n\n".join(chunks)

    if len(text) <= max_chars:
        return text

    return text[-max_chars:]


# ---------------------------------------------------------------------------
# Provider execution
# ---------------------------------------------------------------------------

def _failed_provider_result(seat: Any, exc: Exception) -> Dict[str, Any]:
    """
    Convert an unexpected worker exception into an isolated result.

    Important:
        One broken provider must NEVER terminate the entire council round.
    """
    seat_name = _safe_text(getattr(seat, "name", "Unknown")) or "Unknown"

    return {
        "seat": seat_name,
        "status": "FAILED",
        "mode": "COORDINATOR_ERROR",
        "label": f"🔴 {seat_name} — Coordinator error",
        "content": (
            "تعذر إكمال استدعاء هذا المقعد بسبب خطأ داخلي في المنسق. "
            f"نوع الخطأ: {type(exc).__name__}"
        ),
        "latency": 0.0,
    }


def _call_one(
    seat: Any,
    user_prompt: str,
    snapshot: str,
    round_no: int,
    local_fallback: bool,
) -> Dict[str, Any]:
    """
    Execute exactly one provider call.

    This wrapper exists so unexpected exceptions remain isolated
    from the ThreadPoolExecutor.
    """
    try:
        result = call_seat(
            seat,
            user_prompt,
            snapshot,
            round_no,
            local_fallback,
        )

        if not isinstance(result, dict):
            return {
                "seat": getattr(seat, "name", "Unknown"),
                "status": "FAILED",
                "mode": "COORDINATOR_ERROR",
                "label": (
                    f"🔴 {getattr(seat, 'name', 'Unknown')} "
                    "— Invalid provider result"
                ),
                "content": "المزود أعاد نتيجة غير صالحة.",
                "latency": 0.0,
            }

        return result

    except Exception as exc:
        return _failed_provider_result(seat, exc)


# ---------------------------------------------------------------------------
# Six-seat room
# ---------------------------------------------------------------------------

def run_room(
    user_prompt: str,
    history: List[Dict[str, Any]],
    rounds: int,
    local_fallback: bool,
) -> List[Dict[str, Any]]:
    """
    Run the AI council.

    Seat model:
        Seats 1-5 = official AI providers
        Seat 6     = human user

    Barrier semantics:
        Round N starts from ONE immutable snapshot.

        All five AI providers receive the same snapshot.

        Their results are collected.

        Only after every provider task has completed does the coordinator
        commit successful results to the working history.

        Therefore:
            Provider A cannot see Provider B's Round-N response
            until Round N+1.
    """
    try:
        rounds = int(rounds)
    except (TypeError, ValueError):
        rounds = 1

    rounds = max(1, min(rounds, MAX_ROUNDS))

    prompt = _safe_text(user_prompt)

    if not prompt:
        return []

    working_history: List[Dict[str, Any]] = list(history or [])
    results: List[Dict[str, Any]] = []

    # Stable ordering: ChatGPT -> Gemini -> Claude -> Grok -> Kimi.
    seat_order = {
        getattr(seat, "name", f"seat-{index}"): index
        for index, seat in enumerate(SEATS)
    }

    for round_no in range(1, rounds + 1):

        # ---------------------------------------------------------------
        # Barrier 1:
        # Freeze the shared context BEFORE launching any provider.
        # ---------------------------------------------------------------
        snapshot = _context(working_history)

        round_results: List[Dict[str, Any]] = []

        # ---------------------------------------------------------------
        # Execute all five official seats concurrently.
        # ---------------------------------------------------------------
        max_workers = max(1, len(SEATS))

        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="ai-council",
        ) as executor:

            futures = {
                executor.submit(
                    _call_one,
                    seat,
                    prompt,
                    snapshot,
                    round_no,
                    bool(local_fallback),
                ): seat
                for seat in SEATS
            }

            for future in as_completed(futures):
                seat = futures[future]

                try:
                    result = future.result()
                except Exception as exc:
                    # Defensive second barrier against executor-level errors.
                    result = _failed_provider_result(seat, exc)

                round_results.append(result)

        # ---------------------------------------------------------------
        # Restore deterministic seat order.
        # Completion order must NOT determine room order.
        # ---------------------------------------------------------------
        round_results.sort(
            key=lambda item: seat_order.get(
                _safe_text(item.get("seat")),
                10_000,
            )
        )

        # ---------------------------------------------------------------
        # Barrier 2:
        # Commit the completed round only AFTER all five calls finish.
        # ---------------------------------------------------------------
        for item in round_results:

            results.append(item)

            status = _safe_text(item.get("status")).upper()

            if status == "SUCCESS":
                sender = _safe_text(item.get("label")) or "AI Council"
                content = _safe_text(item.get("content"))

                if content:
                    working_history.append(
                        {
                            "role": "assistant",
                            "sender": sender,
                            "content": content,
                            "round": round_no,
                        }
                    )

    return results


# ---------------------------------------------------------------------------
# Seat configuration helpers
# ---------------------------------------------------------------------------

def _is_configured(seat: Any) -> bool:
    """
    Determine whether an official credential appears configured.

    This function only returns True/False.
    It never exposes the secret.
    """
    env_key = _safe_text(getattr(seat, "env_key", ""))

    if env_key and os.getenv(env_key):
        return True

    provider_id = _safe_text(getattr(seat, "provider_id", ""))

    aliases = {
        "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "xai": ("XAI_API_KEY", "GROK_API_KEY"),
        "kimi": ("KIMI_API_KEY", "MOONSHOT_API_KEY"),
        "anthropic": (
            "ANTHROPIC_API_KEY",
        ),
        "openai": (
            "OPENAI_API_KEY",
        ),
    }

    for key in aliases.get(provider_id, ()):
        if os.getenv(key):
            return True

    try:
        for key in aliases.get(provider_id, ()):
            value = st.secrets.get(key)
            if value is not None and str(value).strip():
                return True

        if env_key:
            value = st.secrets.get(env_key)
            if value is not None and str(value).strip():
                return True

    except Exception:
        pass

    return False


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def run_app() -> None:
    """
    Streamlit application entry point.

    app.py calls:
        from main import run_app
        run_app()
    """

    st.title("🏛️ AI Council — Six-Seat Room")

    st.caption(
        "V21 Clean Baseline • "
        "ChatGPT + Gemini + Claude + Grok + Kimi + أنت"
    )

    # ---------------------------------------------------------------
    # Session state
    # ---------------------------------------------------------------

    if "history" not in st.session_state:
        st.session_state.history = []

    if "last_round_results" not in st.session_state:
        st.session_state.last_round_results = []

    # ---------------------------------------------------------------
    # Sidebar
    # ---------------------------------------------------------------

    with st.sidebar:
        st.header("⚙️ إعدادات المجلس")

        rounds = st.slider(
            "عدد الجولات",
            min_value=1,
            max_value=MAX_ROUNDS,
            value=min(2, MAX_ROUNDS),
            step=1,
        )

        local_fallback = st.checkbox(
            "تفعيل Ollama كبديل محلي معلن",
            value=False,
            help=(
                "إذا فشل المزود الرسمي يمكن استخدام Ollama المحلي. "
                "سيتم تمييز الرد بوضوح على أنه LOCAL."
            ),
        )

        st.divider()

        st.subheader("🪑 المقاعد الخمسة الأصلية")

        for seat in SEATS:
            configured = _is_configured(seat)

            if configured:
                st.write(
                    f"🟢 {getattr(seat, 'name', 'Unknown')} — configured"
                )
            else:
                st.write(
                    f"⚪ {getattr(seat, 'name', 'Unknown')} — unavailable"
                )

        st.divider()

        st.subheader("🪑 المقعد السادس")

        st.write("🟣 أنت — Human Seat")

        st.caption(
            "أنت صاحب القرار النهائي في الغرفة. "
            "المقاعد الخمسة تقدم التحليل، وأنت المقعد السادس."
        )

        st.divider()

        if st.button("🗑️ مسح سجل الغرفة", use_container_width=True):
            st.session_state.history = []
            st.session_state.last_round_results = []
            st.rerun()

        st.caption(
            "لا يتم عرض مفاتيح API أو إدراجها في واجهة المستخدم."
        )

    # ---------------------------------------------------------------
    # Display conversation history
    # ---------------------------------------------------------------

    for item in st.session_state.history:
        if not isinstance(item, dict):
            continue

        role = (
            "user"
            if item.get("role") == "user"
            else "assistant"
        )

        sender = _safe_text(item.get("sender"))
        content = _safe_text(item.get("content"))

        with st.chat_message(role):
            if sender:
                st.markdown(f"**{sender}**")

            if content:
                st.markdown(content)

    # ---------------------------------------------------------------
    # Human Seat — input
    # ---------------------------------------------------------------

    prompt = st.chat_input(
        "المقعد السادس — اكتب موضوع النقاش هنا..."
    )

    if not prompt:
        return

    prompt = _safe_text(prompt)

    if not prompt:
        st.warning("يرجى إدخال سؤال أو موضوع للنقاش.")
        return

    # ---------------------------------------------------------------
    # Commit user's message FIRST.
    #
    # This means the five AI seats receive the human's current
    # question as part of the same shared room state.
    # ---------------------------------------------------------------

    user_message = {
        "role": "user",
        "sender": "🟣 المقعد السادس — أنت",
        "content": prompt,
    }

    st.session_state.history.append(user_message)

    with st.chat_message("user"):
        st.markdown("**🟣 المقعد السادس — أنت**")
        st.markdown(prompt)

    # ---------------------------------------------------------------
    # Execute council
    # ---------------------------------------------------------------

    with st.spinner(
        "🏛️ المقاعد الخمسة تحلل السؤال بالتوازي..."
    ):
        results = run_room(
            user_prompt=prompt,
            history=st.session_state.history,
            rounds=rounds,
            local_fallback=local_fallback,
        )

    st.session_state.last_round_results = results

    # ---------------------------------------------------------------
    # Display results
    # ---------------------------------------------------------------

    if not results:
        st.warning(
            "لم يتم الحصول على نتائج من المقاعد."
        )
        return

    for item in results:
        label = _safe_text(item.get("label")) or "AI Seat"
        content = _safe_text(item.get("content"))
        status = _safe_text(item.get("status")).upper()

        with st.chat_message("assistant"):

            st.markdown(f"**{label}**")

            if content:
                st.markdown(content)

            latency = item.get("latency")

            if isinstance(latency, (int, float)):
                st.caption(
                    f"الحالة: {status or 'UNKNOWN'} • "
                    f"زمن الاستجابة: {latency:.2f}s"
                )


# ---------------------------------------------------------------------------
# Direct execution support
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_app()

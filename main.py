from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st
import os

from providers import SEATS, call_seat


def _context(history: list[dict], max_chars: int = 50000) -> str:
    chunks = []
    for item in history:
        chunks.append(f"{item.get('sender', 'Unknown')}: {item.get('content', '')}")
    text = '\n\n'.join(chunks)
    return text[-max_chars:]


def run_room(user_prompt: str, history: list[dict], rounds: int, local_fallback: bool) -> list[dict]:
    results: list[dict] = []
    working_history = list(history)
    for round_no in range(1, rounds + 1):
        # Barrier model: each round starts from the same snapshot, so no seat gets an unfair
        # ordering advantage. All five calls are concurrent; the entire round is then committed.
        snapshot = _context(working_history)
        round_results = []
        with ThreadPoolExecutor(max_workers=len(SEATS)) as pool:
            futures = {
                pool.submit(call_seat, seat, user_prompt, snapshot, round_no, local_fallback): seat
                for seat in SEATS
            }
            for future in as_completed(futures):
                round_results.append(future.result())
        order = {seat.name: i for i, seat in enumerate(SEATS)}
        round_results.sort(key=lambda item: order[item['seat']])
        for item in round_results:
            if item['status'] == 'SUCCESS':
                working_history.append({'sender': item['label'], 'content': item['content']})
            results.append(item)
    return results


def run_app() -> None:
    st.title('🏛️ AI Council — Shared Context Arena')
    st.caption('V20 Secure • خمسة مقاعد أصلية + سياق مشترك + جولات متزامنة')

    if 'history' not in st.session_state:
        st.session_state.history = []

    with st.sidebar:
        st.header('⚙️ إعدادات المجلس')
        rounds = st.slider('عدد الجولات', 1, 4, 2)
        local_fallback = st.checkbox('تفعيل Ollama كبديل محلي معلن', False)
        st.divider()
        st.subheader('المقاعد')
        for seat in SEATS:
            configured = bool(os.getenv(seat.env_key) or (os.getenv('GROK_API_KEY') if seat.name == 'Grok' else None))
            try:
                configured = configured or bool(st.secrets.get(seat.env_key, None))
            except Exception:
                pass
            st.write(f"{'🟢' if configured else '⚪'} {seat.name}")
        st.caption('لا يتم عرض أو حفظ مفاتيح API في الواجهة أو سجل التدقيق.')

    for item in st.session_state.history:
        role = 'user' if item.get('role') == 'user' else 'assistant'
        with st.chat_message(role):
            st.markdown(f"**{item.get('sender', '')}**\n\n{item.get('content', '')}")

    prompt = st.chat_input('اكتب موضوع النقاش على المجلس...')
    if not prompt:
        return

    st.session_state.history.append({'role': 'user', 'sender': '👤 أنت', 'content': prompt})
    with st.chat_message('user'):
        st.markdown(f'**👤 أنت**\n\n{prompt}')

    with st.spinner('المجلس يناقش...'):
        results = run_room(prompt, st.session_state.history, rounds, local_fallback)

    for item in results:
        st.session_state.history.append({'role': 'assistant', 'sender': item['label'], 'content': item['content']})
        with st.chat_message('assistant'):
            st.markdown(f"**{item['label']}**\n\n{item['content']}")

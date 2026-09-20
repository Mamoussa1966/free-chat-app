from __future__ import annotations
import streamlit as st

def render_conversation_sidebar(chats: list[dict], active_id: str) -> tuple[str|None, str|None]:
    st.subheader("💬 المحادثات")
    selected=None; action=None
    for item in list(chats)[:30]:
        icon="🟢" if item.get("id")==active_id else "⚪"
        if st.button(f"{icon} {item.get('title','محادثة')}", key=f"v24_chat_{item.get('id')}", use_container_width=True): selected=item.get("id")
    return selected, action

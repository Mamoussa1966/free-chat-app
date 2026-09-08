# -*- coding: utf-8 -*-
"""AI Council — Streamlit entry point."""
from __future__ import annotations
import streamlit as st
from main import run_app
st.set_page_config(
    page_title="AI Council",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)
if __name__ == "__main__":
    run_app()

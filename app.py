# -*- coding: utf-8 -*-
"""Streamlit entry point for AI Council."""

from __future__ import annotations

import streamlit as st

from main import run_app


st.set_page_config(
    page_title="AI Council V21",
    page_icon="🏛️",
    layout="wide",
)


if __name__ == "__main__":
    run_app()

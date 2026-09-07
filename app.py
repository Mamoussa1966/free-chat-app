import streamlit as st

from main import run_app

st.set_page_config(
    page_title="AI Council",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

run_app()

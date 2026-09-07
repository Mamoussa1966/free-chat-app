import streamlit as st

st.set_page_config(
    page_title="AI Council — Free Cascade",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from main import run_app

run_app()

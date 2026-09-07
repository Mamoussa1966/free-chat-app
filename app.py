import streamlit as st

from main import run_app


st.set_page_config(
    page_title="AI Council V21.5",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)


if __name__ == "__main__":
    run_app()

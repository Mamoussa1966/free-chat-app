import streamlit as st


st.set_page_config(
    page_title="AI Council",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)


try:
    from main import run_app

except SyntaxError as exc:
    st.error("❌ يوجد SyntaxError أثناء تحميل المشروع.")

    st.markdown("### الملف الذي يحتوي على الخطأ")
    st.code(str(exc.filename or "غير محدد"))

    st.markdown("### رقم السطر")
    st.code(str(exc.lineno or "غير محدد"))

    st.markdown("### الموضع")
    st.code(str(exc.offset or "غير محدد"))

    st.markdown("### رسالة Python الأصلية")
    st.code(str(exc.msg or exc))

    st.stop()

except Exception as exc:
    st.error("❌ فشل تحميل المشروع.")

    st.markdown("### نوع الخطأ")
    st.code(type(exc).__name__)

    st.markdown("### الرسالة")
    st.code(str(exc))

    st.stop()


run_app()

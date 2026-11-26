from __future__ import annotations

import streamlit as st

from supabase_native_auth_probe import render_supabase_native_auth_denial_probe

st.set_page_config(
    page_title="Supabase Native Auth Boundary Probe",
    page_icon="🧪",
    layout="centered",
)

st.title("🧪 اختبار رفض رمز Supabase Auth الأصلي")
st.caption("بيئة اختبار مستقلة — لا تستخدم قاعدة بيانات الإنتاج ولا تغيّر إعدادات المصادقة.")
st.caption("Build marker: SUPABASE-NATIVE-AUTH-DENIAL-PROBE-READ-WRITE-CLEANUP-VERIFIED-20261126")
st.warning(
    "استخدم حسابًا تجريبيًا في مشروع Supabase الاختباري فقط. ينفذ الفحص قراءة لجدول Clerk ومحاولة INSERT بسجل مؤقت فريد لاختبار رفض الكتابة. "
    "إذا قُبل الإدخال على نحو غير متوقع، يحاول الاختبار حذف هذا السجل وحده؛ إذا لم يتأكد الاختبار من حذف السجل المؤقت بالضبط، فتوقف ولا تُعد التشغيل."
)
render_supabase_native_auth_denial_probe()

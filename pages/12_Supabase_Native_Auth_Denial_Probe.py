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
st.caption("Build marker: SUPABASE-NATIVE-AUTH-DENIAL-PROBE-20261112")
st.warning("أدخل بيانات حساب Supabase Auth التجريبي فقط. كلمة المرور والرمز لا يغادران إطار المتصفح إلا إلى مشروع Supabase التجريبي.")
render_supabase_native_auth_denial_probe()

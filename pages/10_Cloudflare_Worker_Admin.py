"""Authenticated bootstrap page for the Cloudflare Worker admin gateway.

This page exposes only the verified Supabase Auth user UUID needed for
owner-controlled operator enrollment. It never displays or logs bearer tokens.
"""
from __future__ import annotations

import streamlit as st

from cloudflare_worker_admin_client import (
    CloudflareWorkerAdminClient,
    CloudflareWorkerAdminClientError,
)
from supabase_streamlit_auth import AUTH_SESSION_KEY, ensure_supabase_auth, get_supabase_config


def _masked_email(value: str) -> str:
    email = str(value or "").strip()
    if "@" not in email:
        return "غير متاح"
    local, domain = email.rsplit("@", 1)
    visible = local[:2]
    return f"{visible}{'*' * max(3, len(local) - len(visible))}@{domain}"


def _client_from_verified_session() -> tuple[CloudflareWorkerAdminClient | None, str]:
    url, publishable_key, enabled = get_supabase_config(st)
    if not (enabled and url and publishable_key):
        return None, "Supabase Auth غير مفعّل أو إعدادات المشروع غير مكتملة."

    session = st.session_state.get(AUTH_SESSION_KEY)
    if not isinstance(session, dict):
        return None, "لا توجد جلسة Supabase Auth موثّقة في هذا المتصفح."

    access_token = str(session.get("access_token") or "").strip()
    user_id = str(session.get("user_id") or "").strip()
    issuer = str(session.get("issuer") or "").strip()
    if not access_token or not user_id or not issuer:
        return None, "بيانات الجلسة الموثّقة غير مكتملة. سجّل الخروج ثم الدخول مجددًا."

    try:
        client = CloudflareWorkerAdminClient(
            supabase_url=url,
            publishable_key=publishable_key,
            access_token=access_token,
            verified_user_id=user_id,
            expected_issuer=issuer,
        )
    except (TypeError, ValueError):
        return None, "تعذّر التحقق محليًا من تطابق جلسة المستخدم مع مشروع Supabase."
    return client, ""


st.title("Cloudflare Worker Admin")
st.caption("بوابة الإدارة المحمية — تهيئة هوية المشغّل")

auth_gate = ensure_supabase_auth(st)
if auth_gate is False:
    st.stop()
if auth_gate is not True:
    st.error("هذه الصفحة تتطلب تفعيل Supabase Auth في مشروع الإنتاج.")
    st.stop()

session = st.session_state.get(AUTH_SESSION_KEY)
client, client_error = _client_from_verified_session()
if client is None:
    st.error(client_error or "الجلسة غير صالحة.")
    st.stop()

user_id = str(session.get("user_id") or "").strip()
email = _masked_email(str(session.get("email") or ""))

st.subheader("هوية الحساب الحالي")
st.write(f"البريد المرتبط بالجلسة: **{email}**")
st.caption(
    "معرّف المستخدم أدناه مأخوذ من جلسة Supabase التي جرى التحقق منها عبر Auth /user؛ "
    "ليس من بريد إلكتروني أو JWT مفكوك محليًا."
)
st.code(user_id, language=None)
st.info(
    "أرسل هذا المعرّف النصي إلى مسؤول قاعدة البيانات لاعتماد حسابك كمشغّل. "
    "لا ترسل access token أو refresh token أو أي مفتاح سري."
)

st.divider()
st.subheader("اختبار صلاحية البوابة")
st.caption(
    "هذا الاختبار ينفّذ عملية list فقط. قد يسجل البوابة محاولة رفض في سجل التدقيق "
    "إذا لم يكن الحساب مسجلًا كمشغّل؛ ولا يغيّر Worker أو إصداراته."
)
if st.button("التحقق من صلاحية المشغّل", type="secondary", use_container_width=True):
    try:
        result = client.dispatch("list")
        if result.get("ok") is True:
            st.success("تم قبول الجلسة وصلاحية المشغّل.")
            st.json(result)
        else:
            reason = str(result.get("reason") or result.get("code") or "access_denied")
            st.warning(f"لم تُمنح صلاحية الإدارة بعد: {reason}")
    except CloudflareWorkerAdminClientError as exc:
        if exc.status_code == 403:
            st.warning("الجلسة صالحة، لكن هذا الحساب غير معتمد كمشغّل أو أن صلاحية list غير ممنوحة.")
        elif exc.status_code == 401:
            st.error("رفضت بوابة Supabase الجلسة. سجّل الدخول مجددًا.")
        else:
            st.error(f"تعذّر إكمال الفحص: {exc.code} (HTTP {exc.status_code or 'unknown'}).")

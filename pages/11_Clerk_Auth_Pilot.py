from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import streamlit as st

# Streamlit Cloud may execute a page with the pages/ directory as its
# import base. Add the repository root explicitly before importing the
# root-level Clerk pilot module.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_text = str(PROJECT_ROOT)
if project_root_text not in sys.path:
    sys.path.insert(0, project_root_text)

from clerk_streamlit_auth import (
    ClerkPilotAPIError,
    ClerkPilotAuthError,
    ClerkPilotRepository,
    get_clerk_pilot_config,
    render_clerk_login,
)


st.set_page_config(
    page_title="Clerk Authentication Pilot",
    page_icon="🔐",
    layout="centered",
)

st.title("🔐 Clerk Authentication Pilot")
st.caption(
    "بيئة اختبار معزولة: Clerk Development → Supabase Third-Party Auth → "
    "جدول اختبار محمي بسياسات RLS."
)
st.caption("Build marker: CLERK-PILOT-SIGNIN-EMAIL-CODE-20261111")

st.warning(
    "هذه الصفحة لا تغيّر تسجيل الدخول الحالي، ولا تستخدم قاعدة بيانات الإنتاج، "
    "ولا تتيح بوابة Cloudflare Worker Admin. لا تستخدمها لإدخال بيانات حقيقية."
)

try:
    config = get_clerk_pilot_config(st)
except ClerkPilotAuthError as exc:
    st.error(str(exc))
    st.stop()

st.markdown(
    f"""
**Clerk issuer:** `{config.issuer}`  
**Supabase test project:** `{config.supabase_url}`  
**Authorized origin:** `{", ".join(config.authorized_parties)}`
"""
)

try:
    verified = render_clerk_login(st)
except ClerkPilotAuthError as exc:
    st.error(str(exc))
    st.stop()

diagnostics = st.session_state.get("_clerk_pilot_environment_diagnostics")
if isinstance(diagnostics, dict):
    st.divider()
    st.subheader("تشخيص إعدادات Clerk الفعلية — قراءة فقط")
    st.caption(
        f"ClerkJS: {diagnostics.get('sdk_version') or 'غير متاح'} · "
        f"Clerk UI: {diagnostics.get('ui_version') or 'غير متاح'} · "
        f"Frontend API: {diagnostics.get('frontend_api') or 'غير متاح'}"
    )
    diag_left, diag_mid, diag_right = st.columns(3)
    with diag_left:
        st.metric(
            "البريد الإلكتروني",
            "مفعّل" if diagnostics.get("email_enabled") is True
            else "معطّل" if diagnostics.get("email_enabled") is False
            else "غير معروف",
        )
    with diag_mid:
        st.metric(
            "كلمة المرور",
            "مفعّلة" if diagnostics.get("password_enabled") is True
            else "معطّلة" if diagnostics.get("password_enabled") is False
            else "غير معروفة",
        )
    with diag_right:
        st.metric(
            "رمز التحقق عند التسجيل",
            "مفعّل" if diagnostics.get("email_verify_at_sign_up") is True
            else "غير مفعّل" if diagnostics.get("email_verify_at_sign_up") is False
            else "غير معروف",
        )

    st.caption(
        "تطابق نطاق الواجهة: "
        + ("نعم" if diagnostics.get("domain_matches") is True else "لا" if diagnostics.get("domain_matches") is False else "غير معروف")
        + " · تطابق المفتاح الذي شغّل SDK مع الإعداد: "
        + ("نعم" if diagnostics.get("publishable_key_matches") is True else "لا" if diagnostics.get("publishable_key_matches") is False else "غير معروف")
        + " · طرق تحقق البريد: "
        + ", ".join(diagnostics.get("email_verifications") or [])
    )
    if diagnostics.get("email_enabled") is False or diagnostics.get("password_enabled") is False:
        st.error("إعداد البريد أو كلمة المرور معطّل فعليًا في بيئة Clerk التي استجاب لها SDK.")
    elif diagnostics.get("email_enabled") is True and diagnostics.get("password_enabled") is True:
        st.success("إعدادا البريد الإلكتروني وكلمة المرور مفعّلان في بيئة Clerk الفعلية.")
    else:
        st.warning(
            "لم يتمكن SDK من إرجاع إعدادات البيئة كاملة. "
            f"رمز التشخيص: {diagnostics.get('error_code') or diagnostics.get('status') or 'غير متاح'}"
        )

if verified is None:
    st.info(
        "سجّل الدخول من نافذة Clerk أعلاه. لن تظهر بيانات الاختبار حتى يتحقق "
        "الخادم من توقيع JWT ومُصدره ووقت صلاحيته وحقلي azp وrole."
    )
    st.stop()

st.success("تم التحقق خادميًا من توقيع جلسة Clerk وصلاحيتها ومُصدرها.")
left, right = st.columns(2)
with left:
    st.metric("Verified Clerk User", verified.subject)
with right:
    expiry = datetime.fromtimestamp(verified.expires_at, tz=timezone.utc)
    st.metric("Token expires (UTC)", expiry.strftime("%H:%M:%S"))

st.caption(
    "يُستخدم رمز جلسة قصير العمر في ذاكرة جلسة Streamlit فقط. "
    "لا يُحفظ في ملفات أو localStorage مخصص أو سجلات."
)

repository = ClerkPilotRepository(config=config, session=verified)

st.divider()
st.subheader("1. اختبار سجل يملكه حسابك")

with st.form("clerk_pilot_create_record", clear_on_submit=True):
    record_key = st.text_input(
        "Record key",
        placeholder="my-first-record",
        max_chars=128,
    )
    record_value = st.text_area(
        "بيانات اختبار غير حساسة",
        placeholder="Clerk session verified successfully",
        max_chars=2000,
    )
    submitted = st.form_submit_button(
        "إنشاء سجل مملوك لحسابي",
        type="primary",
        use_container_width=True,
    )

if submitted:
    try:
        created = repository.create_own(record_key, record_value)
    except (ValueError, ClerkPilotAPIError) as exc:
        st.error(str(exc))
    else:
        st.success(
            "نجح INSERT عبر PostgREST باستخدام رمز Clerk، وقبلت RLS سجلًا "
            "يحمل subject الحساب الذي تم التحقق منه."
        )
        st.code(str(created.get("record_id") or ""), language="text")

st.divider()
st.subheader("2. قراءة السجلات المملوكة لحسابك فقط")

try:
    records = repository.list_own()
except ClerkPilotAPIError as exc:
    st.error(str(exc))
    records = []

st.caption(f"عدد السجلات التي أعادتها RLS لهذا الحساب: {len(records)}")

if records:
    for record in records:
        record_id = str(record.get("record_id") or "")
        record_key = str(record.get("record_key") or "")
        payload = record.get("record_payload")
        with st.container(border=True):
            st.markdown(f"**{record_key or 'بدون معرّف'}**")
            st.json(payload if isinstance(payload, dict) else {})
            st.caption(f"Created: {record.get('created_at') or '—'}")
            if st.button(
                "حذف هذا السجل",
                key=f"clerk-pilot-delete-{record_id}",
                type="secondary",
            ):
                try:
                    deleted = repository.delete_own(record_id)
                except (ValueError, ClerkPilotAPIError) as exc:
                    st.error(str(exc))
                else:
                    if deleted:
                        st.success("حُذف السجل المملوك لحسابك.")
                    else:
                        st.info("لم يُحذف أي سجل؛ ربما لم يعد السجل موجودًا أو لا تملكه.")
                    st.rerun()
else:
    st.info("لا توجد سجلات لهذا الحساب حتى الآن.")

st.divider()
st.subheader("3. اختبار منع انتحال مالك سجل")

st.write(
    "يرسل هذا الاختبار محاولة INSERT واحدة باسم subject مختلف عن حسابك. "
    "النتيجة الآمنة هي رفض Supabase العملية برمز HTTP 401 أو 403."
)
if st.button(
    "اختبار رفض انتحال المالك",
    key="clerk_pilot_owner_spoof_probe",
    use_container_width=True,
):
    try:
        denied = repository.probe_owner_spoof_denial()
    except ClerkPilotAPIError as exc:
        st.error(str(exc))
    else:
        if denied:
            st.success(
                "PASS — رفضت Supabase محاولة الكتابة باسم مستخدم آخر."
            )
        else:
            st.error("لم يمكن إثبات رفض انتحال المالك.")

st.divider()
st.subheader("حدود ما تم إثباته")
st.write(
    "- جلسة Clerk الحالية: توقيع RS256، وJWKS، وiss، وsub، وsid، وexp، "
    "وnbf، وiat، وazp، وrole تُراجع على الخادم.\n"
    "- عمليات PostgREST هنا تستخدم رمز Clerk نفسه وتخضع لسياسات RLS للجدول التجريبي.\n"
    "- الاختبار هنا لا يثبت وحده منع رموز Supabase Auth الأصلية الحقيقية؛ "
    "ذلك يتطلب تشغيل اختبار مستقل برمز مستخدم Supabase Auth صالح.\n"
    "- لا تستخدم جدول المحادثات UUID الحالي مع Clerk قبل تنفيذ تصميم ربط هوية "
    "ومجموعة اختبارات مستقلة."
)

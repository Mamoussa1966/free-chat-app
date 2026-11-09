"""Authenticated Cloudflare Worker administration page.

All mutations pass through the Supabase JWT gateway and the database's
operator/worker allow-lists. Destructive Worker deletion is not exposed.
"""
from __future__ import annotations

import re
import streamlit as st

from cloudflare_worker_admin_client import (
    CloudflareWorkerAdminClient,
    CloudflareWorkerAdminClientError,
)
from supabase_streamlit_auth import AUTH_SESSION_KEY, ensure_supabase_auth, get_supabase_config


_ALLOWED_POLICY_ACTIONS = [
    "inspect",
    "update_metadata",
    "upload_version",
    "deploy",
    "rollback",
]
_WORKER_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_RESULT_KEY = "cloudflare_worker_admin_last_result"


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


def _dispatch(
    client: CloudflareWorkerAdminClient,
    operation: str,
    *,
    worker_name: str | None = None,
    payload: dict | None = None,
    confirmation: str | None = None,
) -> None:
    """Execute one explicitly submitted operation and retain only its response."""
    try:
        response = client.dispatch(
            operation,
            worker_name=worker_name,
            payload=payload,
            confirmation=confirmation,
        )
        st.session_state[_RESULT_KEY] = {
            "operation": operation,
            "response": response,
            "error": "",
            "status": 200,
        }
    except CloudflareWorkerAdminClientError as exc:
        st.session_state[_RESULT_KEY] = {
            "operation": operation,
            "response": {},
            "error": exc.code,
            "status": exc.status_code or 0,
        }
    except (TypeError, ValueError):
        st.session_state[_RESULT_KEY] = {
            "operation": operation,
            "response": {},
            "error": "invalid_request",
            "status": 0,
        }


def _render_last_result() -> None:
    saved = st.session_state.get(_RESULT_KEY)
    if not isinstance(saved, dict):
        return

    st.divider()
    st.subheader("نتيجة آخر عملية")
    status = int(saved.get("status") or 0)
    response = saved.get("response")
    error = str(saved.get("error") or "")

    if error:
        if status == 401:
            st.error("رفضت بوابة Supabase الجلسة (HTTP 401). سجّل الدخول مجددًا.")
        elif status == 403 and error == "admin_access_denied":
            st.warning(
                "رفضت سياسة الإدارة العملية. قد يكون السبب غياب AAL2 أو عدم سماح "
                "قائمة المشغّلين بهذا الإجراء."
            )
        else:
            st.error(f"تعذّر تنفيذ العملية: {error} (HTTP {status or 'unknown'}).")
        return

    if not isinstance(response, dict):
        st.error("استجابة البوابة ليست كائن JSON متوقعًا.")
        return

    data = response.get("result")
    inner_ok = data.get("ok") if isinstance(data, dict) else None
    if response.get("ok") is True and inner_ok is not False:
        st.success(f"تمت عملية {saved.get('operation')} بنجاح.")
    else:
        reason = (
            str(response.get("reason") or response.get("code") or "")
            or (str(data.get("code") or data.get("reason") or "") if isinstance(data, dict) else "")
        )
        st.warning(f"لم تكتمل العملية. {reason}".strip())

    # Gateway responses contain structured operation metadata, not bearer tokens.
    st.json(response)


st.set_page_config(page_title="Cloudflare Worker Admin", page_icon="☁️", layout="wide")
st.title("Cloudflare Worker Admin")
st.caption("بوابة إدارة Workers عبر Supabase Auth — مع قائمة سماح وسجل تدقيق")

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
with st.container(border=True):
    st.subheader("هوية المشغّل المصادق عليه")
    st.write(f"البريد المرتبط بالجلسة: **{email}**")
    st.code(user_id, language=None)
    st.caption(
        "الرمز السري الخاص بـ Cloudflare لا يصل إلى المتصفح. تستخدم الصفحة مفتاح "
        "Supabase publishable وجلسة المستخدم الموقعة فقط."
    )

st.warning(
    "لا توجد عملية حذف Worker في هذه الواجهة. عمليات النشر والرجوع ورفع الإصدارات "
    "تتطلب AAL2 وعبارة التأكيد الدقيقة التي تتحقق منها قاعدة البيانات."
)

overview_tab, register_tab, policy_tab, release_tab, metadata_tab = st.tabs(
    ["نظرة عامة", "تسجيل Worker", "السياسات", "الإصدارات والنشر", "البيانات الوصفية"]
)

with overview_tab:
    st.subheader("Workers المسجلة في القائمة البيضاء")
    st.caption("القائمة من سجل Supabase الإداري؛ لا تستكشف أو تعدّل أي مورد خارج القائمة.")
    if st.button("تحديث قائمة Workers", key="cf_admin_list", use_container_width=True):
        _dispatch(client, "list")
    saved = st.session_state.get(_RESULT_KEY)
    if isinstance(saved, dict) and saved.get("operation") == "list" and not saved.get("error"):
        st.json(saved.get("response") or {})

with register_tab:
    st.subheader("تسجيل Worker موجود مسبقًا في Cloudflare")
    st.caption("هذه العملية لا تنشئ Worker جديدًا. تتحقق من وجود Worker وإعداداته وإصداراته قبل إضافته لقائمة السماح.")
    with st.form("cf_admin_register_form"):
        register_name = st.text_input(
            "اسم Worker",
            value="ai-council-cloudflare-canary",
            max_chars=63,
            key="cf_admin_register_name",
        ).strip()
        register_environment = st.selectbox(
            "البيئة",
            ["staging", "development", "test", "production"],
            index=0,
            key="cf_admin_register_environment",
        )
        register_actions = st.multiselect(
            "العمليات المسموح بها لهذا Worker",
            _ALLOWED_POLICY_ACTIONS,
            default=["inspect"],
            key="cf_admin_register_actions",
        )
        st.caption("الحذف مستبعد دائمًا. الإنتاج محمي من الحذف وتعديل البيانات الوصفية.")
        register_confirmation = st.text_input(
            "عبارة التأكيد",
            placeholder=f"REGISTER WORKER {register_name or '<worker>'} AS {register_environment}",
            key="cf_admin_register_confirmation",
        )
        register_submit = st.form_submit_button("تسجيل Worker في Allowlist", use_container_width=True)
    if register_submit:
        if not _WORKER_NAME.fullmatch(register_name or ""):
            st.error("اسم Worker غير صالح.")
        elif not register_actions:
            st.error("اختر عملية واحدة على الأقل.")
        else:
            _dispatch(
                client,
                "register",
                worker_name=register_name,
                payload={
                    "environment": register_environment,
                    "allowed_operations": register_actions,
                    "allow_delete": False,
                },
                confirmation=register_confirmation,
            )

with policy_tab:
    st.subheader("تغيير سياسة Worker")
    st.caption("لا يمكن تفعيل الحذف. Worker المصنف production يظل محميًا من الحذف وتعديل البيانات الوصفية.")
    with st.form("cf_admin_policy_form"):
        policy_name = st.text_input(
            "اسم Worker",
            value="ai-council-cloudflare-canary",
            max_chars=63,
            key="cf_admin_policy_name",
        ).strip()
        policy_environment = st.selectbox(
            "البيئة الجديدة",
            ["staging", "development", "test", "production"],
            index=0,
            key="cf_admin_policy_environment",
        )
        policy_actions = st.multiselect(
            "العمليات المسموح بها",
            _ALLOWED_POLICY_ACTIONS,
            default=["inspect", "update_metadata", "upload_version", "deploy", "rollback"],
            key="cf_admin_policy_actions",
        )
        st.caption(
            "عبارة التأكيد العادية: SET POLICY <worker> <environment>. "
            "عند خفض حماية production يلزم نص DEMOTE PRODUCTION PROTECTION المحدد."
        )
        policy_confirmation = st.text_input(
            "عبارة التأكيد الدقيقة",
            placeholder=f"SET POLICY {policy_name or '<worker>'} {policy_environment}",
            key="cf_admin_policy_confirmation",
        )
        policy_submit = st.form_submit_button("تطبيق السياسة", use_container_width=True)
    if policy_submit:
        if not _WORKER_NAME.fullmatch(policy_name or ""):
            st.error("اسم Worker غير صالح.")
        elif not policy_actions:
            st.error("اختر عملية واحدة على الأقل.")
        else:
            _dispatch(
                client,
                "set_policy",
                worker_name=policy_name,
                payload={
                    "environment": policy_environment,
                    "allowed_operations": policy_actions,
                    "allow_delete": False,
                },
                confirmation=policy_confirmation,
            )

with release_tab:
    st.subheader("مزامنة سجل الإصدارات")
    refresh_name = st.text_input(
        "اسم Worker للمزامنة",
        value="ai-council-cloudflare-canary",
        max_chars=63,
        key="cf_admin_refresh_name",
    ).strip()
    if st.button("قراءة الإصدارات والنشرات من Cloudflare", key="cf_admin_refresh_versions", use_container_width=True):
        if _WORKER_NAME.fullmatch(refresh_name or ""):
            _dispatch(client, "refresh_versions", worker_name=refresh_name, payload={})
        else:
            st.error("اسم Worker غير صالح.")

    st.divider()
    st.subheader("رفع إصدار جديد دون نشره")
    with st.form("cf_admin_upload_form"):
        upload_name = st.text_input(
            "اسم Worker",
            value="ai-council-cloudflare-canary",
            max_chars=63,
            key="cf_admin_upload_name",
        ).strip()
        module_source = st.text_area(
            "مصدر JavaScript Module",
            height=240,
            max_chars=200000,
            key="cf_admin_module_source",
            help="هذه الواجهة تدعم Worker أحادي الملف فقط؛ لن تحذف أو تستبدل bindings أو assets.",
        )
        version_message = st.text_input(
            "رسالة الإصدار",
            value="Uploaded via authenticated Supabase admin gateway",
            max_chars=1000,
            key="cf_admin_version_message",
        )
        compatibility_date = st.text_input(
            "Compatibility date",
            value="2026-11-09",
            max_chars=10,
            key="cf_admin_compatibility_date",
        )
        st.caption(
            f"عبارة التأكيد للبيئة غير الإنتاجية: UPLOAD VERSION {upload_name}. "
            f"للإنتاج: APPROVE PRODUCTION VERSION UPLOAD {upload_name}."
        )
        upload_confirmation = st.text_input(
            "عبارة تأكيد الرفع",
            key="cf_admin_upload_confirmation",
        )
        upload_submit = st.form_submit_button("رفع الإصدار دون نشره", use_container_width=True)
    if upload_submit:
        from datetime import date
        valid_date = False
        try:
            parsed_date = date.fromisoformat(compatibility_date)
            valid_date = parsed_date.isoformat() == compatibility_date
        except (TypeError, ValueError):
            parsed_date = None
        if not _WORKER_NAME.fullmatch(upload_name or ""):
            st.error("اسم Worker غير صالح.")
        elif not module_source.strip():
            st.error("مصدر JavaScript مطلوب.")
        elif not version_message.strip():
            st.error("رسالة الإصدار مطلوبة.")
        elif not valid_date:
            st.error("صيغة compatibility_date يجب أن تكون YYYY-MM-DD.")
        else:
            _dispatch(
                client,
                "upload_version",
                worker_name=upload_name,
                payload={
                    "module_js": module_source,
                    "message": version_message,
                    "compatibility_date": compatibility_date,
                },
                confirmation=upload_confirmation,
            )

    st.divider()
    st.subheader("نشر إصدار مرفوع")
    st.caption("أدخل UUID لإصدار غير منشور. لا تختَر الإصدار النشط أو إصدارًا سبق نشره؛ قاعدة البيانات ترفض ذلك.")
    with st.form("cf_admin_deploy_form"):
        deploy_name = st.text_input(
            "اسم Worker",
            value="ai-council-cloudflare-canary",
            max_chars=63,
            key="cf_admin_deploy_name",
        ).strip()
        deploy_version = st.text_input("Version UUID", key="cf_admin_deploy_version")
        st.caption(
            f"لغير الإنتاج: DEPLOY {deploy_name} <version_uuid>. "
            f"للإنتاج: APPROVE PRODUCTION DEPLOY {deploy_name} <version_uuid>."
        )
        deploy_confirmation = st.text_input("عبارة تأكيد النشر", key="cf_admin_deploy_confirmation")
        deploy_submit = st.form_submit_button("نشر الإصدار بنسبة 100%", use_container_width=True)
    if deploy_submit:
        try:
            import uuid
            normalized_version = str(uuid.UUID(deploy_version.strip()))
        except (TypeError, ValueError, AttributeError):
            normalized_version = ""
        if not _WORKER_NAME.fullmatch(deploy_name or ""):
            st.error("اسم Worker غير صالح.")
        elif not normalized_version:
            st.error("Version UUID غير صالح.")
        else:
            _dispatch(
                client,
                "deploy",
                worker_name=deploy_name,
                payload={"version_id": normalized_version},
                confirmation=deploy_confirmation,
            )

    st.divider()
    st.subheader("الرجوع إلى إصدار سبق نشره")
    st.caption("أدخل UUID لإصدار قديم سبق نشره وليس الإصدار النشط حاليًا. لا يوجد خيار Force.")
    with st.form("cf_admin_rollback_form"):
        rollback_name = st.text_input(
            "اسم Worker",
            value="ai-council-cloudflare-canary",
            max_chars=63,
            key="cf_admin_rollback_name",
        ).strip()
        rollback_version = st.text_input("Previous Version UUID", key="cf_admin_rollback_version")
        st.caption(
            f"لغير الإنتاج: ROLLBACK {rollback_name} <version_uuid>. "
            f"للإنتاج: APPROVE PRODUCTION ROLLBACK {rollback_name} <version_uuid>."
        )
        rollback_confirmation = st.text_input("عبارة تأكيد الرجوع", key="cf_admin_rollback_confirmation")
        rollback_submit = st.form_submit_button("الرجوع إلى الإصدار المحدد", use_container_width=True)
    if rollback_submit:
        try:
            import uuid
            normalized_version = str(uuid.UUID(rollback_version.strip()))
        except (TypeError, ValueError, AttributeError):
            normalized_version = ""
        if not _WORKER_NAME.fullmatch(rollback_name or ""):
            st.error("اسم Worker غير صالح.")
        elif not normalized_version:
            st.error("Version UUID غير صالح.")
        else:
            _dispatch(
                client,
                "rollback",
                worker_name=rollback_name,
                payload={"version_id": normalized_version},
                confirmation=rollback_confirmation,
            )

with metadata_tab:
    st.subheader("تحديث Tags")
    st.caption("متاح فقط للـ Workers غير المصنفة production. أدخل القيم مفصولة بفواصل.")
    with st.form("cf_admin_tags_form"):
        tags_name = st.text_input(
            "اسم Worker",
            value="ai-council-cloudflare-canary",
            max_chars=63,
            key="cf_admin_tags_name",
        ).strip()
        tags_text = st.text_input(
            "Tags",
            value="ai-council,canary,managed-by-supabase",
            max_chars=2048,
            key="cf_admin_tags_values",
        )
        st.caption(f"عبارة التأكيد الدقيقة: UPDATE METADATA {tags_name}.")
        tags_confirmation = st.text_input("عبارة تأكيد تحديث Tags", key="cf_admin_tags_confirmation")
        tags_submit = st.form_submit_button("تحديث Tags", use_container_width=True)
    if tags_submit:
        tags = [item.strip() for item in tags_text.split(",") if item.strip()]
        if not _WORKER_NAME.fullmatch(tags_name or ""):
            st.error("اسم Worker غير صالح.")
        else:
            _dispatch(
                client,
                "update_metadata",
                worker_name=tags_name,
                payload={"tags": tags},
                confirmation=tags_confirmation,
            )

_render_last_result()

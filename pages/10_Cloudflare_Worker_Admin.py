"""Authenticated Cloudflare Worker administration page.

All mutations pass through the Supabase JWT gateway and the database's
operator/worker allow-lists. Destructive Worker deletion is not exposed.
"""
from __future__ import annotations

import base64
import json
import re
import time
import streamlit as st

from cloudflare_worker_admin_client import (
    CloudflareWorkerAdminClient,
    CloudflareWorkerAdminClientError,
)
from supabase_auth import SupabaseAuthClient
from supabase_mfa import SupabaseMFAClient, SupabaseMFAError
from supabase_streamlit_auth import (
    AUTH_SESSION_KEY,
    _schedule_browser_write,
    ensure_supabase_auth,
    get_supabase_config,
)


_ALLOWED_POLICY_ACTIONS = [
    "inspect",
    "update_metadata",
    "upload_version",
    "deploy",
    "rollback",
]
_WORKER_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_RESULT_KEY = "cloudflare_worker_admin_last_result"


def _session_aal_for_display(access_token: str) -> str:
    """Read the already Auth-verified JWT assurance claim for UI display only.

    This value never authorizes operations; the Supabase gateway still enforces AAL2.
    """
    parts = str(access_token or "").split(".")
    if len(parts) != 3 or len(parts[1]) > 8192:
        return "unknown"
    try:
        payload = json.loads(
            base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)).decode("utf-8")
        )
    except Exception:
        return "unknown"
    level = str(payload.get("aal") or "").lower() if isinstance(payload, dict) else ""
    return level if level in {"aal1", "aal2"} else "unknown"


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


def _mfa_client_from_verified_session() -> tuple[SupabaseMFAClient | None, str]:
    url, publishable_key, enabled = get_supabase_config(st)
    session = st.session_state.get(AUTH_SESSION_KEY)
    if not (enabled and url and publishable_key and isinstance(session, dict)):
        return None, "Supabase Auth غير مفعّل أو الجلسة غير متاحة."
    try:
        client = SupabaseMFAClient(
            supabase_url=url,
            publishable_key=publishable_key,
            access_token=str(session.get("access_token") or ""),
            verified_user_id=str(session.get("user_id") or ""),
            expected_issuer=str(session.get("issuer") or ""),
        )
    except (TypeError, ValueError):
        return None, "تعذّر التحقق من جلسة Supabase الحالية."
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


def _render_mfa_panel(
    mfa_client: SupabaseMFAClient,
    session_state: dict,
) -> None:
    # Streamlit widget values are cleared at the start of the next rerun,
    # before the corresponding text_input widgets are instantiated.
    if st.session_state.pop("_cf_mfa_clear_enrollment_code_next_run", False):
        st.session_state.pop("cf_mfa_enrollment_code", None)
    if st.session_state.pop("_cf_mfa_clear_stepup_code_next_run", False):
        st.session_state.pop("cf_mfa_stepup_code", None)

    st.subheader("المصادقة الثنائية للحساب")
    st.caption(
        "استخدم تطبيق مصادقة يدعم TOTP. هذه الطريقة لا ترسل SMS ولا تحتاج إلى إعداد مزود رسائل."
    )

    if st.button("فحص عوامل MFA الحالية", key="cf_mfa_refresh_factors", use_container_width=True):
        try:
            factors_data = mfa_client.list_factors()
            factors = factors_data.get("all") if isinstance(factors_data.get("all"), list) else []
            safe_factors = []
            for factor in factors:
                if not isinstance(factor, dict):
                    continue
                if factor.get("factor_type") == "totp":
                    safe_factors.append(
                        {
                            "id": str(factor.get("id") or ""),
                            "friendly_name": str(factor.get("friendly_name") or "Authenticator"),
                            "status": str(factor.get("status") or "unknown"),
                            "created_at": str(factor.get("created_at") or ""),
                        }
                    )
            st.session_state["cf_mfa_safe_factors"] = safe_factors
        except SupabaseMFAError as exc:
            st.error(f"تعذّر قراءة عوامل المصادقة: {exc.code} (HTTP {exc.status_code or 'unknown'}).")

    factors = st.session_state.get("cf_mfa_safe_factors")
    if isinstance(factors, list) and factors:
        st.write("عوامل TOTP المسجلة:")
        st.dataframe(
            [
                {
                    "اسم العامل": str(item.get("friendly_name") or "Authenticator"),
                    "الحالة": str(item.get("status") or "unknown"),
                    "تاريخ التسجيل": str(item.get("created_at") or ""),
                }
                for item in factors
                if isinstance(item, dict)
            ],
            use_container_width=True,
            hide_index=True,
        )
        verified_ids = [
            str(item.get("id") or "")
            for item in factors
            if isinstance(item, dict) and item.get("status") == "verified" and item.get("id")
        ]
    else:
        verified_ids = []
        if isinstance(factors, list):
            st.info("لم يُعثر على عامل TOTP موثّق للحساب بعد.")

    pending_factor_id = str(st.session_state.get("cf_mfa_pending_factor_id") or "")
    pending_qr = str(st.session_state.get("cf_mfa_pending_qr") or "")
    pending_secret = str(st.session_state.get("cf_mfa_pending_secret") or "")

    if pending_factor_id and pending_qr and pending_secret:
        st.divider()
        st.subheader("إكمال إعداد تطبيق المصادقة")
        st.warning(
            "رمز الإعداد التالي سرّ خاص بحسابك. لا تشاركه أو ترسله في المحادثة. "
            "سيُمسح من جلسة التطبيق بعد نجاح التحقق أو إلغاء الإعداد."
        )
        encoded_qr = base64.b64encode(pending_qr.encode("utf-8")).decode("ascii")
        st.markdown(
            f'<img src="data:image/svg+xml;base64,{encoded_qr}" alt="TOTP QR code" '
            'style="width:240px;max-width:100%;height:auto;background:white;padding:12px;border-radius:8px;" />',
            unsafe_allow_html=True,
        )
        st.write("على الهاتف نفسه، استخدم خيار **إدخال مفتاح الإعداد يدويًا** في تطبيق المصادقة.")
        st.code(pending_secret, language=None)
        st.caption("اسم الحساب: AI Council Cloudflare Admin · نوع الرمز: Time-based (TOTP)")

        with st.form("cf_mfa_verify_enrollment_form"):
            enrollment_code = st.text_input(
                "أدخل الرمز الحالي المكوّن من 6 أرقام من تطبيق المصادقة",
                max_chars=10,
                key="cf_mfa_enrollment_code",
            ).strip()
            verify_enrollment = st.form_submit_button("التحقق وتفعيل MFA", use_container_width=True)

        if verify_enrollment:
            try:
                challenge_id = mfa_client.challenge(pending_factor_id)
                verification = mfa_client.verify(pending_factor_id, challenge_id, enrollment_code)
                new_access_token = str(verification.get("access_token") or "").strip()
                if not new_access_token:
                    raise SupabaseMFAError("verified_session_missing", 200)

                url, publishable_key, enabled = get_supabase_config(st)
                if not (enabled and url and publishable_key):
                    raise SupabaseMFAError("auth_configuration_missing", 0)
                auth_client = SupabaseAuthClient(
                    supabase_url=url,
                    publishable_key=publishable_key,
                )
                verified_user = auth_client.get_verified_user(new_access_token)
                expected_user_id = str(session_state.get("user_id") or "")
                if verified_user.get("id") != expected_user_id:
                    raise SupabaseMFAError("verified_user_mismatch", 401)

                refreshed_state = dict(session_state)
                refreshed_state["access_token"] = new_access_token
                refreshed_state["refresh_token"] = str(
                    verification.get("refresh_token") or session_state.get("refresh_token") or ""
                )
                refreshed_state["expires_at"] = int(
                    verification.get("expires_at")
                    or (int(time.time()) + int(verification.get("expires_in") or 3600))
                )
                refreshed_state["verified_at"] = int(time.time())
                refreshed_state["email"] = str(verified_user.get("email") or session_state.get("email") or "")
                st.session_state[AUTH_SESSION_KEY] = refreshed_state
                _schedule_browser_write(st, refreshed_state)

                for key in (
                    "cf_mfa_pending_factor_id",
                    "cf_mfa_pending_qr",
                    "cf_mfa_pending_secret",
                ):
                    st.session_state.pop(key, None)
                st.session_state["_cf_mfa_clear_enrollment_code_next_run"] = True
                st.session_state["cf_mfa_safe_factors"] = [
                    {
                        "id": pending_factor_id,
                        "friendly_name": "AI Council Cloudflare Admin",
                        "status": "verified",
                        "created_at": "",
                    }
                ]
                st.success("تم تفعيل TOTP والتحقق من جلسة AAL2 بنجاح.")
                st.rerun()
            except SupabaseMFAError as exc:
                st.error(f"لم يكتمل التحقق: {exc.code} (HTTP {exc.status_code or 'unknown'}).")
            except Exception:
                st.error("تعذّر تثبيت جلسة المصادقة الجديدة. أعد تحميل الصفحة ثم افحص عوامل MFA.")

        st.caption("اترك هذه الصفحة مفتوحة حتى تكمل إدخال الرمز والتحقق؛ لا تغلق شاشة الإعداد قبل إتمام التفعيل.")

    elif verified_ids:
        current_aal = _session_aal_for_display(str(session_state.get("access_token") or ""))
        if current_aal == "aal2":
            st.success("تم التحقق بنجاح. الجلسة الحالية مؤكدة بالمستوى AAL2.")
            st.caption(
                "لن نطلب رمز المصادقة مرة أخرى في هذه الجلسة. "
                "ستظل عمليات النشر والرجوع محمية بفحص AAL2 داخل بوابة Supabase."
            )
        else:
            st.divider()
            st.subheader("رفع الجلسة الحالية إلى AAL2")
            selected_factor = st.selectbox(
                "عامل المصادقة",
                verified_ids,
                key="cf_mfa_stepup_factor",
            )
            with st.form("cf_mfa_stepup_form"):
                stepup_code = st.text_input(
                    "أدخل الرمز الحالي من تطبيق المصادقة",
                    max_chars=10,
                    key="cf_mfa_stepup_code",
                ).strip()
                stepup_submit = st.form_submit_button("التحقق ورفع مستوى الجلسة", use_container_width=True)
            if stepup_submit:
                try:
                    challenge_id = mfa_client.challenge(selected_factor)
                    verification = mfa_client.verify(selected_factor, challenge_id, stepup_code)
                    new_access_token = str(verification.get("access_token") or "").strip()
                    if not new_access_token:
                        raise SupabaseMFAError("verified_session_missing", 200)

                    url, publishable_key, enabled = get_supabase_config(st)
                    if not (enabled and url and publishable_key):
                        raise SupabaseMFAError("auth_configuration_missing", 0)
                    auth_client = SupabaseAuthClient(
                        supabase_url=url,
                        publishable_key=publishable_key,
                    )
                    verified_user = auth_client.get_verified_user(new_access_token)
                    expected_user_id = str(session_state.get("user_id") or "")
                    if verified_user.get("id") != expected_user_id:
                        raise SupabaseMFAError("verified_user_mismatch", 401)

                    refreshed_state = dict(session_state)
                    refreshed_state["access_token"] = new_access_token
                    refreshed_state["refresh_token"] = str(
                        verification.get("refresh_token") or session_state.get("refresh_token") or ""
                    )
                    refreshed_state["expires_at"] = int(
                        verification.get("expires_at")
                        or (int(time.time()) + int(verification.get("expires_in") or 3600))
                    )
                    refreshed_state["verified_at"] = int(time.time())
                    refreshed_state["email"] = str(verified_user.get("email") or session_state.get("email") or "")
                    st.session_state[AUTH_SESSION_KEY] = refreshed_state
                    _schedule_browser_write(st, refreshed_state)
                    st.session_state["_cf_mfa_clear_stepup_code_next_run"] = True
                    st.success("تم التحقق من العامل ورفع الجلسة إلى AAL2.")
                    st.rerun()
                except SupabaseMFAError as exc:
                    st.error(f"فشل تحقق AAL2: {exc.code} (HTTP {exc.status_code or 'unknown'}).")
                except Exception:
                    st.error("تعذّر تحديث جلسة المصادقة. أعد تحميل الصفحة ثم حاول مرة أخرى.")

    else:
        st.divider()
        st.subheader("إعداد تطبيق المصادقة")
        if st.button("إنشاء مفتاح TOTP جديد", key="cf_mfa_start_enrollment", use_container_width=True):
            try:
                existing = mfa_client.list_factors()
                all_factors = existing.get("all") if isinstance(existing.get("all"), list) else []
                has_verified_totp = any(
                    isinstance(item, dict)
                    and item.get("factor_type") == "totp"
                    and item.get("status") == "verified"
                    for item in all_factors
                )
                has_unverified_totp = any(
                    isinstance(item, dict)
                    and item.get("factor_type") == "totp"
                    and item.get("status") == "unverified"
                    for item in all_factors
                )
                if has_verified_totp:
                    st.session_state["cf_mfa_safe_factors"] = [
                        {
                            "id": str(item.get("id") or ""),
                            "friendly_name": str(item.get("friendly_name") or "Authenticator"),
                            "status": str(item.get("status") or ""),
                            "created_at": str(item.get("created_at") or ""),
                        }
                        for item in all_factors
                        if isinstance(item, dict) and item.get("factor_type") == "totp"
                    ]
                    st.info("يوجد عامل TOTP موثّق بالفعل. حدّث الصفحة أو افحص عوامل MFA.")
                elif has_unverified_totp:
                    st.warning(
                        "يوجد عامل TOTP غير مكتمل من محاولة سابقة. لا تنشئ عاملًا جديدًا؛ "
                        "أكمل الإعداد المعلّق أو اطلب معالجة العامل غير المكتمل."
                    )
                else:
                    setup = mfa_client.enroll_totp()
                    st.session_state["cf_mfa_pending_factor_id"] = setup["factor_id"]
                    st.session_state["cf_mfa_pending_qr"] = setup["qr_code"]
                    st.session_state["cf_mfa_pending_secret"] = setup["secret"]
                    st.rerun()
            except SupabaseMFAError as exc:
                st.error(f"تعذّر بدء إعداد TOTP: {exc.code} (HTTP {exc.status_code or 'unknown'}).")

    st.caption(
        "ملاحظة: نجاح التحقق يرفع الجلسة الحالية إلى AAL2. بعد انتهاء الجلسة أو تسجيل الخروج "
        "قد تحتاج إلى تنفيذ خطوة التحقق مرة أخرى قبل عمليات الإدارة الحساسة."
    )


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

overview_tab, mfa_tab, register_tab, policy_tab, release_tab, metadata_tab = st.tabs(
    ["نظرة عامة", "تأمين الحساب (MFA)", "تسجيل Worker", "السياسات", "الإصدارات والنشر", "البيانات الوصفية"]
)

with overview_tab:
    st.subheader("Workers المسجلة في القائمة البيضاء")
    st.caption("القائمة من سجل Supabase الإداري؛ لا تستكشف أو تعدّل أي مورد خارج القائمة.")
    if st.button("تحديث قائمة Workers", key="cf_admin_list", use_container_width=True):
        _dispatch(client, "list")
    saved = st.session_state.get(_RESULT_KEY)
    if isinstance(saved, dict) and saved.get("operation") == "list" and not saved.get("error"):
        st.json(saved.get("response") or {})

with mfa_tab:
    mfa_client, mfa_error = _mfa_client_from_verified_session()
    if mfa_client is None:
        st.error(mfa_error or "جلسة المصادقة غير صالحة.")
    else:
        _render_mfa_panel(mfa_client, session)


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

from __future__ import annotations

import streamlit as st
from streamlit.components.v2 import component


_NATIVE_AUTH_PROBE_HTML = """
<div class="native-auth-probe panel" dir="rtl" lang="ar">
  <h3>بيانات حساب Supabase التجريبي</h3>
  <p class="hint">هذه ليست شاشة Clerk. استخدم حساب Supabase Auth الموجود في مشروع الاختبار فقط.</p>
  <label for="native-email">البريد الإلكتروني</label>
  <input id="native-email" type="email" autocomplete="username" required maxlength="254">
  <label for="native-password">كلمة مرور حساب Supabase التجريبي</label>
  <input id="native-password" type="text" autocomplete="off" required maxlength="256">
  <p class="hint">ستظهر كلمة المرور أثناء الكتابة لمراجعة الأحرف، وسيتم مسحها بعد تنفيذ الاختبار.</p>
  <button id="run-probe" type="button">تنفيذ اختبار الرمز الأصلي</button>
  <div id="result" role="status" aria-live="polite">تهيئة واجهة الاختبار…</div>
</div>
"""

_NATIVE_AUTH_PROBE_CSS = """
.native-auth-probe {
  font-family: system-ui, sans-serif;
  border: 1px solid rgba(128,128,128,.45);
  border-radius: 12px;
  padding: 16px;
  color: var(--text-color);
}
.native-auth-probe label { display:block; margin:12px 0 6px; font-weight:600; }
.native-auth-probe input {
  box-sizing:border-box; width:100%; padding:12px;
  border:1px solid rgba(128,128,128,.55); border-radius:8px;
  font:inherit; color:var(--text-color); background:var(--secondary-background-color);
}
.native-auth-probe button {
  width:100%; margin-top:16px; padding:12px; border:0; border-radius:8px;
  font:inherit; font-weight:700; cursor:pointer;
  background:var(--primary-color); color:white;
}
.native-auth-probe button:disabled { opacity:.6; cursor:wait; }
.native-auth-probe #result {
  margin-top:14px; padding:12px; border-radius:8px;
  white-space:pre-wrap; overflow-wrap:anywhere;
  background:var(--secondary-background-color);
}
.native-auth-probe .hint { opacity:.78; font-size:.92rem; }
"""

_NATIVE_AUTH_PROBE_JS = r"""
export default function(component) {
  const { data, parentElement } = component;
  const root = parentElement.querySelector(".native-auth-probe");
  if (!root) return () => {};

  const supabaseUrl = String(data?.supabase_url || "");
  const publishableKey = String(data?.publishable_key || "");
  const emailInput = root.querySelector("#native-email");
  const passwordInput = root.querySelector("#native-password");
  const runButton = root.querySelector("#run-probe");
  const resultNode = root.querySelector("#result");
  let busy = false;

  function show(message) {
    if (resultNode) resultNode.textContent = String(message || "");
  }

  async function readJson(response) {
    try { return await response.json(); } catch (_) { return null; }
  }

  function updateReadyState() {
    if (busy) return;
    if (String(emailInput?.value || "").trim() && String(passwordInput?.value || "")) {
      show("الحقول مكتملة والزر جاهز. اضغط «تنفيذ اختبار الرمز الأصلي» لبدء الاتصال بمشروع Supabase التجريبي.");
    } else {
      show("واجهة الاختبار جاهزة. أدخل بريد حساب Supabase التجريبي وكلمة مروره، ثم اضغط زر التنفيذ.");
    }
  }

  async function runProbe(event) {
    event?.preventDefault?.();
    if (busy) return;

    const email = String(emailInput?.value || "").trim();
    let password = String(passwordInput?.value || "");
    if (!email || !password) {
      show("أدخل البريد وكلمة المرور أولًا.");
      return;
    }
    if (!supabaseUrl || !publishableKey) {
      password = "";
      if (passwordInput) passwordInput.value = "";
      show("إعدادات مشروع Supabase التجريبي غير مكتملة. لم يبدأ الاتصال.");
      return;
    }

    busy = true;
    runButton.disabled = true;
    show("1/4 — يجري إنشاء جلسة Supabase Auth أصلية داخل المتصفح…");

    let accessToken = "";
    let authenticated = false;
    let readPass = false;
    let readDetail = "";
    let sessionCreated = false;
    let logoutPass = false;
    let signInFailure = "";

    try {
      const signInResponse = await fetch(
        supabaseUrl + "/auth/v1/token?grant_type=password",
        {
          method: "POST",
          headers: {
            "apikey": publishableKey,
            "Content-Type": "application/json",
            "Accept": "application/json"
          },
          body: JSON.stringify({ email, password }),
          cache: "no-store",
          credentials: "omit",
          redirect: "error"
        }
      );
      password = "";
      if (passwordInput) passwordInput.value = "";
      const signInData = await readJson(signInResponse);
      accessToken = typeof signInData?.access_token === "string"
        ? signInData.access_token : "";
      sessionCreated = !!accessToken;
      if (signInData && typeof signInData === "object") {
        signInData.access_token = "";
        signInData.refresh_token = "";
      }

      if (!signInResponse.ok || !accessToken) {
        const code = String(signInData?.code || signInData?.error || "auth_sign_in_failed");
        signInFailure = "لم ينجح تسجيل الدخول الأصلي إلى Supabase. HTTP "
          + signInResponse.status + " · " + code + "\nلم يتم تنفيذ اختبار الجدول.";
      } else {
        show("2/4 — التحقق من الرمز لدى Supabase Auth…");
        const userResponse = await fetch(supabaseUrl + "/auth/v1/user", {
          method: "GET",
          headers: {
            "apikey": publishableKey,
            "Authorization": "Bearer " + accessToken,
            "Accept": "application/json"
          },
          cache: "no-store",
          credentials: "omit",
          redirect: "error"
        });
        const userData = await readJson(userResponse);
        authenticated = userResponse.ok && typeof userData?.id === "string";
        if (userData && typeof userData === "object") {
          userData.id = "";
        }

        if (!authenticated) {
          readDetail = "تسجيل الدخول أعاد رمزًا، لكن التحقق من المستخدم فشل. HTTP "
            + userResponse.status + ". أوقفنا اختبار الجدول.";
        } else {
          show("3/4 — فحص قراءة جدول Clerk باستخدام JWT الأصلي…");
          const readResponse = await fetch(
            supabaseUrl + "/rest/v1/clerk_auth_pilot_records?select=record_id&limit=10",
            {
              method: "GET",
              headers: {
                "apikey": publishableKey,
                "Authorization": "Bearer " + accessToken,
                "Accept": "application/json"
              },
              cache: "no-store",
              credentials: "omit",
              redirect: "error"
            }
          );
          const rows = await readJson(readResponse);

          if (readResponse.status === 200 && Array.isArray(rows) && rows.length === 0) {
            readPass = true;
            readDetail = "RLS أعادت صفر سجلات؛ لم يتمكن رمز Supabase Auth من قراءة سجلات Clerk.";
          } else if (readResponse.status === 401 || readResponse.status === 403) {
            readPass = true;
            readDetail = "Supabase رفض طلب قراءة جدول Clerk مباشرةً (HTTP "
              + readResponse.status + ").";
          } else if (readResponse.ok && Array.isArray(rows) && rows.length > 0) {
            readDetail = "FAIL: رمز Supabase Auth قرأ " + rows.length
              + " سجلًا من جدول Clerk. يجب إيقاف اعتماد هذا العزل والتحقيق فورًا.";
          } else {
            readDetail = "نتيجة غير حاسمة لقراءة الجدول (HTTP "
              + readResponse.status + "). لا تُحسب PASS.";
          }
        }
      }
    } catch (error) {
      password = "";
      if (passwordInput) passwordInput.value = "";
      readDetail = "تعذر إكمال الطلب بسبب خطأ اتصال أو متصفح: "
        + String(error?.name || "network_error");
    } finally {
      if (accessToken) {
        try {
          const logoutResponse = await fetch(
            supabaseUrl + "/auth/v1/logout?scope=local",
            {
              method: "POST",
              headers: {
                "apikey": publishableKey,
                "Authorization": "Bearer " + accessToken,
                "Accept": "application/json"
              },
              cache: "no-store",
              credentials: "omit",
              redirect: "error"
            }
          );
          logoutPass = logoutResponse.ok;
        } catch (_) {
          logoutPass = false;
        }
      }

      accessToken = "";
      password = "";
      if (passwordInput) passwordInput.value = "";
      busy = false;
      if (runButton) runButton.disabled = false;

      if (signInFailure) {
        show(signInFailure + "\nتم مسح كلمة المرور من الحقل.");
      } else {
        const authLine = authenticated
          ? "PASS — Supabase Auth تحقق من JWT ومستخدمه."
          : "FAIL — لم يثبت تحقق Supabase Auth من JWT.";
        const readLine = readPass
          ? "PASS — " + readDetail
          : "NOT PASS — " + (readDetail || "لم تكتمل قراءة جدول Clerk.");
        const logoutLine = !sessionCreated
          ? "لم تُنشأ جلسة Supabase؛ لذلك لم تكن هناك جلسة تحتاج إلى إنهاء."
          : logoutPass
            ? "PASS — أُنهيت جلسة الاختبار الحالية فقط (scope=local)."
            : "تنبيه — لم نتأكد من إنهاء الجلسة المحلية؛ لا تعِد الاختبار قبل مراجعة حالة الجلسة.";

        show(authLine + "\n" + readLine + "\n" + logoutLine
          + "\n\nلم نعرض رمز الجلسة أو معرّف المستخدم، ولم نحفظ كلمة المرور أو الرمز.");
      }
    }
  }

  runButton?.addEventListener("click", runProbe);
  emailInput?.addEventListener("input", updateReadyState);
  passwordInput?.addEventListener("input", updateReadyState);
  updateReadyState();

  return () => {
    runButton?.removeEventListener("click", runProbe);
    emailInput?.removeEventListener("input", updateReadyState);
    passwordInput?.removeEventListener("input", updateReadyState);
    if (passwordInput) passwordInput.value = "";
  };
}
"""

_NATIVE_AUTH_PROBE_COMPONENT = component(
    "ai_council.supabase_native_auth_probe_v2",
    html=_NATIVE_AUTH_PROBE_HTML,
    css=_NATIVE_AUTH_PROBE_CSS,
    js=_NATIVE_AUTH_PROBE_JS,
    isolate_styles=True,
)


def render_supabase_native_auth_denial_probe() -> None:
    """Render a browser-only native Supabase Auth token denial test.

    Credentials and the returned JWT remain inside the Components v2 iframe.
    They are sent only to the isolated Supabase test project and never returned
    to Python, Streamlit session state, logs, URLs, or component state.
    """
    st.subheader("اختبار رفض رمز Supabase Auth الأصلي")
    st.caption("Build marker: SUPABASE-NATIVE-AUTH-DENIAL-PROBE-20261112")
    st.warning(
        "أدخل بيانات حساب موجود بالفعل في مشروع Supabase التجريبي فقط. "
        "كلمة المرور ورمز الجلسة يبقيان داخل إطار المتصفح ويُرسلان مباشرة إلى "
        "Supabase التجريبي؛ لا يرسلهما هذا الاختبار إلى Streamlit أو GitHub أو قاعدة "
        "بيانات المجلس. لا تدخل كلمة مرور الإنتاج إذا كانت مختلفة."
    )
    st.markdown(
        "**Supabase test project:** `https://pidcepvwsezdrlhxqksg.supabase.co`  \n\n"
        "الاختبار: تسجيل دخول أصلي، التحقق من JWT، ثم محاولة قراءة جدول Clerk المعزول."
    )

    _NATIVE_AUTH_PROBE_COMPONENT(
        key="ai_council_supabase_native_auth_probe_v2",
        data={
            "supabase_url": "https://pidcepvwsezdrlhxqksg.supabase.co",
            "publishable_key": "sb_publishable_DYeRykN5_v4KIpwfF6uY6A_yj18ggAz",
        },
    )

    st.caption(
        "الاختبار يقرأ فقط جدول Clerk. لا ينشئ سجلات ولا يغيّر بيانات الجدول. "
        "يستخدم تسجيل دخول كلمة مرور Supabase Auth المحلي لهذا الفحص فقط، "
        "ثم يطلب إنهاء الجلسة الحالية بنطاق local، ولا يخرج المستخدم من أجهزته الأخرى."
    )

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from clerk_streamlit_auth import (
    TEST_SUPABASE_PUBLISHABLE_KEY,
    TEST_SUPABASE_URL,
)


def render_supabase_native_auth_denial_probe() -> None:
    """Render a browser-only native Supabase Auth token denial test.

    Credentials and the returned JWT remain in this isolated iframe and are
    sent only to the test Supabase project. Nothing is persisted by Streamlit.
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
        f"**Supabase test project:** `{TEST_SUPABASE_URL}`  \n\n"
        "الاختبار: تسجيل دخول أصلي، التحقق من JWT، ثم محاولة قراءة جدول Clerk المعزول."
    )
    SUPABASE_URL_JSON = json.dumps(TEST_SUPABASE_URL)
    SUPABASE_KEY_JSON = json.dumps(TEST_SUPABASE_PUBLISHABLE_KEY)
    
    PROBE_HTML = """
    <!doctype html>
    <html lang="ar" dir="rtl">
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      :root { color-scheme: light dark; }
      body { font-family: system-ui, sans-serif; margin: 0; padding: 12px; }
      .panel { border: 1px solid rgba(128,128,128,.45); border-radius: 12px; padding: 16px; }
      label { display:block; margin: 12px 0 6px; font-weight: 600; }
      input { box-sizing: border-box; width: 100%; padding: 12px; border: 1px solid #8888;
              border-radius: 8px; font: inherit; }
      button { width:100%; margin-top:16px; padding:12px; border:0; border-radius:8px;
               font:inherit; font-weight:700; cursor:pointer; background:#2563eb; color:white; }
      button:disabled { opacity:.6; cursor:wait; }
      button.secondary { width:auto; margin-top:8px; padding:8px 12px; border:1px solid #8888; background:transparent; color:CanvasText; }
      #result { margin-top:14px; padding:12px; border-radius:8px; white-space:pre-wrap;
                overflow-wrap:anywhere; background:rgba(128,128,128,.12); }
      .hint { color:CanvasText; opacity:.75; font-size:.92rem; }
    </style>
    </head>
    <body>
    <div class="panel">
      <h3>بيانات حساب Supabase التجريبي</h3>
      <p class="hint">هذه ليست شاشة Clerk. أدخل كلمة مرور حساب Supabase Auth الموجود في مشروع الاختبار.</p>
      <form id="native-auth-form" autocomplete="off">
        <label for="native-email">البريد الإلكتروني</label>
        <input id="native-email" type="email" autocomplete="username" required maxlength="254">
        <label for="native-password">كلمة مرور حساب Supabase التجريبي</label>
        <input id="native-password" type="text" autocomplete="off" required maxlength="256">
      <p class="hint">ستظهر كلمة المرور أثناء الكتابة لمراجعة الأحرف، وسيتم مسحها بعد تنفيذ الاختبار.</p>
        <button id="run-probe" type="button">تنفيذ اختبار الرمز الأصلي</button>
      </form>
      <div id="result" role="status" aria-live="polite">جارٍ تجهيز واجهة الاختبار داخل المتصفح…</div>
    </div>
    <script>
    (() => {
      "use strict";
      const SUPABASE_URL = __SUPABASE_URL__;
      const SUPABASE_KEY = __SUPABASE_KEY__;
      const form = document.getElementById("native-auth-form");
      const emailInput = document.getElementById("native-email");
      const passwordInput = document.getElementById("native-password");
      const runButton = document.getElementById("run-probe");
      const resultNode = document.getElementById("result");
      let busy = false;
    
      function show(message) {
        resultNode.textContent = String(message || "");
      }
    
      async function readJson(response) {
        try { return await response.json(); } catch (_) { return null; }
      }
    
      async function runProbe(event) {
        event.preventDefault();
        if (busy) return;
    
        const email = String(emailInput.value || "").trim();
        const password = String(passwordInput.value || "");
        if (!email || !password) {
          show("أدخل البريد وكلمة المرور أولًا.");
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
    
        try {
          const signInResponse = await fetch(
            SUPABASE_URL + "/auth/v1/token?grant_type=password",
            {
              method: "POST",
              headers: {
                "apikey": SUPABASE_KEY,
                "Content-Type": "application/json",
                "Accept": "application/json"
              },
              body: JSON.stringify({ email, password }),
              cache: "no-store",
              credentials: "omit",
              redirect: "error"
            }
          );
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
            show("لم ينجح تسجيل الدخول الأصلي إلى Supabase. HTTP "
              + signInResponse.status + " · " + code
              + "\nلم يتم تنفيذ اختبار الجدول.");
            return;
          }
    
          show("2/4 — التحقق من الرمز لدى Supabase Auth…");
          const userResponse = await fetch(SUPABASE_URL + "/auth/v1/user", {
            method: "GET",
            headers: {
              "apikey": SUPABASE_KEY,
              "Authorization": "Bearer " + accessToken,
              "Accept": "application/json"
            },
            cache: "no-store",
            credentials: "omit",
            redirect: "error"
          });
          const userData = await readJson(userResponse);
          authenticated = userResponse.ok && typeof userData?.id === "string";
          if (!authenticated) {
            show("تسجيل الدخول أعاد رمزًا، لكن التحقق من المستخدم فشل. HTTP "
              + userResponse.status + "\nأوقفنا اختبار الجدول.");
            return;
          }
    
          show("3/4 — فحص قراءة جدول Clerk باستخدام JWT الأصلي…");
          const readResponse = await fetch(
            SUPABASE_URL + "/rest/v1/clerk_auth_pilot_records?select=record_id&limit=10",
            {
              method: "GET",
              headers: {
                "apikey": SUPABASE_KEY,
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
    
          show("4/4 — إنهاء جلسة الاختبار المحلية…");
        } catch (error) {
          readDetail = "تعذر إكمال الطلب بسبب خطأ اتصال أو متصفح: "
            + String(error?.name || "network_error");
        } finally {
          if (accessToken) {
            try {
              const logoutResponse = await fetch(
                SUPABASE_URL + "/auth/v1/logout?scope=local",
                {
                  method: "POST",
                  headers: {
                    "apikey": SUPABASE_KEY,
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
    
          // Do not retain credentials or the JWT in browser storage, component state,
          // Streamlit state, URLs, or DOM output.
          accessToken = "";
          passwordInput.value = "";
          busy = false;
          runButton.disabled = false;
    
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
    
      function updateReadyState() {
        if (busy) return;
        if (String(emailInput.value || "").trim() && String(passwordInput.value || "")) {
          show("الحقول مكتملة والزر جاهز. اضغط «تنفيذ اختبار الرمز الأصلي» لبدء الاتصال بمشروع Supabase التجريبي.");
        } else {
          show("واجهة الاختبار جاهزة. أدخل بريد حساب Supabase التجريبي وكلمة مروره، ثم اضغط زر التنفيذ.");
        }
      }

      // Use a direct click listener rather than relying only on mobile form submission.
      // Keep form submit as a keyboard-accessible fallback.
      runButton.addEventListener("click", runProbe);
      form.addEventListener("submit", runProbe);
      emailInput.addEventListener("input", updateReadyState);
      passwordInput.addEventListener("input", updateReadyState);
      updateReadyState();
    })();
    </script>
    </body>
    </html>
    """.replace("__SUPABASE_URL__", SUPABASE_URL_JSON).replace(
        "__SUPABASE_KEY__", SUPABASE_KEY_JSON
    )
    
    components.html(PROBE_HTML, height=470, scrolling=True)
    
    st.caption(
        "الاختبار يقرأ فقط جدول Clerk. لا ينشئ سجلات ولا يغيّر بيانات الجدول. "
        "يستخدم تسجيل دخول كلمة مرور Supabase Auth المحلي لهذا الفحص فقط، "
        "ثم يطلب إنهاء الجلسة الحالية بنطاق local، ولا يخرج المستخدم من أجهزته الأخرى."
    )

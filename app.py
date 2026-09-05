from __future__ import annotations

import concurrent.futures
import hashlib
import html
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import streamlit as st

from local_engine import generate_local
from providers import PROVIDERS, call_official, get_models, get_secret, safe_error

APP_VERSION = "V9.0-PROVIDER-LAYER-FREE-FIRST"
MAX_QUERY_CHARS = 6000
MAX_HISTORY = 40
MAX_CONTEXT_CHARS = 14000
MAX_OUTPUT_CHARS = 6000
REQUEST_TIMEOUT = int(os.getenv("AI_ROOM_TIMEOUT", "35"))
MAX_WORKERS = 5

AGENTS: Tuple[Dict[str, str], ...] = (
    {"id": "analysis", "provider": "openai", "name": "ChatGPT", "role": "التحليل العام", "icon": "💬", "instruction": "حلل الهدف والوقائع والقيود والخيارات الرئيسية."},
    {"id": "reasoning", "provider": "gemini", "name": "Gemini", "role": "الاستدلال المنطقي", "icon": "♊", "instruction": "فكك السؤال إلى فرضيات واختبر العلاقات المنطقية."},
    {"id": "critic", "provider": "anthropic", "name": "Claude", "role": "النقد والمنهج", "icon": "🧠", "instruction": "اكشف الافتراضات الخفية والتناقضات وما يحتاج إلى دليل."},
    {"id": "risk", "provider": "xai", "name": "Grok", "role": "البدائل والمخاطر", "icon": "⚡", "instruction": "قيّم المخاطر ونقاط الفشل والبدائل وخطة الرجوع."},
    {"id": "synthesis", "provider": "kimi", "name": "Kimi", "role": "التركيب التنفيذي", "icon": "🌙", "instruction": "ركب أفضل النقاط في خلاصة عملية قابلة للتنفيذ."},
)


@dataclass
class AgentResult:
    agent_id: str
    agent_name: str
    role: str
    provider: str
    text: str
    success: bool
    latency: float
    mode: str
    model_used: str = ""
    error: Optional[str] = None


def normalize_text(value: object, limit: int = MAX_OUTPUT_CHARS) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:limit].strip()


def validate_query(query: str) -> Tuple[bool, str]:
    q = normalize_text(query, MAX_QUERY_CHARS)
    if not q:
        return False, "اكتب رسالتك أولاً."
    if len(q) > MAX_QUERY_CHARS:
        return False, f"الرسالة طويلة جداً. الحد الأقصى {MAX_QUERY_CHARS} حرف."
    return True, ""


def build_context(history: List[dict]) -> str:
    rows = []
    for item in history[-10:]:
        sender = normalize_text(item.get("sender", ""), 80)
        content = normalize_text(item.get("content", ""), 1800)
        if content:
            rows.append(f"{sender}: {content}")
    return "\n".join(rows)[-MAX_CONTEXT_CHARS:]


def system_prompt(agent: Dict[str, str], tone: str) -> str:
    return (
        "أنت عضو مستقل في غرفة AI Council. "
        f"اسم الدور: {agent['name']}. الدور الوظيفي: {agent['role']}. "
        f"المهمة: {agent['instruction']} "
        f"النبرة: {tone}. أجب بالعربية الواضحة. لا تنتحل هوية مزود آخر، ولا تدّعِ معلومة غير متاحة. "
        "إذا كان السؤال تحية فقط، أجب باختصار."
    )


def clean_provider_labels(text: str) -> str:
    return re.sub(r"^\s*(ChatGPT|Gemini|Claude|Grok|Kimi)\s*[:：-]\s*", "", text or "", flags=re.I).strip()


def run_one_agent(agent: Dict[str, str], query: str, context: str, tone: str) -> AgentResult:
    started = time.perf_counter()
    cfg = PROVIDERS[agent["provider"]]
    api_key = get_secret(cfg.key_names)
    user_prompt = f"السياق السابق:\n{context or 'لا يوجد سياق سابق.'}\n\nرسالة المستخدم:\n{query}"
    system = system_prompt(agent, tone)

    # Critical invariant: no credential => no network attempt => local room remains usable.
    if not api_key:
        text = generate_local(agent, query, context, tone)
        return AgentResult(agent["id"], agent["name"], agent["role"], cfg.family, text, True,
                           time.perf_counter() - started, "محلي مجاني — بلا اعتماد رسمي", "local")

    errors: List[str] = []
    for model in get_models(cfg):
        try:
            text = clean_provider_labels(call_official(agent["provider"], api_key, model, system, user_prompt, REQUEST_TIMEOUT))
            return AgentResult(agent["id"], agent["name"], agent["role"], cfg.family, normalize_text(text), True,
                               time.perf_counter() - started, "نموذج أصلي عبر API رسمي", model)
        except Exception as exc:
            errors.append(f"{model}: {safe_error(exc)}")

    # Authenticated route failed: fail open to the local engine, never fail the room.
    text = generate_local(agent, query, context, tone)
    return AgentResult(agent["id"], agent["name"], agent["role"], cfg.family, text, True,
                       time.perf_counter() - started, "محلي مجاني — fallback بعد فشل الرسمي", "local",
                       " | ".join(errors)[:1200])


def run_council(query: str, tone: str) -> List[AgentResult]:
    context = build_context(st.session_state.get("chat_history", []))
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(run_one_agent, agent, query, context, tone) for agent in AGENTS]
        return [f.result() for f in futures]


def council_summary(query: str, results: List[AgentResult]) -> str:
    official = [r for r in results if r.mode == "نموذج أصلي عبر API رسمي"]
    local = [r for r in results if r.mode != "نموذج أصلي عبر API رسمي"]
    if official and local:
        return f"الجولة هجينة: {len(official)} مسار أصلي عبر API رسمي و{len(local)} مسار محلي احتياطي. لم يتوقف المجلس عند تعذر أي مزود."
    if official:
        return f"اكتملت الجولة عبر {len(official)}/5 مسارات رسمية موثقة."
    return "اكتملت الجولة بالكامل بالمحرك المحلي المجاني؛ لا توجد اعتمادات رسمية لازمة لتشغيل الغرفة."


def round_id(query: str, results: List[AgentResult]) -> str:
    payload = json.dumps({"q": query, "r": [asdict(r) for r in results]}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def export_payload(query: str, results: List[AgentResult], summary: str) -> str:
    return json.dumps({
        "app_version": APP_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "identity_policy": "Only authenticated official provider API results are labeled as official/original; local fallback is never represented as a provider model.",
        "query": query,
        "results": [asdict(r) for r in results],
        "summary": summary,
    }, ensure_ascii=False, indent=2)


def provider_status() -> Dict[str, bool]:
    return {pid: bool(get_secret(cfg.key_names)) for pid, cfg in PROVIDERS.items()}


def render_css() -> None:
    st.markdown("""
    <style>
      .block-container {max-width: 980px; padding-top: 1rem; padding-bottom: 5rem;}
      .hero {text-align:center; margin-bottom:1rem;}
      .hero h1 {font-size:2.15rem; margin-bottom:.2rem;}
      .hero p {opacity:.7; margin-top:0;}
      .truth {border:1px solid rgba(180,140,40,.35); border-radius:16px; padding:15px; line-height:1.8;}
      .agent {border:1px solid rgba(120,120,120,.22); border-radius:16px; padding:16px; margin:10px 0;}
      .agent-title {font-weight:800; font-size:1.08rem; margin-bottom:8px;}
      .meta {font-size:.78rem; opacity:.62; margin-top:10px; line-height:1.65;}
      .summary {border:1px solid rgba(80,120,180,.28); border-radius:16px; padding:16px; line-height:1.8;}
      @media (max-width: 650px) { .hero h1 {font-size:1.65rem;} .block-container {padding-left:.75rem; padding-right:.75rem;} }
    </style>
    """, unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(page_title="AI Council — الغرفة الخماسية", page_icon="🏛️", layout="centered", initial_sidebar_state="collapsed")
    render_css()
    st.session_state.setdefault("chat_history", [])
    st.session_state.setdefault("last_results", [])
    st.session_state.setdefault("last_query", "")
    st.session_state.setdefault("last_summary", "")

    st.markdown(f"<div class='hero'><h1>🏛️ الغرفة الخماسية الكبرى</h1><p>{APP_VERSION}</p></div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='truth'><b>العقد المعماري:</b> الغرفة تعمل بدون أي مفاتيح. عند وجود اعتماد رسمي محفوظ على الخادم، يستخدم كل Provider قناته الرسمية ونموذجه المحدد؛ وعند عدم وجود الاعتماد أو فشل الشبكة/النموذج يعود ذلك العضو فوراً إلى المحرك المحلي. لا توجد شاشة إدخال مفاتيح ولا Session Scraping ولا Cookies.</div>",
        unsafe_allow_html=True,
    )

    statuses = provider_status()
    with st.sidebar:
        st.header("⚙️ لوحة التحكم")
        st.caption(APP_VERSION)
        tone = st.selectbox("النبرة", ["علمية دقيقة", "مباشرة وسريعة", "ودية", "نقدية صارمة"], index=0)
        st.divider()
        st.subheader("🔌 حالة Providers")
        for pid, cfg in PROVIDERS.items():
            if statuses[pid]:
                st.success(f"{cfg.icon} {cfg.family}: اعتماد رسمي موجود")
            else:
                st.info(f"{cfg.icon} {cfg.family}: محلي احتياطي")
        st.caption("هذه الحالة تعني وجود اعتماد على الخادم فقط؛ الاختبار الفعلي يحدث عند الطلب.")
        st.divider()
        if st.button("🗑️ مسح الجلسة", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.last_results = []
            st.session_state.last_query = ""
            st.session_state.last_summary = ""
            st.rerun()

    st.subheader("🧩 أعضاء الغرفة")
    cols = st.columns(5)
    for col, agent in zip(cols, AGENTS):
        with col:
            cfg = PROVIDERS[agent["provider"]]
            label = "🟢 رسمي" if statuses[agent["provider"]] else "🔵 محلي"
            st.metric(agent["icon"], label, agent["name"])
            st.caption(agent["role"])

    for item in st.session_state.chat_history[-MAX_HISTORY:]:
        with st.chat_message("user" if item.get("role") == "user" else "assistant"):
            st.write(item.get("content", ""))

    query = st.chat_input("اكتب رسالتك للمجلس الخماسي…")
    if query is not None:
        ok, error = validate_query(query)
        if not ok:
            st.error(error)
            return
        query = normalize_text(query, MAX_QUERY_CHARS)
        st.session_state.chat_history.append({"role": "user", "sender": "المستخدم", "content": query})
        with st.status("🔄 المجلس يعمل — الرسمي عند توفر الاعتماد، والمحلي عند الحاجة…", expanded=False) as status:
            results = run_council(query, tone)
            summary = council_summary(query, results)
            st.session_state.last_results = results
            st.session_state.last_query = query
            st.session_state.last_summary = summary
            status.update(label="✅ اكتملت الجولة دون توقف", state="complete")

    if st.session_state.last_results:
        st.subheader("🧠 نتائج الوكلاء")
        for r in st.session_state.last_results:
            safe_name = html.escape(r.agent_name)
            safe_role = html.escape(r.role)
            safe_text = html.escape(r.text).replace("\n", "<br>")
            safe_mode = html.escape(r.mode)
            safe_model = html.escape(r.model_used or "—")
            err_note = "<br>تم استخدام fallback المحلي بعد تعذر المسار الرسمي." if r.error else ""
            st.markdown(
                f"<div class='agent'><div class='agent-title'>{safe_name} · {safe_role}</div>"
                f"<div>{safe_text}</div><div class='meta'>المسار: {safe_mode} · النموذج: {safe_model} · الزمن: {r.latency:.2f}s{err_note}</div></div>",
                unsafe_allow_html=True,
            )

        summary = st.session_state.last_summary or council_summary(st.session_state.last_query, st.session_state.last_results)
        st.subheader("🏆 خلاصة المجلس")
        st.markdown(f"<div class='summary'>{html.escape(summary)}</div>", unsafe_allow_html=True)
        rid = round_id(st.session_state.last_query, st.session_state.last_results)
        st.caption(f"معرّف الجولة: {rid}")

        payload = export_payload(st.session_state.last_query, st.session_state.last_results, summary)
        st.download_button("⬇️ تصدير الجولة JSON", payload, file_name=f"ai_council_{rid}.json", mime="application/json")

        existing = [x for x in st.session_state.chat_history if x.get("role") == "assistant"]
        if not existing or existing[-1].get("content") != summary:
            st.session_state.chat_history.append({"role": "assistant", "sender": "المجلس الخماسي", "content": summary})
    else:
        st.info("الغرفة جاهزة. اكتب أول رسالة لبدء الجولة.")


if __name__ == "__main__":
    main()

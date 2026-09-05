# -*- coding: utf-8 -*-
from __future__ import annotations
import html
import os
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple
import requests
import streamlit as st

APP_VERSION = "V6.1-FREE-ONLY-FINAL"
REQUEST_TIMEOUT = 8
MAX_INPUT = 2500

st.set_page_config(page_title="AI Council — الغرفة الخماسية", page_icon="🧠", layout="wide")

AGENTS: Dict[str, Dict[str, str]] = {
    "ChatGPT": {"icon": "💬", "role": "التحليل العام"},
    "Gemini": {"icon": "♊", "role": "الاستدلال والتنظيم"},
    "Claude": {"icon": "🧠", "role": "النقد والمنهج"},
    "Grok": {"icon": "🏴‍☠️", "role": "البدائل والمخاطر"},
    "Kimi": {"icon": "🥝", "role": "التركيب والخلاصة"},
}

@dataclass
class AgentResult:
    name: str
    role: str
    text: str
    latency: float
    source: str = "local-role-engine"
    success: bool = True

def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())

def is_greeting(text: str) -> bool:
    t = clean_text(text).lower()
    patterns = [
        r"\bgood\s+morning\b", r"\bgood\s+evening\b",
        r"\bgood\s+afternoon\b", r"\bhello\b", r"\bhi\b", r"\bhey\b",
        r"صباح\s+الخير", r"مساء\s+الخير", r"السلام\s+عليكم",
        r"مرحبا", r"مرحباً", r"اهلا", r"أهلا", r"هاي",
    ]
    return any(re.search(p, t, re.I) for p in patterns)

def greeting_reply(name: str) -> str:
    replies = {
        "ChatGPT": "صباح الخير! 👋 سعيد بوجودك. اكتب ما تريد مناقشته وسأساعدك في تنظيم الفكرة وتحليلها.",
        "Gemini": "صباح النور! ☀️ جاهز لترتيب الموضوع إلى نقاط واضحة ومقارنة الخيارات.",
        "Claude": "صباح الخير 🌷 جاهز لمراجعة الفكرة بهدوء والتنبيه إلى الافتراضات والنقاط التي تحتاج تدقيقاً.",
        "Grok": "صباح النور! 🚀 أعطني الموضوع مباشرة وسأركز على البدائل والمخاطر والنقاط العملية.",
        "Kimi": "صباح الخير! 🥝 أعطني التفاصيل وسأجمع زوايا المجلس في خلاصة عملية.",
    }
    return replies[name]

def local_role_response(name: str, user_text: str) -> str:
    t = clean_text(user_text)
    role = AGENTS[name]["role"]
    if is_greeting(t):
        return greeting_reply(name)
    if len(t) < 12:
        return f"أنا وكيل {role}. أحتاج تفاصيل إضافية قليلة حتى أقدم رأياً مفيداً بدلاً من التخمين."
    if name == "ChatGPT":
        return f"من زاوية {role}: أحدد الهدف والقيود والنتيجة المطلوبة في «{t[:320]}»، ثم أقترح مساراً عملياً قابلاً للاختبار."
    if name == "Gemini":
        return f"من زاوية {role}: أقسم «{t[:320]}» إلى معطيات مؤكدة، نقاط تحتاج تحققاً، ثم خيارات تنفيذ مرتبة."
    if name == "Claude":
        return f"من زاوية {role}: أراجع الافتراضات في «{t[:320]}»، وأفصل الحقائق عن الفرضيات وأشير إلى نقاط الفشل المحتملة."
    if name == "Grok":
        return f"من زاوية {role}: أبحث عن أقصر مسار عملي في «{t[:320]}» مع إبراز المخاطر والبدائل وخطة التعامل مع الفشل."
    return f"من زاوية {role}: أجمع زوايا «{t[:320]}» في قرار وخطوات تنفيذ، مع عدم اعتبار أي ادعاء خارجي مؤكداً قبل التحقق."

def synthesize(results: List[AgentResult], user_text: str) -> str:
    if is_greeting(user_text):
        return (
            "### 👋 المجلس جاهز\n\n"
            "هذه الغرفة تعمل بدون مفاتيح API. الوكلاء الخمسة هنا أدوار محلية مستقلة، "
            "وليست نسخاً أصلية من نماذج الشركات. اكتب سؤالك أو المهمة وسأجمع زواياهم."
        )
    lines = [
        "### 🏛️ خلاصة المجلس",
        f"**الموضوع:** {clean_text(user_text)[:500]}",
        "",
        "**النتيجة:** افصل الحقائق المؤكدة عن الافتراضات، ثم ابدأ بأصغر اختبار عملي قابل للقياس.",
        "",
        "**زوايا الوكلاء:**",
    ]
    for r in results:
        lines.append(f"- **{r.name} — {r.role}:** {clean_text(r.text)[:360]}")
    lines.append("")
    lines.append("**الخطوة المقترحة:** نفّذ اختباراً صغيراً، سجّل النتيجة، ثم وسّع الحل بعد التحقق.")
    return "\n".join(lines)

def external_best_effort(prompt: str) -> Tuple[str, str]:
    endpoint = os.getenv("FREE_COUNCIL_PUBLIC_ENDPOINT", "").strip()
    if not endpoint:
        return "", "disabled"
    try:
        r = requests.post(endpoint, json={"prompt": prompt}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        if "application/json" in r.headers.get("content-type", ""):
            data = r.json()
            text = ""
            if isinstance(data, dict):
                text = data.get("text") or data.get("response") or data.get("content") or ""
            else:
                text = str(data)
        else:
            text = r.text
        text = clean_text(text)
        return (text[:5000], "public-network-best-effort") if text else ("", "empty")
    except Exception:
        return "", "network-error"

def run_council(user_text: str, use_external: bool) -> List[AgentResult]:
    out = []
    for name, meta in AGENTS.items():
        started = time.perf_counter()
        text = local_role_response(name, user_text)
        source = "local-role-engine"
        if use_external and not is_greeting(user_text):
            prompt = (
                "أنت دور محلي ضمن مجلس ذكاء اصطناعي. لا تدّع أنك نموذج تابع لشركة بعينها. "
                f"الدور: {meta['role']}. المستخدم: {user_text}"
            )
            network_text, network_source = external_best_effort(prompt)
            if network_text:
                text, source = network_text, network_source
        out.append(AgentResult(name, meta["role"], text, time.perf_counter() - started, source))
    return out

def render_agent(r: AgentResult) -> None:
    meta = AGENTS[r.name]
    source = "🟢 محلي — بدون مفتاح" if r.source == "local-role-engine" else "🌐 مسار شبكة تجريبي"
    safe = html.escape(r.text).replace("\n", "<br>")
    block = (
        '<div class="agent-card">'
        f'<div class="agent-title">{meta["icon"]} <strong>{html.escape(r.name)}</strong> '
        f'<span class="role">— {html.escape(r.role)}</span></div>'
        f'<div class="agent-source">{source} · {r.latency:.2f}s</div>'
        f'<div class="agent-text">{safe}</div></div>'
    )
    st.markdown(block, unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_results" not in st.session_state:
    st.session_state.last_results = []

st.markdown(
    "<style>.main-title{font-size:2rem;font-weight:800}.subtitle{opacity:.75}.agent-card{"
    "border:1px solid rgba(128,128,128,.28);border-radius:16px;padding:14px;margin:8px 0;"
    "background:rgba(128,128,128,.045)}.agent-title{display:flex;gap:8px;align-items:center;flex-wrap:wrap}"
    ".role,.agent-source{opacity:.7}.agent-source{font-size:.82rem;margin:5px 0 9px}.agent-text{line-height:1.75}"
    ".truth-box{border:1px solid rgba(255,165,0,.45);border-radius:14px;padding:12px;background:rgba(255,165,0,.07);line-height:1.7}"
    "</style>",
    unsafe_allow_html=True,
)

st.markdown('<div class="main-title">🏛️ AI Council — الغرفة الخماسية</div>', unsafe_allow_html=True)
st.markdown(f'<div class="subtitle">{APP_VERSION} · بدون مفاتيح API</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="truth-box"><b>التصحيح المعماري:</b> الغرفة تعمل بدون مفاتيح لأن الوكلاء الخمسة '
    '<b>أدوار محلية</b> وليست النماذج الأصلية لـ ChatGPT/Gemini/Claude/Grok/Kimi. '
    'لا يتم تزوير هوية أي مزود.</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("⚙️ التحكم")
    use_external = st.toggle(
        "محاولة مسار شبكة تجريبي",
        value=False,
        help="معطل افتراضياً. لا يستخدم مفاتيح API ولا يضمن نموذجاً تابعاً لمزود بعينه.",
    )
    if use_external:
        st.caption("يعمل فقط عند تعريف FREE_COUNCIL_PUBLIC_ENDPOINT. عند الفشل تستمر الأدوار المحلية.")
    st.divider()
    st.subheader("الوكلاء المحليون")
    for n, m in AGENTS.items():
        st.write(f'{m["icon"]} **{n}** — 🟢 متاح محلياً')
        st.caption(m["role"])
    st.divider()
    if st.button("🗑️ بدء غرفة جديدة", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_results = []
        st.rerun()
    st.caption("لا توجد شاشة مفاتيح API ولا قراءة من st.secrets.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if st.session_state.last_results:
    st.subheader("👥 ردود المجلس الأخيرة")
    for result in st.session_state.last_results:
        render_agent(result)

user_prompt = st.chat_input("اكتب رسالتك للمجلس…")
if user_prompt is not None:
    user_prompt = clean_text(user_prompt)
    if not user_prompt:
        st.warning("اكتب رسالة أولاً.")
        st.stop()
    if len(user_prompt) > MAX_INPUT:
        st.error(f"الرسالة طويلة جداً. الحد الأقصى {MAX_INPUT} حرف.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.markdown(user_prompt)

    with st.chat_message("assistant"):
        with st.spinner("المجلس يعمل…"):
            results = run_council(user_prompt, use_external)
            summary = synthesize(results, user_prompt)
        st.markdown(summary)

    st.session_state.last_results = results
    st.session_state.messages.append({"role": "assistant", "content": summary})
    st.rerun()

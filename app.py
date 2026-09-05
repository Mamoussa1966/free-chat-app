import os
import re
import json
import time
import hashlib
import concurrent.futures
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import requests
import streamlit as st

APP_VERSION = "V6-FREE-COUNCIL"
MAX_HISTORY_MESSAGES = 20
MAX_CONTEXT_CHARS = 12000
REMOTE_TIMEOUT = 18
MAX_OUTPUT_CHARS = 5000

# No API keys, no st.secrets, no environment credentials.
# The remote route is opportunistic only. If it requires authentication or fails,
# the application automatically switches to the built-in offline engine.
FREE_ROUTES = [
    {"id": "free-openai", "family": "OpenAI-style", "label": "وكيل التحليل العام", "model": "openai"},
    {"id": "free-gemini", "family": "Gemini-style", "label": "وكيل الاستدلال", "model": "gemini"},
    {"id": "free-claude", "family": "Claude-style", "label": "وكيل النقد والمنهج", "model": "claude"},
    {"id": "free-grok", "family": "Grok-style", "label": "وكيل البدائل والمخاطر", "model": "grok"},
    {"id": "free-kimi", "family": "Kimi-style", "label": "وكيل التركيب والخلاصة", "model": "kimi"},
]


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text[:MAX_OUTPUT_CHARS]


def stable_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class InputGuard:
    @staticmethod
    def inspect(query: str) -> Tuple[bool, str]:
        q = (query or "").strip()
        if not q:
            return False, "اكتب السؤال أولاً."
        if len(q) < 3:
            return False, "السؤال قصير جداً."
        if len(q) > 5000:
            return False, "الحد الأقصى للسؤال 5000 حرف."
        return True, ""


class ContextManager:
    @staticmethod
    def build(history: List[dict], limit: int = 8) -> str:
        rows = []
        for item in history[-limit:]:
            sender = clean_text(str(item.get("sender", "")))
            content = clean_text(str(item.get("content", item.get("content_ar", ""))))
            if content:
                rows.append(f"{sender}: {content}")
        context = "\n".join(rows)
        return context[-MAX_CONTEXT_CHARS:]


class FreeRemote:
    """Best-effort unauthenticated legacy/free route. Never requires a key."""

    BASE = "https://text.pollinations.ai"

    @classmethod
    def call(cls, route: dict, prompt: str) -> Tuple[bool, str, str]:
        try:
            url = f"{cls.BASE}/{quote(prompt, safe='')}"
            response = requests.get(
                url,
                params={"model": route["model"], "temperature": 0.35},
                timeout=REMOTE_TIMEOUT,
                headers={"User-Agent": "AI-Council-Free/6.0"},
            )
            if response.status_code != 200:
                return False, "", f"HTTP {response.status_code}"
            text = clean_text(response.text)
            if not text:
                return False, "", "empty response"
            return True, text, "remote-free-route"
        except requests.RequestException as exc:
            return False, "", type(exc).__name__
        except Exception as exc:
            return False, "", type(exc).__name__


class LocalCouncilEngine:
    """Deterministic offline fallback: always works without network/API credentials."""

    @staticmethod
    def tokenize(text: str) -> List[str]:
        return [x for x in re.findall(r"[\w\u0600-\u06FF]+", text.lower()) if len(x) > 2]

    @classmethod
    def generate(cls, route: dict, query: str, context: str) -> str:
        words = cls.tokenize(query)
        focus = "، ".join(words[:8]) if words else "جوهر السؤال"
        q = query.strip()
        family = route["family"]
        role = route["label"]

        templates = {
            "free-openai": (
                f"أتعامل مع السؤال من زاوية التحليل العام. جوهر المسألة يدور حول: {focus}. "
                f"أولاً نحدد الهدف والقيود، ثم نفصل الحقائق عن الافتراضات، ثم نقارن البدائل وفق معيار واضح. "
                f"الاستنتاج الأولي: لا ينبغي اختيار حل لمجرد أنه يبدو أسرع؛ يجب قياس قابلية التنفيذ والمخاطر والاعتمادية. "
                f"السؤال محل التقييم: {q}"
            ),
            "free-gemini": (
                f"من منظور الاستدلال المنظم، أبدأ بتفكيك السؤال إلى فرضيات قابلة للاختبار: {focus}. "
                f"إذا كانت إحدى الفرضيات غير مؤكدة، فالأفضل وضعها كشرط بدلاً من بناء النتيجة عليها. "
                f"أفضل مسار هو: تعريف المشكلة، تحديد الأدلة، اختبار البدائل، ثم اتخاذ قرار مع خطة رجوع عند الفشل."
            ),
            "free-claude": (
                f"النقطة الحرجة منهجياً هي التمييز بين الادعاء والدليل في موضوع: {focus}. "
                f"أبحث عن التناقضات، حالات الفشل، والافتراضات المخفية. أي حل قوي يجب أن يوضح ما الذي يعرفه، "
                f"وما الذي لا يعرفه، وما الاختبار الذي يمكن أن يثبت أو ينفي النتيجة."
            ),
            "free-grok": (
                f"أفحص البدائل والمخاطر العملية المتعلقة بـ {focus}. "
                f"السيناريو المتفائل وحده لا يكفي؛ نحتاج إلى سيناريو فشل، نقطة اختناق، وخطة بديلة. "
                f"إذا كان الخيار المقترح يعتمد على خدمة خارجية، فيجب أن يكون هناك fallback حتى لا تتوقف الغرفة بالكامل."
            ),
            "free-kimi": (
                f"أجمع النقاط السابقة في مسار تنفيذي مختصر حول {focus}: حدد الهدف، رتب الأولويات، "
                f"اختبر أقل حل قابل للتشغيل، ثم وسّع النظام بعد نجاح الاختبار. "
                f"القرار الأفضل ليس بالضرورة الأكثر تعقيداً، بل الأكثر وضوحاً وقابلية للقياس والتراجع."
            ),
        }
        answer = templates.get(route["id"], "تحليل مستقل للسؤال.")
        if context:
            answer += "\n\nالسياق السابق أُخذ في الاعتبار، لكن لم يُسمح له بتجاوز السؤال الحالي."
        return clean_text(answer)


@dataclass
class AgentResult:
    agent_id: str
    label: str
    family: str
    model: str
    text: str
    success: bool
    latency: float
    source: str
    error: Optional[str] = None


class Council:
    @staticmethod
    def prompt(route: dict, query: str, context: str, tone: str) -> str:
        return (
            "أنت وكيل مستقل داخل مجلس ذكاء اصطناعي. "
            f"دورك: {route['label']}. النبرة: {tone}.\n"
            "أجب بالعربية بوضوح، ولا تدّعِ أنك استخدمت أدوات أو مصادر لم تستخدمها.\n"
            f"السؤال: {query}\n"
            f"السياق السابق: {context or 'لا يوجد'}\n"
            "قدّم تحليلاً عملياً مركزاً مع نقاط قوة وضعف ومقترح قابل للتنفيذ."
        )

    @classmethod
    def run_one(cls, route: dict, query: str, context: str, tone: str, allow_remote: bool) -> AgentResult:
        start = time.perf_counter()
        prompt = cls.prompt(route, query, context, tone)
        if allow_remote:
            ok, text, source = FreeRemote.call(route, prompt)
            if ok:
                return AgentResult(route["id"], route["label"], route["family"], route["model"], text, True,
                                   time.perf_counter() - start, source)
        text = LocalCouncilEngine.generate(route, query, context)
        return AgentResult(route["id"], route["label"], route["family"], route["model"], text, True,
                           time.perf_counter() - start, "offline-fallback",
                           None if not allow_remote else "remote route unavailable")

    @classmethod
    def run(cls, query: str, history: List[dict], tone: str, allow_remote: bool) -> List[AgentResult]:
        context = ContextManager.build(history)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(cls.run_one, r, query, context, tone, allow_remote) for r in FREE_ROUTES]
            return [f.result() for f in futures]


def build_consensus(results: List[AgentResult], query: str) -> str:
    successful = [r for r in results if r.success]
    if not successful:
        return "لم ينتج أي وكيل نتيجة."
    lines = [
        "### 🏆 خلاصة المجلس",
        f"**السؤال:** {query}",
        "",
        "**نقاط الاتفاق:** التركيز على تعريف الهدف، اختبار الافتراضات، قياس المخاطر، ووجود مسار رجوع عند الفشل.",
        "",
        "**التباين:** تختلف الزوايا بين التحليل العام، الاستدلال، النقد، إدارة المخاطر، والتركيب التنفيذي.",
        "",
        "**القرار العملي:** ابدأ بأصغر تجربة قابلة للقياس، ثم وسّع الحل بعد نجاحها؛ لا تعتمد على مسار خارجي واحد.",
    ]
    return "\n".join(lines)


def init_state() -> None:
    st.session_state.setdefault("chat_history", [])
    st.session_state.setdefault("last_results", [])
    st.session_state.setdefault("last_consensus", "")
    st.session_state.setdefault("allow_remote", True)


st.set_page_config(page_title="AI Council V6 Free", page_icon="🤖", layout="wide", initial_sidebar_state="collapsed")
init_state()

st.markdown("<h1 style='text-align:center'>🤖 الغرفة الخماسية الكبرى — V6 Free</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center;opacity:.75'>5 مسارات وكلاء + تشغيل احتياطي محلي — بدون API Keys وبدون Secrets</p>", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ لوحة التحكم")
    st.caption(APP_VERSION)
    tone = st.selectbox("النبرة", ["علمية دقيقة", "مباشرة وسريعة", "ودية وداعمة", "نقدية وصارمة"])
    mode = st.radio("الوضع", ["المجلس الخماسي", "وكيل واحد بالتناوب"], index=0)
    st.session_state.allow_remote = st.toggle("محاولة المسار المجاني الخارجي", value=True,
                                               help="لا يستخدم أي مفتاح. عند فشله يعمل النظام محلياً تلقائياً.")
    st.divider()
    if st.button("🗑️ إعادة ضبط ومسح المجلس", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.last_results = []
        st.session_state.last_consensus = ""
        st.rerun()

cols = st.columns(5)
for col, route in zip(cols, FREE_ROUTES):
    with col:
        st.metric(route["label"], "جاهز", route["model"])

for msg in st.session_state.chat_history:
    role = msg.get("role", "assistant")
    with st.chat_message("user" if role == "user" else "assistant"):
        st.markdown(msg.get("content", ""))

query = st.chat_input("اكتب سؤالك للمجلس الخماسي…")
if query:
    valid, error = InputGuard.inspect(query)
    if not valid:
        st.error(error)
    else:
        st.session_state.chat_history.append({"role": "user", "sender": "أنت", "content": query})
        with st.status("🧠 المجلس يعمل…", expanded=False) as status:
            results = Council.run(query, st.session_state.chat_history[:-1], tone, st.session_state.allow_remote)
            st.session_state.last_results = [asdict(r) for r in results]
            consensus = build_consensus(results, query)
            st.session_state.last_consensus = consensus
            status.update(label="✅ اكتملت الجولة", state="complete")
        st.rerun()

if st.session_state.last_results:
    st.divider()
    st.subheader("🧠 نتائج الوكلاء")
    for raw in st.session_state.last_results:
        source = raw.get("source", "")
        badge = "🌐 مسار خارجي" if source == "remote-free-route" else "💾 Fallback محلي"
        with st.expander(f"{raw['label']} · {badge}", expanded=True):
            st.markdown(raw["text"])
            st.caption(f"العائلة: {raw['family']} · المسار: {raw['model']} · الزمن: {raw['latency']:.2f}s")
    st.divider()
    st.markdown(st.session_state.last_consensus)

st.caption("ملاحظة تقنية: لا توجد طريقة شرعية لضمان تشغيل ChatGPT/Gemini/Claude/Grok/Kimi الأصليين من خادم Streamlit بدون اعتماد من الجهة المقدمة. هذا الإصدار لا يطلب مفاتيح؛ يحاول مساراً مجانياً إن كان متاحاً، وإلا يعمل محلياً بلا شبكة.")

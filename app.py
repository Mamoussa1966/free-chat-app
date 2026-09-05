import os
import re
import json
import time
import hashlib
import concurrent.futures
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

import streamlit as st

try:
    from google import genai
except Exception:
    genai = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    import anthropic
except Exception:
    anthropic = None

APP_VERSION = "V6.0-REAL-COUNCIL"
MAX_HISTORY_MESSAGES = 12
MAX_CONTEXT_CHARS = 14000
MAX_PROMPT_CHARS = 26000
DEFAULT_TIMEOUT = 45
MAX_WORKERS = 15
CACHE_LIMIT = 80

# Preferred current model IDs. The runtime also discovers provider models where possible.
PREFERRED_MODELS = {
    "Gemini ♊": ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"],
    "ChatGPT 💬": ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"],
    "Claude 🧠": ["claude-opus-5", "claude-sonnet-5", "claude-sonnet-4-6"],
    "Grok 🏴‍☠️": ["grok-4.6", "grok-4.5", "grok-4.3"],
    "Kimi 🥝": [],
}

PROVIDERS = {
    "Gemini ♊": {"secret": "GEMINI_API_KEY"},
    "ChatGPT 💬": {"secret": "OPENAI_API_KEY"},
    "Claude 🧠": {"secret": "ANTHROPIC_API_KEY"},
    "Grok 🏴‍☠️": {"secret": "XAI_API_KEY", "base_url": "https://api.x.ai/v1"},
    "Kimi 🥝": {"secret": "MOONSHOT_API_KEY", "base_url": "https://api.moonshot.ai/v1"},
}

@dataclass(frozen=True)
class ModelSlot:
    family: str
    level: int
    name: str
    model: str

@dataclass
class AgentResult:
    agent_name: str
    family: str
    level: int
    text: str
    success: bool
    latency: float
    model_used: str
    error: Optional[str] = None
    cached: bool = False


def get_secret(name: str) -> Optional[str]:
    try:
        value = st.secrets.get(name)
        if value:
            return str(value).strip()
    except Exception:
        pass
    value = os.getenv(name)
    return value.strip() if value else None


def safe_error(exc: Exception) -> str:
    text = str(exc).strip().replace("\n", " ")
    text = re.sub(r"(?i)(api[_ -]?key|authorization|bearer)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    return text[:700] or exc.__class__.__name__


def clean_response(text: str, speaker: str = "") -> str:
    if not text:
        return ""
    text = str(text).strip()
    if speaker:
        clean_name = re.sub(r"[^\w\u0600-\u06ff ]", "", speaker).strip()
        for name in (speaker, clean_name):
            if name:
                text = re.sub(rf"^\s*(?:\[{re.escape(name)}\]|\({re.escape(name)}\)|{re.escape(name)})\s*[:：\-]\s*", "", text, flags=re.I)
    return text.strip()


class InputGuard:
    @staticmethod
    def inspect(query: str) -> Tuple[bool, str]:
        q = (query or "").strip()
        if not q:
            return False, "⚠️ اكتب السؤال أولًا."
        if len(q) < 5:
            return False, "⚠️ السؤال قصير جدًا."
        if len(q) > 5000:
            return False, "⚠️ الحد الأقصى للسؤال 5000 حرف."
        return True, ""


class ContextManager:
    @staticmethod
    def build_context(history: List[dict], limit: int = MAX_HISTORY_MESSAGES) -> str:
        lines = []
        for msg in history[-limit:]:
            sender = str(msg.get("sender", "Unknown"))
            content = str(msg.get("content_ar", "")).strip()
            if content:
                lines.append(f"{sender}: {content}")
        return "\n".join(lines)[-MAX_CONTEXT_CHARS:]


class PromptBuilder:
    @staticmethod
    def round1(slot: ModelSlot, query: str, context: str, tone: str) -> str:
        return f"""أنت وكيل مستقل داخل مجلس ذكاء اصطناعي متعدد المزودين.
المزود: {slot.family}
الدور: {slot.name}
النبرة: {tone}

السؤال الحالي:
{query}

السياق السابق:
{context or '(لا يوجد سياق سابق)'}

قواعد صارمة:
- أجب بالعربية الفصحى ما لم يتطلب السؤال لغة أخرى.
- لا تدّعِ أنك تمثل بقية النماذج.
- لا تخترع مصادر أو أرقامًا أو نتائج تجارب.
- فرّق بوضوح بين الحقيقة والاستنتاج والافتراض.
- ابدأ بالإجابة مباشرة.
- قدم نقاطًا قابلة للتحقق والتنفيذ.
"""

    @staticmethod
    def critique(slot: ModelSlot, own: str, peers: str, tone: str) -> str:
        return f"""أنت {slot.name} داخل مجلس مستقل.
النبرة: {tone}

إجابتك السابقة:
{own}

آراء وكلاء آخرين:
{peers}

نفّذ مراجعة نقدية قصيرة:
1) ما أقوى نقطة؟
2) ما أضعف ادعاء أو فجوة منطقية؟
3) ما الذي يجب تصحيحه؟
4) ما النتيجة التي تدافع عنها بعد المراجعة؟
لا توافق لمجرد التوافق، ولا تخترع أدلة.
أجب بالعربية الفصحى مباشرة.
"""

    @staticmethod
    def moderator(query: str, records: str) -> str:
        return f"""أنت مدير الجلسة المحايد لمجلس ذكاء اصطناعي متعدد المزودين.
السؤال الأصلي:
{query}

سجل المجلس:
{records}

اكتب الحكم النهائي بالعربية الفصحى بهذا البناء:
### الحكم التنفيذي
### نقاط الاتفاق
### نقاط الخلاف
### أقوى الحجج
### المخاطر والفجوات
### التوصية النهائية
### مستوى الثقة

لا تنسب إجماعًا غير موجود. إذا اختلف الوكلاء، اذكر ذلك صراحة. لا تضف حقائق غير موجودة في السجل.
"""


class GeminiAdapter:
    def __init__(self, model: str):
        self.model = model

    def execute(self, prompt: str, api_key: str) -> str:
        if genai is None:
            raise RuntimeError("حزمة google-genai غير مثبتة")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=self.model, contents=prompt)
        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("Gemini أعاد استجابة بلا نص")
        return text


class OpenAIAdapter:
    def __init__(self, model: str, base_url: Optional[str] = None):
        self.model = model
        self.base_url = base_url

    def execute(self, prompt: str, api_key: str) -> str:
        if OpenAI is None:
            raise RuntimeError("حزمة openai غير مثبتة")
        kwargs = {"api_key": api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        client = OpenAI(**kwargs)
        # Responses API is the current OpenAI interface; xAI supports it too.
        response = client.responses.create(model=self.model, input=prompt)
        text = getattr(response, "output_text", None)
        if text:
            return text
        # Compatibility fallback for OpenAI-compatible gateways.
        response = client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": prompt}])
        return response.choices[0].message.content or ""


class ClaudeAdapter:
    def __init__(self, model: str):
        self.model = model

    def execute(self, prompt: str, api_key: str) -> str:
        if anthropic is None:
            raise RuntimeError("حزمة anthropic غير مثبتة")
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=1800,
            system="أنت عضو مستقل في مجلس ذكاء اصطناعي. لا تخترع مصادر.",
            messages=[{"role": "user", "content": prompt}],
        )
        parts = [getattr(block, "text", "") for block in response.content]
        return "".join(parts).strip()


class CouncilOrchestrator:
    def __init__(self):
        self.keys = {family: get_secret(cfg["secret"]) for family, cfg in PROVIDERS.items()}

    def adapter(self, slot: ModelSlot):
        if slot.family == "Gemini ♊":
            return GeminiAdapter(slot.model)
        if slot.family == "Claude 🧠":
            return ClaudeAdapter(slot.model)
        if slot.family == "ChatGPT 💬":
            return OpenAIAdapter(slot.model)
        if slot.family in ("Grok 🏴‍☠️", "Kimi 🥝"):
            return OpenAIAdapter(slot.model, PROVIDERS[slot.family]["base_url"])
        raise RuntimeError(f"مزود غير معروف: {slot.family}")

    def discover_models(self, family: str) -> List[str]:
        key = self.keys.get(family)
        if not key:
            return []
        preferred = list(PREFERRED_MODELS.get(family, []))
        discovered: List[str] = []
        try:
            if family == "Gemini ♊" and genai:
                client = genai.Client(api_key=key)
                for item in client.models.list():
                    name = str(getattr(item, "name", ""))
                    name = name.removeprefix("models/")
                    if name and "embed" not in name.lower() and "image" not in name.lower() and "tts" not in name.lower() and "live" not in name.lower():
                        discovered.append(name)
            elif family == "ChatGPT 💬" and OpenAI:
                for item in OpenAI(api_key=key).models.list().data:
                    name = str(getattr(item, "id", ""))
                    if name.startswith("gpt-"):
                        discovered.append(name)
            elif family == "Grok 🏴‍☠️" and OpenAI:
                for item in OpenAI(api_key=key, base_url=PROVIDERS[family]["base_url"]).models.list().data:
                    name = str(getattr(item, "id", ""))
                    if "grok" in name.lower():
                        discovered.append(name)
            elif family == "Kimi 🥝" and OpenAI:
                for item in OpenAI(api_key=key, base_url=PROVIDERS[family]["base_url"]).models.list().data:
                    name = str(getattr(item, "id", ""))
                    if any(x in name.lower() for x in ("kimi", "moonshot", "k2", "k3")):
                        discovered.append(name)
            elif family == "Claude 🧠" and anthropic:
                for item in anthropic.Anthropic(api_key=key).models.list().data:
                    name = str(getattr(item, "id", ""))
                    if name:
                        discovered.append(name)
        except Exception:
            pass
        # Preferred models first; discovered models fill remaining slots.
        result = []
        for model in preferred + discovered:
            if model and model not in result:
                result.append(model)
        return result[:3]

    def slots(self) -> Dict[str, List[ModelSlot]]:
        result = {}
        for family in PROVIDERS:
            models = self.discover_models(family)
            result[family] = [
                ModelSlot(family, i + 1, f"{family} — {model}", model)
                for i, model in enumerate(models[:3])
            ]
        return result

    def run_one(self, slot: ModelSlot, prompt: str, timeout: int) -> AgentResult:
        start = time.perf_counter()
        key = self.keys.get(slot.family)
        if not key:
            return AgentResult(slot.name, slot.family, slot.level, "", False, 0, slot.model, "لا توجد بيانات اعتماد على الخادم")
        try:
            text = self.adapter(slot).execute(prompt, key)
            text = clean_response(text, slot.name)
            if not text:
                raise RuntimeError("الوكيل أعاد نصًا فارغًا")
            return AgentResult(slot.name, slot.family, slot.level, text, True, time.perf_counter() - start, slot.model)
        except Exception as exc:
            return AgentResult(slot.name, slot.family, slot.level, "", False, time.perf_counter() - start, slot.model, safe_error(exc))


def cache_key(query: str, slots: List[ModelSlot], mode: str, tone: str, context: str) -> str:
    payload = {
        "q": query, "models": [(s.family, s.model) for s in slots], "mode": mode,
        "tone": tone, "context": context,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def select_slots(all_slots: Dict[str, List[ModelSlot]], depth: str) -> List[ModelSlot]:
    count = {"5": 1, "10": 2, "15": 3}[depth]
    return [slot for family in all_slots for slot in all_slots[family][:count]]


def compact_records(results: List[AgentResult], limit_each: int = 3500) -> str:
    chunks = []
    for r in results:
        if r.success:
            chunks.append(f"[{r.family} | {r.model_used}]\n{r.text[:limit_each]}")
    return "\n\n---\n\n".join(chunks)


def run_council(query: str, history: List[dict], slots: List[ModelSlot], mode: str, tone: str, orch: CouncilOrchestrator):
    context = ContextManager.build_context(history)
    key = cache_key(query, slots, mode, tone, context)
    if key in st.session_state.council_cache:
        return st.session_state.council_cache[key], True

    results: List[AgentResult] = []
    prompts = {slot: PromptBuilder.round1(slot, query, context, tone)[:MAX_PROMPT_CHARS] for slot in slots}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, max(1, len(slots)))) as pool:
        future_map = {pool.submit(orch.run_one, slot, prompts[slot], DEFAULT_TIMEOUT): slot for slot in slots}
        for future in concurrent.futures.as_completed(future_map):
            results.append(future.result())
    results.sort(key=lambda r: (not r.success, r.family, r.level))

    if mode != "إجابة عادية متوازية ⚡":
        successful = [r for r in results if r.success]
        if len(successful) >= 2:
            critique_results: List[AgentResult] = []
            for r in successful:
                peers = [p for p in successful if p.family != r.family][:3]
                peer_text = "\n\n".join(f"{p.family}: {p.text[:2200]}" for p in peers)
                slot = next(s for s in slots if s.family == r.family and s.model == r.model_used)
                prompt = PromptBuilder.critique(slot, r.text[:4500], peer_text, tone)[:MAX_PROMPT_CHARS]
                critique_results.append((slot, prompt))
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(critique_results))) as pool:
                futures = [pool.submit(orch.run_one, slot, prompt, DEFAULT_TIMEOUT) for slot, prompt in critique_results]
                critiques = [f.result() for f in futures]
            results.extend([r for r in critiques if r.success])

    moderator = None
    if mode == "مناظرة كاملة متعددة الجولات 🔥" or mode == "نقاش عميق بملخص الحكم 🧠":
        successful = [r for r in results if r.success]
        if successful:
            # Use the highest-priority successful real model as moderator; no synthetic sixth model.
            successful.sort(key=lambda r: (r.level, r.latency))
            moderator_slot = next(s for s in slots if s.family == successful[0].family and s.model == successful[0].model_used)
            record_text = compact_records(successful)
            mod_prompt = PromptBuilder.moderator(query, record_text)[:MAX_PROMPT_CHARS]
            moderator = orch.run_one(moderator_slot, mod_prompt, DEFAULT_TIMEOUT)

    payload = {"results": [asdict(r) for r in results], "moderator": asdict(moderator) if moderator else None}
    if len(st.session_state.council_cache) >= CACHE_LIMIT:
        st.session_state.council_cache.pop(next(iter(st.session_state.council_cache)))
    st.session_state.council_cache[key] = payload
    return payload, False


def reset_state():
    st.session_state.chat_history = []
    st.session_state.council_cache = {}
    st.session_state.pending_query = None
    st.session_state.last_run = None
    st.rerun()


st.set_page_config(page_title="AI Council", page_icon="🤖", layout="wide")

for name, default in (("chat_history", []), ("council_cache", {}), ("pending_query", None), ("last_run", None)):
    if name not in st.session_state:
        st.session_state[name] = default

st.markdown("<h1 style='text-align:center'>🤖 الغرفة الخماسية الكبرى</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center;opacity:.72'>Gemini · ChatGPT · Claude · Grok · Kimi — Real Multi-Provider Council</p>", unsafe_allow_html=True)

orch = CouncilOrchestrator()

with st.sidebar:
    st.header("⚙️ تحكم المجلس")
    st.caption(f"{APP_VERSION} · Server-side credentials only")
    st.divider()

    st.subheader("🔌 القنوات")
    for family, cfg in PROVIDERS.items():
        key_ok = bool(orch.keys.get(family))
        st.write(f"{'🟢' if key_ok else '🔴'} {family}")

    st.divider()
    depth_label = st.radio("حجم المجلس", ("5", "10", "15"), format_func=lambda x: f"{x} وكيل حقيقي")
    tone = st.selectbox("النبرة", ("علمي وأكاديمي دقيق 📚", "مباشر وسريع ⚡", "إيجابي وداعم 🤝", "ساخر ومرح 🎭"))
    mode = st.selectbox("النمط", ("إجابة عادية متوازية ⚡", "نقاش عميق بملخص الحكم 🧠", "مناظرة كاملة متعددة الجولات 🔥"))
    if st.button("🗑️ مسح المجلس", use_container_width=True):
        reset_state()

    st.divider()
    st.caption("لا توجد خانات API Keys في الواجهة. تُقرأ الأسرار من Streamlit Secrets أو متغيرات البيئة فقط.")

with st.expander("🧩 حالة النماذج الحقيقية", expanded=False):
    with st.spinner("اكتشاف النماذج المتاحة...", show_time=False):
        all_slots = orch.slots()
    for family, family_slots in all_slots.items():
        if not family_slots:
            st.warning(f"{family}: لا يوجد نموذج مكتشف/متاح حاليًا.")
        else:
            st.write(f"**{family}**")
            for slot in family_slots:
                st.write(f"{slot.level}. `{slot.model}`")

for msg in st.session_state.chat_history:
    role = "user" if msg.get("role") == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(msg.get("content_ar", ""))

query = st.chat_input("اكتب سؤالك للمجلس الخماسي...")
if query:
    ok, error = InputGuard.inspect(query)
    if not ok:
        st.error(error)
    else:
        st.session_state.chat_history.append({"role": "user", "sender": "أنت", "content_ar": query})
        st.session_state.pending_query = query
        st.rerun()

if st.session_state.pending_query:
    query = st.session_state.pending_query
    ok, error = InputGuard.inspect(query)
    if ok:
        with st.spinner("⚡ المجلس يعمل بالتوازي...", show_time=True):
            all_slots = orch.slots()
            slots = select_slots(all_slots, depth_label)
            payload, cached = run_council(query, st.session_state.chat_history[:-1], slots, mode, tone, orch)

        successful = [r for r in payload["results"] if r["success"]]
        failed = [r for r in payload["results"] if not r["success"]]
        st.session_state.last_run = payload

        st.subheader(f"🧠 نتائج المجلس — {len(successful)} ناجح / {len(failed)} غير متاح")
        if cached:
            st.caption("💾 النتيجة مسترجعة من الذاكرة المؤقتة.")

        for r in payload["results"]:
            title = f"{r['family']} · {r['model_used']}"
            with st.expander(("🟢 " if r["success"] else "🔴 ") + title, expanded=r["success"]):
                if r["success"]:
                    st.markdown(r["text"])
                    st.caption(f"زمن التنفيذ: {r['latency']:.2f}s")
                else:
                    st.error(r["error"] or "فشل غير معروف")

        if payload.get("moderator") and payload["moderator"].get("success"):
            st.divider()
            st.subheader("🏆 الحكم النهائي للمجلس")
            st.markdown(payload["moderator"]["text"])
            st.caption(f"الحَكَم: {payload['moderator']['model_used']}")
            st.session_state.chat_history.append({
                "role": "assistant", "sender": "AI Council Moderator",
                "content_ar": payload["moderator"]["text"],
            })
        else:
            summary = "\n\n".join(f"### {r['family']} — {r['model_used']}\n{r['text']}" for r in payload["results"] if r["success"])
            if summary:
                st.session_state.chat_history.append({"role": "assistant", "sender": "AI Council", "content_ar": summary})

        export_json = json.dumps(payload, ensure_ascii=False, indent=2)
        export_txt = "\n\n".join(f"{r['family']} | {r['model_used']}\n{r['text'] or r['error']}" for r in payload["results"])
        if payload.get("moderator"):
            export_txt += "\n\n===== MODERATOR =====\n" + (payload["moderator"]["text"] or payload["moderator"]["error"] or "")
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("📥 تصدير JSON", export_json, "ai_council_run.json", "application/json", use_container_width=True)
        with c2:
            st.download_button("📥 تصدير TXT", export_txt, "ai_council_run.txt", "text/plain", use_container_width=True)

        st.session_state.pending_query = None

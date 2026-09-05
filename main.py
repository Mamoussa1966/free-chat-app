# -*- coding: utf-8 -*-
from __future__ import annotations

import concurrent.futures
import os
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

try:
    import streamlit as st
except ModuleNotFoundError:  # Allows provider/local unit tests in minimal CI environments.
    st = None

from audit import build_audit
from local_engine import generate_local
from providers import PROVIDERS, call_official, get_models, get_secret, safe_error

APP_VERSION = "V19.4-PRODUCTION-HARDENED"
SCHEMA_VERSION = "5.0"
MAX_QUERY_CHARS = 6000
MAX_HISTORY_MESSAGES = 30
MAX_CONTEXT_CHARS = 12000
MAX_OUTPUT_CHARS = 6000
MAX_PEER_CHARS = 8000
MAX_ROOM_SIZE = 15
MAX_WORKERS = 15
try:
    REQUEST_TIMEOUT = max(5, min(90, int(os.getenv("AI_ROOM_TIMEOUT", "35"))))
except ValueError:
    REQUEST_TIMEOUT = 35

CORE_AGENTS: Tuple[Dict[str, str], ...] = (
    {"id":"analysis", "provider":"openai", "name":"ChatGPT", "role":"التحليل العام", "icon":"💬", "instruction":"حلل الهدف والوقائع والقيود والخيارات الرئيسية."},
    {"id":"reasoning", "provider":"gemini", "name":"Gemini", "role":"الاستدلال المنطقي", "icon":"♊", "instruction":"فكك المسألة واختبر العلاقات المنطقية والبدائل."},
    {"id":"critic", "provider":"anthropic", "name":"Claude", "role":"النقد والمنهج", "icon":"🧠", "instruction":"ابحث عن الثغرات والتناقضات وما يحتاج دليلاً."},
    {"id":"risk", "provider":"xai", "name":"Grok", "role":"المخاطر والبدائل", "icon":"⚡", "instruction":"قيّم المخاطر ونقاط الفشل والبدائل."},
    {"id":"synthesis", "provider":"kimi", "name":"Kimi", "role":"التركيب التنفيذي", "icon":"🌙", "instruction":"ركب أفضل النقاط في قرار عملي."},
)
EXTRA_LOCAL_AGENTS: Tuple[Dict[str, str], ...] = (
    {"id":"factcheck", "provider":"local", "name":"مراجع الحقائق", "role":"فحص الادعاءات", "icon":"🔬", "instruction":"حدد الادعاءات التي تحتاج تحققاً."},
    {"id":"planner", "provider":"local", "name":"مخطط التنفيذ", "role":"خطة العمل", "icon":"🗺️", "instruction":"حوّل النتيجة إلى خطوات قابلة للتنفيذ."},
    {"id":"security", "provider":"local", "name":"مراجع الأمان", "role":"الأمان", "icon":"🛡️", "instruction":"راجع مخاطر الأمان والخصوصية."},
    {"id":"engineering", "provider":"local", "name":"المهندس", "role":"الهندسة", "icon":"⚙️", "instruction":"راجع الاعتمادية والصيانة والتوسع."},
    {"id":"economics", "provider":"local", "name":"محلل التكلفة", "role":"الكفاءة", "icon":"📊", "instruction":"وازن الموارد والتكلفة."},
    {"id":"ux", "provider":"local", "name":"مراجع التجربة", "role":"تجربة المستخدم", "icon":"🧩", "instruction":"راجع الوضوح وسهولة الاستخدام."},
    {"id":"devils_advocate", "provider":"local", "name":"محامي الشيطان", "role":"الاعتراض", "icon":"⚖️", "instruction":"قدم أقوى اعتراض منطقي."},
    {"id":"minimalist", "provider":"local", "name":"المبسّط", "role":"التبسيط", "icon":"✂️", "instruction":"ابحث عن أبسط حل آمن."},
    {"id":"quality", "provider":"local", "name":"ضابط الجودة", "role":"الجودة", "icon":"✅", "instruction":"ضع معايير قبول واختبارات."},
    {"id":"compliance", "provider":"local", "name":"مراجع الامتثال", "role":"الامتثال", "icon":"⚖️", "instruction":"راجع المتطلبات التنظيمية وحدد ما يحتاج مراجعة متخصصة."},
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
    error: str = ""
    official_authenticated: bool = False
    source_mode: str = "local_direct"
    fallback_used: bool = False
    provider_attempted: bool = False


def clean_text(value: object, limit: int = MAX_OUTPUT_CHARS) -> str:
    return str(value or "").strip()[:limit].strip()


def build_context(messages: List[dict]) -> str:
    rows = []
    for msg in messages[-MAX_HISTORY_MESSAGES:]:
        sender = clean_text(msg.get("sender", ""), 80)
        content = clean_text(msg.get("content", ""), 900)
        if content:
            rows.append(f"{sender}: {content}")
    return "\n".join(rows)[-MAX_CONTEXT_CHARS:]


def validate_query(query: str) -> Tuple[bool, str]:
    q = (query or "").strip()
    if not q:
        return False, "اكتب السؤال أولاً."
    if len(q) > MAX_QUERY_CHARS:
        return False, f"الحد الأقصى للسؤال {MAX_QUERY_CHARS} حرف."
    return True, ""


def select_agents(size: int) -> List[Dict[str, str]]:
    size = max(5, min(MAX_ROOM_SIZE, int(size)))
    return list(CORE_AGENTS) + list(EXTRA_LOCAL_AGENTS[: size - 5])


def make_prompt(agent: Dict[str, str], query: str, context: str, tone: str, peer_text: str = "") -> str:
    peer = f"\nنتائج زملاء سابقة للنقد:\n{peer_text[-MAX_PEER_CHARS:]}" if peer_text else ""
    return (
        "أنت عضو في غرفة متعددة المصادر. لا تدّع أنك نموذج تجاري معين إلا إذا كان الرد فعلياً من مزود رسمي مصادق عليه. "
        f"دورك: {agent['role']}. تعليمات الدور: {agent['instruction']}. النبرة: {tone}. "
        "أجب بالعربية ما لم يتطلب السؤال غير ذلك.\n\n"
        f"السؤال:\n{query}\n\nالسياق السابق:\n{context or '(لا يوجد)'}{peer}"
    )


def _local_result(agent: Dict[str, str], text: str, started: float, error: str = "", fallback: bool = False) -> AgentResult:
    return AgentResult(
        agent["id"], agent["name"], agent["role"], agent["provider"], clean_text(text), bool(text),
        time.perf_counter() - started, "local_fallback" if fallback else "local_direct", "local-engine", error,
        False, "local_fallback" if fallback else "local_direct", fallback, bool(fallback),
    )


def run_agent(agent: Dict[str, str], query: str, context: str, tone: str, credential: Optional[str] = None, peer_text: str = "") -> AgentResult:
    started = time.perf_counter()

    if agent["provider"] == "local":
        try:
            text = generate_local(agent["id"], agent["role"], agent["instruction"], query, context, tone, peer_text)
            return _local_result(agent, text, started)
        except Exception as exc:
            return AgentResult(agent["id"], agent["name"], agent["role"], "local", "تعذر تشغيل المقعد المحلي.", False, time.perf_counter()-started, "error", "local-engine", safe_error(exc), False, "error", False, False)

    key = (credential or "").strip()
    if not key:
        try:
            text = generate_local(agent["id"], agent["role"], agent["instruction"], query, context, tone, peer_text)
            return _local_result(agent, text, started)
        except Exception as exc:
            return AgentResult(agent["id"], agent["name"], agent["role"], agent["provider"], "تعذر تشغيل المقعد المحلي.", False, time.perf_counter()-started, "error", "local-engine", safe_error(exc), False, "error", False, False)

    errors: List[str] = []
    prompt = make_prompt(agent, query, context, tone, peer_text)
    cfg = PROVIDERS[agent["provider"]]
    for model in get_models(cfg):
        try:
            text = call_official(agent["provider"], prompt, model, REQUEST_TIMEOUT, credential=key)
            return AgentResult(agent["id"], agent["name"], agent["role"], agent["provider"], clean_text(text), True,
                               time.perf_counter()-started, "official_api", model, "", True, "official_api", False, True)
        except Exception as exc:
            errors.append(f"{model}: {safe_error(exc)}")

    try:
        text = generate_local(agent["id"], agent["role"], agent["instruction"], query, context, tone, peer_text)
        return _local_result(agent, text, started, " | ".join(errors)[:1400], True)
    except Exception as exc:
        return AgentResult(agent["id"], agent["name"], agent["role"], agent["provider"], "تعذر تشغيل المقعد بعد فشل المزود الرسمي.", False,
                           time.perf_counter()-started, "error", "", safe_error(exc), False, "error", True, True)


def collect_active_credentials() -> Dict[str, Optional[str]]:
    return {provider_id: get_secret(cfg.key_names) for provider_id, cfg in PROVIDERS.items()}


def run_parallel(agents: List[Dict[str, str]], query: str, history: List[dict], tone: str, active_credentials: Optional[Dict[str, Optional[str]]] = None) -> List[AgentResult]:
    context = build_context(history)
    active_credentials = active_credentials if active_credentials is not None else collect_active_credentials()
    results: List[AgentResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(agents))) as pool:
        future_map = {
            pool.submit(run_agent, a, query, context, tone, active_credentials.get(a["provider"]), ""): a
            for a in agents
        }
        for future in concurrent.futures.as_completed(future_map):
            agent = future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(AgentResult(agent["id"], agent["name"], agent["role"], agent["provider"], "تعذر تشغيل هذا المقعد، واستمر المجلس بدونه.", False, 0.0, "error", "", safe_error(exc), False, "error", True, bool(active_credentials.get(agent["provider"]))))
    order = {a["id"]: i for i, a in enumerate(agents)}
    results.sort(key=lambda r: order.get(r.agent_id, 999))
    return results


def compact_results(results: List[AgentResult], limit: int = 9000) -> str:
    chunks = []
    for r in results:
        if r.success and r.text:
            source = "رسمي" if r.official_authenticated else "محلي"
            chunks.append(f"[{r.agent_name} | {source}]\n{r.text}")
    return "\n\n".join(chunks)[-limit:]


def run_debate(results: List[AgentResult], query: str, tone: str) -> List[AgentResult]:
    good = [r for r in results if r.success]
    if not good:
        return results
    started = time.perf_counter()
    text = generate_local("devils_advocate", "مراجع المناظرة", "قارن الردود وحدد الاتفاق والاختلاف وأقوى نقطة ضعف.", query, "", tone, compact_results(good, 8000))
    results.append(AgentResult("bounded_critique", "مراجع المناظرة", "مراجعة جماعية محدودة", "local", clean_text(text), True, time.perf_counter()-started, "local_debate", "local-engine", "", False, "local_direct", False, False))
    return results


def local_moderator(query: str, results: List[AgentResult], tone: str) -> AgentResult:
    started = time.perf_counter()
    text = generate_local("quality", "الحكم المحلي", "اجمع الأدلة ورجّح النتيجة دون ادعاء مصادر خارجية.", query, "", tone, compact_results(results, 10000))
    return AgentResult("moderator_local", "الحكم المحلي", "الخلاصة المحايدة", "local", clean_text(text), True, time.perf_counter()-started, "local_moderator", "local-engine", "", False, "local_direct", False, False)


def result_audit(r: AgentResult) -> dict:
    return {
        "agent_id": r.agent_id,
        "agent_name": r.agent_name,
        "provider_family": r.provider,
        "mode": r.mode,
        "source_mode": r.source_mode,
        "provider_attempted": r.provider_attempted,
        "official_authenticated": r.official_authenticated,
        "fallback_used": r.fallback_used,
        "model_id": r.model_used if r.official_authenticated else None,
        "local_engine": not r.official_authenticated,
        "success": r.success,
        "latency_seconds": round(r.latency, 4),
        "error_present": bool(r.error),
    }


def build_export(query: str, results: List[AgentResult], moderator: Optional[AgentResult], run_id: str) -> str:
    payload = build_audit(run_id, query, results, moderator, APP_VERSION, SCHEMA_VERSION)
    payload["results"] = [{**asdict(r), "audit": result_audit(r)} for r in results]
    if moderator:
        payload["moderator"] = {**asdict(moderator), "audit": result_audit(moderator)}
    return __import__("json").dumps(payload, ensure_ascii=False, indent=2)


def render_result(r: AgentResult) -> None:
    if r.mode == "official_api":
        source = f"🟢 رسمي — {r.model_used}"
    elif r.mode == "local_fallback":
        source = "🟡 احتياطي محلي بعد محاولة رسمية"
    elif r.mode.startswith("local"):
        source = "🔵 محلي مباشر"
    else:
        source = "🔴 تعذر التشغيل"
    icons = {a["id"]: a["icon"] for a in CORE_AGENTS + EXTRA_LOCAL_AGENTS}
    with st.container(border=True):
        st.caption(f"{icons.get(r.agent_id, '🤖')} **{r.agent_name}** · {r.role} · {source} · {r.latency:.2f}s")
        st.markdown(r.text)
        if r.error:
            with st.expander("تفاصيل المسار"):
                st.caption(r.error)


def reset() -> None:
    for key in ("messages", "last_results", "last_moderator", "last_query", "last_run_id"):
        st.session_state[key] = [] if key in ("messages", "last_results") else (None if key == "last_moderator" else "")
    st.rerun()


def init_state() -> None:
    defaults = {"messages": [], "last_results": [], "last_moderator": None, "last_query": "", "last_run_id": ""}
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def main() -> None:
    if st is None:
        raise RuntimeError("Streamlit is required to run the web UI. Install requirements.txt first.")
    st.set_page_config(page_title="AI Council V19.4", page_icon="🏛️", layout="centered", initial_sidebar_state="collapsed")
    init_state()
    st.markdown("<style>.block-container{max-width:1100px;padding:1rem .8rem 5rem}.hero{text-align:center}.truth,.summary{border:1px solid rgba(128,128,128,.28);border-radius:16px;padding:15px;margin:10px 0;line-height:1.85}</style>", unsafe_allow_html=True)
    st.markdown(f"<div class='hero'><h1>🏛️ AI Council — V19.4</h1><div>{APP_VERSION}</div></div>", unsafe_allow_html=True)
    st.markdown("<div class='truth'><b>قاعدة الهوية:</b> المقاعد الخمسة تمثل عائلات ChatGPT/OpenAI وGemini/Google وClaude/Anthropic وGrok/xAI وKimi/Moonshot. بدون اعتماد رسمي تعمل محلياً. لا تُعرض الهوية الأصلية إلا بعد نجاح API رسمي مصادق عليه.</div>", unsafe_allow_html=True)

    active_credentials = collect_active_credentials()
    with st.sidebar:
        st.header("⚙️ لوحة التحكم")
        size = int(st.radio("حجم الغرفة", ["5", "10", "15"], index=0))
        tone = st.selectbox("النبرة", ["علمية دقيقة", "مباشرة وسريعة", "ودية", "نقدية صارمة"], index=0)
        mode = st.selectbox("النمط", ["موازٍ سريع", "نقاش محدود", "نقاش + حكم محلي"], index=0)
        st.divider()
        st.subheader("🔌 حالة الاعتمادات")
        for cfg in PROVIDERS.values():
            st.success(f"{cfg.icon} {cfg.family}: API متاح") if active_credentials.get(cfg.provider_id) else st.info(f"{cfg.icon} {cfg.family}: بدون API → محلي")
        st.caption("الأسرار تُقرأ من Streamlit Secrets أو Environment فقط؛ لا توجد حقول مفاتيح في الواجهة.")
        if st.button("🗑️ مسح الغرفة", use_container_width=True):
            reset()

    agents = select_agents(size)
    cols = st.columns(5)
    for col, agent in zip(cols, CORE_AGENTS):
        with col:
            connected = bool(active_credentials.get(agent["provider"]))
            st.metric(agent["name"], "🟢 API" if connected else "🔵 Local", agent["role"])
    if size > 5:
        st.caption(f"المقاعد الإضافية ({size - 5}) محلية صراحةً.")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    query = st.chat_input("اكتب سؤالك للمجلس…")
    if query:
        ok, error = validate_query(query)
        if not ok:
            st.error(error)
            return
        query = query.strip()
        st.session_state.messages.append({"role":"user", "sender":"أنت", "content":query})
        with st.status("⚡ تشغيل أعضاء الغرفة…", expanded=True) as status:
            results = run_parallel(agents, query, st.session_state.messages[:-1], tone, active_credentials)
            status.update(label="اكتملت الجولة الأساسية", state="complete")
        if mode in ("نقاش محدود", "نقاش + حكم محلي"):
            results = run_debate(results, query, tone)
        moderator = local_moderator(query, results, tone) if mode == "نقاش + حكم محلي" else None
        run_id = uuid.uuid4().hex[:16]
        st.session_state.last_results = [asdict(r) for r in results]
        st.session_state.last_moderator = asdict(moderator) if moderator else None
        st.session_state.last_query = query
        st.session_state.last_run_id = run_id
        with st.chat_message("assistant"):
            official = sum(r.official_authenticated for r in results)
            fallback = sum(r.fallback_used for r in results)
            direct = sum(r.mode.startswith("local") and not r.fallback_used for r in results)
            st.markdown(f"<div class='summary'><b>الجولة:</b> {len(results)} نتيجة · {official} رسمي ناجح · {direct} محلي مباشر · {fallback} احتياطي</div>", unsafe_allow_html=True)
            for result in results:
                render_result(result)
            if moderator:
                st.markdown("### 🏛️ الحكم المحلي")
                render_result(moderator)
        combined = "\n\n".join(f"{r.agent_name}: {r.text}" for r in results)
        if moderator:
            combined += f"\n\nالحكم المحلي: {moderator.text}"
        st.session_state.messages.append({"role":"assistant", "sender":"المجلس", "content":combined})

    if st.session_state.last_results:
        results = [AgentResult(**x) for x in st.session_state.last_results]
        moderator = AgentResult(**st.session_state.last_moderator) if st.session_state.last_moderator else None
        st.download_button("⬇️ تصدير JSON Audit", build_export(st.session_state.last_query, results, moderator, st.session_state.last_run_id or "round"), file_name=f"ai_council_{st.session_state.last_run_id or 'round'}.json", mime="application/json", use_container_width=True)


if __name__ == "__main__":
    main()

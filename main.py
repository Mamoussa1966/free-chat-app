# -*- coding: utf-8 -*-
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import streamlit as st

from local_engine import generate_local
from providers import PROVIDERS, call_official, get_models, get_secret, safe_error

APP_VERSION = "V20.0-MULTI-MODEL-VERIFICATION-GATED"
SCHEMA_VERSION = "5.0"
MAX_QUERY_CHARS = 6000
MAX_HISTORY_MESSAGES = 30
MAX_CONTEXT_CHARS = 12000
MAX_OUTPUT_CHARS = 5000
MAX_PEER_CHARS = 7000
MAX_WORKERS = 15
REQUEST_TIMEOUT = max(5, min(90, int(os.getenv("AI_ROOM_TIMEOUT", "35"))))

# Multi-model verification contract. These are model-role assignments, not claims
# that this application can directly access models exposed only by a chat UI.
# Actual API execution remains opt-in and uses server-side provider credentials.
VERIFICATION_COUNCIL: Tuple[Dict[str, str], ...] = (
    {"id": "haiku_scan", "model": "Haiku 4.5", "stage": "SCAN", "authority": "DISCOVERY",
     "instruction": "امسح الكود وابحث عن الأخطاء الواضحة، imports المكسورة، التعارضات، الملفات المفقودة، ونقاط الفشل المحتملة."},
    {"id": "sonnet_audit", "model": "Sonnet 5", "stage": "AUDIT", "authority": "CODE_AUDITOR",
     "instruction": "دقق الكود والـ contracts والـ error handling والـ providers والـ state management، وتحقق من نتائج الفحص الأولي."},
    {"id": "opus_red_team", "model": "Opus 5", "stage": "RED_TEAM", "authority": "INDEPENDENT_REVIEW",
     "instruction": "افترض أن المراجعات السابقة قد تكون خاطئة. حاول إثبات فشل النظام، خصوصاً في مسارات الانقطاع والتزامن والعزل والـ fallback."},
    {"id": "fable_judge", "model": "Fable 5.1", "stage": "FINAL_GATE", "authority": "FINAL_ADJUDICATOR",
     "instruction": "احكم بالأدلة فقط. حل تعارضات المراجعين وفق Requirement -> Contract -> Code -> Evidence، ولا تمنح Production Freeze مع Critical/High غير مغلق."},
)

PRODUCTION_FREEZE_RULES = {
    "required_models": tuple(x["model"] for x in VERIFICATION_COUNCIL),
    "critical_open_blocks": True,
    "high_open_blocks": True,
    "majority_vote": False,
    "fable_is_final_gate": True,
}

CORE_AGENTS: Tuple[Dict[str, str], ...] = (
    {"id": "analysis", "provider": "openai", "name": "ChatGPT", "role": "التحليل العام", "icon": "💬", "instruction": "حلل الهدف والوقائع والقيود والخيارات الرئيسية."},
    {"id": "reasoning", "provider": "gemini", "name": "Gemini", "role": "الاستدلال المنطقي", "icon": "♊", "instruction": "فكك المسألة واختبر العلاقات المنطقية والبدائل."},
    {"id": "critic", "provider": "anthropic", "name": "Claude", "role": "النقد والمنهج", "icon": "🧠", "instruction": "ابحث عن الثغرات والتناقضات وما يحتاج دليلاً."},
    {"id": "risk", "provider": "xai", "name": "Grok", "role": "المخاطر والبدائل", "icon": "⚡", "instruction": "قيّم المخاطر ونقاط الفشل والبدائل."},
    {"id": "synthesis", "provider": "kimi", "name": "Kimi", "role": "التركيب التنفيذي", "icon": "🌙", "instruction": "ركب أفضل النقاط في قرار عملي."},
)

EXTRA_LOCAL_AGENTS: Tuple[Dict[str, str], ...] = (
    {"id": "factcheck", "provider": "local", "name": "مراجع الحقائق", "role": "فحص الادعاءات", "icon": "🔬", "instruction": "حدد الادعاءات التي تحتاج تحققاً."},
    {"id": "planner", "provider": "local", "name": "مخطط التنفيذ", "role": "خطة العمل", "icon": "🗺️", "instruction": "حوّل النتيجة إلى خطوات قابلة للتنفيذ."},
    {"id": "security", "provider": "local", "name": "مراجع الأمان", "role": "الأمان", "icon": "🛡️", "instruction": "راجع مخاطر الأمان والخصوصية."},
    {"id": "engineering", "provider": "local", "name": "المهندس", "role": "الهندسة", "icon": "⚙️", "instruction": "راجع الاعتمادية والصيانة والتوسع."},
    {"id": "economics", "provider": "local", "name": "محلل التكلفة", "role": "الكفاءة", "icon": "📊", "instruction": "وازن الموارد والتكلفة."},
    {"id": "ux", "provider": "local", "name": "مراجع التجربة", "role": "تجربة المستخدم", "icon": "🧩", "instruction": "راجع الوضوح وسهولة الاستخدام."},
    {"id": "devils_advocate", "provider": "local", "name": "محامي الشيطان", "role": "الاعتراض", "icon": "⚖️", "instruction": "قدم أقوى اعتراض منطقي."},
    {"id": "minimalist", "provider": "local", "name": "المبسّط", "role": "التبسيط", "icon": "✂️", "instruction": "ابحث عن أبسط حل آمن."},
    {"id": "quality", "provider": "local", "name": "ضابط الجودة", "role": "الجودة", "icon": "✅", "instruction": "ضع معايير قبول واختبارات."},
    {"id": "compliance", "provider": "local", "name": "مراجِع الامتثال", "role": "الامتثال والقانون", "icon": "⚖️", "instruction": "راجع التوافق مع اللوائح والأنظمة وحدد ما يحتاج مراجعة قانونية متخصصة."},
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
    source_mode: str = "local"
    fallback_used: bool = False


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
    size = max(5, min(15, int(size)))
    return list(CORE_AGENTS) + list(EXTRA_LOCAL_AGENTS[: size - 5])


def make_prompt(agent: Dict[str, str], query: str, context: str, tone: str, peer_text: str = "") -> str:
    peer = f"\nنتائج زملاء سابقة للنقد:\n{peer_text[-MAX_PEER_CHARS:]}" if peer_text else ""
    return (
        "أنت عضو في غرفة ذكاء اصطناعي متعددة المصادر. لا تدّع أنك نموذج تجاري معين إلا إذا كان الرد فعلياً من مزود رسمي مصادق عليه. "
        f"دورك: {agent['role']}. تعليمات الدور: {agent['instruction']}. النبرة: {tone}. "
        "أجب بالعربية ما لم يتطلب السؤال غير ذلك.\n\n"
        f"السؤال:\n{query}\n\nالسياق السابق:\n{context or '(لا يوجد)'}{peer}"
    )


def _local_result(agent: Dict[str, str], text: str, started: float, error: str = "", fallback: bool = False) -> AgentResult:
    return AgentResult(
        agent["id"], agent["name"], agent["role"], agent["provider"], clean_text(text), bool(text),
        time.perf_counter() - started, "local-fallback" if fallback else "local", "local-engine", error,
        False, "local-fallback" if fallback else "local", fallback,
    )


def run_agent(agent: Dict[str, str], query: str, context: str, tone: str, credential: Optional[str] = None, peer_text: str = "") -> AgentResult:
    started = time.perf_counter()

    # Local-only seats never enter the provider layer.
    if agent["provider"] == "local":
        try:
            return _local_result(agent, generate_local(agent["id"], agent["role"], agent["instruction"], query, context, tone, peer_text), started)
        except Exception as exc:
            return AgentResult(agent["id"], agent["name"], agent["role"], "local", "تعذر تشغيل المقعد المحلي.", False,
                               time.perf_counter() - started, "error", "local-engine", safe_error(exc), False, "error", False)

    cfg = PROVIDERS[agent["provider"]]
    key = (credential or "").strip()
    errors: List[str] = []

    # No credential reaches this worker as None/empty; therefore no network call.
    if key:
        prompt = make_prompt(agent, query, context, tone, peer_text)
        for model in get_models(cfg):
            try:
                text = call_official(agent["provider"], prompt, model, REQUEST_TIMEOUT, credential=key)
                return AgentResult(agent["id"], agent["name"], agent["role"], agent["provider"], clean_text(text), True,
                                   time.perf_counter() - started, "official", model, "", True, "official", False)
            except Exception as exc:
                errors.append(f"{model}: {safe_error(exc)}")
    else:
        # Missing credentials are a normal local-direct state, not a fallback.
        try:
            text = generate_local(agent["id"], agent["role"], agent["instruction"], query, context, tone, peer_text)
            return _local_result(agent, text, started, "", False)
        except Exception as exc:
            return AgentResult(agent["id"], agent["name"], agent["role"], agent["provider"],
                               "تعذر تشغيل المقعد المحلي، واستمر المجلس ببقية المقاعد.", False,
                               time.perf_counter() - started, "error", "local-engine", safe_error(exc), False, "error", False)

    # Official path is optional. Local continuity is mandatory after an actual
    # authenticated-provider attempt has failed.
    try:
        text = generate_local(agent["id"], agent["role"], agent["instruction"], query, context, tone, peer_text)
        return _local_result(agent, text, started, " | ".join(errors)[:1200], True)
    except Exception as exc:
        return AgentResult(agent["id"], agent["name"], agent["role"], agent["provider"],
                           "تعذر تشغيل المقعد، واستمر المجلس ببقية المقاعد.", False,
                           time.perf_counter() - started, "error", "", safe_error(exc), False, "error", True)


def collect_active_credentials() -> Dict[str, Optional[str]]:
    """Read Streamlit secrets exactly once on the Streamlit script thread."""
    active: Dict[str, Optional[str]] = {}
    for provider_id, cfg in PROVIDERS.items():
        active[provider_id] = get_secret(cfg.key_names)
    return active


def run_parallel(agents: List[Dict[str, str]], query: str, history: List[dict], tone: str,
                 active_credentials: Optional[Dict[str, Optional[str]]] = None) -> List[AgentResult]:
    context = build_context(history)
    # IMPORTANT: never call st.secrets from worker threads. Credentials are
    # captured on the main Streamlit thread and passed as plain strings.
    active_credentials = active_credentials or collect_active_credentials()
    results: List[AgentResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(agents))) as pool:
        future_map = {
            pool.submit(
                run_agent, a, query, context, tone,
                active_credentials.get(a["provider"]),
            ): a
            for a in agents
        }
        for future in concurrent.futures.as_completed(future_map):
            agent = future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(AgentResult(agent["id"], agent["name"], agent["role"], agent["provider"],
                                           "تعذر تشغيل هذا المقعد، واستمر المجلس بدونه.", False, 0.0,
                                           "error", "", safe_error(exc), False, "error", True))
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
    results.append(AgentResult("bounded_critique", "مراجع المناظرة", "مراجعة جماعية محدودة", "local", clean_text(text), True,
                               time.perf_counter() - started, "local-debate", "local-engine", "", False, "local", False))
    return results


def local_moderator(query: str, results: List[AgentResult], tone: str) -> AgentResult:
    started = time.perf_counter()
    text = generate_local("quality", "الحكم المحلي", "اجمع الأدلة ورجّح النتيجة دون ادعاء مصادر خارجية.", query, "", tone, compact_results(results, 10000))
    return AgentResult("moderator_local", "الحكم المحلي", "الخلاصة المحايدة", "local", clean_text(text), True,
                       time.perf_counter() - started, "local-moderator", "local-engine", "", False, "local", False)


def verification_contract() -> dict:
    """Return the immutable verification policy used by the application UI/audit."""
    return {
        "pipeline": [dict(x) for x in VERIFICATION_COUNCIL],
        "rules": dict(PRODUCTION_FREEZE_RULES),
        "decision": "BLOCK unless all required gates pass; no majority-vote override.",
    }


def production_freeze_decision(gate_results: Dict[str, str]) -> str:
    """Deterministic release gate. Expected values: PASS/FAIL/BLOCKED/OPEN."""
    normalized = {k: str(v).upper().strip() for k, v in gate_results.items()}
    required = [x["id"] for x in VERIFICATION_COUNCIL]
    if any(normalized.get(k) != "PASS" for k in required):
        return "BLOCKED"
    return "PASS"


def verification_prompt(query: str, stage: Dict[str, str], evidence: str = "") -> str:
    return (
        "أنت جزء من لجنة تحقق متعددة النماذج. لا تفترض صحة أي تقرير سابق. "
        f"المرحلة: {stage['stage']} | النموذج المكلّف: {stage['model']} | السلطة: {stage['authority']}.\n"
        f"تعليمات المرحلة: {stage['instruction']}\n\n"
        f"المسألة/المهمة:\n{query}\n\n"
        f"الأدلة المتاحة:\n{evidence[-12000:] if evidence else '(لا توجد أدلة إضافية)'}\n\n"
        "أخرج findings قابلة للتدقيق، ولا تستخدم PASS إلا إذا كانت الأدلة كافية."
    )


def audit_record(r: AgentResult) -> dict:
    return {
        "agent_id": r.agent_id,
        "agent_name": r.agent_name,
        "provider_family": r.provider,
        "mode": r.mode,
        "source_mode": r.source_mode,
        "official_authenticated": bool(r.official_authenticated),
        "fallback_used": bool(r.fallback_used),
        "model_id": r.model_used if r.official_authenticated else None,
        "local_engine": not r.official_authenticated,
        "success": bool(r.success),
        "latency_seconds": round(r.latency, 4),
    }


def round_hash(query: str, results: List[AgentResult], moderator: Optional[AgentResult]) -> str:
    payload = {"q": query, "r": [asdict(r) for r in results], "m": asdict(moderator) if moderator else None}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def export_json(query: str, results: List[AgentResult], moderator: Optional[AgentResult], run_id: str) -> str:
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "app_version": APP_VERSION,
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "identity_policy": "Only successful authenticated official-provider responses are labeled official. Local outputs never impersonate commercial models.",
            "verification_contract": verification_contract(),
            "free_mode_guarantee": "No credential means no provider network call; the seat runs Local Engine directly.",
            "query": query,
            "results": [{**asdict(r), "audit": audit_record(r)} for r in results],
            "moderator": ({**asdict(moderator), "audit": audit_record(moderator)} if moderator else None),
        },
        ensure_ascii=False,
        indent=2,
    )


def render_result(r: AgentResult) -> None:
    if r.mode == "official":
        source = f"🟢 رسمي — {r.model_used}"
    elif r.mode == "local-fallback":
        source = "🟡 احتياطي محلي"
    elif r.mode.startswith("local"):
        source = "🔵 محلي"
    else:
        source = "🔴 تعذر التشغيل"

    icon = next((a["icon"] for a in CORE_AGENTS + EXTRA_LOCAL_AGENTS if a["id"] == r.agent_id), "🤖")
    with st.container(border=True):
        st.caption(f"{icon} **{r.agent_name}** | {r.role} · {source} · {r.latency:.2f}s")
        # Preserve Markdown (lists, tables, code blocks, emphasis, etc.).
        # Streamlit renders Markdown safely; do not HTML-escape model output.
        st.markdown(r.text)
        if r.error:
            with st.expander("تفاصيل المسار"):
                st.caption(r.error)


def reset() -> None:
    for key, value in {"messages": [], "last_results": [], "last_moderator": None, "last_query": "", "last_run_id": ""}.items():
        st.session_state[key] = value
    st.rerun()


def main() -> None:
    st.set_page_config(page_title="AI Council V19.3", page_icon="🏛️", layout="centered", initial_sidebar_state="collapsed")
    st.markdown(
        "<style>.block-container{max-width:1050px;padding:1rem .8rem 5rem}.hero{text-align:center}.truth,.card,.summary{border:1px solid rgba(128,128,128,.28);border-radius:16px;padding:15px;margin:10px 0;line-height:1.85}.title{font-weight:800;font-size:1.08rem}.meta{opacity:.65;font-size:.8rem;margin:.35rem 0 .8rem}.body{line-height:1.85}</style>",
        unsafe_allow_html=True,
    )
    for key, value in {"messages": [], "last_results": [], "last_moderator": None, "last_query": "", "last_run_id": ""}.items():
        st.session_state.setdefault(key, value)

    st.markdown(f"<div class='hero'><h1>🏛️ AI Council — الغرفة الخماسية</h1><div>{APP_VERSION}</div></div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='truth'><b>العقد التشغيلي:</b> بدون مفاتيح تعمل الغرفة محلياً. عند وجود اعتماد رسمي فقط يحاول المقعد API الرسمي. أي فشل رسمي يؤدي إلى Local Fallback. المحرك المحلي لا ينتحل هوية نموذج تجاري.</div>",
        unsafe_allow_html=True,
    )

    with st.expander("🔐 بروتوكول التحقق متعدد النماذج", expanded=False):
        for stage in VERIFICATION_COUNCIL:
            st.markdown(f"**{stage['stage']} — {stage['model']}** · {stage['authority']}\n\n{stage['instruction']}")
        st.caption("Production Freeze: لا يوجد تصويت بالأغلبية. Fable 5.1 هو بوابة الحكم النهائية، وأي Critical/High مفتوح يمنع الاعتماد.")

    active_credentials = collect_active_credentials()

    with st.sidebar:
        st.header("⚙️ لوحة التحكم")
        size = int(st.radio("حجم الغرفة", ["5", "10", "15"], index=0))
        tone = st.selectbox("النبرة", ["علمية دقيقة", "مباشرة وسريعة", "ودية", "نقدية صارمة"], index=0)
        mode = st.selectbox("النمط", ["موازٍ سريع", "نقاش محدود", "نقاش + حكم محلي"], index=0)
        st.divider()
        st.subheader("🔌 حالة الاعتمادات")
        for cfg in PROVIDERS.values():
            if active_credentials.get(cfg.provider_id):
                st.success(f"{cfg.icon} {cfg.family}: اعتماد موجود")
            else:
                st.info(f"{cfg.icon} {cfg.family}: بدون اعتماد → محلي")
        st.caption("وجود API Key لا يعني أن استخدام API مجاني.")
        if st.button("🗑️ مسح الغرفة", use_container_width=True):
            reset()

    agents = select_agents(size)
    cols = st.columns(5)
    for col, agent in zip(cols, CORE_AGENTS):
        with col:
            connected = bool(active_credentials.get(agent["provider"]))
            st.metric(agent["name"], "🟢 API" if connected else "🔵 Local", agent["role"])
    if size > 5:
        st.caption(f"المقاعد الإضافية ({size - 5}) محلية عمداً.")

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
        st.session_state.messages.append({"role": "user", "sender": "أنت", "content": query})
        with st.status("⚡ تشغيل أعضاء الغرفة…", expanded=True) as status:
            results = run_parallel(agents, query, st.session_state.messages[:-1], tone, active_credentials)
            status.update(label="اكتملت الجولة الأساسية", state="complete")
        if mode in ("نقاش محدود", "نقاش + حكم محلي"):
            results = run_debate(results, query, tone)
        moderator = local_moderator(query, results, tone) if mode == "نقاش + حكم محلي" else None
        run_id = round_hash(query, results, moderator)
        st.session_state.last_results = [asdict(r) for r in results]
        st.session_state.last_moderator = asdict(moderator) if moderator else None
        st.session_state.last_query = query
        st.session_state.last_run_id = run_id

        with st.chat_message("assistant"):
            official = sum(1 for r in results if r.official_authenticated)
            local_fallback = sum(1 for r in results if r.fallback_used)
            local_direct = sum(1 for r in results if r.mode.startswith("local") and not r.fallback_used)
            local_total = local_fallback + local_direct
            st.markdown(
                f"<div class='summary'><b>الجولة:</b> {len(results)} نتيجة · "
                f"{official} رسمي ناجح · {local_total} محلي/fallback "
                f"({local_direct} محلي مباشر + {local_fallback} احتياطي)</div>",
                unsafe_allow_html=True,
            )
            for result in results:
                render_result(result)
            if moderator:
                st.markdown("### 🏛️ الحكم المحلي")
                render_result(moderator)

        combined = "\n\n".join(f"{r.agent_name}: {r.text}" for r in results)
        if moderator:
            combined += f"\n\nالحكم المحلي: {moderator.text}"
        st.session_state.messages.append({"role": "assistant", "sender": "المجلس", "content": combined})

    # Do not re-render last_results as cards here. The complete assistant turn
    # is already persisted in st.session_state.messages and is rendered above.
    # Re-rendering both paths caused duplicate cards after Streamlit reruns.
    if st.session_state.last_results:
        result_objects = [AgentResult(**item) for item in st.session_state.last_results]
        moderator = AgentResult(**st.session_state.last_moderator) if st.session_state.last_moderator else None
        st.download_button(
            "⬇️ تصدير JSON Audit",
            export_json(st.session_state.last_query, result_objects, moderator, st.session_state.last_run_id or "round"),
            file_name=f"ai_council_{st.session_state.last_run_id or 'round'}.json",
            mime="application/json",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()

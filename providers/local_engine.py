# -*- coding: utf-8 -*-
"""Deterministic, dependency-free local fallback.

This is intentionally NOT an LLM. It never impersonates ChatGPT, Gemini,
Claude, Grok, or Kimi. Its job is continuity: the room remains usable when
no official provider is configured or when an official provider fails.
"""
from __future__ import annotations

import re
from typing import List, Optional


def _clean(value: object, limit: int = 4500) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def _keywords(text: str) -> List[str]:
    words = re.findall(r"[\w\u0600-\u06FF]{4,}", (text or "").lower())
    seen: List[str] = []
    for word in words:
        if word not in seen:
            seen.append(word)
    return seen[:12]


def _simple_social(query: str) -> Optional[str]:
    q = re.sub(r"[\s\.,!?؟،؛:]+", " ", (query or "").strip().lower()).strip()
    if q in {"hello", "hi", "hey", "سلام", "السلام عليكم", "اهلا", "أهلا", "أهلًا", "مرحبا", "مرحبًا"}:
        return "مرحبًا 👋 جاهز للمشاركة في الجولة."
    if q in {"شكرا", "شكرًا", "thanks", "thank you"}:
        return "على الرحب والسعة. جاهز للجولة التالية."
    if q in {"مع السلامة", "الى اللقاء", "إلى اللقاء", "bye", "goodbye"}:
        return "مع السلامة 👋"
    return None


def generate_local(
    agent_id: str,
    role: str,
    instruction: str,
    query: str,
    context: str = "",
    tone: str = "علمية دقيقة",
    peer_text: str = "",
) -> str:
    social = _simple_social(query)
    if social:
        return social + "\nالمصدر: Local Engine؛ ليس نموذجًا تجاريًا أصليًا."

    q = _clean(query, 3500)
    c = _clean(context, 1800)
    peers = _clean(peer_text, 5000)
    keys = _keywords(q)
    focus = ", ".join(keys) if keys else "الهدف والقيود والمخاطر"

    if agent_id in {"quality", "moderator_local"} or "الحكم" in role:
        return (
            "الخلاصة من Local Engine: افصل الحقائق عن الافتراضات، وقارن البدائل وفق الهدف والقيود، "
            "وسجّل مواطن عدم اليقين.\n\n"
            f"نقاط التركيز: {focus}.\n"
            "معيار القبول: نتيجة واضحة، قابلة للتنفيذ، وقابلة للمراجعة.\n"
            + (f"المادة التي تمت مراجعتها: {peers}\n" if peers else "")
            + "المصدر: Local Engine؛ ليست نتيجة من ChatGPT/Gemini/Claude/Grok/Kimi الأصلي."
        )
    if agent_id == "devils_advocate" or agent_id == "bounded_critique":
        return (
            "اعتراض/مراجعة محلية: اختبر الافتراضات، ابحث عن حالة فشل، وحدد الادعاء الذي يحتاج دليلاً مستقلًا.\n"
            f"محور المراجعة: {focus}."
        )
    if agent_id == "security":
        return "مراجعة أمان محلية: لا تسجل الأسرار، افصلها عن الواجهة، قلّل البيانات المرسلة للمزودات، واعزل فشل كل مزود عن بقية الغرفة."
    if agent_id == "planner":
        return "خطة محلية: عرّف النتيجة، اجمع المدخلات، نفّذ أصغر خطوة قابلة للاختبار، اختبر الفشل، ثم راجع النتيجة."
    if agent_id == "factcheck":
        return "مراجعة حقائق محلية: صنّف كل ادعاء إلى حقيقة أو استنتاج أو افتراض. لا يوجد بحث ويب في هذا المحرك."
    if agent_id == "engineering":
        return "مراجعة هندسية محلية: حافظ على فصل Provider/Local، وعزل الأعطال، والمهلات الزمنية، وAudit Metadata الصريح."
    if agent_id == "economics":
        return "مراجعة تكلفة محلية: افصل تكلفة API عن المسار المحلي، وراقب الطلبات والحصص، ولا تجعل API شرطًا للوظيفة الأساسية."
    if agent_id == "ux":
        return "مراجعة تجربة محلية: أظهر مصدر كل رد بوضوح، وميّز الرسمي عن المحلي دون عرض الأسرار."
    if agent_id == "minimalist":
        return "الحل الأبسط: اجعل المسار المحلي هو أساس الاستمرارية، واجعل المزود الرسمي إضافة اختيارية لا توقف الغرفة عند فشلها."

    return (
        f"تحليل محلي — الدور: {role}.\n"
        f"منهج الدور: {instruction}\n"
        f"النبرة: {tone}\n"
        f"السؤال يركز على: {focus}.\n"
        f"السياق المتاح: {c or '(لا يوجد)'}\n"
        "ابدأ بتحديد المطلوب، ثم قارن الخيارات والمخاطر قبل التوصية.\n"
        "المصدر: Local Engine؛ ليست النتيجة من نموذج تجاري أصلي."
    )

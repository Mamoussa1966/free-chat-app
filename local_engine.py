# -*- coding: utf-8 -*-
"""Deterministic, dependency-free local fallback.

This is intentionally NOT an LLM and does not impersonate ChatGPT, Gemini,
Claude, Grok, or Kimi. It provides resilient role-based analysis so the room
remains usable when official providers are unavailable.
"""
from __future__ import annotations

import re
from typing import List


def _keywords(text: str) -> List[str]:
    words = re.findall(r"[\w\u0600-\u06FF]{4,}", (text or "").lower())
    seen = []
    for word in words:
        if word not in seen:
            seen.append(word)
    return seen[:12]


def generate_local(
    agent_id: str,
    role: str,
    instruction: str,
    query: str,
    context: str = "",
    tone: str = "علمية دقيقة",
    peer_text: str = "",
) -> str:
    keys = _keywords(query)
    focus = ", ".join(keys) if keys else "الهدف والقيود والمخاطر"

    if agent_id in {"quality", "moderator_local"} or "الحكم" in role:
        return (
            "الخلاصة من Local Engine: افصل الحقائق عن الافتراضات، قارن البدائل وفق الهدف والقيود، "
            "وسجّل مواطن عدم اليقين.\n\n"
            f"نقاط التركيز: {focus}.\n"
            "معيار القبول: نتيجة واضحة، قابلة للتنفيذ، وقابلة للمراجعة.\n"
            "مصدر هذه النتيجة: Local Engine؛ وليست من نموذج تجاري أصلي."
        )
    if agent_id == "devils_advocate":
        return "اعتراض محلي: اختبر الافتراضات، ابحث عن حالة فشل، وحدد الدليل الذي يمكن أن يغيّر النتيجة."
    if agent_id == "security":
        return "مراجعة أمان محلية: لا تسجل الأسرار، افصلها عن الواجهة، قلّل البيانات المرسلة للمزودات، واعزل فشل كل مزود عن بقية الغرفة."
    if agent_id == "planner":
        return "خطة محلية: عرّف النتيجة، اجمع المدخلات، نفّذ أصغر خطوة قابلة للاختبار، اختبر الفشل، ثم راجع النتيجة."
    if agent_id == "factcheck":
        return "مراجعة حقائق محلية: صنّف كل ادعاء إلى حقيقة أو استنتاج أو افتراض. لا يوجد بحث ويب في هذا المحرك."
    if agent_id == "engineering":
        return "مراجعة هندسية محلية: حافظ على فصل Provider/Local، عزل الأعطال، حدود زمنية، واختبارات Audit Metadata."
    if agent_id == "economics":
        return "مراجعة تكلفة محلية: افصل تكلفة API عن المسار المحلي، راقب الطلبات والحصص، ولا تجعل API شرطاً للوظيفة الأساسية."
    if agent_id == "ux":
        return "مراجعة تجربة محلية: أظهر مصدر كل رد بوضوح، وميّز الرسمي عن المحلي دون عرض الأسرار."
    if agent_id == "minimalist":
        return "الحل الأبسط: شغّل المسار الأساسي محلياً، واجعل المزود الرسمي إضافة اختيارية لا توقف الغرفة عند فشلها."

    return (
        f"تحليل محلي — الدور: {role}. {instruction}\n"
        f"السؤال يركز على: {focus}.\n"
        "ابدأ بتحديد المطلوب، ثم قارن الخيارات والمخاطر قبل التوصية.\n"
        "مصدر هذه النتيجة: Local Engine؛ وليست ChatGPT/Gemini/Claude/Grok/Kimi الأصلي."
    )

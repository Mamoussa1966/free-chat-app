# -*- coding: utf-8 -*-
"""
AI Council Local Engine
V21.3.1 FINAL SYNTAX-SAFE

محرك محلي مستقل لا يحتاج إلى أي مكتبات خارجية.
يُستخدم فقط كاستمرارية محلية معلنة عند تعذر المقعد الرسمي.
"""

from __future__ import annotations

import re


ROLE_ACTIONS = {
    "openai": "افصل الحقائق عن الافتراضات واختبر الاتساق المنطقي.",
    "gemini": "قارن البدائل واكشف الافتراضات قبل إصدار النتيجة.",
    "anthropic": "ابحث عن الثغرات وحدود الاستنتاج والأدلة الناقصة.",
    "xai": "اختبر المخاطر والبدائل ونقاط الفشل المحتملة.",
    "kimi": "نظم الأفكار وحولها إلى قرار عملي قابل للفحص.",
}


def _clean(value: str, limit: int = 2400) -> str:
    """تنظيف النص وتحديد حجمه لمنع تضخم السياق المحلي."""
    return str(value or "").strip()[:limit].strip()


def _keywords(text: str) -> list[str]:
    """استخراج مجموعة صغيرة من الكلمات المفتاحية."""
    words = re.findall(
        r"[\u0600-\u06FFA-Za-z0-9_]{4,}",
        _clean(text, 3000),
    )

    result: list[str] = []

    for word in words:
        if word not in result:
            result.append(word)

    return result[:8]


def generate_local(
    agent_id: str,
    role: str,
    instruction: str,
    query: str,
    context: str = "",
    tone: str = "علمية دقيقة",
    peer_text: str = "",
) -> str:
    """
    إنشاء تحليل محلي مستقل.

    مهم:
    - لا يتصل بالإنترنت.
    - لا يستخدم API.
    - لا يدّعي أنه نموذج رسمي.
    - لا يحتاج إلى Streamlit.
    """

    del tone
    del peer_text

    q = _clean(query, 3000)
    ctx = _clean(context, 1800)

    keys = _keywords(q)

    action = ROLE_ACTIONS.get(
        agent_id,
        _clean(instruction, 700),
    )

    key_text = "، ".join(keys)

    if not key_text:
        key_text = "الموضوع المطروح"

    sections = [
        f"### {role or agent_id} — Local Fallback",
        "",
        f"**السؤال:** {q or 'غير محدد'}",
        f"**المحاور:** {key_text}",
        f"**منهج الدور:** {action}",
        "",
        "**النتيجة الأولية:**",
        (
            "هذا تحليل محلي مستقل يستخدم المعطيات المتاحة فقط. "
            "لا يمثل هذا الرد نموذجًا تجاريًا أصليًا."
        ),
        "",
        "**السياق المختصر:**",
        ctx or "لا يوجد سياق سابق كافٍ.",
        "",
        "**خطوات التحقق:**",
        "1. تحديد معيار نجاح واضح.",
        "2. اختبار أهم افتراض أو مخاطرة.",
        "3. عدم اعتماد القرار النهائي قبل التحقق من الدليل المطلوب.",
        "",
        "> المصدر: Local Engine — محرك محلي مستقل.",
    ]

    return "\n".join(sections)

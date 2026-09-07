# -*- coding: utf-8 -*-

"""
Local deterministic analysis engine.

This module intentionally has NO third-party dependencies.
It must be importable on Streamlit Cloud before any provider is loaded.
"""

from __future__ import annotations

import re
from typing import List


def _clean(value: str, limit: int = 2200) -> str:
    if value is None:
        return ""

    return str(value).strip()[:limit].strip()


def _sentences(text: str, limit: int = 4) -> List[str]:
    text = _clean(text, 2600)

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!؟])\s+|\n+",
        text,
    )

    return [
        part.strip(" -•\t\r\n")
        for part in parts
        if part.strip()
    ][:limit]


def _keywords(query: str) -> List[str]:
    query = _clean(query, 3000)

    words = re.findall(
        r"[\u0600-\u06FFA-Za-z0-9_]{4,}",
        query,
    )

    stop_words = {
        "كيف",
        "يمكن",
        "ماهو",
        "ماذا",
        "الذي",
        "التي",
        "هذا",
        "هذه",
        "ذلك",
        "هناك",
        "على",
        "إلى",
        "من",
        "في",
        "عن",
        "مع",
        "هل",
        "أريد",
        "اريد",
        "لدي",
        "لدينا",
        "بشكل",
        "لذلك",
        "عندما",
        "أجل",
        "أجلًا",
    }

    result: List[str] = []

    for word in words:
        normalized = word.lower()

        if normalized in stop_words:
            continue

        if word not in result:
            result.append(word)

    return result[:8]


def _question_type(query: str) -> str:
    query = _clean(query, 3000)

    if not query:
        return "طلب فارغ أو غير محدد"

    if "؟" in query or re.search(
        r"\b(هل|كيف|لماذا|متى|ما|أي|كم)\b",
        query,
    ):
        if re.search(
            r"\b(كيف|خطة|خطوات|تنفيذ|تطبيق)\b",
            query,
        ):
            return "سؤال إجرائي/تنفيذي"

        if re.search(
            r"\b(لماذا|سبب|أسباب)\b",
            query,
        ):
            return "سؤال سببي/تشخيصي"

        return "سؤال تحليلي/استفهامي"

    return "طلب مفتوح يحتاج تحديد هدف ومعايير نجاح"


ROLE_ACTIONS = {
    "analysis": (
        "افصل الهدف عن القيود، ثم قارن البدائل قبل إصدار الحكم."
    ),
    "reasoning": (
        "اختبر الافتراضات والعلاقات السببية وابحث عن قفزة منطقية غير مبررة."
    ),
    "critic": (
        "ابحث عن نقاط الضعف، الأدلة الناقصة، والاستنتاجات التي تتجاوز المعطيات."
    ),
    "risk": (
        "حدد نقاط الفشل المحتملة، احتمالها، أثرها، وأبسط إجراء لتخفيفها."
    ),
    "synthesis": (
        "حوّل النتائج إلى قرار مختصر مع أولويات واضحة ومعيار نجاح قابل للفحص."
    ),
    "factcheck": (
        "افصل الحقائق القابلة للتحقق عن الآراء والافتراضات التي تحتاج مصدراً."
    ),
    "planner": (
        "حوّل الهدف إلى مراحل صغيرة مرتبة مع مخرجات قبول لكل مرحلة."
    ),
    "security": (
        "افحص الأسرار، الصلاحيات، حدود الثقة، وسلوك النظام عند الفشل."
    ),
    "engineering": (
        "راجع الاعتمادية، قابلية الصيانة، الاختبارات، والتوسع قبل التنفيذ."
    ),
    "economics": (
        "وازن القيمة مقابل الموارد والزمن والتكلفة ومخاطر الاعتماد الخارجي."
    ),
    "ux": (
        "ابحث عن نقاط الالتباس والاحتكاك وما يحتاجه المستخدم كي ينجح من أول محاولة."
    ),
    "devils_advocate": (
        "ابنِ أقوى حجة معاكسة للنتيجة الحالية ثم اختبر هل تصمد أمامها."
    ),
    "minimalist": (
        "ابحث عن أقل حل يحقق الهدف بأمان دون تعقيد غير ضروري."
    ),
    "quality": (
        "حوّل المطلوب إلى معايير قبول واختبارات قابلة للملاحظة."
    ),
    "compliance": (
        "حدد المتطلبات التنظيمية المحتملة وما يحتاج مراجعة متخصصة قبل اعتماده."
    ),
}


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
    Generate a deterministic local analysis.

    This function is intentionally dependency-free.
    """

    q = _clean(query, 3000)
    ctx = _sentences(context, 3)
    peers = _sentences(peer_text, 3)

    keywords = _keywords(q)
    question_type = _question_type(q)

    key_text = (
        "، ".join(keywords)
        if keywords
        else "الموضوع المطروح"
    )

    action = ROLE_ACTIONS.get(
        str(agent_id).strip(),
        _clean(instruction, 1000)
        or "حلل الطلب وفق المعطيات المتاحة.",
    )

    sections = [
        f"### {role or agent_id} — تحليل محلي ديناميكي",
        "",
        f"**السؤال محل التحليل:** {q or 'غير محدد'}",
        f"**نوع الطلب:** {question_type}",
        f"**المحاور البارزة:** {key_text}",
        "",
        f"**قراءة الدور:** {action}",
        "",
        "**النتيجة الأولية:**",
        (
            "المعالجة لا تعتمد على رسالة ثابتة؛ بل تربط السؤال "
            "بالدور المحدد للمقعد. وبناءً على المعطيات المتاحة، "
            "الأولوية هي تحديد ما يجب إثباته أو تنفيذه قبل الانتقال "
            "إلى قرار نهائي."
        ),
    ]

    if ctx:
        sections.extend(
            [
                "",
                "**السياق المؤثر:**",
            ]
        )

        sections.extend(
            f"- {item}"
            for item in ctx
        )
    else:
        sections.extend(
            [
                "",
                "**السياق المؤثر:**",
                (
                    "لا يوجد سياق سابق كافٍ؛ لذلك يجب تجنب "
                    "افتراض معلومات غير مذكورة."
                ),
            ]
        )

    if peers:
        sections.extend(
            [
                "",
                "**مراجعة أولية لآراء الزملاء:**",
            ]
        )

        sections.extend(
            f"- {item}"
            for item in peers
        )

        sections.append(
            "نقطة التدقيق: الاتفاق بين الأعضاء لا يُعد دليلاً بحد ذاته؛ "
            "يجب فحص الافتراضات المشتركة."
        )

    sections.extend(
        [
            "",
            "**خطوة عملية مقترحة:**",
            "1. تحديد معيار نجاح واضح.",
            "2. اختبار أهم افتراض أو مخاطرة أولاً.",
            "3. مقارنة النتيجة بالمعيار قبل اعتماد القرار.",
            "",
            (
                "> **المصدر:** Local Engine — محرك محلي مستقل. "
                "لا يمثل هذا الرد نموذجاً تجارياً أصلياً."
            ),
        ]
    )

    return "\n".join(sections)

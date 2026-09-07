# -*- coding: utf-8 -*-
"""Dependency-free local analysis engine.

This engine is intentionally heuristic/deterministic.
It does not impersonate or claim to be any commercial model.
It produces structured analysis from the actual query,
role, context and peer responses.
"""

from __future__ import annotations

import re
from typing import List


def _clean(value: str, limit: int = 2200) -> str:
    return (value or "").strip()[:limit].strip()


def _sentences(text: str, limit: int = 4) -> List[str]:
    parts = re.split(
        r"(?<=[.!؟])\s+|\n+",
        _clean(text, 2600),
    )
    return [p.strip(" -•") for p in parts if p.strip()][:limit]


def _keywords(query: str) -> List[str]:
    words = re.findall(
        r"[\u0600-\u06FFA-Za-z0-9_]{4,}",
        query,
    )

    stop = {
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
        "يمكننا",
    }

    seen = []

    for word in words:
        if word.lower() not in stop and word not in seen:
            seen.append(word)

    return seen[:8]


def _question_type(query: str) -> str:
    q = query.strip()

    if "؟" in q or re.search(
        r"\b(هل|كيف|لماذا|متى|ما|أي|كم)\b",
        q,
    ):
        if re.search(
            r"\b(كيف|خطة|خطوات|تنفيذ|تطبيق)\b",
            q,
        ):
            return "سؤال إجرائي/تنفيذي"

        if re.search(
            r"\b(لماذا|سبب|أسباب)\b",
            q,
        ):
            return "سؤال سببي/تشخيصي"

        return "سؤال تحليلي/استفهامي"

    return "طلب مفتوح يحتاج تحديد هدف ومعايير نجاح"


def generate_local(
    agent_id: str,
    role: str,
    instruction: str,
    query: str,
    context: str = "",
    tone: str = "علمية دقيقة",
    peer_text: str = "",
) -> str:
    """Generate role-specific local analysis."""

    q = _clean(query, 3000)

    ctx = _sentences(context, 3)
    peers = _sentences(peer_text, 3)

    keys = _keywords(q)
    qtype = _question_type(q)

    key_text = (
        "، ".join(keys)
        if keys
        else "الموضوع المطروح"
    )

    role_actions = {
        "analysis":
            "افصل الهدف عن القيود، ثم قارن البدائل قبل إصدار الحكم.",

        "reasoning":
            "اختبر الافتراضات والعلاقات السببية وابحث عن قفزة منطقية غير مبررة.",

        "critic":
            "ابحث عن نقاط الضعف، الأدلة الناقصة، والاستنتاجات التي تتجاوز المعطيات.",

        "risk":
            "حدد نقاط الفشل المحتملة، احتمالها، أثرها، وأبسط إجراء لتخفيفها.",

        "synthesis":
            "حوّل النتائج إلى قرار مختصر مع أولويات واضحة ومعيار نجاح قابل للفحص.",

        "factcheck":
            "افصل الحقائق القابلة للتحقق عن الآراء والافتراضات التي تحتاج مصدراً.",

        "planner":
            "حوّل الهدف إلى مراحل صغيرة مرتبة مع مخرجات قبول لكل مرحلة.",

        "security":
            "افحص الأسرار، الصلاحيات، حدود الثقة، وسلوك النظام عند الفشل.",

        "engineering":
            "راجع الاعتمادية، قابلية الصيانة، الاختبارات، والتوسع قبل التنفيذ.",

        "economics":
            "وازن القيمة مقابل الموارد والزمن والتكلفة ومخاطر الاعتماد الخارجي.",

        "ux":
            "ابحث عن نقاط الالتباس والاحتكاك وما يحتاجه المستخدم كي ينجح من أول محاولة.",

        "devils_advocate":
            "ابنِ أقوى حجة معاكسة للنتيجة الحالية ثم اختبر هل تصمد أمامها.",

        "minimalist":
            "ابحث عن أقل حل يحقق الهدف بأمان دون تعقيد غير ضروري.",

        "quality":
            "حوّل المطلوب إلى معايير قبول واختبارات قابلة للملاحظة.",

        "compliance":
            "حدد المتطلبات التنظيمية المحتملة وما يحتاج مراجعة قانونية متخصصة قبل اعتماده.",
    }

    action = role_actions.get(
        agent_id,
        instruction,
    )

    sections = [
        f"### {role} — تحليل محلي ديناميكي",

        f"**السؤال محل التحليل:** {q}",

        f"**نوع الطلب:** {qtype}",

        f"**المحاور البارزة:** {key_text}",

        "",

        f"**قراءة الدور:** {action}",

        "",

        "**النتيجة الأولية:**",

        (
            "المعالجة لا تعتمد على رسالة ثابتة؛ بل تربط "
            "السؤال بالدور المحدد للمقعد. وبناءً على "
            "المعطيات المتاحة، الأولوية هي تحديد ما الذي "
            "يجب إثباته أو تنفيذه قبل الانتقال إلى قرار نهائي."
        ),
    ]

    if ctx:
        sections += [
            "",
            "**السياق المؤثر:**",
        ]

        sections += [
            f"- {item}"
            for item in ctx
        ]

    else:
        sections += [
            "",
            "**السياق المؤثر:** "
            "لا يوجد سياق سابق كافٍ؛ لذلك يجب تجنب "
            "افتراض معلومات غير مذكورة.",
        ]

    if peers:
        sections += [
            "",
            "**مراجعة أولية لآراء الزملاء:**",
        ]

        sections += [
            f"- {item}"
            for item in peers
        ]

        sections.append(
            "نقطة التدقيق: أي اتفاق بين الأعضاء لا يُعد "
            "دليلاً بحد ذاته؛ يجب فحص الافتراضات المشتركة."
        )

    sections += [
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

    return "\n".join(sections)

from __future__ import annotations

import re

VERSION = "V21.18-LOCAL-ENGINE"

ROLE_ACTIONS = {
    "ChatGPT": (
        "حلّل الطلب بوضوح، ثم قدّم إجابة "
        "عملية قابلة للتحقق."
    ),
    "Gemini": (
        "ركّز على الحقائق، البنية، "
        "والبدائل العملية."
    ),
    "Claude": (
        "راجع الافتراضات والمخاطر "
        "والاتساق المنطقي."
    ),
    "Grok": (
        "اختبر الادعاءات وابحث عن نقاط "
        "الضعف أو التناقضات."
    ),
    "Kimi": (
        "ركّز على التنفيذ، التفاصيل، "
        "والخطوات القابلة للتطبيق."
    ),
}


def _clean(
    text: str,
    limit: int = 900,
) -> str:
    text = re.sub(
        r"\s+",
        " ",
        str(text or ""),
    ).strip()

    return text[:limit]


def generate_local(
    seat_name: str,
    user_prompt: str,
    shared_context: str = "",
    round_no: int = 1,
) -> str:
    action = ROLE_ACTIONS.get(
        seat_name,
        "حلّل الطلب بصورة مستقلة.",
    )

    context_note = (
        "يوجد سياق مشترك سابق."
        if shared_context.strip()
        else "لا يوجد سياق سابق."
    )

    return (
        "هذا رد من Local Engine المعلن، "
        f"وليس من {seat_name} الرسمي.\n\n"
        f"الدور: {action}\n"
        f"الجولة: {round_no}. "
        f"{context_note}\n\n"
        f"الطلب: {_clean(user_prompt)}\n\n"
        "الاستنتاج المحلي: لا يمكن إثبات هوية "
        "مزود تجاري أو تنفيذ API رسمي من هذا المسار. "
        "استخدم هذا الرد كمسودة/خطة، ثم تحقّق من "
        "النتيجة الرسمية عند توفر API صالح."
    )

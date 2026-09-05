from __future__ import annotations

import re
from typing import Dict, List


def topic_tokens(text: str) -> List[str]:
    words = re.findall(r"[\w\u0600-\u06FF]+", text.lower(), flags=re.UNICODE)
    stop = {
        "من", "في", "على", "عن", "إلى", "الى", "ما", "ماذا", "كيف", "هل", "هو", "هي",
        "هذا", "هذه", "ذلك", "تلك", "مع", "و", "أو", "أن", "إن", "the", "a", "an",
        "is", "are", "to", "of", "in", "on", "for", "and", "or", "how", "what", "why",
    }
    return [w for w in words if len(w) > 1 and w not in stop][:12]


def is_greeting(text: str) -> bool:
    compact = re.sub(r"[^a-zA-Zأ-يء-ى\s]", "", text.lower()).strip()
    return compact in {
        "hello", "hi", "hey", "مرحبا", "مرحباً", "اهلا", "أهلا", "أهلاً",
        "السلام عليكم", "السلام عليكم ورحمة الله وبركاته", "صباح الخير", "مساء الخير",
    }


def generate_local(agent: Dict[str, str], query: str, context: str, tone: str) -> str:
    if is_greeting(query):
        return f"أهلاً بك. أنا {agent['name']} في الدور المحلي: {agent['role']}. جاهز للعمل مع المجلس."

    tokens = "، ".join(topic_tokens(query)) or query[:180]
    ctx = " توجد ملاحظات سابقة في الجلسة؛ سأستخدمها كسياق لا كحقيقة مؤكدة." if context else ""
    base = f"السؤال: «{query}». المحاور الظاهرة: {tokens}."
    role = agent["instruction"]
    if agent["id"] == "analysis":
        extra = " افصل بين الحقائق والافتراضات، وحدد معيار القرار قبل التوصية."
    elif agent["id"] == "reasoning":
        extra = " اختبر الفرضيات، واذكر ما الذي يجعل الاستنتاج مشروطاً أو غير يقيني."
    elif agent["id"] == "critic":
        extra = " ابحث عن الثغرات، واسأل ما الدليل وما الذي قد يغيّر الحكم."
    elif agent["id"] == "risk":
        extra = " حدد نقاط الفشل والتأثير وخطة رجوع منخفضة التكلفة."
    else:
        extra = " حوّل أفضل النقاط إلى خطوات تنفيذية مرتبة وقابلة للقياس."
    return f"{base} {role}{extra} النبرة المطلوبة: {tone}.{ctx}"

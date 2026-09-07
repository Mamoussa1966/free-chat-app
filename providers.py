# -*- coding: utf-8 -*-

"""
AI Council V20 - Provider Gateway

Five original seats:
    1. ChatGPT / OpenAI
    2. Gemini / Google
    3. Claude / Anthropic
    4. Grok / xAI
    5. Kimi / Moonshot

Security:
- API keys are never hard-coded.
- API keys are never returned in results/errors.
- Streamlit secrets are resolved by the main Streamlit thread.
- Worker threads receive only the credential they need.
- Official provider failures are isolated per seat.
- Local fallback is explicitly labelled.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Optional

import requests

from local_engine import generate_local


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

def _bounded_int(
    env_name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(os.getenv(env_name, str(default)))
    except (TypeError, ValueError):
        value = default

    return max(minimum, min(value, maximum))


REQUEST_TIMEOUT = _bounded_int(
    "PROVIDER_TIMEOUT",
    45,
    5,
    90,
)

MAX_OUTPUT_TOKENS = _bounded_int(
    "PROVIDER_MAX_OUTPUT_TOKENS",
    1400,
    128,
    8192,
)


# ---------------------------------------------------------------------
# Seat definition
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class Seat:
    name: str
    env_key: str
    default_model: str
    system: str
    provider_id: str


SEATS = (
    Seat(
        name="ChatGPT",
        env_key="OPENAI_API_KEY",
        default_model=os.getenv(
            "OPENAI_MODEL",
            "gpt-5",
        ),
        system=(
            "أنت مقعد ChatGPT في مجلس ذكاء اصطناعي متعدد النماذج. "
            "حلل السؤال بدقة، افصل الحقائق عن الافتراضات، "
            "وقدم استدلالاً واضحاً ومفيداً."
        ),
        provider_id="openai",
    ),
    Seat(
        name="Gemini",
        env_key="GEMINI_API_KEY",
        default_model=os.getenv(
            "GEMINI_MODEL",
            "gemini-3.8-flash",
        ),
        system=(
            "أنت مقعد Gemini في مجلس ذكاء اصطناعي متعدد النماذج. "
            "ركز على التحليل المنطقي، كشف الافتراضات، "
            "ومقارنة البدائل."
        ),
        provider_id="gemini",
    ),
    Seat(
        name="Claude",
        env_key="ANTHROPIC_API_KEY",
        default_model=os.getenv(
            "ANTHROPIC_MODEL",
            "claude-sonnet-4-6",
        ),
        system=(
            "أنت مقعد Claude في مجلس ذكاء اصطناعي متعدد النماذج. "
            "راجع جودة الحجج، ابحث عن الثغرات، "
            "واذكر حدود الاستنتاج بوضوح."
        ),
        provider_id="anthropic",
    ),
    Seat(
        name="Grok",
        env_key="XAI_API_KEY",
        default_model=os.getenv(
            "XAI_MODEL",
            "grok-4",
        ),
        system=(
            "أنت مقعد Grok في مجلس ذكاء اصطناعي متعدد النماذج. "
            "اختبر المخاطر والبدائل والافتراضات التي قد تكون غير واضحة."
        ),
        provider_id="xai",
    ),
    Seat(
        name="Kimi",
        env_key="KIMI_API_KEY",
        default_model=os.getenv(
            "KIMI_MODEL",
            "kimi-k2.5",
        ),
        system=(
            "أنت مقعد Kimi في مجلس ذكاء اصطناعي متعدد النماذج. "
            "اجمع الأفكار في تحليل منظم ومختصر يساعد على اتخاذ القرار."
        ),
        provider_id="kimi",
    ),
)


# ---------------------------------------------------------------------
# Compatibility map
# ---------------------------------------------------------------------

PROVIDERS = {
    "openai": {
        "env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
    },
    "gemini": {
        "env": "GEMINI_API_KEY",
        "model_env": "GEMINI_MODEL",
    },
    "anthropic": {
        "env": "ANTHROPIC_API_KEY",
        "model_env": "ANTHROPIC_MODEL",
    },
    "xai": {
        "env": "XAI_API_KEY",
        "model_env": "XAI_MODEL",
    },
    "kimi": {
        "env": "KIMI_API_KEY",
        "model_env": "KIMI_MODEL",
    },
}


# ---------------------------------------------------------------------
# Secret helpers
# ---------------------------------------------------------------------

def _redact(value: Any) -> str:
    text = str(value or "")

    patterns = [
        r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+",
        r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;]+",
        r"\bsk-[A-Za-z0-9_-]+\b",
    ]

    for pattern in patterns:
        text = re.sub(
            pattern,
            lambda match: (
                match.group(1) + "[REDACTED]"
                if match.lastindex
                else "[REDACTED]"
            ),
            text,
        )

    return text[:1200]


def safe_error(value: Any) -> str:
    return _redact(value)


def _environment_secret(name: str) -> Optional[str]:
    value = os.getenv(name)

    if value is None:
        return None

    value = str(value).strip()

    return value or None


def get_secret(name: str) -> Optional[str]:
    """
    Compatibility helper.

    Intended to be called from the Streamlit main thread.
    Worker threads should receive the resolved credential explicitly.
    """

    value = _environment_secret(name)

    if value:
        return value

    try:
        import streamlit as st

        value = st.secrets.get(name)
        if value is not None:
            value = str(value).strip()
            return value or None
    except Exception:
        pass

    return None


def _first_secret(*names: str) -> Optional[str]:
    for name in names:
        value = get_secret(name)
        if value:
            return value

    return None


def get_seat_credential(seat: Seat) -> Optional[str]:
    """
    Resolve a seat credential.

    This function should preferably be called by the main Streamlit
    thread before launching worker threads.
    """

    if seat.provider_id == "gemini":
        return _first_secret(
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
        )

    if seat.provider_id == "xai":
        return _first_secret(
            "XAI_API_KEY",
            "GROK_API_KEY",
        )

    if seat.provider_id == "kimi":
        return _first_secret(
            "KIMI_API_KEY",
            "MOONSHOT_API_KEY",
        )

    return get_secret(seat.env_key)


def get_models() -> dict[str, str]:
    return {
        seat.name: seat.default_model
        for seat in SEATS
    }


# ---------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------

class ProviderError(RuntimeError):
    pass


def _post(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout as exc:
        raise ProviderError(
            "Provider request timed out."
        ) from exc
    except requests.RequestException as exc:
        raise ProviderError(
            f"Provider connection failed: {_redact(exc)}"
        ) from exc

    if response.status_code >= 400:
        body = _redact(response.text)
        raise ProviderError(
            f"Provider HTTP {response.status_code}: {body}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderError(
            "Provider returned invalid JSON."
        ) from exc

    if not isinstance(data, dict):
        raise ProviderError(
            "Provider returned an unexpected response."
        )

    return data


# ---------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------

def _openai_text(data: dict[str, Any]) -> str:
    output_text = data.get("output_text")

    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output = data.get("output", [])

    collected: list[str] = []

    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue

            content = item.get("content", [])

            if not isinstance(content, list):
                continue

            for part in content:
                if not isinstance(part, dict):
                    continue

                text = part.get("text")

                if isinstance(text, str) and text.strip():
                    collected.append(text.strip())

    return "\n".join(collected).strip()


def _chat_text(data: dict[str, Any]) -> str:
    choices = data.get("choices", [])

    if not isinstance(choices, list) or not choices:
        return ""

    first = choices[0]

    if not isinstance(first, dict):
        return ""

    message = first.get("message", {})

    if not isinstance(message, dict):
        return ""

    content = message.get("content")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []

        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)

        return "\n".join(parts).strip()

    return ""


def _gemini_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates", [])

    if not isinstance(candidates, list):
        return ""

    collected: list[str] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        content = candidate.get("content", {})

        if not isinstance(content, dict):
            continue

        parts = content.get("parts", [])

        if not isinstance(parts, list):
            continue

        for part in parts:
            if isinstance(part, dict):
                text = part.get("text")

                if isinstance(text, str) and text.strip():
                    collected.append(text.strip())

    return "\n".join(collected).strip()


def _anthropic_text(data: dict[str, Any]) -> str:
    content = data.get("content", [])

    if not isinstance(content, list):
        return ""

    collected: list[str] = []

    for item in content:
        if not isinstance(item, dict):
            continue

        text = item.get("text")

        if isinstance(text, str) and text.strip():
            collected.append(text.strip())

    return "\n".join(collected).strip()


# ---------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------

def _openai_call(
    seat: Seat,
    prompt: str,
    credential: str,
) -> str:

    payload = {
        "model": seat.default_model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": seat.system,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    }
                ],
            },
        ],
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "store": False,
    }

    data = _post(
        "https://api.openai.com/v1/responses",
        {
            "Authorization": f"Bearer {credential}",
            "Content-Type": "application/json",
        },
        payload,
    )

    text = _openai_text(data)

    if not text:
        raise ProviderError(
            "OpenAI returned an empty response."
        )

    return text


def _gemini_call(
    seat: Seat,
    prompt: str,
    credential: str,
) -> str:

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{seat.default_model}:generateContent"
    )

    payload = {
        "system_instruction": {
            "parts": [
                {
                    "text": seat.system,
                }
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt,
                    }
                ],
            }
        ],
        "generationConfig": {
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
        },
    }

    data = _post(
        url,
        {
            "x-goog-api-key": credential,
            "Content-Type": "application/json",
        },
        payload,
    )

    text = _gemini_text(data)

    if not text:
        raise ProviderError(
            "Gemini returned an empty response."
        )

    return text


def _anthropic_call(
    seat: Seat,
    prompt: str,
    credential: str,
) -> str:

    payload = {
        "model": seat.default_model,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "system": seat.system,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }

    workspace_id = _first_secret(
        "ANTHROPIC_WORKSPACE_ID",
        "CLAUDE_WORKSPACE_ID",
    )

    headers = {
        "x-api-key": credential,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    if workspace_id:
        headers["anthropic-workspace-id"] = workspace_id

    data = _post(
        "https://api.anthropic.com/v1/messages",
        headers,
        payload,
    )

    text = _anthropic_text(data)

    if not text:
        raise ProviderError(
            "Anthropic returned an empty response."
        )

    return text


def _xai_call(
    seat: Seat,
    prompt: str,
    credential: str,
) -> str:

    payload = {
        "model": seat.default_model,
        "messages": [
            {
                "role": "system",
                "content": seat.system,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "max_tokens": MAX_OUTPUT_TOKENS,
    }

    data = _post(
        "https://api.x.ai/v1/chat/completions",
        {
            "Authorization": f"Bearer {credential}",
            "Content-Type": "application/json",
        },
        payload,
    )

    text = _chat_text(data)

    if not text:
        raise ProviderError(
            "xAI returned an empty response."
        )

    return text


def _kimi_call(
    seat: Seat,
    prompt: str,
    credential: str,
) -> str:

    payload = {
        "model": seat.default_model,
        "messages": [
            {
                "role": "system",
                "content": seat.system,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "max_tokens": MAX_OUTPUT_TOKENS,
    }

    data = _post(
        "https://api.moonshot.ai/v1/chat/completions",
        {
            "Authorization": f"Bearer {credential}",
            "Content-Type": "application/json",
        },
        payload,
    )

    text = _chat_text(data)

    if not text:
        raise ProviderError(
            "Kimi returned an empty response."
        )

    return text


def _official(
    seat: Seat,
    prompt: str,
    credential: str,
) -> str:

    if not credential:
        raise ProviderError(
            "No official credential configured."
        )

    provider = seat.provider_id

    if provider == "openai":
        return _openai_call(
            seat,
            prompt,
            credential,
        )

    if provider == "gemini":
        return _gemini_call(
            seat,
            prompt,
            credential,
        )

    if provider == "anthropic":
        return _anthropic_call(
            seat,
            prompt,
            credential,
        )

    if provider == "xai":
        return _xai_call(
            seat,
            prompt,
            credential,
        )

    if provider == "kimi":
        return _kimi_call(
            seat,
            prompt,
            credential,
        )

    raise ProviderError(
        f"Unsupported provider: {provider}"
    )


# ---------------------------------------------------------------------
# Local fallback
# ---------------------------------------------------------------------

def _local_call(
    seat: Seat,
    user_prompt: str,
    context: str,
    round_no: int,
) -> str:

    return generate_local(
        agent_id=seat.provider_id,
        role=seat.name,
        instruction=seat.system,
        query=user_prompt,
        context=context,
        tone="علمية دقيقة",
        peer_text=context,
    )


# ---------------------------------------------------------------------
# Public seat API
# ---------------------------------------------------------------------

def call_seat(
    seat: Seat,
    user_prompt: str,
    context: str = "",
    round_no: int = 1,
    local_fallback: bool = False,
    credential: Optional[str] = None,
) -> dict[str, Any]:

    prompt = (
        f"الجولة: {round_no}\n\n"
        f"سؤال المستخدم:\n{user_prompt}\n\n"
        f"السياق المشترك للمجلس:\n{context or 'لا يوجد سياق سابق.'}\n\n"
        "تعليمات التنفيذ:\n"
        "- حلل السؤال من منظور مقعدك.\n"
        "- لا تفترض معلومات غير موجودة.\n"
        "- إذا كانت هناك نقاط غير مؤكدة، صرّح بذلك.\n"
        "- قدم نتيجة عملية قابلة للفحص.\n"
    )

    if credential:
        try:
            text = _official(
                seat,
                prompt,
                credential,
            )

            return {
                "seat": seat.name,
                "label": f"🤖 {seat.name} — {seat.default_model}",
                "provider": seat.provider_id,
                "model": seat.default_model,
                "status": "SUCCESS",
                "mode": "OFFICIAL_API",
                "round": round_no,
                "content": text,
                "error": "",
            }

        except Exception as exc:
            official_error = safe_error(exc)

            if not local_fallback:
                return {
                    "seat": seat.name,
                    "label": f"❌ {seat.name} — API",
                    "provider": seat.provider_id,
                    "model": seat.default_model,
                    "status": "FAILED",
                    "mode": "OFFICIAL_API",
                    "round": round_no,
                    "content": (
                        f"تعذر الحصول على رد رسمي من {seat.name}."
                    ),
                    "error": official_error,
                }

    else:
        official_error = "لا يوجد مفتاح API رسمي مُكوّن."

        if not local_fallback:
            return {
                "seat": seat.name,
                "label": f"⚪ {seat.name} — غير مُهيأ",
                "provider": seat.provider_id,
                "model": seat.default_model,
                "status": "UNAVAILABLE",
                "mode": "NONE",
                "round": round_no,
                "content": (
                    f"المقعد {seat.name} غير متاح لأن مفتاح API "
                    "الرسمي غير مُكوّن."
                ),
                "error": official_error,
            }

    if local_fallback:
        try:
            text = _local_call(
                seat,
                user_prompt,
                context,
                round_no,
            )

            return {
                "seat": seat.name,
                "label": f"🟡 {seat.name} — Local Fallback",
                "provider": seat.provider_id,
                "model": "local_engine",
                "status": "SUCCESS",
                "mode": "LOCAL_FALLBACK",
                "round": round_no,
                "content": text,
                "error": (
                    f"Official API unavailable: {official_error}"
                ),
            }

        except Exception as exc:
            return {
                "seat": seat.name,
                "label": f"❌ {seat.name} — Failed",
                "provider": seat.provider_id,
                "model": seat.default_model,
                "status": "FAILED",
                "mode": "NONE",
                "round": round_no,
                "content": (
                    f"تعذر تشغيل المقعد {seat.name} "
                    "بالـ API الرسمي وبالمحرك المحلي."
                ),
                "error": safe_error(exc),
            }

    return {
        "seat": seat.name,
        "label": f"❌ {seat.name} — Failed",
        "provider": seat.provider_id,
        "model": seat.default_model,
        "status": "FAILED",
        "mode": "NONE",
        "round": round_no,
        "content": "فشل غير متوقع في تشغيل المقعد.",
        "error": "Unexpected provider state.",
    }


# ---------------------------------------------------------------------
# Backward-compatible official API helper
# ---------------------------------------------------------------------

def call_official(
    provider_id: str,
    prompt: str,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
    credential: Optional[str] = None,
) -> str:

    matching = [
        seat
        for seat in SEATS
        if seat.provider_id == provider_id
    ]

    if not matching:
        raise ProviderError(
            f"Unknown provider: {provider_id}"
        )

    original = matching[0]

    if model:
        seat = Seat(
            name=original.name,
            env_key=original.env_key,
            default_model=model,
            system=original.system,
            provider_id=original.provider_id,
        )
    else:
        seat = original

    key = credential or get_seat_credential(seat)

    if not key:
        raise ProviderError(
            "No official credential configured."
        )

    return _official(
        seat,
        prompt,
        key,
    )

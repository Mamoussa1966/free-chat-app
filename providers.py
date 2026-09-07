# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Optional

import requests

from local_engine import generate_local


def _bounded_int(
    env_name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:

    try:
        value = int(
            os.getenv(
                env_name,
                str(default),
            )
        )

    except (TypeError, ValueError):

        value = default

    return max(
        minimum,
        min(value, maximum),
    )


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


@dataclass(frozen=True)
class Seat:

    name: str
    env_key: str
    default_model: str
    system: str
    provider_id: str


SEATS = (

    Seat(
        "ChatGPT",
        "OPENAI_API_KEY",
        os.getenv(
            "OPENAI_MODEL",
            "gpt-5",
        ),
        (
            "أنت مقعد ChatGPT في مجلس متعدد "
            "النماذج. حلل بدقة، افصل الحقائق "
            "عن الافتراضات، وقدم نتيجة قابلة للفحص."
        ),
        "openai",
    ),

    Seat(
        "Gemini",
        "GEMINI_API_KEY",
        os.getenv(
            "GEMINI_MODEL",
            "gemini-3.8-flash",
        ),
        (
            "أنت مقعد Gemini. ركز على التحليل "
            "المنطقي، كشف الافتراضات، ومقارنة البدائل."
        ),
        "gemini",
    ),

    Seat(
        "Claude",
        "ANTHROPIC_API_KEY",
        os.getenv(
            "ANTHROPIC_MODEL",
            "claude-sonnet-4-6",
        ),
        (
            "أنت مقعد Claude. راجع جودة الحجج، "
            "ابحث عن الثغرات، واذكر حدود الاستنتاج بوضوح."
        ),
        "anthropic",
    ),

    Seat(
        "Grok",
        "XAI_API_KEY",
        os.getenv(
            "XAI_MODEL",
            "grok-4.6",
        ),
        (
            "أنت مقعد Grok. اختبر المخاطر "
            "والبدائل والافتراضات غير الواضحة."
        ),
        "xai",
    ),

    Seat(
        "Kimi",
        "KIMI_API_KEY",
        os.getenv(
            "KIMI_MODEL",
            "kimi-k2.5",
        ),
        (
            "أنت مقعد Kimi. اجمع الأفكار في "
            "تحليل منظم ومختصر يساعد على اتخاذ القرار."
        ),
        "kimi",
    ),
)


PROVIDERS = {
    seat.provider_id: {
        "env": seat.env_key
    }
    for seat in SEATS
}


def _redact(value: Any) -> str:

    text = str(value or "")

    patterns = [
        r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+",
        r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;]+",
        r"\bsk-[A-Za-z0-9_-]+\b",
        r"\bxai-[A-Za-z0-9_-]+\b",
    ]

    for pattern in patterns:

        text = re.sub(
            pattern,
            lambda match:
                (
                    match.group(1)
                    + "[REDACTED]"
                )
                if match.lastindex
                else "[REDACTED]",
            text,
        )

    return text[:1600]


def safe_error(value: Any) -> str:
    return _redact(value)


def _environment_secret(
    name: str,
) -> Optional[str]:

    value = os.getenv(name)

    if value is None:
        return None

    value = str(value).strip()

    return value or None


def get_secret(
    name: str,
) -> Optional[str]:

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

        return None

    return None


def _first_secret(
    *names: str,
) -> Optional[str]:

    for name in names:

        value = get_secret(name)

        if value:
            return value

    return None


def get_seat_config(
    seat: Seat,
) -> dict[str, Optional[str]]:

    if seat.provider_id == "gemini":

        credential = _first_secret(
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
        )

    elif seat.provider_id == "xai":

        credential = _first_secret(
            "XAI_API_KEY",
            "GROK_API_KEY",
        )

    elif seat.provider_id == "kimi":

        credential = _first_secret(
            "KIMI_API_KEY",
            "MOONSHOT_API_KEY",
        )

    else:

        credential = get_secret(
            seat.env_key
        )

    workspace_id = None

    if seat.provider_id == "anthropic":

        workspace_id = _first_secret(
            "ANTHROPIC_WORKSPACE_ID",
            "CLAUDE_WORKSPACE_ID",
        )

    return {
        "credential": credential,
        "workspace_id": workspace_id,
    }


def get_seat_credential(
    seat: Seat,
) -> Optional[str]:

    return get_seat_config(
        seat
    )["credential"]


def get_models() -> dict[str, str]:

    return {
        seat.name: seat.default_model
        for seat in SEATS
    }


class ProviderError(RuntimeError):

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
    ):

        super().__init__(message)

        self.status_code = status_code


def _classify_error(
    exc: Exception,
) -> str:

    if (
        isinstance(
            exc,
            ProviderError,
        )
        and exc.status_code
    ):

        code = exc.status_code

        if code in (401, 403):

            return (
                f"AUTH_OR_PERMISSION_ERROR "
                f"({code})"
            )

        if code == 404:

            return (
                "MODEL_OR_ENDPOINT_NOT_FOUND "
                "(404)"
            )

        if code == 429:

            return (
                "RATE_LIMIT_OR_QUOTA "
                "(429)"
            )

        if 500 <= code <= 599:

            return (
                f"PROVIDER_SERVER_ERROR "
                f"({code})"
            )

    if isinstance(
        exc,
        requests.Timeout,
    ):

        return "TIMEOUT"

    return "PROVIDER_ERROR"


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
            "Provider connection failed: "
            f"{_redact(exc)}"
        ) from exc

    if response.status_code >= 400:

        body = _redact(
            response.text
        )

        raise ProviderError(
            (
                f"HTTP {response.status_code}: "
                f"{body}"
            ),
            status_code=response.status_code,
        )

    try:

        data = response.json()

    except ValueError as exc:

        raise ProviderError(
            "Provider returned invalid JSON."
        ) from exc

    if not isinstance(
        data,
        dict,
    ):

        raise ProviderError(
            "Provider returned an unexpected response shape."
        )

    return data


def _openai_text(
    data: dict[str, Any],
) -> str:

    output_text = data.get(
        "output_text"
    )

    if (
        isinstance(
            output_text,
            str,
        )
        and output_text.strip()
    ):

        return output_text.strip()

    collected: list[str] = []

    output = data.get(
        "output",
        [],
    )

    if isinstance(
        output,
        list,
    ):

        for item in output:

            if not isinstance(
                item,
                dict,
            ):
                continue

            content = item.get(
                "content",
                [],
            )

            if not isinstance(
                content,
                list,
            ):
                continue

            for part in content:

                if (
                    isinstance(
                        part,
                        dict,
                    )
                    and isinstance(
                        part.get("text"),
                        str,
                    )
                ):

                    collected.append(
                        part["text"].strip()
                    )

    return "\n".join(
        x
        for x in collected
        if x
    ).strip()


def _chat_text(
    data: dict[str, Any],
) -> str:

    choices = data.get(
        "choices",
        [],
    )

    if (
        not isinstance(
            choices,
            list,
        )
        or not choices
    ):

        return ""

    first = choices[0]

    if not isinstance(
        first,
        dict,
    ):

        return ""

    message = first.get(
        "message",
        {},
    )

    if not isinstance(
        message,
        dict,
    ):

        return ""

    content = message.get(
        "content"
    )

    if isinstance(
        content,
        str,
    ):

        return content.strip()

    if isinstance(
        content,
        list,
    ):

        return "\n".join(
            item.get(
                "text",
                "",
            )
            for item in content
            if (
                isinstance(
                    item,
                    dict,
                )
                and isinstance(
                    item.get("text"),
                    str,
                )
            )
        ).strip()

    return ""


def _gemini_text(
    data: dict[str, Any],
) -> str:

    collected: list[str] = []

    candidates = data.get(
        "candidates",
        [],
    )

    if not isinstance(
        candidates,
        list,
    ):

        return ""

    for candidate in candidates:

        if not isinstance(
            candidate,
            dict,
        ):

            continue

        content = candidate.get(
            "content",
            {},
        )

        if not isinstance(
            content,
            dict,
        ):

            continue

        parts = content.get(
            "parts",
            [],
        )

        if not isinstance(
            parts,
            list,
        ):

            continue

        for part in parts:

            if (
                isinstance(
                    part,
                    dict,
                )
                and isinstance(
                    part.get("text"),
                    str,
                )
            ):

                collected.append(
                    part["text"].strip()
                )

    return "\n".join(
        x
        for x in collected
        if x
    ).strip()


def _anthropic_text(
    data: dict[str, Any],
) -> str:

    content = data.get(
        "content",
        [],
    )

    if not isinstance(
        content,
        list,
    ):

        return ""

    collected: list[str] = []

    for item in content:

        if (
            isinstance(
                item,
                dict,
            )
            and isinstance(
                item.get("text"),
                str,
            )
        ):

            collected.append(
                item["text"].strip()
            )

    return "\n".join(
        x
        for x in collected
        if x
    ).strip()


def _openai_call(
    seat: Seat,
    prompt: str,
    credential: str,
) -> str:

    data = _post(
        "https://api.openai.com/v1/responses",
        {
            "Authorization": (
                f"Bearer {credential}"
            ),
            "Content-Type": (
                "application/json"
            ),
        },
        {
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
            "max_output_tokens": (
                MAX_OUTPUT_TOKENS
            ),
            "store": False,
        },
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
        f"v1beta/models/"
        f"{seat.default_model}:generateContent"
    )

    data = _post(
        url,
        {
            "x-goog-api-key": credential,
            "Content-Type": (
                "application/json"
            ),
        },
        {
            "system_instruction": {
                "parts": [
                    {
                        "text": seat.system
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": prompt
                        }
                    ],
                }
            ],
            "generationConfig": {
                "maxOutputTokens": (
                    MAX_OUTPUT_TOKENS
                )
            },
        },
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
    workspace_id: Optional[str],
) -> str:

    headers = {
        "x-api-key": credential,
        "anthropic-version": "2023-06-01",
        "content-type": (
            "application/json"
        ),
    }

    if workspace_id:

        headers[
            "anthropic-workspace-id"
        ] = workspace_id

    data = _post(
        "https://api.anthropic.com/v1/messages",
        headers,
        {
            "model": seat.default_model,
            "max_tokens": (
                MAX_OUTPUT_TOKENS
            ),
            "system": seat.system,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        },
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

    data = _post(
        "https://api.x.ai/v1/responses",
        {
            "Authorization": (
                f"Bearer {credential}"
            ),
            "Content-Type": (
                "application/json"
            ),
        },
        {
            "model": seat.default_model,
            "input": [
                {
                    "role": "system",
                    "content": seat.system,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "max_output_tokens": (
                MAX_OUTPUT_TOKENS
            ),
            "store": False,
        },
    )

    text = _openai_text(data)

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

    data = _post(
        "https://api.moonshot.ai/v1/chat/completions",
        {
            "Authorization": (
                f"Bearer {credential}"
            ),
            "Content-Type": (
                "application/json"
            ),
        },
        {
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
            "max_tokens": (
                MAX_OUTPUT_TOKENS
            ),
        },
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
    workspace_id: Optional[str] = None,
) -> str:

    if not credential:

        raise ProviderError(
            "No official credential configured."
        )

    if seat.provider_id == "openai":

        return _openai_call(
            seat,
            prompt,
            credential,
        )

    if seat.provider_id == "gemini":

        return _gemini_call(
            seat,
            prompt,
            credential,
        )

    if seat.provider_id == "anthropic":

        return _anthropic_call(
            seat,
            prompt,
            credential,
            workspace_id,
        )

    if seat.provider_id == "xai":

        return _xai_call(
            seat,
            prompt,
            credential,
        )

    if seat.provider_id == "kimi":

        return _kimi_call(
            seat,
            prompt,
            credential,
        )

    raise ProviderError(
        f"Unsupported provider: "
        f"{seat.provider_id}"
    )


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


def call_seat(
    seat: Seat,
    user_prompt: str,
    context: str = "",
    round_no: int = 1,
    local_fallback: bool = False,
    credential: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> dict[str, Any]:

    prompt = (
        f"الجولة: {round_no}\n\n"
        f"سؤال المستخدم:\n"
        f"{user_prompt}\n\n"
        "السياق المشترك للمجلس:\n"
        f"{context or 'لا يوجد سياق سابق.'}\n\n"
        "تعليمات التنفيذ:\n"
        "- حلل السؤال من منظور مقعدك.\n"
        "- لا تفترض معلومات غير موجودة.\n"
        "- إذا كانت هناك نقاط غير مؤكدة، صرّح بذلك.\n"
        "- قدم نتيجة عملية قابلة للفحص.\n"
    )

    official_error = ""

    if credential:

        try:

            text = _official(
                seat,
                prompt,
                credential,
                workspace_id,
            )

            return {
                "seat": seat.name,
                "label": (
                    f"🤖 {seat.name} — "
                    f"{seat.default_model}"
                ),
                "provider": (
                    seat.provider_id
                ),
                "model": (
                    seat.default_model
                ),
                "status": "SUCCESS",
                "mode": "OFFICIAL_API",
                "round": round_no,
                "content": text,
                "error": "",
            }

        except Exception as exc:

            official_error = (
                f"{_classify_error(exc)}: "
                f"{safe_error(exc)}"
            )

    else:

        official_error = (
            "NO_CREDENTIAL: "
            "لا يوجد اعتماد API رسمي مُكوّن."
        )

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
                "label": (
                    f"🟡 {seat.name} — "
                    "Local Fallback"
                ),
                "provider": (
                    seat.provider_id
                ),
                "model": "local_engine",
                "status": "SUCCESS",
                "mode": "LOCAL_FALLBACK",
                "round": round_no,
                "content": text,
                "error": (
                    "Official API unavailable: "
                    f"{official_error}"
                ),
            }

        except Exception as exc:

            return {
                "seat": seat.name,
                "label": (
                    f"❌ {seat.name} — Failed"
                ),
                "provider": (
                    seat.provider_id
                ),
                "model": "local_engine",
                "status": "FAILED",
                "mode": "NONE",
                "round": round_no,
                "content": (
                    f"تعذر تشغيل المقعد "
                    f"{seat.name}."
                ),
                "error": (
                    f"{official_error}; "
                    "LOCAL_ERROR: "
                    f"{safe_error(exc)}"
                ),
            }

    return {
        "seat": seat.name,
        "label": (
            f"❌ {seat.name} — API"
        ),
        "provider": (
            seat.provider_id
        ),
        "model": seat.default_model,
        "status": (
            "FAILED"
            if credential
            else "UNAVAILABLE"
        ),
        "mode": (
            "OFFICIAL_API"
            if credential
            else "NONE"
        ),
        "round": round_no,
        "content": (
            f"تعذر الحصول على رد رسمي "
            f"من {seat.name}."
        ),
        "error": official_error,
    }


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
            f"Unknown provider: "
            f"{provider_id}"
        )

    original = matching[0]

    seat = Seat(
        original.name,
        original.env_key,
        model
        or original.default_model,
        original.system,
        original.provider_id,
    )

    config = get_seat_config(
        seat
    )

    key = (
        credential
        or config["credential"]
    )

    if not key:

        raise ProviderError(
            "No official credential configured."
        )

    return _official(
        seat,
        prompt,
        key,
        config["workspace_id"],
    )

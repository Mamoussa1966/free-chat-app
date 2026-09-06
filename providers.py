# -*- coding: utf-8 -*-
"""
AI Council V21 - Secure Provider Gateway

Public API required by main.py:
    from providers import SEATS, call_seat

Design goals:
- Five official AI seats.
- Per-provider failure isolation.
- No API keys in logs/UI.
- No infinite retries.
- Retry only transient failures.
- Clear classification of authentication, billing, quota and service errors.
- Optional Ollama fallback is explicitly labelled LOCAL.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import requests


# ============================================================
# SAFE CONFIGURATION
# ============================================================

def _safe_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default

    return max(minimum, min(value, maximum))


REQUEST_TIMEOUT = _safe_int_env(
    "PROVIDER_TIMEOUT",
    45,
    5,
    90,
)

MAX_OUTPUT_TOKENS = _safe_int_env(
    "PROVIDER_MAX_OUTPUT_TOKENS",
    1400,
    128,
    8192,
)

MAX_RETRIES = _safe_int_env(
    "PROVIDER_MAX_RETRIES",
    2,
    0,
    3,
)

RETRY_BASE_SECONDS = _safe_int_env(
    "PROVIDER_RETRY_BASE_SECONDS",
    1,
    1,
    10,
)


# ============================================================
# SEATS
# ============================================================

@dataclass(frozen=True)
class Seat:
    name: str
    env_key: str
    default_model: str
    system: str
    provider_id: str


SEATS: Tuple[Seat, ...] = (
    Seat(
        "ChatGPT",
        "OPENAI_API_KEY",
        os.getenv("OPENAI_MODEL", "gpt-5").strip(),
        "You are the OpenAI ChatGPT seat in an AI council. "
        "Be precise, rigorous, and explicit about uncertainty.",
        "openai",
    ),

    Seat(
        "Gemini",
        "GEMINI_API_KEY",
        os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip(),
        "You are the Google Gemini seat in an AI council. "
        "Challenge weak assumptions and use evidence.",
        "gemini",
    ),

    Seat(
        "Claude",
        "ANTHROPIC_API_KEY",
        os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip(),
        "You are the Anthropic Claude seat in an AI council. "
        "Be careful, structured, and nuanced.",
        "anthropic",
    ),

    Seat(
        "Grok",
        "XAI_API_KEY",
        os.getenv("XAI_MODEL", "grok-4").strip(),
        "You are the xAI Grok seat in an AI council. "
        "Be direct, analytical, and willing to challenge assumptions.",
        "xai",
    ),

    Seat(
        "Kimi",
        "KIMI_API_KEY",
        os.getenv("KIMI_MODEL", "kimi-k2.5").strip(),
        "You are the Moonshot Kimi seat in an AI council. "
        "Focus on synthesis and long-context reasoning.",
        "kimi",
    ),
)


# ============================================================
# EXCEPTIONS
# ============================================================

class ProviderError(RuntimeError):
    """Safe provider-facing error."""


class HTTPProviderError(ProviderError):
    """Provider HTTP error with status classification."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


# ============================================================
# SECRETS
# ============================================================

def _secret(name: str) -> Optional[str]:
    """
    Read a secret from Streamlit Secrets first, then environment.
    Never expose the value.
    """
    try:
        import streamlit as st

        value = st.secrets.get(name)

        if value is not None and str(value).strip():
            return str(value).strip()

    except Exception:
        pass

    value = os.getenv(name, "")

    return value.strip() or None


def _first_secret(*names: str) -> Optional[str]:
    for name in names:
        value = _secret(name)
        if value:
            return value

    return None


def _credential(seat: Seat) -> Optional[str]:
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

    return _secret(seat.env_key)


def _workspace_id() -> Optional[str]:
    return _first_secret(
        "ANTHROPIC_WORKSPACE_ID",
        "CLAUDE_WORKSPACE_ID",
    )


# ============================================================
# REDACTION / SAFE ERRORS
# ============================================================

def _redact(text: str) -> str:
    """
    Aggressively remove likely secrets from error text.
    """
    text = str(text or "").replace("\n", " ")

    patterns = [
        (
            r"(?i)bearer\s+[^\s,;]+",
            "Bearer [REDACTED]",
        ),
        (
            r"(?i)(api[_ -]?key|authorization|x-api-key|secret|token|password)"
            r"\s*[:=]\s*[^\s,;]+",
            r"\1=[REDACTED]",
        ),
        (
            r"\bsk-[A-Za-z0-9_-]{8,}\b",
            "[REDACTED]",
        ),
        (
            r"\bAIza[A-Za-z0-9_-]{20,}\b",
            "[REDACTED]",
        ),
    ]

    for pattern, replacement in patterns:
        text = re.sub(
            pattern,
            replacement,
            text,
        )

    return text[:700] or "provider error"


def _extract_provider_message(response: requests.Response) -> str:
    """
    Extract only a short safe diagnostic.
    Never return the entire provider body.
    """
    try:
        data = response.json()
    except ValueError:
        return ""

    if not isinstance(data, dict):
        return ""

    error = data.get("error")

    if isinstance(error, dict):
        message = error.get("message")

        if isinstance(message, str):
            return _redact(message)

    message = data.get("message")

    if isinstance(message, str):
        return _redact(message)

    return ""


def _classify_http_error(
    status_code: int,
    provider_message: str,
) -> tuple[str, bool]:
    """
    Return:
        safe_user_message, retryable
    """

    message = (provider_message or "").lower()

    # --------------------------------------------------------
    # Authentication
    # --------------------------------------------------------

    if status_code == 401:
        return (
            "بيانات اعتماد المزود غير صالحة أو منتهية. "
            "تحقق من API Key.",
            False,
        )

    # --------------------------------------------------------
    # Bad request
    # --------------------------------------------------------

    if status_code == 400:
        if (
            "workspace" in message
            or "anthropic-workspace-id" in message
            or "scoped to a workspace" in message
        ):
            return (
                "مفتاح Claude يحتاج ANTHROPIC_WORKSPACE_ID "
                "أو يجب استخدام مفتاح غير مرتبط بـ Workspace.",
                False,
            )

        return (
            "المزود رفض الطلب بسبب إعدادات أو صيغة الطلب.",
            False,
        )

    # --------------------------------------------------------
    # Permission / billing
    # --------------------------------------------------------

    if status_code == 403:
        if any(
            phrase in message
            for phrase in (
                "credit",
                "credits",
                "spending",
                "billing",
                "balance",
                "payment",
                "quota",
            )
        ):
            return (
                "حساب المزود وصل إلى حد الرصيد أو الإنفاق "
                "أو توجد مشكلة فوترة.",
                False,
            )

        return (
            "المفتاح لا يملك الصلاحية المطلوبة لهذا المورد.",
            False,
        )

    # --------------------------------------------------------
    # Not found
    # --------------------------------------------------------

    if status_code == 404:
        return (
            "النموذج أو نقطة الاتصال غير موجودة. "
            "تحقق من اسم النموذج.",
            False,
        )

    # --------------------------------------------------------
    # Rate limit / quota
    # --------------------------------------------------------

    if status_code == 429:
        if any(
            phrase in message
            for phrase in (
                "insufficient balance",
                "insufficient funds",
                "suspended",
                "billing",
                "credit",
                "credits",
                "balance",
                "payment required",
            )
        ):
            return (
                "الحساب لا يملك رصيدًا كافيًا أو أن الحساب موقوف. "
                "إعادة المحاولة لن تحل المشكلة.",
                False,
            )

        return (
            "تم تجاوز حد الطلبات مؤقتًا. "
            "سيتم إعادة المحاولة تلقائيًا.",
            True,
        )

    # --------------------------------------------------------
    # Temporary server errors
    # --------------------------------------------------------

    if status_code in (408, 500, 502, 503, 504):
        return (
            "الخدمة غير متاحة مؤقتًا. "
            "سيتم إعادة المحاولة تلقائيًا.",
            True,
        )

    # --------------------------------------------------------
    # Unknown
    # --------------------------------------------------------

    return (
        f"المزود أعاد HTTP {status_code}.",
        False,
    )


# ============================================================
# HTTP
# ============================================================

def _post(
    url: str,
    headers: dict,
    payload: dict,
) -> dict:

    last_error: Optional[HTTPProviderError] = None

    total_attempts = MAX_RETRIES + 1

    for attempt in range(total_attempts):

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )

        except requests.Timeout as exc:
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_SECONDS * (2 ** attempt)
                time.sleep(delay)
                continue

            raise ProviderError(
                "network timeout after retries"
            ) from exc

        except requests.RequestException as exc:
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_SECONDS * (2 ** attempt)
                time.sleep(delay)
                continue

            raise ProviderError(
                f"network error: {exc.__class__.__name__}"
            ) from exc

        if response.status_code >= 400:

            raw_message = _extract_provider_message(response)

            safe_message, retryable = _classify_http_error(
                response.status_code,
                raw_message,
            )

            last_error = HTTPProviderError(
                response.status_code,
                safe_message,
                retryable=retryable,
            )

            if retryable and attempt < MAX_RETRIES:
                delay = RETRY_BASE_SECONDS * (2 ** attempt)
                time.sleep(delay)
                continue

            raise last_error

        try:
            data = response.json()

        except ValueError as exc:
            raise ProviderError(
                "provider returned invalid JSON"
            ) from exc

        if not isinstance(data, dict):
            raise ProviderError(
                "provider returned an unexpected response"
            )

        return data

    if last_error:
        raise last_error

    raise ProviderError("provider request failed")


# ============================================================
# RESPONSE PARSERS
# ============================================================

def _openai_text(data: dict) -> str:

    output_text = data.get("output_text")

    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    chunks = []

    for item in data.get("output", []) or []:

        if not isinstance(item, dict):
            continue

        for part in item.get("content", []) or []:

            if (
                isinstance(part, dict)
                and isinstance(part.get("text"), str)
            ):
                chunks.append(part["text"])

    return "\n".join(chunks).strip()


def _chat_text(data: dict) -> str:

    choices = data.get("choices") or []

    if not choices:
        return ""

    first = choices[0]

    if not isinstance(first, dict):
        return ""

    message = first.get("message") or {}

    if not isinstance(message, dict):
        return ""

    content = message.get("content", "")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):

        return "\n".join(
            item.get("text", "")
            for item in content
            if (
                isinstance(item, dict)
                and isinstance(item.get("text"), str)
            )
        ).strip()

    return ""


def _gemini_text(data: dict) -> str:

    chunks = []

    for candidate in data.get("candidates", []) or []:

        if not isinstance(candidate, dict):
            continue

        content = candidate.get("content") or {}

        if not isinstance(content, dict):
            continue

        for part in content.get("parts", []) or []:

            if (
                isinstance(part, dict)
                and isinstance(part.get("text"), str)
            ):
                chunks.append(part["text"])

    return "\n".join(chunks).strip()


def _anthropic_text(data: dict) -> str:

    return "\n".join(
        item.get("text", "")
        for item in data.get("content", []) or []
        if (
            isinstance(item, dict)
            and isinstance(item.get("text"), str)
        )
    ).strip()


# ============================================================
# OFFICIAL PROVIDERS
# ============================================================

def _call_openai(
    seat: Seat,
    key: str,
    prompt: str,
) -> str:

    data = _post(
        "https://api.openai.com/v1/responses",
        {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        {
            "model": seat.default_model,
            "input": prompt,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "store": False,
        },
    )

    text = _openai_text(data)

    if not text:
        raise ProviderError(
            "OpenAI returned no text"
        )

    return text


def _call_gemini(
    seat: Seat,
    key: str,
    prompt: str,
) -> str:

    model = seat.default_model

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
    )

    data = _post(
        url,
        {
            "x-goog-api-key": key,
            "Content-Type": "application/json",
        },
        {
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
        },
    )

    text = _gemini_text(data)

    if not text:
        raise ProviderError(
            "Gemini returned no text"
        )

    return text


def _call_anthropic(
    seat: Seat,
    key: str,
    prompt: str,
) -> str:

    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    workspace = _workspace_id()

    if workspace:
        headers["anthropic-workspace-id"] = workspace

    data = _post(
        "https://api.anthropic.com/v1/messages",
        headers,
        {
            "model": seat.default_model,
            "max_tokens": MAX_OUTPUT_TOKENS,
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
            "Claude returned no text"
        )

    return text


def _call_xai(
    seat: Seat,
    key: str,
    prompt: str,
) -> str:

    data = _post(
        "https://api.x.ai/v1/chat/completions",
        {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        {
            "model": seat.default_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "max_tokens": MAX_OUTPUT_TOKENS,
        },
    )

    text = _chat_text(data)

    if not text:
        raise ProviderError(
            "Grok returned no text"
        )

    return text


def _call_kimi(
    seat: Seat,
    key: str,
    prompt: str,
) -> str:

    data = _post(
        "https://api.moonshot.ai/v1/chat/completions",
        {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        {
            "model": seat.default_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "max_tokens": MAX_OUTPUT_TOKENS,
        },
    )

    text = _chat_text(data)

    if not text:
        raise ProviderError(
            "Kimi returned no text"
        )

    return text


# ============================================================
# OFFICIAL DISPATCH
# ============================================================

def _official(
    seat: Seat,
    prompt: str,
) -> str:

    key = _credential(seat)

    if not key:
        raise ProviderError(
            "no official credential configured"
        )

    if seat.provider_id == "openai":
        return _call_openai(
            seat,
            key,
            prompt,
        )

    if seat.provider_id == "gemini":
        return _call_gemini(
            seat,
            key,
            prompt,
        )

    if seat.provider_id == "anthropic":
        return _call_anthropic(
            seat,
            key,
            prompt,
        )

    if seat.provider_id == "xai":
        return _call_xai(
            seat,
            key,
            prompt,
        )

    if seat.provider_id == "kimi":
        return _call_kimi(
            seat,
            key,
            prompt,
        )

    raise ProviderError(
        "unsupported provider"
    )


# ============================================================
# OLLAMA LOCAL FALLBACK
# ============================================================

def _local(
    seat: Seat,
    prompt: str,
) -> str:

    host = os.getenv(
        "OLLAMA_HOST",
        "http://127.0.0.1:11434",
    ).rstrip("/")

    model = os.getenv(
        "OLLAMA_MODEL",
        "llama3.2",
    ).strip()

    if not model:
        raise ProviderError(
            "OLLAMA_MODEL is empty"
        )

    try:
        response = requests.post(
            f"{host}/api/chat",
            json={
                "model": model,
                "stream": False,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"You are a LOCAL FALLBACK for the "
                            f"{seat.name} seat. "
                            "Never claim to be the official provider.\n\n"
                            f"{prompt}"
                        ),
                    }
                ],
            },
            timeout=_safe_int_env(
                "OLLAMA_TIMEOUT",
                60,
                10,
                120,
            ),
        )

    except requests.Timeout as exc:
        raise ProviderError(
            "local network timeout"
        ) from exc

    except requests.RequestException as exc:
        raise ProviderError(
            f"local network error: {exc.__class__.__name__}"
        ) from exc

    if response.status_code >= 400:
        raise ProviderError(
            f"local HTTP {response.status_code}"
        )

    try:
        data = response.json()

    except ValueError as exc:
        raise ProviderError(
            "Ollama returned invalid JSON"
        ) from exc

    text = (
        (data.get("message") or {})
        .get("content") or ""
    ).strip()

    if not text:
        raise ProviderError(
            "Ollama returned no text"
        )

    return text


# ============================================================
# PROMPT
# ============================================================

def _build_prompt(
    seat: Seat,
    user_prompt: str,
    context: str,
    round_no: int,
) -> str:

    return (
        f"{seat.system}\n\n"
        f"Council round: {round_no}\n"
        "Other council members may be wrong. "
        "Do not blindly agree. "
        "Give your own analysis.\n\n"
        f"USER:\n{user_prompt}\n\n"
        f"SHARED CONTEXT:\n"
        f"{context or '(none)'}"
    )


# ============================================================
# PUBLIC API
# ============================================================

def call_seat(
    seat: Seat,
    user_prompt: str,
    context: str = "",
    round_no: int = 1,
    local_fallback: bool = False,
) -> dict:

    started = time.perf_counter()

    prompt = _build_prompt(
        seat,
        user_prompt,
        context,
        round_no,
    )

    credential = _credential(seat)

    # --------------------------------------------------------
    # OFFICIAL API
    # --------------------------------------------------------

    if credential:

        try:

            text = _official(
                seat,
                prompt,
            )

            return {
                "seat": seat.name,
                "status": "SUCCESS",
                "mode": "OFFICIAL_API",
                "label": (
                    f"🟢 {seat.name} — Official API"
                ),
                "content": text,
                "latency": (
                    time.perf_counter()
                    - started
                ),
            }

        except Exception as exc:

            official_error = _redact(exc)

            if not local_fallback:

                return {
                    "seat": seat.name,
                    "status": "FAILED",
                    "mode": "OFFICIAL_API",
                    "label": (
                        f"🔴 {seat.name} — Official API failed"
                    ),
                    "content": (
                        f"فشل الاتصال الرسمي: "
                        f"{official_error}"
                    ),
                    "latency": (
                        time.perf_counter()
                        - started
                    ),
                }

    else:

        official_error = (
            "لا يوجد اعتماد رسمي مُكوّن"
        )

    # --------------------------------------------------------
    # LOCAL FALLBACK
    # --------------------------------------------------------

    if local_fallback:

        try:

            text = _local(
                seat,
                prompt,
            )

            return {
                "seat": seat.name,
                "status": "SUCCESS",
                "mode": "LOCAL_FALLBACK",
                "label": (
                    f"🟡 {seat.name} — Local Engine"
                ),
                "content": (
                    "**تنبيه:** هذا الرد من "
                    "Ollama المحلي وليس من "
                    f"{seat.name} الأصلي.\n\n"
                    f"{text}"
                ),
                "latency": (
                    time.perf_counter()
                    - started
                ),
            }

        except Exception as exc:

            return {
                "seat": seat.name,
                "status": "FAILED",
                "mode": "LOCAL_FALLBACK",
                "label": (
                    f"🔴 {seat.name} — Local Engine failed"
                ),
                "content": (
                    "تعذر تشغيل البديل المحلي: "
                    f"{_redact(exc)}"
                ),
                "latency": (
                    time.perf_counter()
                    - started
                ),
            }

    # --------------------------------------------------------
    # UNAVAILABLE
    # --------------------------------------------------------

    return {
        "seat": seat.name,
        "status": "UNAVAILABLE",
        "mode": "NONE",
        "label": (
            f"⚪ {seat.name} — Unavailable"
        ),
        "content": (
            "لا يوجد اعتماد رسمي صالح: "
            f"{official_error}"
        ),
        "latency": (
            time.perf_counter()
            - started
        ),
    }


# ============================================================
# COMPATIBILITY API
# ============================================================

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


def call_official(
    provider_id: str,
    prompt: str,
    model: Optional[str] = None,
) -> str:

    by_id = {
        seat.provider_id: seat
        for seat in SEATS
    }

    if provider_id not in by_id:
        raise ProviderError(
            f"unsupported provider: {provider_id}"
        )

    seat = by_id[provider_id]

    if model:
        seat = Seat(
            seat.name,
            seat.env_key,
            model,
            seat.system,
            seat.provider_id,
        )

    return _official(
        seat,
        prompt,
    )


safe_error = _redact

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple
from urllib.parse import urlparse

import requests


VERSION = "V21.5-CONTRACT-HARDENED"

REQUEST_TIMEOUT = max(
    8,
    min(int(os.getenv("PROVIDER_TIMEOUT", "35")), 90),
)

MAX_OUTPUT_TOKENS = max(
    128,
    min(int(os.getenv("PROVIDER_MAX_OUTPUT_TOKENS", "1200")), 4096),
)

RETRIES = max(
    0,
    min(int(os.getenv("PROVIDER_RETRIES", "1")), 3),
)


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
        os.getenv("OPENAI_MODEL", "gpt-5.6"),
        "You are the OpenAI/ChatGPT seat in a multi-agent council. "
        "Be rigorous and explicit about uncertainty.",
        "openai",
    ),
    Seat(
        "Gemini",
        "GEMINI_API_KEY",
        os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        "You are the Google Gemini seat in a multi-agent council. "
        "Challenge weak assumptions and use evidence.",
        "gemini",
    ),
    Seat(
        "Claude",
        "ANTHROPIC_API_KEY",
        os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
        "You are the Anthropic Claude seat in a multi-agent council. "
        "Be careful, structured, and nuanced.",
        "anthropic",
    ),
    Seat(
        "Grok",
        "XAI_API_KEY",
        os.getenv("XAI_MODEL", "grok-4.6"),
        "You are the xAI Grok seat in a multi-agent council. "
        "Be direct, analytical, and willing to challenge assumptions.",
        "xai",
    ),
    Seat(
        "Kimi",
        "KIMI_API_KEY",
        os.getenv("KIMI_MODEL", "kimi-k2.6"),
        "You are the Moonshot Kimi seat in a multi-agent council. "
        "Focus on synthesis and useful conclusions.",
        "kimi",
    ),
)


class ProviderError(RuntimeError):
    """Expected provider-layer failure with safe diagnostic information."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
    ):
        super().__init__(message)
        self.status_code = status_code


PROVIDERS = {
    "openai": {
        "family": "ChatGPT / OpenAI",
        "endpoint": "https://api.openai.com/v1/responses",
        "kind": "responses",
    },
    "gemini": {
        "family": "Gemini / Google",
        "endpoint": (
            "https://generativelanguage.googleapis.com/"
            "v1beta/models/{model}:generateContent"
        ),
        "kind": "gemini",
    },
    "anthropic": {
        "family": "Claude / Anthropic",
        "endpoint": "https://api.anthropic.com/v1/messages",
        "kind": "anthropic",
    },
    "xai": {
        "family": "Grok / xAI",
        "endpoint": "https://api.x.ai/v1/responses",
        "kind": "responses",
    },
    "kimi": {
        "family": "Kimi / Moonshot AI",
        "endpoint": "https://api.moonshot.ai/v1/chat/completions",
        "kind": "chat",
    },
}


def _streamlit_secret(name: str) -> Optional[str]:
    try:
        import streamlit as st

        value = st.secrets.get(name)

        if value is not None and str(value).strip():
            return str(value).strip()

    except Exception:
        pass

    return None


def get_secret(names: Iterable[str]) -> Optional[str]:
    for name in names:
        value = _streamlit_secret(name)

        if value:
            return value

        value = os.getenv(name, "").strip()

        if value:
            return value

    return None


def credential_names(seat: Seat) -> Tuple[str, ...]:
    if seat.provider_id == "gemini":
        return (
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
        )

    if seat.provider_id == "xai":
        return (
            "XAI_API_KEY",
            "GROK_API_KEY",
        )

    if seat.provider_id == "kimi":
        return (
            "KIMI_API_KEY",
            "MOONSHOT_API_KEY",
        )

    return (seat.env_key,)


def get_seat_credential(seat: Seat) -> Optional[str]:
    return get_secret(credential_names(seat))


def get_models(seat: Seat) -> Tuple[str, ...]:
    env_map = {
        "openai": "OPENAI_MODELS",
        "gemini": "GEMINI_MODELS",
        "anthropic": "ANTHROPIC_MODELS",
        "xai": "XAI_MODELS",
        "kimi": "KIMI_MODELS",
    }

    env_name = env_map[seat.provider_id]

    raw = (
        os.getenv(env_name, "").strip()
        or os.getenv(
            env_name.replace("_MODELS", "_MODEL"),
            "",
        ).strip()
    )

    if raw:
        models = tuple(
            item.strip()
            for item in re.split(r"[,;]", raw)
            if item.strip()
        )

        if models:
            return models

    return (seat.default_model,)


def get_model_candidates(seat: Seat) -> Tuple[str, ...]:
    """
    Return configured models first, followed by current safe fallbacks.

    Fallback is only attempted when the provider reports a model-related
    400/404 condition. Authentication, quota, billing, and network errors
    are never hidden by switching models.
    """

    configured = get_models(seat)

    fallbacks = {
        "openai": (
            "gpt-5.6",
            "gpt-5",
        ),
        "gemini": (
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
        ),
        "anthropic": (
            "claude-sonnet-5",
            "claude-sonnet-4-6",
        ),
        "xai": (
            "grok-4.6",
            "grok-4.5",
        ),
        "kimi": (
            "kimi-k2.6",
            "kimi-k2.5",
        ),
    }[seat.provider_id]

    result = []

    for model in configured + fallbacks:
        if model and model not in result:
            result.append(model)

    return tuple(result)


def configured_provider_ids() -> Tuple[str, ...]:
    return tuple(
        seat.provider_id
        for seat in SEATS
        if get_seat_credential(seat)
    )


def safe_error(exc: Exception) -> str:
    text = str(exc).replace("\n", " ").strip()

    patterns = [
        (
            r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+",
            "Bearer [REDACTED]",
        ),
        (
            r"(?i)(api[_ -]?key|x-api-key|authorization|token|secret|password)"
            r"\s*[:=]\s*[^\s,;]+",
            r"\1=[REDACTED]",
        ),
        (
            r"\bsk-[A-Za-z0-9_-]{8,}\b",
            "[REDACTED]",
        ),
    ]

    for pattern, replacement in patterns:
        text = re.sub(
            pattern,
            replacement,
            text,
        )

    return text[:900] or exc.__class__.__name__


def _host(url: str) -> str:
    return urlparse(url).netloc or "unknown-host"


def _safe_response_detail(
    response: requests.Response,
) -> str:
    """
    Never expose a raw provider response body.
    Only safe diagnostic fields are extracted.
    """

    try:
        data = response.json()

    except ValueError:
        return (
            f"HTTP {response.status_code} "
            f"from {_host(response.url)}"
        )

    if isinstance(data, dict):
        err = data.get("error")

        if isinstance(err, dict):
            parts = []

            for key in (
                "type",
                "code",
                "status",
                "message",
            ):
                value = err.get(key)

                if value:
                    parts.append(
                        f"{key}={safe_error(Exception(str(value)))}"
                    )

            if parts:
                return (
                    f"HTTP {response.status_code}: "
                    + "; ".join(parts)
                )

        for key in (
            "message",
            "error",
            "detail",
        ):
            value = data.get(key)

            if isinstance(value, str) and value.strip():
                return (
                    f"HTTP {response.status_code}: "
                    f"{safe_error(Exception(value))}"
                )

    return (
        f"HTTP {response.status_code} "
        f"from {_host(response.url)}"
    )


def _post(
    url: str,
    headers: dict,
    payload: dict,
    timeout: int = REQUEST_TIMEOUT,
) -> dict:

    last_error: Optional[ProviderError] = None

    for attempt in range(RETRIES + 1):

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )

        except requests.Timeout:
            last_error = ProviderError(
                f"network timeout after {timeout}s"
            )

        except requests.RequestException as exc:
            last_error = ProviderError(
                f"network error: {exc.__class__.__name__}"
            )

        else:

            if response.status_code < 400:

                try:
                    return response.json()

                except ValueError as exc:
                    raise ProviderError(
                        f"invalid JSON response from {_host(url)}"
                    ) from exc

            detail = _safe_response_detail(response)

            last_error = ProviderError(
                detail,
                response.status_code,
            )

            retryable = (
                response.status_code
                in {408, 409, 425, 429}
                or response.status_code >= 500
            )

            if not retryable:
                raise last_error

        if attempt < RETRIES:
            time.sleep(
                0.35 * (attempt + 1)
            )

    raise last_error or ProviderError(
        "provider request failed"
    )


def _openai_text(data: dict) -> str:
    output_text = data.get("output_text")

    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    chunks = []

    for item in data.get("output", []) or []:
        if not isinstance(item, dict):
            continue

        for content in item.get("content", []) or []:
            if (
                isinstance(content, dict)
                and isinstance(content.get("text"), str)
            ):
                chunks.append(content["text"])

    return "\n".join(chunks).strip()


def _chat_text(data: dict) -> str:
    choices = data.get("choices") or []

    if not choices:
        return ""

    message = choices[0].get("message") or {}
    content = message.get("content", "")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        chunks = []

        for item in content:
            if isinstance(item, dict):
                text = item.get("text")

                if isinstance(text, str):
                    chunks.append(text)

        return "\n".join(chunks).strip()

    return ""


def _gemini_text(data: dict) -> str:
    chunks = []

    for candidate in data.get("candidates", []) or []:
        content = candidate.get("content") or {}

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
        for item in (data.get("content") or [])
        if (
            isinstance(item, dict)
            and isinstance(item.get("text"), str)
        )
    ).strip()


def _official_call(
    seat: Seat,
    credential: str,
    prompt: str,
    model: str,
    timeout: int,
) -> str:

    provider = seat.provider_id

    if provider == "openai":

        data = _post(
            "https://api.openai.com/v1/responses",
            {
                "Authorization": f"Bearer {credential}",
                "Content-Type": "application/json",
            },
            {
                "model": model,
                "input": prompt,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
            },
            timeout,
        )

        text = _openai_text(data)

    elif provider == "gemini":

        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{model}:generateContent"
        )

        data = _post(
            url,
            {
                "x-goog-api-key": credential,
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
            timeout,
        )

        text = _gemini_text(data)

    elif provider == "anthropic":

        data = _post(
            "https://api.anthropic.com/v1/messages",
            {
                "x-api-key": credential,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            {
                "model": model,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            },
            timeout,
        )

        text = _anthropic_text(data)

    elif provider == "xai":

        data = _post(
            "https://api.x.ai/v1/responses",
            {
                "Authorization": f"Bearer {credential}",
                "Content-Type": "application/json",
            },
            {
                "model": model,
                "input": prompt,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
            },
            timeout,
        )

        text = _openai_text(data)

    elif provider == "kimi":

        data = _post(
            "https://api.moonshot.ai/v1/chat/completions",
            {
                "Authorization": f"Bearer {credential}",
                "Content-Type": "application/json",
            },
            {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                "max_tokens": MAX_OUTPUT_TOKENS,
            },
            timeout,
        )

        text = _chat_text(data)

    else:
        raise ProviderError(
            f"unsupported provider: {provider}"
        )

    if not text:
        raise ProviderError(
            "official provider returned no text"
        )

    return text


def call_official(
    provider_id: str,
    prompt: str,
    model: str,
    timeout: int = REQUEST_TIMEOUT,
    credential: Optional[str] = None,
) -> str:

    seat = next(
        (
            seat
            for seat in SEATS
            if seat.provider_id == provider_id
        ),
        None,
    )

    if seat is None:
        raise ProviderError(
            f"unknown provider: {provider_id}"
        )

    credential = (
        credential
        or get_seat_credential(seat)
    )

    if not credential:
        raise ProviderError(
            "no official credential configured"
        )

    return _official_call(
        seat,
        credential,
        prompt,
        model,
        timeout,
    )


def _build_prompt(
    seat: Seat,
    user_prompt: str,
    context: str,
    round_no: int,
) -> str:

    return (
        f"{seat.system}\n\n"
        f"Council round: {round_no}.\n"
        "Other council members may be wrong. "
        "Do not blindly agree. Give your own analysis.\n\n"
        f"USER:\n{user_prompt}\n\n"
        f"SHARED CONTEXT:\n"
        f"{context or '(none)'}"
    )


def _local_call(
    seat: Seat,
    prompt: str,
) -> str:

    from local_engine import generate_local

    return generate_local(
        seat.provider_id,
        seat.name,
        seat.system,
        prompt,
    )


def _looks_like_model_error(
    exc: Exception,
) -> bool:

    if not isinstance(exc, ProviderError):
        return False

    status = exc.status_code

    if status not in {400, 404}:
        return False

    text = str(exc).lower()

    markers = (
        "model",
        "model_id",
        "model id",
        "not found",
        "unknown model",
        "does not exist",
        "unsupported model",
        "invalid model",
    )

    return any(
        marker in text
        for marker in markers
    )


def call_seat(
    seat: Seat,
    user_prompt: str,
    context: str = "",
    round_no: int = 1,
    local_fallback: bool = False,
    credential: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:

    started = time.perf_counter()

    configured_models = get_model_candidates(seat)

    if model:
        configured_models = (
            model,
        ) + tuple(
            item
            for item in configured_models
            if item != model
        )

    model_name = (
        configured_models[0]
        if configured_models
        else seat.default_model
    )

    prompt = _build_prompt(
        seat,
        user_prompt,
        context,
        round_no,
    )

    credential = (
        credential
        if credential is not None
        else get_seat_credential(seat)
    )

    official_error = (
        "no official credential configured"
        if not credential
        else None
    )

    tried_models = []

    if credential:

        for candidate in configured_models:

            tried_models.append(candidate)

            try:

                text = _official_call(
                    seat,
                    credential,
                    prompt,
                    candidate,
                    REQUEST_TIMEOUT,
                )

                return {
                    "seat": seat.name,
                    "status": "SUCCESS",
                    "mode": "OFFICIAL_API",
                    "label": (
                        f"🟢 {seat.name} — Official API"
                    ),
                    "model": candidate,
                    "content": text,
                    "error": None,
                    "latency": (
                        time.perf_counter()
                        - started
                    ),
                    "attempted_models": tried_models,
                }

            except Exception as exc:

                official_error = safe_error(exc)

                # Never hide authentication, quota,
                # billing, permission, or network failures
                # by switching models.
                if not _looks_like_model_error(exc):
                    break

    if local_fallback:

        try:

            text = _local_call(
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
                "model": model_name,
                "content": text,
                "error": official_error,
                "latency": (
                    time.perf_counter()
                    - started
                ),
                "attempted_models": tried_models,
            }

        except Exception as exc:

            local_error = safe_error(exc)

            return {
                "seat": seat.name,
                "status": "FAILED",
                "mode": "LOCAL_FALLBACK",
                "label": (
                    f"🔴 {seat.name} — Failed"
                ),
                "model": model_name,
                "content": (
                    "لم ينجح المسار الرسمي "
                    "ولا المسار المحلي."
                ),
                "error": (
                    f"official={official_error}; "
                    f"local={local_error}"
                ),
                "latency": (
                    time.perf_counter()
                    - started
                ),
                "attempted_models": tried_models,
            }

    return {
        "seat": seat.name,
        "status": "FAILED",
        "mode": "OFFICIAL_API",
        "label": (
            f"🔴 {seat.name} — Official API failed"
        ),
        "model": model_name,
        "content": (
            "تعذر الحصول على رد رسمي "
            "من هذا المقعد."
        ),
        "error": official_error,
        "latency": (
            time.perf_counter()
            - started
        ),
        "attempted_models": tried_models,
    }

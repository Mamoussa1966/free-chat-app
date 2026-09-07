from __future__ import annotations

import base64
import os
import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

import requests


VERSION = "V21.21-SIX-ROOM-TEXT-VOICE-PRODUCTION-HARDENED"

REQUEST_TIMEOUT = 45
MAX_OUTPUT_TOKENS = 1200
RETRIES = 1
MAX_MODELS_PER_SEAT = 4
MAX_USER_PROMPT_CHARS = 20000
MAX_SHARED_CONTEXT_CHARS = 30000
MAX_PROVIDER_ATTACHMENT_BYTES = 12 * 1024 * 1024
TRANSCRIBE_DEFAULT_MODEL = "gemini-3.5-transcribe"


@dataclass(frozen=True)
class Seat:
    key: str
    name: str
    label: str
    env_names: Tuple[str, ...]
    model_env: Tuple[str, ...]
    default_model: str
    fallback_models: Tuple[str, ...]
    endpoint: str
    kind: str


SEATS = (
    Seat(
        key="openai",
        name="ChatGPT",
        label="🔑 ChatGPT",
        env_names=("OPENAI_API_KEY",),
        model_env=("OPENAI_MODELS", "OPENAI_MODEL"),
        default_model="gpt-5.6-sol",
        fallback_models=("gpt-5.6-terra", "gpt-5.6-luna"),
        endpoint="https://api.openai.com/v1/responses",
        kind="openai_responses",
    ),
    Seat(
        key="gemini",
        name="Gemini",
        label="🔑 Gemini",
        env_names=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        model_env=("GEMINI_MODELS", "GEMINI_MODEL"),
        default_model="gemini-3.8-flash",
        fallback_models=("gemini-3.7-flash", "gemini-3.6-flash"),
        endpoint=(
            "https://generativelanguage.googleapis.com/"
            "v1beta/models/{model}:generateContent"
        ),
        kind="gemini",
    ),
    Seat(
        key="claude",
        name="Claude",
        label="🔑 Claude",
        env_names=("ANTHROPIC_API_KEY",),
        model_env=(
            "ANTHROPIC_MODELS",
            "ANTHROPIC_MODEL",
            "CLAUDE_MODELS",
            "CLAUDE_MODEL",
        ),
        default_model="claude-sonnet-5",
        fallback_models=(
            "claude-opus-5",
            "claude-fable-5-1",
            "claude-haiku-4-5-20251001",
        ),
        endpoint="https://api.anthropic.com/v1/messages",
        kind="anthropic",
    ),
    Seat(
        key="grok",
        name="Grok",
        label="🔑 Grok",
        env_names=("XAI_API_KEY", "GROK_API_KEY"),
        model_env=(
            "XAI_MODELS",
            "XAI_MODEL",
            "GROK_MODELS",
            "GROK_MODEL",
        ),
        default_model="grok-4.6",
        fallback_models=("grok-4.3",),
        endpoint="https://api.x.ai/v1/responses",
        kind="xai_responses",
    ),
    Seat(
        key="kimi",
        name="Kimi",
        label="🔑 Kimi",
        env_names=("KIMI_API_KEY", "MOONSHOT_API_KEY"),
        model_env=(
            "KIMI_MODELS",
            "KIMI_MODEL",
            "MOONSHOT_MODELS",
            "MOONSHOT_MODEL",
        ),
        default_model="kimi-k3",
        fallback_models=("kimi-k2.6",),
        endpoint="https://api.moonshot.ai/v1/chat/completions",
        kind="chat_completions",
    ),
)


class ProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        error_class: str = "provider",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_class = error_class


def _streamlit_secret(name: str) -> Optional[str]:
    try:
        import streamlit as st

        value = st.secrets.get(name)

        if value:
            return str(value).strip()

    except Exception:
        pass

    return None


def _setting(names: Iterable[str]) -> Optional[str]:
    for name in names:
        value = _streamlit_secret(name)

        if value:
            return value

        value = os.getenv(name, "").strip()

        if value:
            return value

    return None


def get_secret(names: Iterable[str]) -> Optional[str]:
    return _setting(names)


def capture_credentials() -> Dict[str, Optional[str]]:
    return {
        seat.key: get_secret(seat.env_names)
        for seat in SEATS
    }


def configured(
    seat: Seat,
    credential: Optional[str] = None,
) -> bool:
    if credential is None:
        credential = get_secret(seat.env_names)

    return bool(credential)


def configured_count(
    credentials: Optional[Dict[str, Optional[str]]] = None,
) -> int:
    if credentials is None:
        return sum(
            1 for seat in SEATS
            if configured(seat)
        )

    return sum(
        1
        for seat in SEATS
        if credentials.get(seat.key)
    )


def _parse_models(raw: str) -> Tuple[str, ...]:
    values = []
    seen = set()

    for value in re.split(r"[,;\n]", str(raw or "")):
        item = value.strip().strip("\"'")

        if not item:
            continue

        if len(item) > 160:
            continue

        if not re.fullmatch(
            r"[A-Za-z0-9._:/-]+",
            item,
        ):
            continue

        if item not in seen:
            seen.add(item)
            values.append(item)

        if len(values) >= MAX_MODELS_PER_SEAT:
            break

    return tuple(values)


def get_model_candidates(
    seat: Seat,
) -> Tuple[str, ...]:
    raw = _setting(seat.model_env)

    if raw:
        parsed = _parse_models(raw)

        if parsed:
            return parsed

    values = (
        seat.default_model,
        *seat.fallback_models,
    )

    return tuple(
        dict.fromkeys(values)
    )[:MAX_MODELS_PER_SEAT]


def capture_model_candidates() -> Dict[
    str,
    Tuple[str, ...],
]:
    return {
        seat.key: get_model_candidates(seat)
        for seat in SEATS
    }


def _sanitize(text: str) -> str:
    text = str(text or "")

    text = re.sub(
        r"(?i)(api[_ -]?key|authorization|bearer|"
        r"x-api-key|x-goog-api-key)\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        text,
    )

    text = re.sub(
        r"(?i)(sk-[A-Za-z0-9._-]{8,}|"
        r"xai-[A-Za-z0-9._-]{8,}|"
        r"AIza[A-Za-z0-9_-]{20,})",
        "[REDACTED]",
        text,
    )

    text = re.sub(
        r"(?i)(secret|token|password)\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        text,
    )

    return text.replace("\n", " ").strip()[:700]


def _classify(
    status: Optional[int],
    body: str,
) -> str:
    low = body.lower()

    billing_markers = (
        "credit",
        "balance",
        "insufficient",
        "billing",
        "spending",
        "payment required",
        "account suspended",
    )

    if any(
        marker in low
        for marker in billing_markers
    ):
        return "billing_or_quota"

    if status in (401, 403):
        return "authentication_or_permission"

    if status == 429:
        return "rate_limit_or_quota"

    if status is not None and status >= 500:
        return "provider_server"

    if status in (400, 404):
        if any(
            marker in low
            for marker in (
                "model",
                "not found",
                "unknown model",
                "invalid model",
            )
        ):
            return "model_not_found_or_invalid"

    if status is not None and status >= 400:
        return "provider_request_rejected"

    return "provider_error"


def _retryable(
    status: int,
    body: str,
) -> bool:
    if status in (408, 409, 425) or status >= 500:
        return True

    if status != 429:
        return False

    low = body.lower()

    persistent = (
        "credit" in low
        or "balance" in low
        or "insufficient" in low
        or "monthly spending" in low
        or "spending limit" in low
        or "account suspended" in low
        or "quota exceeded" in low
    )

    return not persistent


def _retry_delay(
    response,
    attempt: int,
) -> float:
    retry_after = None

    try:
        if response is not None:
            retry_after = float(
                response.headers.get(
                    "Retry-After",
                    "",
                )
            )
    except (
        TypeError,
        ValueError,
        AttributeError,
    ):
        retry_after = None

    if retry_after is not None:
        return max(
            0.05,
            min(retry_after, 5.0),
        )

    return min(
        2.0,
        0.35 * (attempt + 1),
    )


def _post(
    url: str,
    headers: dict,
    payload: dict,
    timeout: int,
) -> dict:
    last_error = None

    for attempt in range(
        RETRIES + 1
    ):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )

        except requests.Timeout as exc:
            last_error = ProviderError(
                "network timeout",
                error_class="timeout",
            )

            if attempt < RETRIES:
                time.sleep(
                    _retry_delay(
                        None,
                        attempt,
                    )
                )
                continue

            raise last_error from exc

        except requests.RequestException as exc:
            last_error = ProviderError(
                "network error: "
                + exc.__class__.__name__,
                error_class="network",
            )

            if attempt < RETRIES:
                time.sleep(
                    _retry_delay(
                        None,
                        attempt,
                    )
                )
                continue

            raise last_error from exc

        if response.status_code >= 400:
            body = _sanitize(
                response.text[:1200]
            )

            last_error = ProviderError(
                "HTTP "
                + str(response.status_code)
                + ": "
                + (
                    body
                    or "empty error body"
                ),
                status_code=response.status_code,
                error_class=_classify(
                    response.status_code,
                    body,
                ),
            )

            if (
                _retryable(
                    response.status_code,
                    body,
                )
                and attempt < RETRIES
            ):
                time.sleep(
                    _retry_delay(
                        response,
                        attempt,
                    )
                )
                continue

            raise last_error

        try:
            return response.json()

        except ValueError as exc:
            raise ProviderError(
                "invalid JSON response",
                status_code=response.status_code,
                error_class="invalid_response",
            ) from exc

    raise (
        last_error
        or ProviderError(
            "provider request failed"
        )
    )


def _openai_text(data: dict) -> str:
    output_text = data.get(
        "output_text"
    )

    if (
        isinstance(output_text, str)
        and output_text.strip()
    ):
        return output_text.strip()

    parts = []

    for item in data.get(
        "output",
        [],
    ) or []:
        if not isinstance(
            item,
            dict,
        ):
            continue

        for content in item.get(
            "content",
            [],
        ) or []:
            if (
                isinstance(content, dict)
                and isinstance(
                    content.get("text"),
                    str,
                )
            ):
                parts.append(
                    content["text"]
                )

    return "\n".join(parts).strip()


def _chat_text(data: dict) -> str:
    choices = data.get(
        "choices"
    ) or []

    if not choices:
        return ""

    message = (
        choices[0].get("message")
        or {}
    )

    content = message.get(
        "content",
        "",
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
            str(item.get("text", ""))
            for item in content
            if isinstance(
                item,
                dict,
            )
        ).strip()

    return ""


def _gemini_text(data: dict) -> str:
    output = []

    for candidate in data.get(
        "candidates",
        [],
    ) or []:
        content = (
            candidate.get("content")

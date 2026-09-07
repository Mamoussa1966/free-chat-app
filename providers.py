from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

import requests


VERSION = "V21.11-PROVIDER-COMPATIBILITY-HARDENED"


def _bounded_int_env(
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(
            os.getenv(
                name,
                str(default),
            )
        )
    except (TypeError, ValueError):
        value = default

    return max(
        minimum,
        min(value, maximum),
    )


REQUEST_TIMEOUT = _bounded_int_env(
    "PROVIDER_TIMEOUT_SECONDS",
    45,
    5,
    90,
)

MAX_OUTPUT_TOKENS = _bounded_int_env(
    "MAX_OUTPUT_TOKENS",
    1200,
    128,
    4096,
)

RETRIES = 1


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
        "openai",
        "ChatGPT",
        "🔑 ChatGPT",
        ("OPENAI_API_KEY",),
        ("OPENAI_MODELS", "OPENAI_MODEL"),
        "gpt-5.6",
        (
            "gpt-5.6-luna",
            "gpt-5.6-terra",
        ),
        "https://api.openai.com/v1/responses",
        "openai_responses",
    ),

    Seat(
        "gemini",
        "Gemini",
        "🔑 Gemini",
        (
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
        ),
        (
            "GEMINI_MODELS",
            "GEMINI_MODEL",
        ),
        "gemini-3.8-flash",
        (
            "gemini-3.7-flash",
            "gemini-3.6-flash",
        ),
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "gemini",
    ),

    Seat(
        "claude",
        "Claude",
        "🔑 Claude",
        ("ANTHROPIC_API_KEY",),
        (
            "ANTHROPIC_MODELS",
            "ANTHROPIC_MODEL",
            "CLAUDE_MODELS",
            "CLAUDE_MODEL",
        ),
        "claude-sonnet-5",
        ("claude-sonnet-4-6",),
        "https://api.anthropic.com/v1/messages",
        "anthropic",
    ),

    Seat(
        "grok",
        "Grok",
        "🔑 Grok",
        (
            "XAI_API_KEY",
            "GROK_API_KEY",
        ),
        (
            "XAI_MODELS",
            "XAI_MODEL",
            "GROK_MODELS",
            "GROK_MODEL",
        ),
        "grok-4.6",
        ("grok-4.5",),
        "https://api.x.ai/v1/responses",
        "xai_responses",
    ),

    Seat(
        "kimi",
        "Kimi",
        "🔑 Kimi",
        (
            "KIMI_API_KEY",
            "MOONSHOT_API_KEY",
        ),
        (
            "KIMI_MODELS",
            "KIMI_MODEL",
            "MOONSHOT_MODELS",
            "MOONSHOT_MODEL",
        ),
        "kimi-k2.6",
        ("kimi-k2.5",),
        "https://api.moonshot.ai/v1/chat/completions",
        "chat_completions",
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


def _streamlit_secret(
    name: str,
) -> Optional[str]:

    try:
        import streamlit as st

        value = st.secrets.get(name)

        return (
            str(value).strip()
            if value
            else None
        )

    except Exception:
        return None


def _setting(
    names: Iterable[str],
) -> Optional[str]:

    for name in names:

        value = _streamlit_secret(name)

        if value:
            return value

        value = os.getenv(
            name,
            "",
        ).strip()

        if value:
            return value

    return None


def get_secret(
    names: Iterable[str],
) -> Optional[str]:
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

    return bool(
        credential
        if credential is not None
        else get_secret(seat.env_names)
    )


def configured_count(
    credentials: Optional[
        Dict[str, Optional[str]]
    ] = None,
) -> int:

    if credentials is None:
        return sum(
            configured(seat)
            for seat in SEATS
        )

    return sum(
        bool(credentials.get(seat.key))
        for seat in SEATS
    )


def _parse_models(
    raw: str,
) -> Tuple[str, ...]:

    values = tuple(
        x.strip()
        for x in re.split(
            r"[,;\n]",
            raw,
        )
        if x.strip()
    )

    return values


def get_model_candidates(
    seat: Seat,
) -> Tuple[str, ...]:

    raw = _setting(
        seat.model_env
    )

    if raw:

        values = _parse_models(raw)

        if values:
            return values

    return (
        seat.default_model,
        *seat.fallback_models,
    )


def capture_model_candidates() -> Dict[
    str,
    Tuple[str, ...],
]:
    """
    Capture model configuration on the
    Streamlit script thread only.

    Worker threads receive this immutable
    snapshot and never access st.secrets.
    """

    return {
        seat.key: get_model_candidates(seat)
        for seat in SEATS
    }


def _sanitize(text: str) -> str:

    text = re.sub(
        r"(?i)"
        r"(api[_ -]?key|authorization|bearer|"
        r"x-api-key|x-goog-api-key)"
        r"\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        text,
    )

    text = re.sub(
        r"(?i)sk-[A-Za-z0-9._-]{8,}",
        "[REDACTED]",
        text,
    )

    text = re.sub(
        r"(?i)"
        r"(secret|token|password)"
        r"\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        text,
    )

    return (
        text.replace("\n", " ")
        .strip()[:700]
    )


def _classify(
    status: Optional[int],
    body: str,
) -> str:

    low = body.lower()

    if status in (401, 403):
        return "authentication_or_permission"

    if status == 429:
        return "rate_limit_or_quota"

    if status is not None and status >= 500:
        return "provider_server"

    if (
        status in (400, 404)
        and any(
            k in low
            for k in (
                "model",
                "not found",
                "unknown model",
                "invalid model",
            )
        )
    ):
        return "model_not_found_or_invalid"

    if status is not None and status >= 400:
        return "provider_request_rejected"

    return "provider_error"


def _post(
    url: str,
    headers: dict,
    payload: dict,
    timeout: int,
) -> dict:

    last: Optional[
        ProviderError
    ] = None

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

            last = ProviderError(
                "network timeout",
                error_class="timeout",
            )

            if attempt < RETRIES:

                time.sleep(
                    0.35
                    * (attempt + 1)
                )

                continue

            raise last from exc

        except requests.RequestException as exc:

            last = ProviderError(
                "network error: "
                f"{exc.__class__.__name__}",
                error_class="network",
            )

            if attempt < RETRIES:

                time.sleep(
                    0.35
                    * (attempt + 1)
                )

                continue

            raise last from exc

        if response.status_code >= 400:

            body = _sanitize(
                response.text[:1200]
            )

            last = ProviderError(
                f"HTTP {response.status_code}: "
                f"{body or 'empty error body'}",
                status_code=response.status_code,
                error_class=_classify(
                    response.status_code,
                    body,
                ),
            )

            retryable = (
                response.status_code
                in (
                    408,
                    409,
                    425,
                    429,
                )
                or response.status_code >= 500
            )

            if (
                retryable
                and attempt < RETRIES
            ):

                time.sleep(
                    0.35
                    * (attempt + 1)
                )

                continue

            raise last

        try:
            return response.json()

        except ValueError as exc:

            raise ProviderError(
                "invalid JSON response",
                status_code=response.status_code,
                error_class="invalid_response",
            ) from exc

    raise last or ProviderError(
        "provider request failed"
    )


def _openai_text(
    data: dict,
) -> str:

    if (
        isinstance(
            data.get("output_text"),
            str,
        )
        and data["output_text"].strip()
    ):
        return data[
            "output_text"
        ].strip()

    parts = []

    for item in (
        data.get("output", [])
        or []
    ):

        if not isinstance(
            item,
            dict,
        ):
            continue

        for content in (
            item.get("content", [])
            or []
        ):

            if (
                isinstance(
                    content,
                    dict,
                )
                and isinstance(
                    content.get("text"),
                    str,
                )
            ):

                parts.append(
                    content["text"]
                )

    return "\n".join(
        parts
    ).strip()


def _chat_text(
    data: dict,
) -> str:

    choices = (
        data.get("choices")
        or []
    )

    if not choices:
        return ""

    content = (
        choices[0].get("message")
        or {}
    ).get(
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
            str(
                x.get(
                    "text",
                    "",
                )
            )
            for x in content
            if isinstance(
                x,
                dict,
            )
        ).strip()

    return ""


def _gemini_text(
    data: dict,
) -> str:

    out = []

    for candidate in (
        data.get(
            "candidates",
            [],
        )
        or []
    ):

        for part in (
            candidate.get(
                "content"
            )
            or {}
        ).get(
            "parts",
            [],
        ) or []:

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

                out.append(
                    part["text"]
                )

    return "\n".join(
        out
    ).strip()


def _anthropic_text(
    data: dict,
) -> str:

    return "\n".join(
        item.get(
            "text",
            "",
        )
        for item in (
            data.get(
                "content"
            )
            or []
        )
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


def _prompt(
    user_prompt: str,
    shared_context: str,
    round_no: int,
    attachment_note: str = "",
) -> str:

    return (
        "You are one seat in a multi-provider "
        "AI council. Answer independently "
        "and honestly. Do not claim to be "
        "another provider. Use the shared "
        "context only as background. "
        f"This is council round {round_no}.\n\n"
        f"SHARED CONTEXT:\n"
        f"{shared_context.strip() or '(none)'}\n\n"
        f"CURRENT USER REQUEST:\n"
        f"{user_prompt.strip()}"
        f"{attachment_note}"
    )


def call_official(
    seat: Seat,
    prompt: str,
    model: str,
    credential: Optional[str],
    timeout: int = REQUEST_TIMEOUT,
    attachments: Optional[
        list[dict]
    ] = None,
) -> str:

    key = (
        credential or ""
    ).strip()

    if not key:
        raise ProviderError(
            "no official credential configured",
            error_class="not_configured",
        )

    attachments = attachments or []

    from attachment_utils import (
        as_base64,
        as_data_url,
        extract_text,
        is_image,
    )

    if seat.kind == "openai_responses":

        content = [
            {
                "type": "input_text",
                "text": prompt,
            }
        ]

        for attachment in attachments:

            if is_image(attachment):

                content.append(
                    {
                        "type": "input_image",
                        "image_url": as_data_url(
                            attachment
                        ),
                    }
                )

            else:

                content.append(
                    {
                        "type": "input_file",
                        "filename": attachment.get(
                            "name",
                            "attachment",
                        ),
                        "file_data": as_base64(
                            attachment
                        ),
                    }
                )

        data = _post(
            seat.endpoint,
            {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            {
                "model": model,
                "input": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ],
                "max_output_tokens": MAX_OUTPUT_TOKENS,
            },
            timeout,
        )

        text = _openai_text(data)

    elif seat.kind == "gemini":

        parts = [
            {
                "text": prompt
            }
        ]

        for attachment in attachments:

            parts.append(
                {
                    "inlineData": {
                        "mimeType": attachment.get(
                            "mime",
                            "application/octet-stream",
                        ),
                        "data": as_base64(
                            attachment
                        ),
                    }
                }
            )

        data = _post(
            seat.endpoint.format(
                model=model
            ),
            {
                "x-goog-api-key": key,
                "Content-Type": "application/json",
            },
            {
                "contents": [
                    {
                        "role": "user",
                        "parts": parts,
                    }
                ],
                "generationConfig": {
                    "maxOutputTokens": MAX_OUTPUT_TOKENS,
                },
            },
            timeout,
        )

        text = _gemini_text(data)

    elif seat.kind == "anthropic":

        content = [
            {
                "type": "text",
                "text": prompt,
            }
        ]

        for attachment in attachments:

            if is_image(attachment):

                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": attachment.get(
                                "mime",
                                "image/png",
                            ),
                            "data": as_base64(
                                attachment
                            ),
                        },
                    }
                )

            else:

                extracted = extract_text(
                    attachment
                )

                content.append(
                    {
                        "type": "text",
                        "text": (
                            f"Attached file: "
                            f"{attachment.get('name')}\n"
                            f"{extracted or '[binary attachment; filename only]'}"
                        ),
                    }
                )

        data = _post(
            seat.endpoint,
            {
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            {
                "model": model,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "messages": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ],
            },
            timeout,
        )

        text = _anthropic_text(data)

    elif seat.kind == "xai_responses":

        content = [
            {
                "type": "input_text",
                "text": prompt,
            }
        ]

        for attachment in attachments:

            if is_image(attachment):

                content.append(
                    {
                        "type": "input_image",
                        "image_url": as_data_url(
                            attachment
                        ),
                    }
                )

            else:

                extracted = extract_text(
                    attachment
                )

                content.append(
                    {
                        "type": "input_text",
                        "text": (
                            f"Attached file: "
                            f"{attachment.get('name')}\n"
                            f"{extracted or '[binary attachment; filename only]'}"
                        ),
                    }
                )

        data = _post(
            seat.endpoint,
            {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            {
                "model": model,
                "input": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ],
                "max_output_tokens": MAX_OUTPUT_TOKENS,
            },
            timeout,
        )

        text = _openai_text(data)

    elif seat.kind == "chat_completions":

        content = [
            {
                "type": "text",
                "text": prompt,
            }
        ]

        for attachment in attachments:

            if is_image(attachment):

                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": as_data_url(
                                attachment
                            )
                        },
                    }
                )

            else:

                extracted = extract_text(
                    attachment
                )

                content.append(
                    {
                        "type": "text",
                        "text": (
                            f"Attached file: "
                            f"{attachment.get('name')}\n"
                            f"{extracted or '[binary attachment; filename only]'}"
                        ),
                    }
                )

        data = _post(
            seat.endpoint,
            {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ],
                "max_tokens": MAX_OUTPUT_TOKENS,
            },
            timeout,
        )

        text = _chat_text(data)

    else:

        raise ProviderError(
            "unsupported provider contract",
            error_class="configuration",
        )

    if not text:
        raise ProviderError(
            "official provider returned no text",
            error_class="empty_response",
        )

    return text


def call_seat(
    seat: Seat,
    user_prompt: str,
    shared_context: str,
    round_no: int,
    local_fallback: bool,
    credential: Optional[str],
    attachments: Optional[
        list[dict]
    ] = None,
    model_candidates: Optional[
        Tuple[str, ...]
    ] = None,
) -> dict:

    started = time.perf_counter()

    candidates = tuple(
        model_candidates
        or (
            seat.default_model,
            *seat.fallback_models,
        )
    )

    attempted: list[str] = []

    last_error: Optional[
        ProviderError
    ] = None

    if not credential:

        if local_fallback:

            from local_engine import (
                generate_local
            )

            content = generate_local(
                seat.name,
                user_prompt,
                shared_context,
                round_no,
            )

            return _result(
                seat,
                "LOCAL",
                "local",
                "local",
                content,
                (
                    "class=not_configured; "
                    "No official credential configured."
                ),
                started,
                attempted,
            )

        return _result(
            seat,
            "FAILED",
            "official",
            candidates[0],
            "",
            (
                "class=not_configured; "
                "No official credential configured."
            ),
            started,
            attempted,
        )

    for index, model in enumerate(
        candidates
    ):

        attempted.append(model)

        try:

            content = call_official(
                seat,
                _prompt(
                    user_prompt,
                    shared_context,
                    round_no,
                ),
                model,
                credential,
                attachments=attachments,
            )

            return _result(
                seat,
                "SUCCESS",
                "official",
                model,
                content,
                None,
                started,
                attempted,
            )

        except ProviderError as exc:

            last_error = exc

            if (
                exc.error_class
                == "model_not_found_or_invalid"
                and index
                < len(candidates) - 1
            ):
                continue

            break

    diagnostic = _diagnostic(
        last_error
    )

    if local_fallback:

        from local_engine import (
            generate_local
        )

        content = generate_local(
            seat.name,
            user_prompt,
            shared_context,
            round_no,
        )

        return _result(
            seat,
            "LOCAL",
            "local",
            "local",
            content,
            diagnostic,
            started,
            attempted,
        )

    return _result(
        seat,
        "FAILED",
        "official",
        (
            attempted[-1]
            if attempted
            else candidates[0]
        ),
        "",
        diagnostic,
        started,
        attempted,
    )


def diagnostic_seat(
    seat: Seat,
    credential: Optional[str],
    model_candidates: Optional[
        Tuple[str, ...]
    ] = None,
) -> dict:

    """
    Run one minimal official API probe
    without local fallback or attachments.
    """

    return call_seat(
        seat,
        "Reply with exactly: DIAGNOSTIC_OK",
        "",
        0,
        False,
        credential,
        [],
        model_candidates=model_candidates,
    )


def _diagnostic(
    exc: Optional[ProviderError],
) -> str:

    if exc is None:
        return (
            "class=provider_error; "
            "Unknown provider failure."
        )

    status = (
        f"HTTP {exc.status_code}; "
        if exc.status_code
        else ""
    )

    return (
        f"{status}"
        f"class={exc.error_class}; "
        f"{_sanitize(str(exc))}"
    )


def _result(
    seat: Seat,
    status: str,
    mode: str,
    model: str,
    content: str,
    error: Optional[str],
    started: float,
    attempted: list[str],
) -> dict:

    return {
        "seat": seat.key,
        "name": seat.name,
        "label": seat.label,
        "status": status,
        "mode": mode,
        "model": model,
        "content": content,
        "error": error,
        "latency": round(
            time.perf_counter()
            - started,
            3,
        ),
        "attempted_models": attempted,
        "official_authenticated": (
            status == "SUCCESS"
            and mode == "official"
        ),
    }

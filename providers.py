# -*- coding: utf-8 -*-
"""Optional official-provider adapters.

Design invariant:
    no configured credential -> no network request for that provider.
    official failure -> caller can safely fall back to local execution.

The local engine never uses commercial model IDs and never claims commercial identity.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

import requests


@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str
    family: str
    icon: str
    key_names: Tuple[str, ...]
    model_env: str
    default_models: Tuple[str, ...]
    kind: str
    endpoint: str


PROVIDERS: Dict[str, ProviderConfig] = {
    "openai": ProviderConfig(
        "openai", "ChatGPT / OpenAI", "💬", ("OPENAI_API_KEY",), "OPENAI_MODELS",
        ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"),
        "openai_responses", "https://api.openai.com/v1/responses",
    ),
    "gemini": ProviderConfig(
        "gemini", "Gemini / Google", "♊", ("GEMINI_API_KEY", "GOOGLE_API_KEY"), "GEMINI_MODELS",
        ("gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"),
        "gemini_interactions", "https://generativelanguage.googleapis.com/v1beta/interactions",
    ),
    "anthropic": ProviderConfig(
        "anthropic", "Claude / Anthropic", "🧠", ("ANTHROPIC_API_KEY",), "ANTHROPIC_MODELS",
        ("claude-sonnet-5", "claude-sonnet-4-6"),
        "anthropic_messages", "https://api.anthropic.com/v1/messages",
    ),
    "xai": ProviderConfig(
        "xai", "Grok / xAI", "⚡", ("XAI_API_KEY",), "XAI_MODELS",
        ("grok-4.6",), "xai_responses", "https://api.x.ai/v1/responses",
    ),
    "kimi": ProviderConfig(
        "kimi", "Kimi / Moonshot AI", "🌙", ("MOONSHOT_API_KEY", "KIMI_API_KEY"), "KIMI_MODELS",
        ("kimi-k3",), "chat_completions", "https://api.moonshot.ai/v1/chat/completions",
    ),
}


class ProviderError(RuntimeError):
    """Expected, sanitized provider-layer failure."""


def _streamlit_secret(name: str) -> Optional[str]:
    try:
        import streamlit as st
        value = st.secrets.get(name)
        return str(value).strip() if value else None
    except Exception:
        return None


def get_secret(names: Iterable[str]) -> Optional[str]:
    """Read server-side secrets only; never from UI input."""
    for name in names:
        value = _streamlit_secret(name)
        if value:
            return value
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def has_credential(provider_id: str) -> bool:
    cfg = PROVIDERS[provider_id]
    return bool(get_secret(cfg.key_names))


def configured_provider_ids() -> Tuple[str, ...]:
    return tuple(pid for pid in PROVIDERS if has_credential(pid))


def get_models(cfg: ProviderConfig) -> Tuple[str, ...]:
    raw = os.getenv(cfg.model_env, "").strip()
    if not raw:
        raw = os.getenv(cfg.model_env.replace("_MODELS", "_MODEL"), "").strip()
    if raw:
        models = tuple(x.strip() for x in re.split(r"[,;]", raw) if x.strip())
        if models:
            return models
    return cfg.default_models


def safe_error(exc: Exception) -> str:
    """Return short diagnostic text with common credential forms redacted."""
    text = str(exc).replace("\n", " ").strip()
    patterns = [
        r"(?i)(authorization\s*[:=]\s*bearer)\s+[^\s,;]+",
        r"(?i)(x-api-key\s*[:=])\s*[^\s,;]+",
        r"(?i)(api[_ -]?key\s*[:=])\s*[^\s,;]+",
        r"(?i)(bearer\s+)\S+",
    ]
    for pattern in patterns:
        text = re.sub(pattern, r"\1[REDACTED]", text)
    return text[:700] or exc.__class__.__name__


def _post(url: str, headers: dict, payload: dict, timeout: int, retries: int = 1) -> dict:
    last: Optional[Exception] = None
    for attempt in range(max(0, retries) + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            last = ProviderError(f"network:{exc.__class__.__name__}")
            if attempt < retries:
                time.sleep(0.25 * (attempt + 1))
                continue
            raise last from exc
        if response.status_code >= 400:
            body = response.text[:600].replace("\n", " ")
            body = safe_error(Exception(body))
            last = ProviderError(f"HTTP {response.status_code}: {body}")
            if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
                if attempt < retries:
                    time.sleep(0.25 * (attempt + 1))
                    continue
            raise last
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("invalid JSON response") from exc
        if not isinstance(data, dict):
            raise ProviderError("unexpected JSON response")
        return data
    raise last or ProviderError("provider request failed")


def _openai_text(data: dict) -> str:
    value = data.get("output_text")
    if isinstance(value, str) and value.strip():
        return value.strip()
    chunks = []
    for item in data.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def _gemini_text(data: dict) -> str:
    value = data.get("output_text")
    if isinstance(value, str) and value.strip():
        return value.strip()
    chunks = []
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("text"), str):
                chunks.append(item["text"])
            for part in item.get("content", []) or []:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
    return "\n".join(chunks).strip()


def _anthropic_text(data: dict) -> str:
    return "\n".join(
        x.get("text", "") for x in (data.get("content") or [])
        if isinstance(x, dict) and isinstance(x.get("text"), str)
    ).strip()


def _chat_text(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(
            item.get("text", "") for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ).strip()
    return ""


def call_official(provider_id: str, prompt: str, model: str, timeout: int = 35) -> str:
    """Perform exactly one official request. Caller owns fallback behavior."""
    if provider_id not in PROVIDERS:
        raise ProviderError("unknown provider")
    cfg = PROVIDERS[provider_id]
    key = get_secret(cfg.key_names)
    if not key:
        raise ProviderError("no official credential configured")
    timeout = max(5, min(90, int(timeout)))

    if cfg.kind in {"openai_responses", "xai_responses"}:
        data = _post(
            cfg.endpoint,
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            {"model": model, "input": prompt, "max_output_tokens": 1400},
            timeout,
        )
        text = _openai_text(data)
    elif cfg.kind == "gemini_interactions":
        data = _post(
            cfg.endpoint,
            {"x-goog-api-key": key, "Content-Type": "application/json"},
            {"model": model, "input": prompt, "generation_config": {"thinking_level": "medium"}},
            timeout,
        )
        text = _gemini_text(data)
    elif cfg.kind == "anthropic_messages":
        data = _post(
            cfg.endpoint,
            {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            {"model": model, "max_tokens": 1400, "messages": [{"role": "user", "content": prompt}]},
            timeout,
        )
        text = _anthropic_text(data)
    elif cfg.kind == "chat_completions":
        data = _post(
            cfg.endpoint,
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1400},
            timeout,
        )
        text = _chat_text(data)
    else:
        raise ProviderError("unsupported provider kind")

    if not text:
        raise ProviderError("official provider returned no text")
    return text

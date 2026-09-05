# -*- coding: utf-8 -*-
"""V19.4 optional official Provider layer.

Truth contract:
- No credential => no provider network call.
- Successful authenticated provider response => official_api.
- Provider failure after an attempted call is handled by main.py as local_fallback.
- This module never claims that a local engine is a commercial model.
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
        "responses", "https://api.openai.com/v1/responses",
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
        ("grok-4.6",), "responses", "https://api.x.ai/v1/responses",
    ),
    "kimi": ProviderConfig(
        "kimi", "Kimi / Moonshot AI", "🌙", ("MOONSHOT_API_KEY", "KIMI_API_KEY"), "KIMI_MODELS",
        ("kimi-k3", "kimi-k2.7-code-highspeed", "kimi-k2.6"),
        "chat_completions", "https://api.moonshot.ai/v1/chat/completions",
    ),
}


class ProviderError(RuntimeError):
    """Expected, isolated provider failure."""


def _streamlit_secret(name: str) -> Optional[str]:
    try:
        import streamlit as st
        value = st.secrets.get(name)
        return str(value).strip() if value else None
    except Exception:
        return None


def get_secret(names: Iterable[str]) -> Optional[str]:
    """Resolve server-side credentials only; never expose them to the UI."""
    for name in names:
        value = _streamlit_secret(name)
        if value:
            return value
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def get_models(cfg: ProviderConfig) -> Tuple[str, ...]:
    raw = os.getenv(cfg.model_env, "").strip()
    if not raw:
        raw = os.getenv(cfg.model_env.replace("_MODELS", "_MODEL"), "").strip()
    if raw:
        models = tuple(x.strip() for x in re.split(r"[,;]", raw) if x.strip())
        if models:
            return models
    return cfg.default_models


def configured_provider_ids() -> Tuple[str, ...]:
    return tuple(pid for pid, cfg in PROVIDERS.items() if get_secret(cfg.key_names))


def _redact(text: str) -> str:
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)(api[_ -]?key|x-api-key|authorization)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)(secret|token|password)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    return text


def safe_error(exc: Exception) -> str:
    text = _redact(str(exc).replace("\n", " ").strip())
    return text[:700] or exc.__class__.__name__


def _post(url: str, headers: dict, payload: dict, timeout: int, retries: int = 1) -> dict:
    last: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            last = ProviderError(f"network:{exc.__class__.__name__}")
            if attempt < retries:
                time.sleep(0.35 * (attempt + 1))
                continue
            raise last from exc
        if response.status_code >= 400:
            body = _redact(response.text[:600]).replace("\n", " ")
            last = ProviderError(f"HTTP {response.status_code}: {body}")
            if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
                if attempt < retries:
                    time.sleep(0.35 * (attempt + 1))
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


def _responses_text(data: dict) -> str:
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


def _chat_text(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    content = (choices[0].get("message") or {}).get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(x.get("text", "") for x in content if isinstance(x, dict) and isinstance(x.get("text"), str)).strip()
    return ""


def _gemini_interaction_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"].strip()
    chunks = []
    for item in data.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("text"), str):
            chunks.append(item["text"])
        for content in item.get("content", []) or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    for step in data.get("steps", []) or []:
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        for item in step.get("content", []) or []:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                chunks.append(item["text"])
    return "\n".join(chunks).strip()


def _anthropic_text(data: dict) -> str:
    return "\n".join(
        item.get("text", "") for item in data.get("content", []) or []
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    ).strip()


def call_official(provider_id: str, prompt: str, model: str, timeout: int = 35, credential: Optional[str] = None) -> str:
    """Perform one official authenticated request using the supplied credential."""
    if provider_id not in PROVIDERS:
        raise ProviderError("unknown provider")
    cfg = PROVIDERS[provider_id]
    key = (credential or "").strip() if credential is not None else get_secret(cfg.key_names)
    if not key:
        raise ProviderError("no official credential configured")

    if cfg.kind == "responses":
        data = _post(
            cfg.endpoint,
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            {"model": model, "input": prompt, "max_output_tokens": 1400, "store": False},
            timeout,
        )
        text = _responses_text(data)
    elif cfg.kind == "gemini_interactions":
        data = _post(
            cfg.endpoint,
            {"x-goog-api-key": key, "Content-Type": "application/json"},
            {"model": model, "input": prompt, "store": False},
            timeout,
        )
        text = _gemini_interaction_text(data)
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

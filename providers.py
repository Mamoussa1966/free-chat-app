# -*- coding: utf-8 -*-
"""AI Council V20 — provider compatibility layer.

This file intentionally exposes the API expected by main.py:
    from providers import SEATS, call_seat

Properties:
- Five stable seat objects: ChatGPT, Gemini, Claude, Grok, Kimi.
- No credential => no official network request for that seat.
- Official failures are isolated and never crash the whole room.
- Optional Ollama fallback is explicitly labelled as local.
- Secrets are read from environment variables or Streamlit Secrets only.
- API keys are never included in returned errors.

The implementation uses HTTP directly through requests, so provider SDKs are
not required for importing this module.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

import requests


REQUEST_TIMEOUT = max(5, min(int(os.getenv("PROVIDER_TIMEOUT", "35")), 90))
MAX_OUTPUT_TOKENS = max(128, min(int(os.getenv("PROVIDER_MAX_OUTPUT_TOKENS", "1200")), 4096))


@dataclass(frozen=True)
class Seat:
    """Public seat contract consumed by main.py."""

    name: str
    env_key: str
    default_model: str
    system: str
    provider_id: str


# Keep defaults conservative and overridable. The application must not assume
# that a future/internal ChatGPT model name is a public API model name.
SEATS: Tuple[Seat, ...] = (
    Seat(
        "ChatGPT",
        "OPENAI_API_KEY",
        os.getenv("OPENAI_MODEL", "gpt-5"),
        "You are the OpenAI/ChatGPT seat in a multi-agent council. "
        "Be rigorous, useful, and explicit about uncertainty.",
        "openai",
    ),
    Seat(
        "Gemini",
        "GEMINI_API_KEY",
        os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "You are the Google Gemini seat in a multi-agent council. "
        "Analyze evidence and challenge weak reasoning.",
        "gemini",
    ),
    Seat(
        "Claude",
        "ANTHROPIC_API_KEY",
        os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        "You are the Anthropic Claude seat in a multi-agent council. "
        "Be careful, structured, and nuanced.",
        "anthropic",
    ),
    Seat(
        "Grok",
        "XAI_API_KEY",
        os.getenv("XAI_MODEL", "grok-4"),
        "You are the xAI Grok seat in a multi-agent council. "
        "Be direct, analytical, and willing to challenge assumptions.",
        "xai",
    ),
    Seat(
        "Kimi",
        "KIMI_API_KEY",
        os.getenv("KIMI_MODEL", "kimi-k2.5"),
        "You are the Moonshot Kimi seat in a multi-agent council. "
        "Focus on synthesis, long-context reasoning, and useful conclusions.",
        "kimi",
    ),
)


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


# Compatibility API retained for older V16–V19 code paths.
PROVIDERS: Dict[str, ProviderConfig] = {
    "openai": ProviderConfig(
        "openai", "ChatGPT / OpenAI", "💬", ("OPENAI_API_KEY",),
        "OPENAI_MODELS", (os.getenv("OPENAI_MODEL", "gpt-5"),),
        "openai_responses", "https://api.openai.com/v1/responses",
    ),
    "gemini": ProviderConfig(
        "gemini", "Gemini / Google", "♊", ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "GEMINI_MODELS", (os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),),
        "gemini", "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    ),
    "anthropic": ProviderConfig(
        "anthropic", "Claude / Anthropic", "🧠", ("ANTHROPIC_API_KEY",),
        "ANTHROPIC_MODELS", (os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),),
        "anthropic", "https://api.anthropic.com/v1/messages",
    ),
    "xai": ProviderConfig(
        "xai", "Grok / xAI", "⚡", ("XAI_API_KEY",),
        "XAI_MODELS", (os.getenv("XAI_MODEL", "grok-4"),),
        "openai_chat", "https://api.x.ai/v1/chat/completions",
    ),
    "kimi": ProviderConfig(
        "kimi", "Kimi / Moonshot AI", "🌙", ("MOONSHOT_API_KEY", "KIMI_API_KEY"),
        "KIMI_MODELS", (os.getenv("KIMI_MODEL", "kimi-k2.5"),),
        "openai_chat", "https://api.moonshot.ai/v1/chat/completions",
    ),
}


class ProviderError(RuntimeError):
    """Expected provider-layer failure."""


def _streamlit_secret(name: str) -> Optional[str]:
    try:
        import streamlit as st
        value = st.secrets.get(name)
        return str(value).strip() if value else None
    except Exception:
        return None


def get_secret(names: Iterable[str]) -> Optional[str]:
    """Read server-side credentials without exposing them to the UI."""
    for name in names:
        value = _streamlit_secret(name)
        if value:
            return value
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def _key(seat: Seat) -> Optional[str]:
    names = (seat.env_key,)
    if seat.name == "Grok":
        names = ("XAI_API_KEY", "GROK_API_KEY")
    elif seat.name == "Kimi":
        names = ("KIMI_API_KEY", "MOONSHOT_API_KEY")
    elif seat.name == "Gemini":
        names = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
    return get_secret(names)


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


def safe_error(exc: Exception) -> str:
    """Return a short error with credentials and authorization data redacted."""
    text = str(exc).replace("\n", " ").strip()
    text = re.sub(r"(?i)bearer\s+[^\s,;]+", "Bearer [REDACTED]", text)
    text = re.sub(
        r"(?i)(api[_ -]?key|authorization|x-api-key|secret|token|password)\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        text,
    )
    # Also avoid leaking common OpenAI-style secret prefixes embedded in text.
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[REDACTED]", text)
    return text[:700] or exc.__class__.__name__


def _post(url: str, headers: dict, payload: dict, timeout: int = REQUEST_TIMEOUT) -> dict:
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise ProviderError(f"network: {exc.__class__.__name__}") from exc

    if response.status_code >= 400:
        body = safe_error(ProviderError(response.text[:500]))
        raise ProviderError(f"HTTP {response.status_code}: {body}")

    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderError("invalid JSON response") from exc

    if not isinstance(data, dict):
        raise ProviderError("unexpected provider response")
    return data


def _openai_text(data: dict) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

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
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ).strip()
    return ""


def _gemini_text(data: dict) -> str:
    chunks = []
    for candidate in data.get("candidates", []) or []:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content") or {}
        for part in content.get("parts", []) or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "\n".join(chunks).strip()


def _anthropic_text(data: dict) -> str:
    return "\n".join(
        item.get("text", "")
        for item in (data.get("content") or [])
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    ).strip()


def call_official(provider_id: str, prompt: str, model: str, timeout: int = REQUEST_TIMEOUT) -> str:
    """Call exactly one official provider endpoint."""
    cfg = PROVIDERS[provider_id]
    key = get_secret(cfg.key_names)
    if not key:
        raise ProviderError("no official credential configured")

    if cfg.kind == "openai_responses":
        data = _post(
            cfg.endpoint,
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            {"model": model, "input": prompt, "max_output_tokens": MAX_OUTPUT_TOKENS},
            timeout,
        )
        text = _openai_text(data)
    elif cfg.kind == "openai_chat":
        data = _post(
            cfg.endpoint,
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": MAX_OUTPUT_TOKENS},
            timeout,
        )
        text = _chat_text(data)
    elif cfg.kind == "anthropic":
        data = _post(
            cfg.endpoint,
            {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            {
                "model": model,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "system": "You are an Anthropic Claude seat in a multi-agent council.",
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout,
        )
        text = _anthropic_text(data)
    elif cfg.kind == "gemini":
        url = cfg.endpoint.format(model=model)
        data = _post(
            url,
            {"x-goog-api-key": key, "Content-Type": "application/json"},
            {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS},
            },
            timeout,
        )
        text = _gemini_text(data)
    else:
        raise ProviderError("unsupported provider kind")

    if not text:
        raise ProviderError("official provider returned no text")
    return text


def _prompt(seat: Seat, user_prompt: str, context: str, round_no: int) -> str:
    return (
        f"{seat.system}\n\n"
        f"Round {round_no}.\n"
        "The following is shared room context. Other agents may be wrong. "
        "Do not blindly agree; identify agreements, disagreements, corrections, "
        "and your best contribution.\n\n"
        f"USER QUESTION:\n{user_prompt}\n\n"
        f"SHARED ROOM CONTEXT:\n{context or '(no previous replies)'}"
    )


def _local_call(seat: Seat, prompt: str) -> str:
    """Call Ollama only when the caller explicitly enables local fallback."""
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.2").strip()
    if not model:
        raise ProviderError("OLLAMA_MODEL is empty")

    try:
        response = requests.post(
            f"{host}/api/chat",
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"You are a local fallback model contributing to the {seat.name} seat. "
                            f"Never claim to be the official {seat.name} service.\n\n{prompt}"
                        ),
                    }
                ],
                "stream": False,
            },
            timeout=max(10, min(int(os.getenv("OLLAMA_TIMEOUT", "60")), 120)),
        )
    except requests.RequestException as exc:
        raise ProviderError(f"local network: {exc.__class__.__name__}") from exc

    if response.status_code >= 400:
        raise ProviderError(f"local HTTP {response.status_code}")

    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderError("local engine returned invalid JSON") from exc

    text = ((data.get("message") or {}).get("content") or "").strip()
    if not text:
        raise ProviderError("local engine returned no text")
    return text


def call_seat(
    seat: Seat,
    user_prompt: str,
    context: str,
    round_no: int,
    local_fallback: bool = False,
) -> dict:
    """Execute one seat and return a main.py-compatible result dictionary."""
    started = time.perf_counter()
    prompt = _prompt(seat, user_prompt, context, round_no)
    key = _key(seat)
    official_error = "NO_CREDENTIAL"

    if key:
        try:
            reply = call_official(
                seat.provider_id,
                prompt,
                seat.default_model,
                REQUEST_TIMEOUT,
            )
            return {
                "seat": seat.name,
                "status": "SUCCESS",
                "mode": "OFFICIAL_API",
                "label": f"🟢 {seat.name} — Official API",
                "content": reply,
                "latency": time.perf_counter() - started,
            }
        except Exception as exc:
            official_error = safe_error(exc)
            if not local_fallback:
                return {
                    "seat": seat.name,
                    "status": "FAILED",
                    "mode": "OFFICIAL_API",
                    "label": f"🔴 {seat.name} — Official API failed",
                    "content": f"الاتصال الرسمي فشل: {official_error}",
                    "latency": time.perf_counter() - started,
                }

    if local_fallback:
        try:
            reply = _local_call(seat, prompt)
            return {
                "seat": seat.name,
                "status": "SUCCESS",
                "mode": "LOCAL_FALLBACK",
                "label": f"🟡 {seat.name} — Local Engine",
                "content": (
                    f"**تنبيه:** هذا الرد من محرك Ollama المحلي، وليس {seat.name} الأصلي.\n\n"
                    f"{reply}"
                ),
                "latency": time.perf_counter() - started,
            }
        except Exception as exc:
            local_error = safe_error(exc)
            return {
                "seat": seat.name,
                "status": "FAILED",
                "mode": "LOCAL_FALLBACK",
                "label": f"🔴 {seat.name} — Local Engine failed",
                "content": f"تعذر تشغيل البديل المحلي: {local_error}",
                "latency": time.perf_counter() - started,
            }

    return {
        "seat": seat.name,
        "status": "UNAVAILABLE",
        "mode": "NONE",
        "label": f"⚪ {seat.name} — Unavailable",
        "content": (
            "لا يوجد اعتماد رسمي صالح، ولم يتم تشغيل البديل المحلي."
            if official_error == "NO_CREDENTIAL"
            else f"تعذر الاتصال الرسمي: {official_error}"
        ),
        "latency": time.perf_counter() - started,
    }


# Backward-compatible aliases used by some older tests/modules.
streamlit_secret = _streamlit_secret

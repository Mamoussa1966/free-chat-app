# -*- coding: utf-8 -*-
"""AI Council V20 Secure - provider gateway.

Public API required by main.py:
    from providers import SEATS, call_seat

Security:
- API keys are read from Streamlit Secrets or environment variables only.
- Keys are never returned in errors/results.
- No official request is attempted without a credential.
- Optional Ollama fallback is explicitly labelled LOCAL and is opt-in.

Provider notes (September 2026):
- Gemini defaults to gemini-3.8-flash; override with GEMINI_MODEL.
- Claude supports ANTHROPIC_WORKSPACE_ID when the key is workspace-scoped.
- Grok uses XAI_API_KEY.
- Kimi accepts KIMI_API_KEY or MOONSHOT_API_KEY.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import requests


REQUEST_TIMEOUT = max(5, min(int(os.getenv("PROVIDER_TIMEOUT", "45")), 90))
MAX_OUTPUT_TOKENS = max(128, min(int(os.getenv("PROVIDER_MAX_OUTPUT_TOKENS", "1400")), 8192))


@dataclass(frozen=True)
class Seat:
    name: str
    env_key: str
    default_model: str
    system: str
    provider_id: str


# Stable public seat list. main.py imports this symbol directly.
SEATS: Tuple[Seat, ...] = (
    Seat(
        "ChatGPT", "OPENAI_API_KEY", os.getenv("OPENAI_MODEL", "gpt-5"),
        "You are the OpenAI ChatGPT seat in an AI council. Be precise, rigorous, and explicit about uncertainty.",
        "openai",
    ),
    Seat(
        "Gemini", "GEMINI_API_KEY", os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        "You are the Google Gemini seat in an AI council. Challenge weak assumptions and use evidence.",
        "gemini",
    ),
    Seat(
        "Claude", "ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        "You are the Anthropic Claude seat in an AI council. Be careful, structured, and nuanced.",
        "anthropic",
    ),
    Seat(
        "Grok", "XAI_API_KEY", os.getenv("XAI_MODEL", "grok-4"),
        "You are the xAI Grok seat in an AI council. Be direct, analytical, and willing to challenge assumptions.",
        "xai",
    ),
    Seat(
        "Kimi", "KIMI_API_KEY", os.getenv("KIMI_MODEL", "kimi-k2.5"),
        "You are the Moonshot Kimi seat in an AI council. Focus on synthesis and long-context reasoning.",
        "kimi",
    ),
)


class ProviderError(RuntimeError):
    pass


def _secret(name: str) -> Optional[str]:
    """Read a secret without ever displaying it."""
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
        return _first_secret("GEMINI_API_KEY", "GOOGLE_API_KEY")
    if seat.provider_id == "xai":
        return _first_secret("XAI_API_KEY", "GROK_API_KEY")
    if seat.provider_id == "kimi":
        return _first_secret("KIMI_API_KEY", "MOONSHOT_API_KEY")
    return _secret(seat.env_key)


def _workspace_id() -> Optional[str]:
    return _first_secret("ANTHROPIC_WORKSPACE_ID", "CLAUDE_WORKSPACE_ID")


def _redact(text: str) -> str:
    text = str(text or "").replace("\n", " ")
    patterns = [
        (r"(?i)bearer\s+[^\s,;]+", "Bearer [REDACTED]"),
        (r"(?i)(api[_ -]?key|authorization|x-api-key|secret|token|password)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]"),
        (r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text[:700] or "provider error"


def _post(url: str, headers: dict, payload: dict) -> dict:
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise ProviderError(f"network error: {exc.__class__.__name__}") from exc

    if r.status_code >= 400:
        # Keep provider diagnostics useful, but never expose credentials.
        raise ProviderError(f"HTTP {r.status_code}: {_redact(r.text[:900])}")

    try:
        data = r.json()
    except ValueError as exc:
        raise ProviderError("provider returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ProviderError("provider returned an unexpected response")
    return data


def _openai_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"].strip()
    chunks = []
    for item in data.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content", []) or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
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
        return "\n".join(
            p.get("text", "") for p in content
            if isinstance(p, dict) and isinstance(p.get("text"), str)
        ).strip()
    return ""


def _gemini_text(data: dict) -> str:
    chunks = []
    for candidate in data.get("candidates", []) or []:
        content = candidate.get("content") or {}
        for part in content.get("parts", []) or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "\n".join(chunks).strip()


def _anthropic_text(data: dict) -> str:
    return "\n".join(
        item.get("text", "") for item in data.get("content", []) or []
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    ).strip()


def _call_openai(seat: Seat, key: str, prompt: str) -> str:
    data = _post(
        "https://api.openai.com/v1/responses",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        {"model": seat.default_model, "input": prompt, "max_output_tokens": MAX_OUTPUT_TOKENS, "store": False},
    )
    text = _openai_text(data)
    if not text:
        raise ProviderError("OpenAI returned no text")
    return text


def _call_gemini(seat: Seat, key: str, prompt: str) -> str:
    model = seat.default_model
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    data = _post(
        url,
        {"x-goog-api-key": key, "Content-Type": "application/json"},
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS},
        },
    )
    text = _gemini_text(data)
    if not text:
        raise ProviderError("Gemini returned no text")
    return text


def _call_anthropic(seat: Seat, key: str, prompt: str) -> str:
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
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    text = _anthropic_text(data)
    if not text:
        raise ProviderError("Claude returned no text")
    return text


def _call_xai(seat: Seat, key: str, prompt: str) -> str:
    data = _post(
        "https://api.x.ai/v1/chat/completions",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        {"model": seat.default_model, "messages": [{"role": "user", "content": prompt}], "max_tokens": MAX_OUTPUT_TOKENS},
    )
    text = _chat_text(data)
    if not text:
        raise ProviderError("Grok returned no text")
    return text


def _call_kimi(seat: Seat, key: str, prompt: str) -> str:
    data = _post(
        "https://api.moonshot.ai/v1/chat/completions",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        {"model": seat.default_model, "messages": [{"role": "user", "content": prompt}], "max_tokens": MAX_OUTPUT_TOKENS},
    )
    text = _chat_text(data)
    if not text:
        raise ProviderError("Kimi returned no text")
    return text


def _official(seat: Seat, prompt: str) -> str:
    key = _credential(seat)
    if not key:
        raise ProviderError("no official credential configured")
    if seat.provider_id == "openai":
        return _call_openai(seat, key, prompt)
    if seat.provider_id == "gemini":
        return _call_gemini(seat, key, prompt)
    if seat.provider_id == "anthropic":
        return _call_anthropic(seat, key, prompt)
    if seat.provider_id == "xai":
        return _call_xai(seat, key, prompt)
    if seat.provider_id == "kimi":
        return _call_kimi(seat, key, prompt)
    raise ProviderError("unsupported provider")


def _local(seat: Seat, prompt: str) -> str:
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.2").strip()
    if not model:
        raise ProviderError("OLLAMA_MODEL is empty")
    try:
        r = requests.post(
            f"{host}/api/chat",
            json={
                "model": model,
                "stream": False,
                "messages": [{
                    "role": "user",
                    "content": f"You are a LOCAL FALLBACK for the {seat.name} seat. Never claim to be the official provider.\n\n{prompt}",
                }],
            },
            timeout=max(10, min(int(os.getenv("OLLAMA_TIMEOUT", "60")), 120)),
        )
    except requests.RequestException as exc:
        raise ProviderError(f"local network error: {exc.__class__.__name__}") from exc
    if r.status_code >= 400:
        raise ProviderError(f"local HTTP {r.status_code}")
    try:
        data = r.json()
    except ValueError as exc:
        raise ProviderError("Ollama returned invalid JSON") from exc
    text = ((data.get("message") or {}).get("content") or "").strip()
    if not text:
        raise ProviderError("Ollama returned no text")
    return text


def _build_prompt(seat: Seat, user_prompt: str, context: str, round_no: int) -> str:
    return (
        f"{seat.system}\n\n"
        f"Council round: {round_no}\n"
        "Other council members may be wrong. Do not blindly agree. Give your own analysis.\n\n"
        f"USER:\n{user_prompt}\n\n"
        f"SHARED CONTEXT:\n{context or '(none)'}"
    )


def call_seat(
    seat: Seat,
    user_prompt: str,
    context: str = "",
    round_no: int = 1,
    local_fallback: bool = False,
) -> dict:
    """main.py-compatible seat call; provider failures are isolated."""
    started = time.perf_counter()
    prompt = _build_prompt(seat, user_prompt, context, round_no)
    credential = _credential(seat)

    if credential:
        try:
            text = _official(seat, prompt)
            return {
                "seat": seat.name,
                "status": "SUCCESS",
                "mode": "OFFICIAL_API",
                "label": f"🟢 {seat.name} — Official API",
                "content": text,
                "latency": time.perf_counter() - started,
            }
        except Exception as exc:
            official_error = _redact(exc)
            if not local_fallback:
                return {
                    "seat": seat.name,
                    "status": "FAILED",
                    "mode": "OFFICIAL_API",
                    "label": f"🔴 {seat.name} — Official API failed",
                    "content": f"الاتصال الرسمي فشل: {official_error}",
                    "latency": time.perf_counter() - started,
                }
    else:
        official_error = "no official credential configured"

    if local_fallback:
        try:
            text = _local(seat, prompt)
            return {
                "seat": seat.name,
                "status": "SUCCESS",
                "mode": "LOCAL_FALLBACK",
                "label": f"🟡 {seat.name} — Local Engine",
                "content": f"**تنبيه:** هذا الرد من Ollama المحلي وليس {seat.name} الأصلي.\n\n{text}",
                "latency": time.perf_counter() - started,
            }
        except Exception as exc:
            return {
                "seat": seat.name,
                "status": "FAILED",
                "mode": "LOCAL_FALLBACK",
                "label": f"🔴 {seat.name} — Local Engine failed",
                "content": f"تعذر تشغيل البديل المحلي: {_redact(exc)}",
                "latency": time.perf_counter() - started,
            }

    return {
        "seat": seat.name,
        "status": "UNAVAILABLE",
        "mode": "NONE",
        "label": f"⚪ {seat.name} — Unavailable",
        "content": f"لا يوجد اعتماد رسمي صالح: {official_error}",
        "latency": time.perf_counter() - started,
    }


# Compatibility symbols for older V19/V20 modules.
PROVIDERS = {
    "openai": {"env": "OPENAI_API_KEY", "model_env": "OPENAI_MODEL"},
    "gemini": {"env": "GEMINI_API_KEY", "model_env": "GEMINI_MODEL"},
    "anthropic": {"env": "ANTHROPIC_API_KEY", "model_env": "ANTHROPIC_MODEL"},
    "xai": {"env": "XAI_API_KEY", "model_env": "XAI_MODEL"},
    "kimi": {"env": "KIMI_API_KEY", "model_env": "KIMI_MODEL"},
}


def call_official(provider_id: str, prompt: str, model: Optional[str] = None) -> str:
    """Backward-compatible official-provider entry point."""
    by_id = {seat.provider_id: seat for seat in SEATS}
    if provider_id not in by_id:
        raise ProviderError(f"unsupported provider: {provider_id}")
    seat = by_id[provider_id]
    if model:
        seat = Seat(seat.name, seat.env_key, model, seat.system, seat.provider_id)
    return _official(seat, prompt)


# Backward-compatible helper names.
safe_error = _redact

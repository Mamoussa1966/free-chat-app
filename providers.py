from __future__ import annotations

import os
import re
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
        "openai", "ChatGPT / OpenAI", "💬", ("OPENAI_API_KEY",),
        "OPENAI_MODEL", ("gpt-5", "gpt-5.1", "gpt-5-mini"),
        "openai_responses", "https://api.openai.com/v1/responses",
    ),
    "gemini": ProviderConfig(
        "gemini", "Gemini / Google", "♊", ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "GEMINI_MODEL", ("gemini-3.7-flash", "gemini-3.6-flash"),
        "gemini", "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    ),
    "anthropic": ProviderConfig(
        "anthropic", "Claude / Anthropic", "🧠", ("ANTHROPIC_API_KEY",),
        "ANTHROPIC_MODEL", ("claude-sonnet-5", "claude-opus-5", "claude-sonnet-4-6"),
        "anthropic", "https://api.anthropic.com/v1/messages",
    ),
    "xai": ProviderConfig(
        "xai", "Grok / xAI", "⚡", ("XAI_API_KEY",),
        "XAI_MODEL", ("grok-4.6", "grok-4.1"),
        "openai_responses", "https://api.x.ai/v1/responses",
    ),
    "kimi": ProviderConfig(
        "kimi", "Kimi / Moonshot AI", "🌙", ("MOONSHOT_API_KEY",),
        "KIMI_MODEL", ("kimi-k2.5", "kimi-k2"),
        "openai_chat", "https://api.moonshot.ai/v1/chat/completions",
    ),
}


class ProviderError(RuntimeError):
    pass


def _secret_from_streamlit(name: str) -> Optional[str]:
    try:
        import streamlit as st
        value = st.secrets.get(name)
        if value:
            return str(value).strip()
    except Exception:
        pass
    return None


def get_secret(names: Iterable[str]) -> Optional[str]:
    for name in names:
        value = _secret_from_streamlit(name)
        if value:
            return value
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def get_models(cfg: ProviderConfig) -> Tuple[str, ...]:
    override = os.getenv(cfg.model_env, "").strip()
    if not override:
        # Also allow a comma-separated *_MODELS list without changing the UI.
        override = os.getenv(cfg.model_env.replace("_MODEL", "_MODELS"), "").strip()
    if override:
        models = tuple(x.strip() for x in re.split(r"[,;]", override) if x.strip())
        if models:
            return models
    return cfg.default_models


def configured_provider_ids() -> Tuple[str, ...]:
    return tuple(pid for pid, cfg in PROVIDERS.items() if get_secret(cfg.key_names))


def safe_error(exc: Exception) -> str:
    text = str(exc).replace("\n", " ").strip()
    text = re.sub(r"(?i)(api[_ -]?key|authorization|bearer|x-api-key)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    return text[:700] or exc.__class__.__name__


def _post(url: str, headers: Dict[str, str], payload: dict, timeout: int) -> dict:
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise ProviderError(f"network: {exc.__class__.__name__}") from exc
    if response.status_code >= 400:
        body = response.text[:500].replace("\n", " ")
        raise ProviderError(f"HTTP {response.status_code}: {body}")
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError("المزود أعاد JSON غير صالح.") from exc


def _openai_text(data: dict) -> str:
    text = data.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    chunks = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def _gemini_text(data: dict) -> str:
    chunks = []
    for candidate in data.get("candidates", []) or []:
        for part in (candidate.get("content", {}) or {}).get("parts", []) or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "\n".join(chunks).strip()


def _anthropic_text(data: dict) -> str:
    return "\n".join(
        block.get("text", "")
        for block in data.get("content", []) or []
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    ).strip()


def _chat_text(data: dict) -> str:
    choices = data.get("choices", []) or []
    if not choices:
        return ""
    content = (choices[0].get("message", {}) or {}).get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(
            x.get("text", "") for x in content if isinstance(x, dict) and isinstance(x.get("text"), str)
        ).strip()
    return ""


def call_official(provider_id: str, api_key: str, model: str, system_prompt: str, user_prompt: str, timeout: int = 35) -> str:
    cfg = PROVIDERS[provider_id]
    if cfg.kind == "openai_responses":
        data = _post(
            cfg.endpoint,
            {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            {"model": model, "instructions": system_prompt, "input": user_prompt, "max_output_tokens": 1400, "store": False},
            timeout,
        )
        text = _openai_text(data)
    elif cfg.kind == "gemini":
        url = cfg.endpoint.format(model=model)
        data = _post(
            url + f"?key={api_key}",
            {"Content-Type": "application/json"},
            {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {"maxOutputTokens": 1400, "temperature": 0.4},
            },
            timeout,
        )
        text = _gemini_text(data)
    elif cfg.kind == "anthropic":
        data = _post(
            cfg.endpoint,
            {
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            {
                "model": model,
                "system": system_prompt,
                "max_tokens": 1400,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout,
        )
        text = _anthropic_text(data)
    elif cfg.kind == "openai_chat":
        data = _post(
            cfg.endpoint,
            {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 1400,
                "temperature": 0.4,
            },
            timeout,
        )
        text = _chat_text(data)
    else:
        raise ProviderError("نوع Provider غير مدعوم.")

    if not text:
        raise ProviderError("المزود أعاد استجابة بلا نص.")
    return text

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

from audit.logger import log_event

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    from anthropic import Anthropic
except Exception:
    Anthropic = None

try:
    from google import genai
except Exception:
    genai = None

try:
    import ollama
except Exception:
    ollama = None


@dataclass(frozen=True)
class Seat:
    name: str
    env_key: str
    default_model: str
    system: str


SEATS = (
    Seat('ChatGPT', 'OPENAI_API_KEY', os.getenv('OPENAI_MODEL', 'gpt-5-mini'), 'You are the official OpenAI ChatGPT seat in a multi-agent council. Be rigorous, useful, and explicit about uncertainty.'),
    Seat('Gemini', 'GEMINI_API_KEY', os.getenv('GEMINI_MODEL', 'gemini-3.7-flash'), 'You are the official Google Gemini seat in a multi-agent council. Analyze evidence and challenge weak reasoning.'),
    Seat('Claude', 'ANTHROPIC_API_KEY', os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-6'), 'You are the official Anthropic Claude seat in a multi-agent council. Be careful, structured, and nuanced.'),
    Seat('Grok', 'XAI_API_KEY', os.getenv('XAI_MODEL', 'grok-4.6'), 'You are the official xAI Grok seat in a multi-agent council. Be direct, analytical, and willing to challenge assumptions.'),
    Seat('Kimi', 'KIMI_API_KEY', os.getenv('KIMI_MODEL', 'kimi-k2.5'), 'You are the official Moonshot Kimi seat in a multi-agent council. Focus on synthesis, long-context reasoning, and useful conclusions.'),
)


def _key(seat: Seat) -> Optional[str]:
    value = os.getenv(seat.env_key)
    if not value and seat.name == 'Grok':
        value = os.getenv('GROK_API_KEY')
    if value:
        return value.strip()
    try:
        import streamlit as st
        value = st.secrets.get(seat.env_key)
        return str(value).strip() if value else None
    except Exception:
        return None


def _prompt(seat: Seat, user_prompt: str, context: str, round_no: int) -> str:
    return (
        f'{seat.system}\n\n'
        f'You are participating in Round {round_no}.\n'
        'The text below is the shared room context. Other agents may have made claims that are wrong. '
        'Do not blindly agree. Explicitly identify agreements, disagreements, corrections, and your best contribution.\n\n'
        f'USER QUESTION:\n{user_prompt}\n\n'
        f'SHARED ROOM CONTEXT:\n{context or "(no previous replies)"}'
    )


def _official_call(seat: Seat, key: str, prompt: str) -> str:
    model = seat.default_model
    if seat.name == 'ChatGPT':
        if OpenAI is None:
            raise RuntimeError('OpenAI SDK is not installed')
        client = OpenAI(api_key=key)
        response = client.responses.create(model=model, input=prompt)
        return (response.output_text or '').strip()
    if seat.name == 'Gemini':
        if genai is None:
            raise RuntimeError('Google GenAI SDK is not installed')
        client = genai.Client(api_key=key)
        response = client.models.generate_content(model=model, contents=prompt)
        return (response.text or '').strip()
    if seat.name == 'Claude':
        if Anthropic is None:
            raise RuntimeError('Anthropic SDK is not installed')
        client = Anthropic(api_key=key)
        response = client.messages.create(
            model=model,
            max_tokens=1600,
            system=seat.system,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return ''.join(getattr(block, 'text', '') for block in response.content).strip()
    if seat.name == 'Grok':
        if OpenAI is None:
            raise RuntimeError('OpenAI SDK is not installed')
        client = OpenAI(api_key=key, base_url='https://api.x.ai/v1')
        response = client.responses.create(model=model, input=prompt)
        return (response.output_text or '').strip()
    if seat.name == 'Kimi':
        if OpenAI is None:
            raise RuntimeError('OpenAI SDK is not installed')
        client = OpenAI(api_key=key, base_url='https://api.moonshot.ai/v1')
        response = client.responses.create(model=model, input=prompt)
        return (response.output_text or '').strip()
    raise RuntimeError(f'Unsupported seat: {seat.name}')


def _local_call(seat: Seat, prompt: str) -> str:
    if ollama is None:
        raise RuntimeError('Ollama package is not installed')
    model = os.getenv('OLLAMA_MODEL', 'llama3.2')
    local_prompt = (
        f'You are a local fallback model contributing a role-inspired answer for the {seat.name} seat. '
        f'Never claim to be the official {seat.name} service.\n\n{prompt}'
    )
    response = ollama.chat(model=model, messages=[{'role': 'user', 'content': local_prompt}])
    return response['message']['content'].strip()


def call_seat(seat: Seat, user_prompt: str, context: str, round_no: int, local_fallback: bool = False) -> dict:
    started = time.perf_counter()
    key = _key(seat)
    prompt = _prompt(seat, user_prompt, context, round_no)

    if key:
        try:
            reply = _official_call(seat, key, prompt)
            latency = time.perf_counter() - started
            log_event(seat.name, 'SUCCESS', 'OFFICIAL_API', latency)
            return {'seat': seat.name, 'status': 'SUCCESS', 'mode': 'OFFICIAL_API', 'label': f'🟢 {seat.name} — Official API', 'content': reply, 'latency': latency}
        except Exception as exc:
            log_event(seat.name, 'FAILED', 'OFFICIAL_API', time.perf_counter() - started, type(exc).__name__)
            official_error = type(exc).__name__
            if not local_fallback:
                return {'seat': seat.name, 'status': 'FAILED', 'mode': 'OFFICIAL_API', 'label': f'🔴 {seat.name} — Official API failed', 'content': f'الاتصال الرسمي فشل ({official_error}).', 'latency': time.perf_counter() - started}
    else:
        official_error = 'NO_CREDENTIAL'

    if local_fallback:
        try:
            reply = _local_call(seat, prompt)
            latency = time.perf_counter() - started
            log_event(seat.name, 'SUCCESS', 'LOCAL_FALLBACK', latency)
            return {'seat': seat.name, 'status': 'SUCCESS', 'mode': 'LOCAL_FALLBACK', 'label': f'🟡 {seat.name} — Local Engine', 'content': f'**تنبيه:** هذا رد من Ollama المحلي، وليس {seat.name} الأصلي.\n\n{reply}', 'latency': latency}
        except Exception as exc:
            log_event(seat.name, 'FAILED', 'LOCAL_FALLBACK', time.perf_counter() - started, type(exc).__name__)

    log_event(seat.name, 'UNAVAILABLE', 'NONE', time.perf_counter() - started, official_error)
    return {'seat': seat.name, 'status': 'UNAVAILABLE', 'mode': 'NONE', 'label': f'⚪ {seat.name} — Unavailable', 'content': 'لا يوجد اعتماد رسمي صالح، ولم يتم تشغيل البديل المحلي.', 'latency': time.perf_counter() - started}

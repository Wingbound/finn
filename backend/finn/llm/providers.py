"""Thin provider adapters: call_* sends the request, parse_* -> (text, in_tokens, out_tokens)."""

from __future__ import annotations

import httpx

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT = 30.0


def call_groq(
    client: httpx.Client, api_key: str, model: str, system: str, user: str
) -> httpx.Response:
    return client.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        },
    )


def parse_groq(data: dict) -> tuple[str, int, int]:
    usage = data.get("usage") or {}
    return (
        data["choices"][0]["message"]["content"],
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
    )


def call_gemini(
    client: httpx.Client, api_key: str, model: str, system: str, user: str
) -> httpx.Response:
    return client.post(
        GEMINI_URL.format(model=model),
        headers={"x-goog-api-key": api_key},
        json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
        },
    )


def parse_gemini(data: dict) -> tuple[str, int, int]:
    usage = data.get("usageMetadata") or {}
    return (
        data["candidates"][0]["content"]["parts"][0]["text"],
        usage.get("promptTokenCount", 0),
        usage.get("candidatesTokenCount", 0),
    )


PROVIDERS = {
    "groq": (call_groq, parse_groq, "groq_api_key", "GROQ_API_KEY"),
    "gemini": (call_gemini, parse_gemini, "gemini_api_key", "GEMINI_API_KEY"),
}

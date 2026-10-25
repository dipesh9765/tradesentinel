"""
Multi-Provider LLM Gateway - KitePulse AI

Single entry point for the AI layer so the rest of the app never touches a vendor SDK.
Supports Google Gemini, OpenAI and Anthropic Claude. The active provider, per-provider
model and API keys live in the encrypted vault and can be changed at runtime from the
Settings page.

Keys and models are looked up on every call (cheap vault read), so a change made in the
UI takes effect immediately with no restart.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

import database
from config import settings

logger = logging.getLogger(__name__)

AI_PROVIDER_SETTING = "AI_PROVIDER"
DEFAULT_PROVIDER = "gemini"
REQUEST_TIMEOUT_SECONDS = 30.0

# Suggested models only; the UI also accepts any custom model id the provider supports.
PROVIDERS: Dict[str, Dict[str, Any]] = {
    "gemini": {
        "label": "Google Gemini",
        "key_setting": "GEMINI_API_KEY",
        "model_setting": "AI_MODEL_GEMINI",
        "default_model": settings.GEMINI_MODEL,
        "models": ["gemini-3.6-flash", "gemini-3.6-pro", "gemini-2.5-pro", "gemini-2.5-flash"],
        "key_url": "https://aistudio.google.com/app/apikey",
        "key_hint": "AIzaSy...",
    },
    "openai": {
        "label": "OpenAI",
        "key_setting": "OPENAI_API_KEY",
        "model_setting": "AI_MODEL_OPENAI",
        "default_model": "gpt-4.1",
        "models": ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini", "o4-mini"],
        "key_url": "https://platform.openai.com/api-keys",
        "key_hint": "sk-...",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "key_setting": "ANTHROPIC_API_KEY",
        "model_setting": "AI_MODEL_ANTHROPIC",
        "default_model": "claude-sonnet-5-5",
        "models": ["claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
        "key_url": "https://console.anthropic.com/settings/keys",
        "key_hint": "sk-ant-...",
    },
}


class AIProviderError(Exception):
    """Raised when a provider call fails or returns unusable output."""


def get_active_provider() -> str:
    provider = database.get_secure_setting(AI_PROVIDER_SETTING, "") or DEFAULT_PROVIDER
    return provider if provider in PROVIDERS else DEFAULT_PROVIDER


def set_active_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown AI provider '{provider}'.")
    database.save_secure_setting(AI_PROVIDER_SETTING, provider)


def get_api_key(provider: str) -> str:
    meta = PROVIDERS[provider]
    key = database.get_secure_setting(meta["key_setting"], "")
    if not key and provider == "gemini":
        key = settings.GEMINI_API_KEY
    return key


def set_api_key(provider: str, key: str) -> None:
    database.save_secure_setting(PROVIDERS[provider]["key_setting"], key.strip())
    if provider == "gemini":
        settings.GEMINI_API_KEY = key.strip()


def get_model(provider: str) -> str:
    meta = PROVIDERS[provider]
    return database.get_secure_setting(meta["model_setting"], "") or meta["default_model"]


def set_model(provider: str, model: str) -> None:
    model = model.strip()
    if not model:
        raise ValueError("Model name cannot be empty.")
    database.save_secure_setting(PROVIDERS[provider]["model_setting"], model)


def is_configured(provider: Optional[str] = None) -> bool:
    return bool(get_api_key(provider or get_active_provider()))


def describe_config() -> Dict[str, Any]:
    """Settings-page view: never includes raw keys, only whether one is stored."""
    def mask(val: str) -> str:
        if not val:
            return ""
        return "••••••••" if len(val) <= 8 else val[:3] + "••••••••" + val[-3:]

    return {
        "active_provider": get_active_provider(),
        "providers": [
            {
                "id": pid,
                "label": meta["label"],
                "models": meta["models"],
                "model": get_model(pid),
                "has_key": bool(get_api_key(pid)),
                "key_preview": mask(get_api_key(pid)),
                "key_url": meta["key_url"],
                "key_hint": meta["key_hint"],
            }
            for pid, meta in PROVIDERS.items()
        ],
    }


def _extract_json(text: str) -> Dict[str, Any]:
    """Parses a JSON object from model text, tolerating code fences and surrounding prose."""
    text = (text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise AIProviderError("Model response contained no JSON object.")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise AIProviderError(f"Model returned malformed JSON: {e}")


def _call_gemini(api_key: str, model: str, prompt: str) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
    )
    return response.text


def _call_openai(api_key: str, model: str, prompt: str) -> str:
    body: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Respond with a single valid JSON object and nothing else."},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    # Reasoning models (o-series) reject a custom temperature.
    if not model.startswith("o"):
        body["temperature"] = 0.2
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise AIProviderError(f"OpenAI error {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"]["content"]


def _call_anthropic(api_key: str, model: str, prompt: str) -> str:
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 1024,
            "system": "Respond with a single valid JSON object and nothing else.",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise AIProviderError(f"Anthropic error {resp.status_code}: {resp.text[:300]}")
    blocks: List[Dict[str, Any]] = resp.json().get("content", [])
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


_CALLERS = {"gemini": _call_gemini, "openai": _call_openai, "anthropic": _call_anthropic}


def generate_json(prompt: str, provider: Optional[str] = None, model: Optional[str] = None,
                  api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Sends a prompt to the chosen provider (default: the active one) and returns the parsed
    JSON object. Retries once on a transient 5xx/429/network failure. Raises AIProviderError.
    """
    provider = provider or get_active_provider()
    if provider not in PROVIDERS:
        raise AIProviderError(f"Unknown AI provider '{provider}'.")
    api_key = api_key or get_api_key(provider)
    if not api_key:
        raise AIProviderError(f"No API key configured for {PROVIDERS[provider]['label']}.")
    model = model or get_model(provider)

    last_error: Optional[Exception] = None
    for attempt in range(2):
        try:
            return _extract_json(_CALLERS[provider](api_key, model, prompt))
        except AIProviderError as e:
            last_error = e
            transient = any(code in str(e) for code in (" 429", " 500", " 502", " 503", " 529"))
            if not transient:
                break
        except Exception as e:  # SDK / network errors
            last_error = e
            msg = str(e)
            transient = any(code in msg for code in ("429", "500", "502", "503", "timed out", "Timeout"))
            if not transient:
                break
        if attempt == 0:
            logger.info(f"{provider}/{model} transient failure, retrying: {last_error}")
            time.sleep(1.5)
    raise AIProviderError(f"{provider}/{model} failed: {last_error}")

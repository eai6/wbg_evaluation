"""Thin LiteLLM wrapper: one place for model config, timeouts, usage/latency accounting and error handling.

Any LiteLLM model id works (anthropic/..., openai/..., gemini/..., groq/..., ollama/...); reviewers set it in .env.
"""
from __future__ import annotations

import json
import logging
import time

from django.conf import settings

log = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    pass


def available() -> bool:
    cfg = settings.LLM
    return bool(cfg["api_key"] or cfg["api_base"] or cfg["model"].startswith("ollama"))


def complete(messages: list[dict], *, fast: bool = False, tools: list | None = None, json_mode: bool = False,
             temperature: float = 0.0, max_tokens: int = 1500, usage: list | None = None):
    """Return the LiteLLM message object. Appends {model, in, out, ms} to ``usage`` for cost/latency tracking."""
    if not available():
        raise LLMUnavailable("No LLM configured (set LLM_MODEL and LLM_API_KEY in .env)")
    import litellm  # imported lazily: keeps startup fast and the app usable without an LLM

    cfg = settings.LLM
    model = cfg["fast_model"] if fast else cfg["model"]
    kwargs = dict(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens,
                  timeout=cfg["timeout"], api_key=cfg["api_key"] or None, api_base=cfg["api_base"])
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    if json_mode and not model.startswith("anthropic/"):
        kwargs["response_format"] = {"type": "json_object"}
    t0 = time.time()
    try:
        resp = litellm.completion(**kwargs)
    except Exception as exc:  # provider errors, content policy, timeouts
        log.warning("LLM call failed (%s): %s", model, exc)
        raise LLMUnavailable(str(exc)[:300]) from exc
    if usage is not None:
        u = getattr(resp, "usage", None)
        usage.append({"model": model, "in": getattr(u, "prompt_tokens", 0) or 0,
                      "out": getattr(u, "completion_tokens", 0) or 0, "ms": int((time.time() - t0) * 1000)})
    return resp.choices[0].message


def complete_json(messages: list[dict], **kw) -> dict:
    msg = complete(messages, json_mode=True, **kw)
    text = (msg.content or "").strip()
    text = text[text.find("{"): text.rfind("}") + 1] if "{" in text else "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.warning("router returned non-JSON: %s", text[:200])
        return {}

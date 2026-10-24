"""Voyance II — AI explanation layer.

Provider chain (first working wins, surfaced honestly in responses):
  1. OpenCode Zen  (OPENCODE_API_KEY) — model list from their /models endpoint
  2. Groq          (GROQ_API_KEY)
  3. OpenRouter    (OPENROUTER_API_KEY)
Keys are read directly from ~/.bashrc (the uvicorn process does not inherit
interactive-shell exports). Every response states which provider+model served it.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests

UA = {"User-Agent": "voyance2/2.0 (open-source maritime terminal)"}
BASHRC = Path.home() / ".bashrc"


def _key_from_bashrc(var: str) -> str:
    if os.environ.get(var):
        return os.environ[var]
    if BASHRC.exists():
        m = re.search(rf'^export {var}="?([^"\n]+)"?', BASHRC.read_text(errors="ignore"), re.M)
        if m:
            return m.group(1)
    return ""


def _chat(base: str, key: str, model: str, messages: list[dict],
          max_tokens: int = 1600, timeout: int = 120) -> str:
    r = requests.post(f"{base}/chat/completions",
                      headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
                      json={"model": model, "messages": messages,
                            "max_tokens": max_tokens, "temperature": 0.3},
                      timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def providers_status() -> list[dict]:
    """Probe the chain and report availability + model menus.

    chat_ok means a real 5-token completion succeeded — a key that lists models
    but rejects chat (Zen free tier is CLI-only) reports chat_ok=False honestly.
    """
    out = []
    oc_key = _key_from_bashrc("OPENCODE_API_KEY")
    oc_models: list[str] = []
    if oc_key:
        try:
            r = requests.get("https://opencode.ai/zen/v1/models",
                             headers={"Authorization": f"Bearer {oc_key}"}, timeout=20)
            oc_models = [m["id"] for m in r.json().get("data", [])]
            chat_ok, chat_note = False, ""
            try:
                _chat("https://opencode.ai/zen/v1", oc_key, oc_models[0] if oc_models else "grok-code",
                      [{"role": "user", "content": "ok"}], max_tokens=5, timeout=30)
                chat_ok = True
            except requests.RequestException as e:
                body = getattr(e, "response", None)
                chat_note = body.text[:100] if body is not None else str(e)[:100]
            out.append({"provider": "opencode", "key": "OPENCODE_API_KEY",
                        "reachable": True, "chat_ok": chat_ok, "models": oc_models,
                        "note": chat_note or "verified by 5-token completion"})
        except requests.RequestException as e:
            out.append({"provider": "opencode", "reachable": False, "models": [],
                        "note": str(e)[:120]})
    gk = _key_from_bashrc("GROQ_API_KEY")
    if gk:
        gok = False
        try:
            _chat("https://api.groq.com/openai/v1", gk, "qwen/qwen3.8-27b",
                  [{"role": "user", "content": "ok"}], max_tokens=5, timeout=30)
            gok = True
        except requests.RequestException:
            pass
        out.append({"provider": "groq", "key": "GROQ_API_KEY", "reachable": True,
                    "chat_ok": gok,
                    "models": ["qwen/qwen3.8-27b", "openai/gpt-oss-120b"],
                    "note": "verified by 5-token completion" if gok else "chat probe failed"})
    ok = _key_from_bashrc("OPENROUTER_API_KEY")
    if ok:
        ook = False
        try:
            _chat("https://openrouter.ai/api/v1", ok, "meta-llama/llama-3.3-70b-instruct",
                  [{"role": "user", "content": "ok"}], max_tokens=5, timeout=30)
            ook = True
        except requests.RequestException:
            pass
        out.append({"provider": "openrouter", "key": "OPENROUTER_API_KEY", "reachable": True,
                    "chat_ok": ook,
                    "models": ["meta-llama/llama-3.3-70b-instruct",
                               "google/gemini-2.5-flash",
                               "openai/gpt-oss-120b"],
                    "note": "verified by 5-token completion (metered)" if ook else "chat probe failed"})
    return out


DEFAULT_CHAIN = [
    ("opencode", "https://opencode.ai/zen/v1", "OPENCODE_API_KEY", "grok-code"),
    ("groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "qwen/qwen3.8-27b"),
    ("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
     "meta-llama/llama-3.3-70b-instruct"),
]


def explain(messages: list[dict], provider: str | None = None,
            model: str | None = None, max_tokens: int = 1800) -> dict:
    """Run the chain (or a specific provider+model) and return {answer, provider, model}."""
    chain = DEFAULT_CHAIN
    if provider:
        chain = [c for c in DEFAULT_CHAIN if c[0] == provider] + \
                [c for c in DEFAULT_CHAIN if c[0] != provider]
    errors = []
    for name, base, var, default_model in chain:
        key = _key_from_bashrc(var)
        if not key:
            errors.append(f"{name}: no {var} in ~/.bashrc")
            continue
        mdl = model if (model and provider == name) else default_model
        try:
            answer = _chat(base, key, mdl, messages, max_tokens=max_tokens)
            return {"answer": answer, "provider": name, "model": mdl,
                    "errors": errors}
        except requests.RequestException as e:
            detail = ""
            if getattr(e, "response", None) is not None:
                detail = e.response.text[:160]
            errors.append(f"{name}/{mdl}: {type(e).__name__} {detail}")
        except KeyError:
            errors.append(f"{name}/{mdl}: malformed response")
    return {"answer": "", "provider": None, "model": None,
            "errors": errors + ["no provider in the chain could serve the request"]}

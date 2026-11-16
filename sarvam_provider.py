"""Sarvam Token Factory provider (OpenAI-compatible chat completions).

Used only when PROVIDER=sarvam. Same vision prompt + JSON schema as NVIDIA;
all post-OCR / tariff / self-check logic is shared. Never logs the API key,
request body, or model content.

Prices (₹ per 1M tokens, docs.sarvam.ai, fetched 14 Nov 2026; reasoning is
billed as output):
  glm5.3-flash: in 13.5 / cached 2.5 / out 45   (reasoning cannot be turned off)
  gemma4:       in 35   / cached 10  / out 90
"""
from __future__ import annotations

import base64
import os
import time
from typing import Any, Dict, Optional, Tuple

import requests

SARVAM_URL = "https://api.sarvam.ai/v2/chat/completions"
SARVAM_MODEL = "glm5.3-flash"
SARVAM_FALLBACK_MODEL = "gemma4"

SARVAM_MODELS: Dict[str, Dict[str, Any]] = {
    "glm5.3-flash": {
        "reasoning_effort": "low",  # cannot disable; "low" keeps cost/latency down
        "max_tokens": 4000,          # reasoning shares this budget
        "timeout_s": 120,
        "price_in": 13.5, "price_cached": 2.5, "price_out": 45.0,
    },
    "gemma4": {
        "reasoning_effort": None,    # off when omitted
        "max_tokens": 1600,
        "timeout_s": 90,
        "price_in": 35.0, "price_cached": 10.0, "price_out": 90.0,
    },
}

# Running totals for this process (benchmarks / budget guards). No PII.
SPEND = {"calls": 0, "cost_inr": 0.0}
LAST_CALL: Dict[str, Any] = {}


def get_provider() -> str:
    p = (os.environ.get("PROVIDER") or "").strip().lower()
    if not p:
        try:
            import streamlit as st
            p = str(st.secrets.get("PROVIDER", "") or "").strip().lower()  # type: ignore[attr-defined]
        except Exception:
            p = ""
    return "sarvam" if p == "sarvam" else "nvidia"


def get_sarvam_api_key() -> Optional[str]:
    v = os.environ.get("SARVAM_API_KEY")
    if v and str(v).strip():
        return str(v).strip()
    try:
        import streamlit as st
        v = st.secrets.get("SARVAM_API_KEY")  # type: ignore[attr-defined]
        if v and str(v).strip():
            return str(v).strip()
    except Exception:
        pass
    return None


def usage_counts(usage: Dict[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        v = (usage or {}).get(k)
        if isinstance(v, (int, float)):
            out[k] = int(v)
    pd = (usage or {}).get("prompt_tokens_details") or {}
    if isinstance(pd, dict) and isinstance(pd.get("cached_tokens"), (int, float)):
        out["cached_tokens"] = int(pd["cached_tokens"])
    if isinstance((usage or {}).get("cached_tokens"), (int, float)):
        out["cached_tokens"] = int(usage["cached_tokens"])
    cd = (usage or {}).get("completion_tokens_details") or {}
    if isinstance(cd, dict) and isinstance(cd.get("reasoning_tokens"), (int, float)):
        out["reasoning_tokens"] = int(cd["reasoning_tokens"])
    return out


def cost_inr(usage: Dict[str, int], model: str) -> float:
    m = SARVAM_MODELS.get(model) or SARVAM_MODELS[SARVAM_MODEL]
    prompt = int(usage.get("prompt_tokens") or 0)
    cached = int(usage.get("cached_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    uncached = max(0, prompt - cached)
    return (uncached * m["price_in"] + cached * m["price_cached"] + completion * m["price_out"]) / 1_000_000


def call_sarvam_once(
    image_bytes: bytes,
    mime: str = "image/jpeg",
    prompt: Optional[str] = None,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Tuple[Dict[str, Any], float, str]:
    """Same contract as nvidia_pipeline.call_nvidia_once: (raw_json, latency_s, content)."""
    from nvidia_pipeline import (
        NvidiaCallError, VISION_PROMPT, TEMPERATURE, TOP_P, _parse_json_loose, jpeg_payload_info,
        _log_nvidia,
    )
    key = get_sarvam_api_key()
    if not key:
        raise NvidiaCallError("missing_key", "SARVAM_API_KEY missing")
    use_model = model or SARVAM_MODEL
    cfg = SARVAM_MODELS.get(use_model) or SARVAM_MODELS[SARVAM_MODEL]
    use_timeout = cfg["timeout_s"] if timeout is None else timeout
    info = jpeg_payload_info(image_bytes)
    data_url = "data:%s;base64,%s" % (mime, base64.b64encode(image_bytes).decode("ascii"))
    payload: Dict[str, Any] = {
        "model": use_model,
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        "max_tokens": cfg["max_tokens"],
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt or VISION_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
    }
    if cfg.get("reasoning_effort"):
        payload["reasoning_effort"] = cfg["reasoning_effort"]
    headers = {
        "Authorization": "Bearer " + key,
        "api-subscription-key": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    t0 = time.time()
    SPEND["calls"] += 1
    try:
        resp = requests.post(SARVAM_URL, headers=headers, json=payload, timeout=use_timeout)
    except requests.Timeout as e:
        elapsed = round(time.time() - t0, 2)
        raise NvidiaCallError("timeout", "Sarvam timeout after %.2fs" % elapsed,
                              elapsed_s=elapsed, model=use_model, jpeg_bytes=info["jpeg_bytes"]) from e
    except requests.RequestException as e:
        elapsed = round(time.time() - t0, 2)
        raise NvidiaCallError("other", "Sarvam network error after %.2fs" % elapsed,
                              elapsed_s=elapsed, model=use_model, jpeg_bytes=info["jpeg_bytes"]) from e
    elapsed = round(time.time() - t0, 2)
    status = resp.status_code
    body = None
    usage: Dict[str, int] = {}
    if status == 200:
        try:
            body = resp.json()
            usage = usage_counts(body.get("usage") or {})
        except Exception:
            body = None
    cost = cost_inr(usage, use_model) if usage else 0.0
    SPEND["cost_inr"] += cost
    LAST_CALL.clear()
    LAST_CALL.update({"model": use_model, "latency_s": elapsed, "status": status,
                      "usage": usage, "cost_inr": round(cost, 6)})
    _log_nvidia("sarvam_http", status=status, elapsed_s=elapsed, model=use_model,
                cost_inr=round(cost, 5), **usage, **info)
    if status in (401, 403):
        raise NvidiaCallError("auth", "Sarvam HTTP %s" % status, status=status,
                              elapsed_s=elapsed, model=use_model, jpeg_bytes=info["jpeg_bytes"])
    if status >= 400 or body is None:
        raise NvidiaCallError("http", "Sarvam HTTP %s" % status, status=status,
                              elapsed_s=elapsed, model=use_model, jpeg_bytes=info["jpeg_bytes"])
    msg = ((body.get("choices") or [{}])[0] or {}).get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        content = "".join((p.get("text") or "") if isinstance(p, dict) else str(p) for p in content)
    if not content:
        raise NvidiaCallError("other", "empty model content", status=status,
                              elapsed_s=elapsed, model=use_model, jpeg_bytes=info["jpeg_bytes"])
    return _parse_json_loose(content), elapsed, content

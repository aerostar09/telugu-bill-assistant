"""Shared NVIDIA extract pipeline: temp=0, small top_p, post-OCR, checks, retry.

At most 2 NVIDIA HTTP calls per bill. If the first post-OCR checks fail, a second
call is made. Keep the passing result, else the one with fewer failures.
Never logs API key values.
"""
from __future__ import annotations

import base64
import io
import os
import time
from typing import Any, Dict, Optional, Tuple

import requests
from PIL import Image

from self_checks import IMPROVED_VISION_PROMPT, run_all_checks, image_guard
from post_ocr import apply_post_ocr_corrections

# Reuse prompt + parse helpers from the app/harness style
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
# Primary + fallback chosen from a 2026-11-12 probe of this key's live catalog.
# Both models think by default. On a real tall thermal slip that burned the
# 3000-token cap (and the 60s Cloud timeout) on reasoning, leaving empty content.
# Always send chat_template_kwargs.enable_thinking=false. With thinking off,
# the primary returned the known 82 / ₹314 / ₹10 DPS fields in ~8s; the fallback
# finished in ~38s (bill total and DPS correct). 90b is deprecated after 16 Nov.
NIM_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
NIM_TIMEOUT = 60  # first attempt; thinking-off primary is ~8s
NIM_FALLBACK_TIMEOUT = 90  # MiniMax thinking-off was ~38s on a real slip
NIM_FALLBACK_MODEL = "minimaxai/minimax-m3.1-flash"
JPEG_QUALITY = 85
MAX_SIDE = 1600
MAX_TOKENS = 1600  # JSON extract; 3000 was all consumed by reasoning traces
TEMPERATURE = 0
TOP_P = 0.1
MAX_CALLS = 2
ENABLE_THINKING = False

SCHEMA_BLOCK = """
Return ONLY a single JSON object (no markdown fences) with exactly these keys.
Use null for any field that is not clearly readable — do NOT guess or invent.
{
  "discom": string|null,
  "usc_no": string|null,
  "category": string|null,
  "contracted_load_kw": number|null,
  "phase": string|null,
  "bill_date": string|null,
  "prev_reading": number|null,
  "present_reading": number|null,
  "units": number|null,
  "days": number|null,
  "energy_charges": number|null,
  "fixed_charges": number|null,
  "customer_charges": number|null,
  "electricity_duty": number|null,
  "interest_on_ed": number|null,
  "surcharge": number|null,
  "trueup_charges": number|null,
  "trueup_units": number|null,
  "fsa_fca": number|null,
  "subsidy": number|null,
  "adjustment": number|null,
  "loss_gain": number|null,
  "bill_amount": number|null,
  "arrears": number|null,
  "total_due": number|null,
  "due_date": string|null,
  "present_reading_date": string|null,
  "prev_reading_date": string|null,
  "average_month_units": number|null,
  "acd_due": number|null,
  "acd_surcharge": number|null,
  "unit_history": [{"year": number, "month": number, "units": number, "estimated": boolean}]|null,
  "is_electricity_bill": boolean,
  "image_quality": "clear"|"cropped"|"crumpled"|"blurry"|"unknown"
}
Ignore handwritten notes scribbled on the form.
""".strip()

VISION_PROMPT = IMPROVED_VISION_PROMPT + "\n\n" + SCHEMA_BLOCK


HISTORY_TABLE_PROMPT = """
This is a screenshot of a TGSPDCL / TGNPDCL / DISCOM consumer-app 'Bill History' table (or similar monthly list).
Return ONLY a single JSON object (no markdown fences):
{"rows": [{"month": "MMM YYYY or YYYY-MM", "units": number|null, "amount": number|null}]}
Rules:
- One row per billing month that is clearly readable.
- units = kWh / consumption for that month; amount = bill amount in rupees if shown.
- Use null for unreadable numbers. Do NOT invent months or guess.
- Ignore names, USC / service numbers, addresses, phone numbers, and payment receipts.
""".strip()


def get_nvidia_api_key():
    """Read NVIDIA_API_KEY from env or Streamlit secrets. Never log the value."""
    for env_name in ("NVIDIA_API_KEY", "nvidia_api_key"):
        val = os.environ.get(env_name)
        if val and str(val).strip():
            return str(val).strip()
    try:
        import streamlit as st
        for key in ("NVIDIA_API_KEY", "nvidia_api_key"):
            try:
                val = st.secrets[key]
            except Exception:
                val = None
            if val and str(val).strip():
                return str(val).strip()
        try:
            block = st.secrets.get("nvidia")  # type: ignore[attr-defined]
        except Exception:
            block = None
        if block:
            val = block.get("NVIDIA_API_KEY") or block.get("api_key") or block.get("nvidia_api_key")
            if val and str(val).strip():
                return str(val).strip()
    except Exception:
        pass
    return None


def nvidia_key_configured() -> bool:
    return bool(get_nvidia_api_key())


def _parse_json_loose(text: str) -> Dict[str, Any]:
    import json, re
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def downscale_jpeg_image(img: Image.Image, max_side: int = MAX_SIDE) -> bytes:
    img = img.convert("RGB")
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    data = buf.getvalue()
    return data



class NvidiaCallError(RuntimeError):
    """Structured NVIDIA failure. Never includes the API key."""

    def __init__(
        self,
        kind: str,
        message: str,
        status: Optional[int] = None,
        elapsed_s: Optional[float] = None,
        model: Optional[str] = None,
        jpeg_bytes: Optional[int] = None,
    ):
        super().__init__(message)
        self.kind = kind  # auth | timeout | http | missing_key | other
        self.status = status
        self.elapsed_s = elapsed_s
        self.model = model
        self.jpeg_bytes = jpeg_bytes

    def user_message(self) -> str:
        return format_nvidia_user_message(self)


def format_nvidia_user_message(exc: BaseException) -> str:
    kind = getattr(exc, "kind", None)
    status = getattr(exc, "status", None)
    if kind is None:
        low = str(exc).lower()
        if "nvidia_api_key missing" in low or "api_key missing" in low:
            kind = "missing_key"
        elif "timeout" in low or "timed out" in low:
            kind = "timeout"
        elif "401" in low or "403" in low:
            kind = "auth"
            if status is None:
                if "401" in low:
                    status = 401
                elif "403" in low:
                    status = 403
        elif "http " in low:
            kind = "http"
    if kind == "missing_key":
        return (
            "NVIDIA_API_KEY లేదు. డెమో మోడ్ (?demo=1) కీ లేకుండా పనిచేస్తుంది. "
            "అసలు ఫోటో చదవడానికి Streamlit secrets లేదా envలో కీ పెట్టండి.\n"
            "API key is not configured. Demo mode works without a key."
        )
    if kind == "auth":
        return (
            "API కీ సమస్య. Streamlit secrets / envలో NVIDIA_API_KEYని సరిచూడండి "
            f"(HTTP {status or '401/403'}).\n"
            f"API key problem (HTTP {status or '401/403'}). Check the key in Streamlit secrets — it may be missing, pasted wrong, or unauthorized."
        )
    if kind == "timeout":
        return "సర్వర్ నెమ్మదిగా ఉంది. దయచేసి కొద్ది సేపు తర్వాత మళ్లీ ప్రయత్నించండి.\nThe vision server timed out. Please try again in a moment."
    if kind == "http":
        return (
            f"NVIDIA సర్వర్ లోపం (HTTP {status}). దయచేసి మళ్లీ ప్రయత్నించండి.\n"
            f"NVIDIA request failed (HTTP {status})."
        )
    # Do not echo raw exception text in the main banner (may contain paths).
    return (
        "బిల్లు చదవడం కాలేదు. దయచేసి మళ్లీ ప్రయత్నించండి.\n"
        "We could not read the bill. Please try again."
    )


def jpeg_payload_info(image_bytes: bytes) -> Dict[str, int]:
    b64_len = (len(image_bytes) + 2) // 3 * 4
    return {
        "jpeg_bytes": len(image_bytes),
        "b64_bytes": b64_len,
        "approx_data_url_bytes": b64_len + 32,
    }


_LOG_DENY = (
    "api_key", "apikey", "access_token", "secret", "authorization",
    "password", "bearer", "nvidia_api_key",
)


def _log_nvidia(event: str, **fields: Any) -> None:
    """Streamlit/Cloud logs. Never includes the API key or response bodies.

    Token *counts* (prompt_tokens, completion_tokens, reasoning_tokens) are OK.
    """
    parts = [f"NVIDIA {event}"]
    for k, v in fields.items():
        if v is None:
            continue
        lk = str(k).lower()
        if lk == "key" or lk.endswith("_key") or any(d in lk for d in _LOG_DENY):
            continue
        parts.append("%s=%s" % (k, v))
    print(" ".join(parts), flush=True)


def _usage_counts(usage: Dict[str, Any]) -> Dict[str, Any]:
    """Numeric token counts only — never raw usage blobs or keys."""
    out: Dict[str, Any] = {}
    for k in ("prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens"):
        v = usage.get(k)
        if isinstance(v, (int, float)):
            out[k] = int(v)
    details = usage.get("completion_tokens_details")
    if isinstance(details, dict) and isinstance(details.get("reasoning_tokens"), (int, float)):
        out["reasoning_tokens"] = int(details["reasoning_tokens"])
    return out


def call_nvidia_once(
    image_bytes: bytes,
    mime: str = "image/jpeg",
    prompt: Optional[str] = None,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Tuple[Dict[str, Any], float, str]:
    key = get_nvidia_api_key()
    if not key:
        raise NvidiaCallError("missing_key", "NVIDIA_API_KEY missing")
    use_model = model or NIM_MODEL
    use_timeout = NIM_TIMEOUT if timeout is None else timeout
    info = jpeg_payload_info(image_bytes)
    data_url = "data:%s;base64,%s" % (mime, base64.b64encode(image_bytes).decode("ascii"))
    payload = {
        "model": use_model,
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        "max_tokens": MAX_TOKENS,
        # Both current models think by default; disable or they burn the token
        # budget on a reasoning trace and return empty content (or time out).
        "chat_template_kwargs": {"enable_thinking": ENABLE_THINKING},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt or VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    }
    headers = {
        "Authorization": "Bearer %s" % key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    t0 = time.time()
    try:
        resp = requests.post(NIM_URL, headers=headers, json=payload, timeout=use_timeout)
    except requests.Timeout as e:
        elapsed = round(time.time() - t0, 2)
        _log_nvidia("timeout", status="timeout", elapsed_s=elapsed, model=use_model, **info)
        raise NvidiaCallError(
            "timeout", "NVIDIA timeout after %.2fs" % elapsed,
            status=None, elapsed_s=elapsed, model=use_model, jpeg_bytes=info["jpeg_bytes"],
        ) from e
    except requests.RequestException as e:
        elapsed = round(time.time() - t0, 2)
        _log_nvidia("network_error", status="error", elapsed_s=elapsed, model=use_model, **info)
        raise NvidiaCallError(
            "other", "NVIDIA network error after %.2fs" % elapsed,
            elapsed_s=elapsed, model=use_model, jpeg_bytes=info["jpeg_bytes"],
        ) from e
    elapsed = round(time.time() - t0, 2)
    usage = {}
    finish_reason = None
    if resp.status_code == 200:
        try:
            _body_peek = resp.json()
            usage = _usage_counts(_body_peek.get("usage") or {})
            finish_reason = ((_body_peek.get("choices") or [{}])[0] or {}).get("finish_reason")
        except Exception:
            _body_peek = None
    else:
        _body_peek = None
    _log_nvidia(
        "http",
        status=resp.status_code,
        elapsed_s=elapsed,
        model=use_model,
        finish_reason=finish_reason,
        **usage,
        **info,
    )
    if resp.status_code in (401, 403):
        raise NvidiaCallError(
            "auth", "NVIDIA HTTP %s" % resp.status_code,
            status=resp.status_code, elapsed_s=elapsed, model=use_model, jpeg_bytes=info["jpeg_bytes"],
        )
    if resp.status_code >= 400:
        raise NvidiaCallError(
            "http", "NVIDIA HTTP %s" % resp.status_code,
            status=resp.status_code, elapsed_s=elapsed, model=use_model, jpeg_bytes=info["jpeg_bytes"],
        )
    body = _body_peek if _body_peek is not None else resp.json()
    content = (body.get("choices") or [{}])[0].get("message", {}).get("content")
    if content is None:
        raise NvidiaCallError(
            "other", "empty model content",
            status=resp.status_code, elapsed_s=elapsed, model=use_model, jpeg_bytes=info["jpeg_bytes"],
        )
    if isinstance(content, list):
        content = "".join((p.get("text") or "") if isinstance(p, dict) else str(p) for p in content)
    return _parse_json_loose(content), elapsed, content


def _evaluate(raw: Dict[str, Any]) -> Dict[str, Any]:
    bill, corrections = apply_post_ocr_corrections(raw)
    guard = image_guard(bill)
    checks = run_all_checks(bill)
    return {
        "extracted_raw": raw,
        "bill": bill,
        "corrections": corrections,
        "guard": guard,
        "checks": checks,
        "failure_count": checks.get("failure_count", 0) if not guard else 99,
        "ok": bool(checks.get("ok")) and not guard,
    }


def extract_bill_pipeline(img: Image.Image) -> Dict[str, Any]:
    """Run extract → post-OCR → checks. Max 2 NVIDIA calls.

    Call 1: primary model, thinking off, 60s timeout, image downscaled to max 1600px JPEG q85.
    Call 2: if the first times out (or 5xx), the faster fallback model; if checks fail,
    a second extract (fallback model to save time).
    """
    jpeg = downscale_jpeg_image(img)
    im = Image.open(io.BytesIO(jpeg))
    info = jpeg_payload_info(jpeg)
    _log_nvidia(
        "payload",
        width=im.size[0],
        height=im.size[1],
        max_side=MAX_SIDE,
        jpeg_quality=JPEG_QUALITY,
        **info,
    )
    attempts = []
    last_err = None
    plan = [
        (1, NIM_MODEL, NIM_TIMEOUT),
        (2, NIM_FALLBACK_MODEL, NIM_FALLBACK_TIMEOUT),
    ]
    for n, model, timeout in plan:
        t0 = time.time()
        try:
            raw, latency, _raw_text = call_nvidia_once(
                jpeg, model=model, timeout=timeout
            )
            ev = _evaluate(raw)
            ev["attempt"] = n
            ev["latency_s"] = latency
            ev["error"] = None
            attempts.append(ev)
            ev["model"] = model
            _log_nvidia(
                "attempt_ok",
                attempt=n,
                model=model,
                ok=ev["ok"],
                failures=ev["failure_count"],
                elapsed_s=latency,
            )
            if ev["ok"]:
                break
        except Exception as e:
            last_err = e
            kind = getattr(e, "kind", None)
            elapsed = getattr(e, "elapsed_s", None) or round(time.time() - t0, 2)
            attempts.append({
                "attempt": n,
                "ok": False,
                "failure_count": 10**6,
                "error": str(e),
                "error_kind": kind,
                "latency_s": elapsed,
                "model": model,
                "bill": None,
                "corrections": [],
                "checks": None,
                "guard": None,
            })
            _log_nvidia(
                "attempt_error",
                attempt=n,
                model=model,
                kind=kind or "other",
                status=getattr(e, "status", None),
                elapsed_s=elapsed,
            )
            # Auth/missing key will not be fixed by a second model.
            if kind in ("auth", "missing_key"):
                break
        if n < MAX_CALLS:
            time.sleep(1.0)

    usable = [a for a in attempts if a.get("bill") is not None]
    if not usable:
        if isinstance(last_err, Exception):
            raise last_err
        raise RuntimeError(last_err or "NVIDIA extract failed")

    passing = [a for a in usable if a.get("ok")]
    if passing:
        kept = passing[0]  # first passing
    else:
        kept = min(usable, key=lambda a: a.get("failure_count", 99))

    return {
        "bill": kept["bill"],
        "corrections": kept.get("corrections") or [],
        "checks": kept["checks"],
        "guard": kept.get("guard"),
        "kept_attempt": kept["attempt"],
        "kept_model": kept.get("model"),
        "attempts_used": len(attempts),
        "attempts": [
            {
                "attempt": a["attempt"],
                "ok": a.get("ok"),
                "model": a.get("model"),
                "failure_count": a.get("failure_count"),
                "fail_keys": (a.get("checks") or {}).get("fail_keys") if a.get("checks") else None,
                "latency_s": a.get("latency_s"),
                "error": a.get("error"),
                "kept": a["attempt"] == kept["attempt"],
            }
            for a in attempts
        ],
        "total_latency_s": round(sum(a.get("latency_s") or 0 for a in attempts), 2),
        "extracted_raw": kept.get("extracted_raw"),
    }


# -----------------------------------------------------------------------------
# On-device hash cache (speed). Not a cloud store; photos themselves are not saved.
# -----------------------------------------------------------------------------
import hashlib
import json
from pathlib import Path as _Path

def get_cache_dir() -> _Path:
    """Prefer a writable directory. Streamlit Cloud can reject the app dir; /tmp works."""
    env = os.environ.get("TISC_EXTRACT_CACHE")
    candidates = []
    if env:
        candidates.append(_Path(env))
    candidates.extend([
        _Path(__file__).resolve().parent / ".extract_cache",
        _Path("/tmp/tisc_extract_cache"),
    ])
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write_probe"
            probe.write_text("ok")
            probe.unlink()
            return d
        except Exception:
            continue
    return candidates[-1]


# Back-compat alias (tests / callers may read the name). Resolved lazily.
def _cache_dir() -> _Path:
    return get_cache_dir()


_MEMORY_CACHE: Dict[str, Any] = {}


def _cache_key(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def load_cached_extract(image_bytes: bytes):
    digest = _cache_key(image_bytes)
    hit = _MEMORY_CACHE.get(digest)
    if hit:
        return dict(hit)
    path = get_cache_dir() / (digest + ".json")
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
        _MEMORY_CACHE[digest] = data
        return dict(data)
    except Exception:
        return None


def save_cached_extract(image_bytes: bytes, result: Dict[str, Any]) -> bool:
    """Store a successful extract (no raw image bytes). Returns whether disk write worked."""
    if not result or not result.get("bill"):
        return False
    slim = dict(result)
    slim.pop("extracted_raw", None)
    digest = _cache_key(image_bytes)
    _MEMORY_CACHE[digest] = slim
    try:
        d = get_cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / (digest + ".json")
        path.write_text(json.dumps(slim, ensure_ascii=False, default=str))
        _log_nvidia("cache_write", ok=True, sha16=digest[:16])
        return True
    except Exception:
        _log_nvidia("cache_write", ok=False, sha16=digest[:16])
        return False


def extract_bill_pipeline_cached(img: Image.Image, use_cache: bool = True) -> Dict[str, Any]:
    jpeg = downscale_jpeg_image(img)
    if use_cache:
        hit = load_cached_extract(jpeg)
        if hit:
            hit["from_cache"] = True
            _log_nvidia("cache_hit", sha16=_cache_key(jpeg)[:16])
            return hit
    result = extract_bill_pipeline(img)
    result["from_cache"] = False
    if use_cache and result.get("bill"):
        save_cached_extract(jpeg, result)
    return result



def extract_history_table_pipeline(img: Image.Image, use_cache: bool = True) -> Dict[str, Any]:
    """Extract month/units/amount rows from a DISCOM app Bill History screenshot."""
    from history_input import parse_history_table_payload

    jpeg = downscale_jpeg_image(img)
    cache_name = "hist_" + _cache_key(jpeg)
    if use_cache:
        path = get_cache_dir() / (cache_name + ".json")
        if path.is_file():
            try:
                hit = json.loads(path.read_text())
                hit["from_cache"] = True
                return hit
            except Exception:
                pass
    raw, latency, _content = call_nvidia_once(jpeg, prompt=HISTORY_TABLE_PROMPT)
    rows = parse_history_table_payload(raw)
    result = {
        "rows": rows,
        "raw": raw,
        "latency_s": latency,
        "from_cache": False,
    }
    if use_cache:
        try:
            d = get_cache_dir()
            d.mkdir(parents=True, exist_ok=True)
            slim = {"rows": rows, "latency_s": latency}
            (d / (cache_name + ".json")).write_text(
                json.dumps(slim, ensure_ascii=False, default=str)
            )
        except Exception:
            pass
    return result

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
NIM_MODEL = "meta/llama-3.2-90b-vision-instruct"
NIM_TIMEOUT = 45
MAX_SIDE = 1600
TEMPERATURE = 0
TOP_P = 0.1
MAX_CALLS = 2

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
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()


def call_nvidia_once(image_bytes: bytes, mime: str = "image/jpeg", prompt: Optional[str] = None) -> Tuple[Dict[str, Any], float, str]:
    key = get_nvidia_api_key()
    if not key:
        raise RuntimeError("NVIDIA_API_KEY missing")
    data_url = "data:%s;base64,%s" % (mime, base64.b64encode(image_bytes).decode("ascii"))
    payload = {
        "model": NIM_MODEL,
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        "max_tokens": 3000,
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
    resp = requests.post(NIM_URL, headers=headers, json=payload, timeout=NIM_TIMEOUT)
    latency = round(time.time() - t0, 2)
    if resp.status_code >= 400:
        raise RuntimeError("HTTP %s: %s" % (resp.status_code, resp.text[:300]))
    body = resp.json()
    content = (body.get("choices") or [{}])[0].get("message", {}).get("content")
    if content is None:
        raise RuntimeError("empty model content")
    if isinstance(content, list):
        content = "".join((p.get("text") or "") if isinstance(p, dict) else str(p) for p in content)
    return _parse_json_loose(content), latency, content


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
    """Run extract → post-OCR → checks, retry once if checks fail. Max 2 NVIDIA calls."""
    jpeg = downscale_jpeg_image(img)
    attempts = []
    last_err = None
    for n in (1, 2):
        t0 = time.time()
        try:
            raw, latency, _raw_text = call_nvidia_once(jpeg)
            ev = _evaluate(raw)
            ev["attempt"] = n
            ev["latency_s"] = latency
            ev["error"] = None
            attempts.append(ev)
            print(
                "NVIDIA attempt %s: ok=%s failures=%s fail_keys=%s latency=%ss"
                % (n, ev["ok"], ev["failure_count"], ev["checks"].get("fail_keys"), latency),
                flush=True,
            )
            if ev["ok"]:
                break
        except Exception as e:
            last_err = str(e)
            attempts.append({
                "attempt": n,
                "ok": False,
                "failure_count": 10**6,
                "error": last_err,
                "latency_s": round(time.time() - t0, 2),
                "bill": None,
                "corrections": [],
                "checks": None,
                "guard": None,
            })
            print("NVIDIA attempt %s: ERROR: %s" % (n, last_err), flush=True)
        if n < MAX_CALLS:
            time.sleep(1.0)

    usable = [a for a in attempts if a.get("bill") is not None]
    if not usable:
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
        "attempts_used": len(attempts),
        "attempts": [
            {
                "attempt": a["attempt"],
                "ok": a.get("ok"),
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

CACHE_DIR = _Path(__file__).resolve().parent / ".extract_cache"


def _cache_key(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def load_cached_extract(image_bytes: bytes):
    path = CACHE_DIR / (_cache_key(image_bytes) + ".json")
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def save_cached_extract(image_bytes: bytes, result: Dict[str, Any]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Do not persist raw image bytes. Drop bulky raw text if huge.
        slim = dict(result)
        slim.pop("extracted_raw", None)
        path = CACHE_DIR / (_cache_key(image_bytes) + ".json")
        path.write_text(json.dumps(slim, ensure_ascii=False, default=str))
    except Exception:
        pass


def extract_bill_pipeline_cached(img: Image.Image, use_cache: bool = True) -> Dict[str, Any]:
    jpeg = downscale_jpeg_image(img)
    if use_cache:
        hit = load_cached_extract(jpeg)
        if hit:
            hit["from_cache"] = True
            return hit
    result = extract_bill_pipeline(img)
    result["from_cache"] = False
    if use_cache:
        save_cached_extract(jpeg, result)
    return result



def extract_history_table_pipeline(img: Image.Image, use_cache: bool = True) -> Dict[str, Any]:
    """Extract month/units/amount rows from a DISCOM app Bill History screenshot."""
    from history_input import parse_history_table_payload

    jpeg = downscale_jpeg_image(img)
    cache_name = "hist_" + _cache_key(jpeg)
    if use_cache:
        path = CACHE_DIR / (cache_name + ".json")
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
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            slim = {"rows": rows, "latency_s": latency}
            (CACHE_DIR / (cache_name + ".json")).write_text(
                json.dumps(slim, ensure_ascii=False, default=str)
            )
        except Exception:
            pass
    return result

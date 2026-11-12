"""Main-screen summary helpers: short voice, top reasons, confidence pill.

Pure functions, no Streamlit. Only data-supported reasons; no invented numbers.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from post_ocr import line_sum, printed_bill_amount
from terms import rupees_spoken, word_count, TARIFF_VERSION

# Minimum rupee move to mention a reason on the main screen / in voice.
_MIN_REASON_RS = 1.0

_JUMP_REASONS = (
    (
        "extra_units_old_rate",
        "అదనపు యూనిట్లు",
        "యూనిట్లు పెరగడం వల్ల బిల్లు పెరిగింది.",
        "యూనిట్లు తగ్గడం వల్ల బిల్లు తగ్గింది.",
    ),
    (
        "category_change",
        "స్లాబ్ / కేటగిరీ",
        "కేటగిరీ లేదా స్లాబ్ మారినందున ఛార్జీ పెరిగింది.",
        "కేటగిరీ లేదా స్లాబ్ మారినందున ఛార్జీ తగ్గింది.",
    ),
    (
        "trueup_added",
        "ట్రూ-అప్",
        "ట్రూ-అప్ (పాత పవర్ ఖర్చు) ఈ బిల్లులో చేరింది.",
        "ట్రూ-అప్ ఈ బిల్లులో తగ్గింది.",
    ),
    (
        "other_changes",
        "ఇతర ఛార్జీలు",
        "ఫిక్స్‌డ్, కస్టమర్ ఛార్జీ లేదా పన్ను మారింది.",
        "ఫిక్స్‌డ్, కస్టమర్ ఛార్జీ లేదా పన్ను మారింది.",
    ),
)


def _amt(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def top_reasons(
    jump: Optional[Dict[str, Any]] = None,
    late: Optional[Dict[str, Any]] = None,
    bill: Optional[Dict[str, Any]] = None,
    max_n: int = 3,
) -> List[Dict[str, Any]]:
    """Up to `max_n` data-supported reasons, largest absolute rupee first.

    Residual is omitted (it is a leftover, not a named charge). Late-reading
    extra is included only when the bill is actually late and the amount ≥ ₹1.
    """
    cands: List[Dict[str, Any]] = []
    if jump:
        for key, title, voice_up, voice_down in _JUMP_REASONS:
            amt = _amt(jump.get(key))
            if amt is None or abs(amt) < _MIN_REASON_RS:
                continue
            cands.append({
                "key": key,
                "title_te": title,
                "amount": round(amt, 2),
                "voice_te": voice_up if amt > 0 else voice_down,
            })
    if late and late.get("is_late"):
        extra = _amt(late.get("extra_rupees"))
        if extra is not None and abs(extra) >= _MIN_REASON_RS:
            days = late.get("days")
            day_bit = f"{int(days)} రోజుల" if days is not None else "ఆలస్య"
            cands.append({
                "key": "late_reading",
                "title_te": "ఆలస్య రీడింగ్",
                "amount": round(extra, 2),
                "voice_te": f"మీటర్ రీడింగ్ {day_bit}కు జరిగి స్లాబ్ పుష్ అయ్యింది.",
            })
    # Genuine printed DPS, only when present and nonzero
    if bill is not None:
        sur = _amt(bill.get("surcharge"))
        if sur is not None and abs(sur) >= _MIN_REASON_RS:
            cands.append({
                "key": "surcharge",
                "title_te": "ఆలస్య రుసుము",
                "amount": round(sur, 2),
                "voice_te": "ఆలస్య చెల్లింపు రుసుము ఈ బిల్లులో ఉంది.",
            })
    cands.sort(key=lambda r: abs(r["amount"]), reverse=True)
    return cands[:max_n]


def confidence_level(
    checks: Optional[Dict[str, Any]] = None,
    corrections: Optional[List[str]] = None,
    image_quality: Optional[str] = None,
) -> Dict[str, str]:
    """green / yellow / red pill for the hero card."""
    checks = checks or {}
    ok = checks.get("ok")
    dirty = bool(corrections)
    q = (image_quality or "").lower()
    messy_photo = q in {"cropped", "crumpled", "blurry"}
    if ok is False:
        return {"level": "red", "label_te": "లెక్కల్లో తేడా ఉంది", "css": "badge-red"}
    if ok and (dirty or messy_photo):
        return {"level": "yellow", "label_te": "కొన్ని అంకెలు సరిచేశాం", "css": "badge-yellow"}
    if ok:
        return {"level": "green", "label_te": "స్పష్టంగా చదివాం", "css": "badge-green"}
    return {"level": "yellow", "label_te": "ఇంకా సరిచూడలేదు", "css": "badge-yellow"}


def printed_vs_calculated(bill: Dict[str, Any]) -> Dict[str, Any]:
    printed = printed_bill_amount(bill)
    calc = line_sum(bill)
    delta = None
    if printed is not None:
        delta = round(calc - printed, 2)
    return {
        "printed": printed,
        "calculated": calc,
        "delta": delta,
        "matches": printed is not None and abs(delta or 99) <= 1.0,
        "tariff_version": TARIFF_VERSION,
    }


VOICE_MAX_WORDS = 60


def build_voice_summary(
    bill: Dict[str, Any],
    *,
    reasons: Optional[List[Dict[str, Any]]] = None,
    forecast_range: Optional[Dict[str, Any]] = None,
) -> str:
    """15–25s Telugu script: amount, units, one main reason, next-bill range."""
    parts: List[str] = []
    total = _amt(bill.get("bill_amount"))
    if total is None:
        total = _amt(bill.get("total_due"))
    if total is not None:
        parts.append(f"ఈ నెల బిల్లు {rupees_spoken(total)}.")
    units = _amt(bill.get("units"))
    if units is not None:
        parts.append(f"{int(round(units))} యూనిట్లు వాడారు.")
    if reasons:
        parts.append(reasons[0]["voice_te"])
    if forecast_range and forecast_range.get("low") is not None:
        lo = int(forecast_range["low"])
        hi = int(forecast_range["high"])
        parts.append(f"వచ్చే నెల అంచనా {lo} నుంచి {hi} రూపాయలు.")
    due = bill.get("due_date")
    if due:
        parts.append(f"చెల్లించాల్సిన తేదీ {due}.")
    parts.append("లెక్క సరిపోయింది.")
    text = " ".join(p.strip() for p in parts if p and p.strip())
    # Hard cap so a future reason cannot inflate the clip.
    words = text.split()
    if len(words) > VOICE_MAX_WORDS:
        text = " ".join(words[:VOICE_MAX_WORDS])
    return text


def voice_word_count(text: str) -> int:
    return word_count(text)

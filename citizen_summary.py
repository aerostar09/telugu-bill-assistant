"""Main-screen summary helpers: short voice, top reasons, confidence pill.

Pure functions, no Streamlit. Only data-supported reasons; no invented numbers.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from post_ocr import line_sum, printed_bill_amount
from terms import rupees_spoken, word_count, format_due_date_display, TARIFF_VERSION

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
        "ట్రూ-అప్ (పాత సంవత్సరం సర్దుబాటు)",
        "ట్రూ-అప్ (పాత సంవత్సరం సర్దుబాటు) ఈ బిల్లులో చేరింది.",
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


def trueup_explain_te(bill: Optional[Dict[str, Any]] = None) -> str:
    """Short distinct true-up explanation (never repeats the title)."""
    bill = bill or {}
    tu_u = _amt(bill.get("trueup_units"))
    from tariff import normalize_trueup_items
    items = [i for i in normalize_trueup_items(bill) if i.get("units") and i.get("rate")]
    if tu_u is not None and tu_u > 0 and items:
        return "; ".join(
            f"{i['fy'] or '2022-23'} బాకీ, {int(round(i['units']))} యూనిట్లు × {int(round(i['rate'] * 100))} పైసలు"
            for i in items
        )
    return "పాత సంవత్సరం పవర్ ఖర్చు సర్దుబాటు"


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
    # Current-bill true-up (even when there is no previous bill / jump).
    # Skip if the jump already contributed the same rupees.
    if bill is not None:
        tu = _amt(bill.get("trueup_charges"))
        if tu is not None and abs(tu) >= _MIN_REASON_RS:
            already = any(c["key"] == "trueup_added" for c in cands)
            if not already:
                cands.append({
                    "key": "trueup_charges",
                    "title_te": "ట్రూ-అప్ (పాత సంవత్సరం సర్దుబాటు)",
                    "amount": round(tu, 2),
                    "voice_te": trueup_explain_te(bill),
                })
            else:
                # Rename the jump reason to the clearer label + a distinct explanation.
                for c in cands:
                    if c["key"] == "trueup_added":
                        c["title_te"] = "ట్రూ-అప్ (పాత సంవత్సరం సర్దుబాటు)"
                        c["voice_te"] = trueup_explain_te(bill)
        # Genuine DPS only when it is present, nonzero, and distinct from true-up.
        sur = _amt(bill.get("surcharge"))
        if sur is not None and abs(sur) >= _MIN_REASON_RS:
            same_as_trueup = tu is not None and abs(abs(sur) - abs(tu)) <= 0.05
            # A 30p/50p multiple that is not a typical ₹10/₹25 DPS is a misfiled true-up.
            looks_tu = False
            try:
                from thermal_repair import looks_like_trueup
                looks_tu = looks_like_trueup(sur, bill.get("trueup_units"))
            except Exception:
                looks_tu = False
            if not same_as_trueup and not looks_tu:
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
    """Hero-card pill: green when the printed total matches, red on a genuine mismatch.

    Repair notes and messy-photo flags do not get a yellow hero pill — those
    belong in the లెక్క tab / technical expander only.
    """
    checks = checks or {}
    ok = checks.get("consumer_ok")
    if ok is None:
        ok = checks.get("ok")
    if ok is False:
        return {
            "level": "red",
            "label_te": "లెక్కల్లో తేడా ఉంది",
            "css": "badge-red",
            "show_on_hero": True,
        }
    if ok:
        return {
            "level": "green",
            "label_te": "స్పష్టంగా చదివాం",
            "css": "badge-green",
            "show_on_hero": True,
        }
    return {"level": "hidden", "label_te": "", "css": "", "show_on_hero": False}


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
    gj: Optional[Dict[str, Any]] = None,
) -> str:
    """Short Telugu voice script: payable amount, units, due date only.

    On-screen copy (true-up, late reading, why-it-changed, forecast,
    scheme-without-subsidy) is unchanged. Callers may still pass reasons /
    forecast_range; they are ignored here. A printed GJS Subsidy line or
    Gruha Jyothi free-mode payable is spoken as the net (₹0 on a zero bill),
    never the gross Bill Amount.
    """
    from bill_lines import payable_amount
    parts: List[str] = []
    pay = payable_amount(bill)
    if (gj or {}).get("mode") == "free" and (gj or {}).get("payable") is not None:
        pay = (gj or {}).get("payable")
    if pay is None:
        pay = _amt(bill.get("bill_amount"))
        if pay is None:
            pay = _amt(bill.get("total_due"))
    if pay is not None:
        parts.append(f"ఈ నెల బిల్లు {rupees_spoken(pay)}.")
    units = _amt(bill.get("units"))
    if units is not None:
        parts.append(f"{int(round(units))} యూనిట్లు వాడారు.")
    due = format_due_date_display(bill.get("due_date"))
    if due:
        parts.append(f"చెల్లించాల్సిన తేదీ {due}.")
    else:
        parts.append("చెల్లించాల్సిన తేదీ బిల్లులో కనిపించలేదు, బిల్లు చూసుకోండి.")
    text = " ".join(p.strip() for p in parts if p and p.strip())
    words = text.split()
    if len(words) > VOICE_MAX_WORDS:
        text = " ".join(words[:VOICE_MAX_WORDS])
    return text


def voice_word_count(text: str) -> int:
    return word_count(text)

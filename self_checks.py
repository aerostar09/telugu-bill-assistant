"""Patched helpers for Streamlit app.py (TISC #13 demo).
Copy these into / alongside app.py; do not invent tariff slabs for the estimate.
"""
from __future__ import annotations
from typing import Any, Dict, Optional

IMPROVED_VISION_PROMPT = """
You are an expert OCR assistant for Telangana electricity bills (TSSPDCL/TGSPDCL and TSNPDCL/TGNPDCL).
Inspect the image carefully. Return ONLY JSON matching the schema.
Rules:
- Convert currency/units to numbers (strip ₹, Rs., commas).
- If a field is not visible or unreadable, set it to null. Do NOT guess.
- trueup_charges = PP TRUEUP / True-up line (often FY 2022-23); trueup_units = units on that line.
- present_reading_date / prev_reading_date = Date column on the Present / Previous reading rows (not the bill date).
- unit_history = the 12–13 month consumption table or chart if printed (year, month, units, estimated=true if billed on average). null if not visible — do NOT invent months.
- average_month_units = 'Average Month Units' if printed.
- acd_due / acd_surcharge = ACD Due or ACD Surcharge line if printed (0 is valid).
- loss_gain = Loss/Gain rounding line (can be negative).
- surcharge = Delayed Payment Surcharge / DPS only (NOT FSA/FCA).
- fsa_fca = Fuel Surcharge / FCA only.
- is_electricity_bill=false if this is not a TG electricity bill photo.
- image_quality one of: clear, cropped, crumpled, blurry, unknown.
""".strip()

IMPROVED_TELUGU_PROMPT = """
You are a friendly Telangana electricity guide (మీ విద్యుత్ బిల్లు సహాయకుడు).
Given ONLY the JSON below (no image), write 5–6 short spoken-Telugu sentences.
Fixed glossary:
- true-up / PP TRUEUP = "2022-23 లో DISCOM కి ఎక్కువైన పవర్ కాస్ట్, ఇప్పుడు కొంచెం కొంచెం వసూలు చేస్తున్నారు"
- customer charges = "నెలవారీ సర్వీస్ ఫీ"
- electricity duty = "ప్రభుత్వానికి పన్ను"
- loss/gain = "రౌండింగ్ సర్దుబాటు"
- FSA/FCA = "ఇంధన ధర సర్దుబాటు"
Do not invent numbers. If a field is null, say "కనిపించలేదు".
End with ONE practical tip.
JSON:
{bill_json}
""".strip()

# Fields the demo must extract (nullable). Use with google-genai response_schema.
BILL_SCHEMA_KEYS = [
    "discom", "usc_no", "category", "contracted_load_kw", "phase", "bill_date",
    "prev_reading", "present_reading", "units", "days",
    "energy_charges", "fixed_charges", "customer_charges", "electricity_duty",
    "interest_on_ed", "surcharge", "trueup_charges", "trueup_units",
    "fsa_fca", "subsidy", "adjustment", "loss_gain",
    "bill_amount", "arrears", "total_due", "due_date",
    "present_reading_date", "prev_reading_date", "average_month_units",
    "acd_due", "acd_surcharge", "unit_history",
    "is_electricity_bill", "image_quality",
]


def run_self_checks(b: Dict[str, Any]) -> Dict[str, Any]:
    units_eq_delta = None
    if b.get("prev_reading") is not None and b.get("present_reading") is not None and b.get("units") is not None:
        units_eq_delta = (b["present_reading"] - b["prev_reading"]) == b["units"]

    parts = [
        b.get("energy_charges") or 0,
        b.get("fixed_charges") or 0,
        b.get("customer_charges") or 0,
        b.get("electricity_duty") or 0,
        b.get("interest_on_ed") or 0,
        b.get("surcharge") or 0,
        b.get("trueup_charges") or 0,
        b.get("fsa_fca") or 0,
        b.get("adjustment") or 0,
        b.get("loss_gain") or 0,
    ]
    subsidy = b.get("subsidy") or 0
    sum_calc = round(sum(parts) - subsidy, 2)
    sum_eq_bill = None
    if b.get("bill_amount") is not None:
        sum_eq_bill = abs(sum_calc - b["bill_amount"]) <= 1.0

    trueup_eq_30p = None
    if b.get("trueup_units") is not None and b.get("trueup_charges") is not None:
        trueup_eq_30p = abs(b["trueup_charges"] - b["trueup_units"] * 0.30) <= 0.05

    failures = [v for v in (units_eq_delta, sum_eq_bill, trueup_eq_30p) if v is False]
    ok = len(failures) == 0
    return {
        "units_eq_delta": units_eq_delta,
        "sum_calc": sum_calc if b.get("bill_amount") is not None else None,
        "sum_eq_bill": sum_eq_bill,
        "trueup_eq_30p": trueup_eq_30p,
        "ok": ok,
        "message_te": None if ok else "మీ బిల్లు లో ఒక్క నంబర్ మ్యాచ్ అవ్వట్లేదు, CSC/1912 కి కాల్ చేయండి.",
    }


def estimate_next_bill_from_actual(b: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Anchana from the bill itself — do NOT use hardcoded slabs for the demo estimate."""
    units, days, energy = b.get("units"), b.get("days"), b.get("energy_charges")
    if not units or not days or days <= 0 or energy is None or units <= 0:
        return None
    est_units = (units / days) * 30
    epu = energy / units
    est_energy = round(est_units * epu, 2)
    other = (b.get("fixed_charges") or 0) + (b.get("customer_charges") or 0) + (b.get("electricity_duty") or 0)
    return {
        "est_units_30d": round(est_units, 1),
        "est_energy": est_energy,
        "est_total_rough": round(est_energy + other, 2),
        "note": "anchana; excludes true-up/FSA/surcharge; not an official tariff quote",
    }


def image_guard(b: Dict[str, Any]) -> Optional[str]:
    if b.get("is_electricity_bill") is False:
        return "ఇది తెలంగాణ కరెంట్ బిల్లు లా లేదు. ఇంకో క్లియర్ ఫోటో పంపండి."
    if b.get("image_quality") in ("blurry",):
        return "ఫోటో అస్పష్టంగా ఉంది. ఇంకో క్లియర్ ఫోటో పంపండి."
    return None


# Typical TG domestic customer-charge amounts (TSERC-style bands, plus common printed values).
TYPICAL_CUSTOMER_CHARGES = (40, 55, 65, 70, 80, 90, 100, 120, 140, 160)


def _n(v):
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def run_label_shift_checks(b: Dict[str, Any]) -> Dict[str, Any]:
    """Detect swapped/shifted charge lines. A False value is a check failure (triggers retry)."""
    units = _n(b.get("units"))
    cust = _n(b.get("customer_charges"))
    ed = _n(b.get("electricity_duty"))
    energy = _n(b.get("energy_charges"))
    fixed = _n(b.get("fixed_charges"))

    customer_typical = None
    if cust is not None:
        customer_typical = any(abs(cust - c) <= 0.05 for c in TYPICAL_CUSTOMER_CHARGES)

    ed_vs_units = None
    if units is not None and units > 0 and ed is not None:
        expected = units * 0.06
        ed_vs_units = abs(ed - expected) <= (0.50 * expected)

    energy_gt_fixed = None
    if units is not None and units > 50 and energy is not None and fixed is not None:
        energy_gt_fixed = energy > fixed

    return {
        "customer_typical": customer_typical,
        "ed_vs_units": ed_vs_units,
        "energy_gt_fixed": energy_gt_fixed,
    }


def run_all_checks(b: Dict[str, Any]) -> Dict[str, Any]:
    """Self-checks + label-shift sanity. failure_count drives extract retry selection."""
    sc = run_self_checks(b)
    ls = run_label_shift_checks(b)
    fail_keys = []
    for k in ("units_eq_delta", "sum_eq_bill", "trueup_eq_30p"):
        if sc.get(k) is False:
            fail_keys.append(k)
    for k in ("customer_typical", "ed_vs_units", "energy_gt_fixed"):
        if ls.get(k) is False:
            fail_keys.append(k)
    ok = len(fail_keys) == 0
    out = dict(sc)
    out.update(ls)
    out["ok"] = ok
    out["fail_keys"] = fail_keys
    out["failure_count"] = len(fail_keys)
    out["message_te"] = (
        None if ok else "మీ బిల్లు లో ఒక్క నంబర్ మ్యాచ్ అవ్వట్లేదు, CSC/1912 కి కాల్ చేయండి."
    )
    return out



def check_jump_sum(prev_bill: Dict[str, Any], curr_bill: Dict[str, Any], pro_rate: bool = False) -> Dict[str, Any]:
    """Self-check: jump_breakdown components + residual must equal the bill difference."""
    from tariff import jump_breakdown, check_jump_breakdown
    br = jump_breakdown(prev_bill, curr_bill, pro_rate=pro_rate)
    out = check_jump_breakdown(br)
    out["breakdown"] = br
    return out

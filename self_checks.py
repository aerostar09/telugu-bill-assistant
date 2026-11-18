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
- Read each printed charge line independently. Never copy one line's amount onto a different line.
- The standard TGSPDCL 'LT-ELECTRICITY BILL-CUM NOTICE' thermal slip prints charge lines in this EXACT order. Read each line independently. Never copy one line's amount onto a different line, and never skip a 0.00 line by sliding the next amount up.
  1) Energy Charges
  2) Fixed Charges
  3) Customer Charges
  4) Electricity Duty
  5) Interest on ED
  6) Surcharge  (Delayed Payment Surcharge / DPS only. If the line is 0.00, surcharge is 0. Do NOT copy PP TRUEUP into surcharge.)
  7) PP TRUEUP Charges  (printed as e.g. "PP TRUEUP Charges 28.80" then "FY-2022-23 Units 96 @30P"). Put EACH printed true-up line in trueup_items as {"fy": "2022-23" or "2023-24", "units": the units printed on that line, "rate_paise": the printed @ paise, "amount": that line's amount}. A bill may print one line or two (one per FY). trueup_charges = sum of the amounts; trueup_units = sum of the printed units. These units are NOT this month's consumption. If no true-up line is printed, use null.
  8) FSA/FCA Charges
  9) Subsidy
  10) Adjustment
  11) Interest on CD
  12) Loss/Gain  (include a negative sign, e.g. -0.24)
  13) Bill Amount
  Gruha Jyothi bills only (header "Gruha Jyothi '0' Bill"): right after Bill Amount they print
    "GJS Subsidy -602.00" and "Net Bill Amount 0.00". GJS Subsidy is the Gruha Jyothi free-power scheme line and is
    DIFFERENT from the plain "Subsidy" line in the list above (that one is often 0.00). Put the GJS amount in gjs_subsidy
    as a POSITIVE number (e.g. 602), Net Bill Amount in net_bill_amount, and NEVER copy the GJS amount into subsidy.
    Keep bill_amount = the printed Bill Amount (before GJS), not the net. gj_zero_bill_header = true only if the
    header "Gruha Jyothi '0' Bill" is printed. If these lines are absent, use null (header: false).
  Then: Arrears as on, Arrears after, ACD Due, Total Due, Due Date, Disc Date, Last Paid Dt.
- Header: Cat, Contracted Load, Present/Previous readings + their dates, Units, Days, Recorded MD.
- present_reading_date / prev_reading_date = Date column on the Present / Previous reading rows (not the bill date).
- unit_history = the 12–13 month consumption table or chart if printed. null if not visible — do NOT invent months.
- average_month_units = 'Average Month Units' if printed.
- acd_due / acd_surcharge = ACD Due or ACD Surcharge line if printed (0 is valid).
- payable = Total Due when arrears > 0; otherwise Bill Amount.
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
SCHEMA_BLOCK = """
Return ONLY a single JSON object (no markdown fences) with exactly these keys.
Use null for any field that is not clearly readable — do NOT guess or invent.
{
  "discom": string|null,
  "category": string|null,
  "contracted_load_kw": number|null,
  "phase": string|null,
  "bill_date": string|null,
  "prev_reading": number|null,
  "present_reading": number|null,
  "prev_reading_date": string|null,
  "present_reading_date": string|null,
  "units": number|null,
  "days": number|null,
  "recorded_md": number|null,
  "energy_charges": number|null,
  "fixed_charges": number|null,
  "customer_charges": number|null,
  "electricity_duty": number|null,
  "interest_on_ed": number|null,
  "surcharge": number|null,
  "trueup_charges": number|null,
  "trueup_units": number|null,
  "trueup_items": [{"fy": string, "units": number|null, "rate_paise": number|null, "amount": number|null}]|null,
  "fsa_fca": number|null,
  "subsidy": number|null,
  "adjustment": number|null,
  "interest_on_cd": number|null,
  "loss_gain": number|null,
  "bill_amount": number|null,
  "gjs_subsidy": number|null,
  "net_bill_amount": number|null,
  "gj_zero_bill_header": boolean,
  "arrears_as_on": number|null,
  "arrears_after": number|null,
  "arrears": number|null,
  "acd_due": number|null,
  "acd_surcharge": number|null,
  "total_due": number|null,
  "due_date": string|null,
  "disc_date": string|null,
  "last_paid_date": string|null,
  "average_month_units": number|null,
  "unit_history": [{"year": number, "month": number, "units": number, "estimated": boolean}]|null,
  "is_electricity_bill": boolean,
  "image_quality": "clear"|"cropped"|"crumpled"|"blurry"|"unknown"
}
Ignore handwritten notes scribbled on the form.
""".strip()


BILL_SCHEMA_KEYS = [
    "discom", "category", "contracted_load_kw", "phase", "bill_date",
    "prev_reading", "present_reading", "prev_reading_date", "present_reading_date",
    "units", "days", "recorded_md",
    "energy_charges", "fixed_charges", "customer_charges", "electricity_duty",
    "interest_on_ed", "surcharge", "trueup_charges", "trueup_units", "trueup_items",
    "fsa_fca", "subsidy", "adjustment", "interest_on_cd", "loss_gain",
    "bill_amount", "gjs_subsidy", "net_bill_amount", "gj_zero_bill_header",
    "arrears_as_on", "arrears_after", "arrears",
    "acd_due", "acd_surcharge", "total_due",
    "due_date", "disc_date", "last_paid_date",
    "average_month_units", "unit_history",
    "is_electricity_bill", "image_quality",
]


def gjs_net_check(b: Dict[str, Any]) -> Optional[bool]:
    """Gruha Jyothi slip: Bill Amount − |GJS Subsidy| == Net Bill Amount (±₹1).

    None when there is no printed GJS line or one of the numbers is missing.
    The charge-line sum is checked separately against Bill Amount (gross).
    """
    gjs = _n(b.get("gjs_subsidy"))
    bill = _n(b.get("bill_amount"))
    net = _n(b.get("net_bill_amount"))
    if gjs is None or abs(gjs) < 0.005 or bill is None or net is None:
        return None
    return abs((bill - abs(gjs)) - net) <= 1.0


def run_self_checks(b: Dict[str, Any]) -> Dict[str, Any]:
    units_eq_delta = None
    if b.get("prev_reading") is not None and b.get("present_reading") is not None and b.get("units") is not None:
        units_eq_delta = (b["present_reading"] - b["prev_reading"]) == b["units"]

    from post_ocr import line_sum, printed_bill_amount
    sum_calc = line_sum(b)
    sum_eq_bill = None
    printed = b.get("bill_amount")
    if printed is None:
        printed = printed_bill_amount(b)
    if printed is not None:
        sum_eq_bill = abs(sum_calc - float(printed)) <= 1.0

    # Each printed true-up line: printed FY quantum × the rate allowed for the
    # bill date (Nov 2026 → 30p, Dec 2026+ → 50p, unknown date → either).
    from tariff import normalize_trueup_items
    trueup_eq_rate = None
    tu_items = [i for i in normalize_trueup_items(b)
                if i.get("units") is not None and i.get("amount") is not None]
    if tu_items:
        trueup_eq_rate = all(i["valid"] for i in tu_items)

    gjs_net_ok = gjs_net_check(b)

    failures = [v for v in (units_eq_delta, sum_eq_bill, trueup_eq_rate, gjs_net_ok) if v is False]
    ok = len(failures) == 0
    consumer_ok = sum_eq_bill is True and gjs_net_ok is not False
    return {
        "units_eq_delta": units_eq_delta,
        "sum_calc": sum_calc if b.get("bill_amount") is not None else None,
        "sum_eq_bill": sum_eq_bill,
        "trueup_eq_rate": trueup_eq_rate,
        "gjs_net_ok": gjs_net_ok,
        "ok": ok,
        "consumer_ok": consumer_ok,
        "message_te": None if consumer_ok else "మీ బిల్లు లో ఒక్క నంబర్ మ్యాచ్ అవ్వట్లేదు, CSC/1912 కి కాల్ చేయండి.",
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
    for k in ("units_eq_delta", "sum_eq_bill", "trueup_eq_rate", "gjs_net_ok"):
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
    # Consumer-facing match: the printed total is explained within ₹1 after
    # reconciliation. Diagnostic fails (true-up paise, label-shift, reading
    # typo) may still drive a retry, but must not show the 1912 banner.
    consumer_ok = sc.get("sum_eq_bill") is True and sc.get("gjs_net_ok") is not False
    out["consumer_ok"] = consumer_ok
    out["message_te"] = (
        None if consumer_ok else "మీ బిల్లు లో ఒక్క నంబర్ మ్యాచ్ అవ్వట్లేదు, CSC/1912 కి కాల్ చేయండి."
    )
    return out



def check_jump_sum(prev_bill: Dict[str, Any], curr_bill: Dict[str, Any], pro_rate: bool = False) -> Dict[str, Any]:
    """Self-check: jump_breakdown components + residual must equal the bill difference."""
    from tariff import jump_breakdown, check_jump_breakdown
    br = jump_breakdown(prev_bill, curr_bill, pro_rate=pro_rate)
    out = check_jump_breakdown(br)
    out["breakdown"] = br
    return out

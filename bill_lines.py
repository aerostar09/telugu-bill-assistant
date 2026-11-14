"""Official TGSPDCL LT-ELECTRICITY BILL-CUM NOTICE line order.

Used by the vision schema, the receipt UI, and tests. No consumer identity
fields live here.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Charge / total lines in the printed thermal order.
# (key, Telugu name, one-line meaning)
CHARGE_ROWS: List[Tuple[str, str, str]] = [
    ("energy_charges", "కరెంటు వాడకం", "మీరు వాడిన యూనిట్లకు"),
    ("fixed_charges", "ఫిక్స్‌డ్ ఛార్జీ", "కనెక్షన్ kW కి"),
    ("customer_charges", "కస్టమర్ ఛార్జీ", "మీటర్ రీడింగ్, బిల్లింగ్"),
    ("electricity_duty", "విద్యుత్ సుంకం", "యూనిట్‌కు 6 పైసలు, ప్రభుత్వానికి"),
    ("interest_on_ed", "ED వడ్డీ", "సుంకం మీద వడ్డీ"),
    ("surcharge", "ఆలస్య రుసుము", "గత బిల్లు ఆలస్యంగా కట్టినందుకు"),
    ("trueup_charges", "ట్రూ-అప్", "పాత సంవత్సరం సర్దుబాటు"),
    ("fsa_fca", "FSA/FCA", "ఇంధన ధర సర్దుబాటు"),
    ("subsidy", "సబ్సిడీ", "ప్రభుత్వం తగ్గించిన మొత్తం"),
    ("adjustment", "సర్దుబాటు", "ఇతర సర్దుబాటు"),
    ("interest_on_cd", "CD వడ్డీ", "సెక్యూరిటీ డిపాజిట్ మీద వడ్డీ"),
    ("loss_gain", "రౌండింగ్ (Loss/Gain)", "పైసల సర్దుబాటు"),
]

AFTER_BILL_ROWS: List[Tuple[str, str, str]] = [
    ("arrears_as_on", "బకాయిలు (as on)", "పాత బకాయి"),
    ("arrears_after", "బకాయిలు (after)", "తర్వాత వచ్చిన బకాయి"),
    ("arrears", "బకాయిలు", "మొత్తం బకాయి"),
    ("acd_due", "ACD బకాయి", "అదనపు సెక్యూరిటీ డిపాజిట్"),
]

HEADER_KEYS = (
    "discom", "category", "contracted_load_kw", "phase",
    "prev_reading", "present_reading", "prev_reading_date", "present_reading_date",
    "units", "days", "recorded_md",
    "bill_date", "due_date", "disc_date", "last_paid_date",
)

# Schema keys in official thermal order (nullable). Identity fields stay last
# and must never be shown on the receipt or in a share card.
SCHEMA_KEYS = [
    "discom", "category", "contracted_load_kw", "phase", "bill_date",
    "prev_reading", "present_reading", "prev_reading_date", "present_reading_date",
    "units", "days", "recorded_md",
    "energy_charges", "fixed_charges", "customer_charges", "electricity_duty",
    "interest_on_ed", "surcharge", "trueup_charges", "trueup_units",
    "fsa_fca", "subsidy", "adjustment", "interest_on_cd", "loss_gain",
    "bill_amount", "arrears_as_on", "arrears_after", "arrears",
    "acd_due", "acd_surcharge", "total_due",
    "due_date", "disc_date", "last_paid_date",
    "average_month_units", "unit_history",
    "usc_no", "is_electricity_bill", "image_quality",
]


def _amt(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


ARREARS_KEYS = ("arrears", "arrears_as_on", "arrears_after")
ARREARS_MIN_SHOW = 1.0  # rupees — paise/rounding slips are not arrears
ARREARS_SUM_TOL = 1.0


def _bill_and_total(bill: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], float]:
    bill_amt = _amt(bill.get("bill_amount"))
    if bill_amt is None:
        bill_amt = _amt(bill.get("bill_amount_printed"))
    total_due = _amt(bill.get("total_due"))
    acd = _amt(bill.get("acd_due")) or 0.0
    return bill_amt, total_due, acd


def _arrears_consistent(bill_amt: Optional[float], arr: float, acd: float,
                        total_due: Optional[float]) -> bool:
    if bill_amt is None or total_due is None:
        return True
    return abs((bill_amt + arr + acd) - total_due) <= ARREARS_SUM_TOL


def effective_arrears(bill: Dict[str, Any]) -> float:
    """Arrears to show or use; 0 if inconsistent or below ₹1.

    Real arrears must be at least ₹1 and satisfy
    Bill Amount + arrears + ACD ≈ Total Due within ±₹1. A stray ₹0.60
    'as on' when Bill already equals Total Due is treated as 0 (often a
    Loss/Gain or rounding leak). If the as-on + after split is inconsistent
    but the combined `arrears` field still fits the totals, that combined
    amount is used.
    """
    bill_amt, total_due, acd = _bill_and_total(bill)
    as_on = _amt(bill.get("arrears_as_on"))
    after = _amt(bill.get("arrears_after"))
    arrears = _amt(bill.get("arrears"))
    candidates: List[float] = []
    if (as_on is not None and abs(as_on) >= 0.005) or (after is not None and abs(after) >= 0.005):
        candidates.append(round((as_on or 0.0) + (after or 0.0), 2))
    if arrears is not None:
        candidates.append(round(arrears, 2))
    seen = set()
    for arr in candidates:
        if arr in seen:
            continue
        seen.add(arr)
        if arr >= ARREARS_MIN_SHOW and _arrears_consistent(bill_amt, arr, acd, total_due):
            return arr
    return 0.0


def _split_arrears_are_usable(bill: Dict[str, Any], eff: float) -> bool:
    if eff < ARREARS_MIN_SHOW:
        return False
    as_on = _amt(bill.get("arrears_as_on")) or 0.0
    after = _amt(bill.get("arrears_after")) or 0.0
    if abs(as_on) < 0.005 and abs(after) < 0.005:
        return False
    return abs(round(as_on + after, 2) - eff) <= 0.05


def nonzero_rows(bill: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Charge rows to show on the receipt: official order, skip zeros.

    Subsidy is included when it reduces the bill (amount > 0).
    If arrears_as_on / arrears_after are present and they sum to the
    effective arrears, the combined `arrears` row is skipped so we do
    not show the same rupees twice. Inconsistent or sub-₹1 arrears are
    omitted entirely.
    """
    out: List[Dict[str, Any]] = []
    for key, name, meaning in CHARGE_ROWS:
        amt = _amt(bill.get(key))
        if amt is None or abs(amt) < 0.005:
            continue
        out.append({"key": key, "name_te": name, "meaning_te": meaning, "amount": round(amt, 2)})
    eff = effective_arrears(bill)
    split = _split_arrears_are_usable(bill, eff)
    for key, name, meaning in AFTER_BILL_ROWS:
        if key in ARREARS_KEYS:
            if eff < ARREARS_MIN_SHOW:
                continue
            if key == "arrears" and split:
                continue
            if key != "arrears" and not split:
                continue
            amt = _amt(bill.get(key)) if key != "arrears" else eff
            if amt is None or abs(amt) < 0.005:
                continue
            out.append({"key": key, "name_te": name, "meaning_te": meaning, "amount": round(float(amt), 2)})
            continue
        amt = _amt(bill.get(key))
        if amt is None or abs(amt) < 0.005:
            continue
        out.append({"key": key, "name_te": name, "meaning_te": meaning, "amount": round(amt, 2)})
    return out


def payable_amount(bill: Dict[str, Any]) -> Optional[float]:
    """Total Due when consistent arrears (or a higher total) exist; otherwise Bill Amount."""
    bill_amt, total_due, _acd = _bill_and_total(bill)
    arr = effective_arrears(bill)
    if arr >= ARREARS_MIN_SHOW and total_due is not None:
        return total_due
    if total_due is not None and bill_amt is not None and total_due > bill_amt + 0.5:
        return total_due
    return bill_amt if bill_amt is not None else total_due

"""Post-OCR repairs for the TGSPDCL LT-ELECTRICITY BILL-CUM NOTICE format.

These run after the vision extract and before / with line-sum reconciliation.
They never invent identity fields and only rearrange or snap amounts when
the printed total and official tariff uniquely support the change.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from post_ocr import (
    TRUEUP_TOL,
    PLAUSIBLE_UNITS_MAX,
    _num,
    _close,
    _is_typical_surcharge,
    _leading_digit_variants,
    line_sum,
    printed_bill_amount,
)

ENERGY_MATCH_TOL = 1.0  # rupees — allow a one-rupee OCR slip
CYCLE_DAYS_MAX = 45


def _energy_for(units: Optional[float], category: Optional[str]) -> Optional[float]:
    if units is None:
        return None
    try:
        from tariff import energy_charges
        return energy_charges(float(units), category)
    except Exception:
        return None


def energy_matches(units: Optional[float], energy: Optional[float], category: Optional[str],
                   tol: float = ENERGY_MATCH_TOL) -> bool:
    exp = _energy_for(units, category)
    if exp is None or energy is None:
        return False
    return abs(exp - float(energy)) <= tol


def expected_fixed(bill: Dict[str, Any]) -> Optional[float]:
    try:
        from tariff import fixed_charges
        return fixed_charges(bill.get("contracted_load_kw"), bill.get("units"))
    except Exception:
        kw = _num(bill.get("contracted_load_kw"))
        if kw is None:
            return None
        units = _num(bill.get("units"))
        rate = 50.0 if (units is not None and units > 800) else 10.0
        return round(kw * rate, 2)


def expected_ed(units: Optional[float]) -> Optional[float]:
    if units is None:
        return None
    return round(float(units) * 0.06, 2)


def trueup_rate(bill: Dict[str, Any]) -> float:
    try:
        from tariff import trueup_rate_for_bill_date
        return float(trueup_rate_for_bill_date(bill.get("bill_date")))
    except Exception:
        return 0.30


def looks_like_trueup(val: Optional[float], units: Optional[float] = None,
                      rate: Optional[float] = None) -> bool:
    """True if val is N × 30p or 50p (and is not a typical ₹10/₹25 DPS)."""
    if val is None or val <= 0 or _is_typical_surcharge(val):
        return False
    rates = [rate] if rate else [0.30, 0.50]
    rates = [r for r in rates if r]
    if units is not None and rate:
        return _close(val, round(float(units) * rate, 2), tol=0.10)
    for r in (0.30, 0.50):
        q = float(val) / r
        if abs(q - round(q)) <= 0.05:
            qi = int(round(q))
            if 1 <= qi <= PLAUSIBLE_UNITS_MAX:
                return True
    return False


def repair_days_units_swap(bill: Dict[str, Any], notes: List[str],
                           raw_days: Optional[float] = None) -> Dict[str, Any]:
    """If the model wrote consumption units into the Days field, swap them back."""
    b = bill
    days = raw_days if raw_days is not None else _num(b.get("days"))
    units = _num(b.get("units"))
    energy = _num(b.get("energy_charges"))
    cat = b.get("category")
    if days is None or days <= CYCLE_DAYS_MAX:
        return b
    # days looks like consumption
    if energy_matches(days, energy, cat) and not energy_matches(units, energy, cat):
        old_u = units
        b["units"] = int(days) if float(days) == int(days) else days
        # Leave days empty so later date-based resolution can fill a real cycle.
        if _num(b.get("days")) is not None and _num(b.get("days")) > CYCLE_DAYS_MAX:
            b["days"] = None
        notes.append(
            f"auto-correct chesam: days {days:g} was actually units "
            f"(energy matches {b['units']:g} units, not {old_u}); "
            f"moved to units / రోజుల ఖానాలో యూనిట్లు వచ్చాయి, సరిచేసాం"
        )
    return b


def repair_readings_from_energy(bill: Dict[str, Any], notes: List[str]) -> Dict[str, Any]:
    """If billed energy matches a unique leading-digit reading variant, use it.

    The existing leading-digit repair only fires when the raw delta is
    implausible (>5000). A compressed thermal photo can yield a plausible
    but wrong delta (e.g. 234) whose energy does not match the printed
    energy charges.
    """
    b = bill
    prev = _num(b.get("prev_reading"))
    pres = _num(b.get("present_reading"))
    units = _num(b.get("units"))
    energy = _num(b.get("energy_charges"))
    cat = b.get("category")
    if prev is None or pres is None or energy is None:
        return b
    delta = pres - prev
    if energy_matches(delta, energy, cat) and (units is None or _close(units, delta, 0.05) or not energy_matches(units, energy, cat)):
        if units is not None and not _close(units, delta, 0.05) and energy_matches(delta, energy, cat):
            b["units"] = int(delta) if float(delta) == int(delta) else delta
            notes.append(
                f"auto-correct chesam: units {units:g} replaced by reading difference "
                f"{b['units']} because energy charges match / యూనిట్లు రీడింగ్ తేడాతో సరిపోయాయి"
            )
        return b
    # Current delta / units do not explain energy — try leading-digit variants.
    target_units: List[Tuple[str, int, int]] = []
    if pres is not None:
        for new_prev in _leading_digit_variants(int(prev)):
            d = int(pres) - new_prev
            if 0 < d <= PLAUSIBLE_UNITS_MAX and energy_matches(d, energy, cat):
                target_units.append(("prev_reading", new_prev, d))
        for new_pres in _leading_digit_variants(int(pres)):
            d = new_pres - int(prev)
            if 0 < d <= PLAUSIBLE_UNITS_MAX and energy_matches(d, energy, cat):
                target_units.append(("present_reading", new_pres, d))
        # Both leading digits may be wrong at once (e.g. 21090→11000 and 21324→11154).
        for new_prev in _leading_digit_variants(int(prev)):
            for new_pres in _leading_digit_variants(int(pres)):
                d = new_pres - new_prev
                if 0 < d <= PLAUSIBLE_UNITS_MAX and energy_matches(d, energy, cat):
                    target_units.append(("both", new_prev + 10_000_000 * new_pres, d))  # pack
    # Unique unit target
    unique_d = {t[2] for t in target_units}
    if len(unique_d) != 1:
        return b
    d = unique_d.pop()
    # Prefer a two-field fix if present, else a single-field fix
    both = [t for t in target_units if t[0] == "both"]
    if both:
        packed = both[0][1]
        new_pres = packed // 10_000_000
        new_prev = packed % 10_000_000
        old_prev, old_pres = b.get("prev_reading"), b.get("present_reading")
        b["prev_reading"] = new_prev
        b["present_reading"] = new_pres
        b["units"] = d
        notes.append(
            f"auto-correct chesam: readings {old_prev:g}→{old_pres:g} to "
            f"{new_prev}→{new_pres} so units={d} matches energy charges"
            f" / రీడింగ్ అంకెలు సరిచేసాం"
        )
        return b
    field, new_val, d = target_units[0]
    old = b[field]
    b[field] = new_val
    b["units"] = d
    notes.append(
        f"auto-correct chesam: leading digit on {field} {old:g} → {new_val} "
        f"so units={d} matches energy charges / {field} మొదటి అంకె సరిచేసాం"
    )
    return b


def repair_thermal_label_shift(bill: Dict[str, Any], notes: List[str]) -> Dict[str, Any]:
    """Unshift Fixed→Customer→ED when a thermal column was dropped.

    Typical failure: Fixed is missing (₹30) and the next amounts slide up
    (Fixed gets 90, Customer gets 9.24, ED gets 0). Detected when Fixed holds
    a typical customer-charge amount and Customer holds the expected ED.
    """
    b = bill
    units = _num(b.get("units"))
    fixed = _num(b.get("fixed_charges"))
    cust = _num(b.get("customer_charges"))
    ed = _num(b.get("electricity_duty"))
    exp_fixed = expected_fixed(b)
    exp_ed = expected_ed(units)
    if units is None or exp_fixed is None or exp_ed is None:
        return b
    # Already looks right
    if _is_typical_customer(cust) and _close(ed, exp_ed, tol=0.10) and _close(fixed, exp_fixed, tol=0.10):
        return b
    # Shifted: fixed has customer, customer has ED
    if (
        _is_typical_customer(fixed)
        and not _is_typical_customer(cust)
        and _close(cust, exp_ed, tol=0.10)
        and (ed is None or abs(ed) < 0.005 or not _close(ed, exp_ed, tol=0.10))
        and not _close(fixed, exp_fixed, tol=0.10)
    ):
        b["electricity_duty"] = cust
        b["customer_charges"] = fixed
        b["fixed_charges"] = exp_fixed
        notes.append(
            f"auto-correct chesam: thermal line shift — restored Fixed ₹{exp_fixed:.2f}, "
            f"Customer ₹{fixed:.2f}, ED ₹{cust:.2f}"
            f" / ఛార్జీ లైన్లు జారి, సరిచేసాం"
        )
    return b


def _is_typical_customer(v: Optional[float]) -> bool:
    if v is None:
        return False
    try:
        from self_checks import TYPICAL_CUSTOMER_CHARGES
        return any(abs(float(v) - c) <= 0.05 for c in TYPICAL_CUSTOMER_CHARGES)
    except Exception:
        return False


def snap_arrears(bill: Dict[str, Any], notes: List[str]) -> Dict[str, Any]:
    """If Total Due equals Bill Amount, a stray 0.60 'arrears' is an OCR slip."""
    b = bill
    printed = printed_bill_amount(b)
    total_due = _num(b.get("total_due"))
    arrears = _num(b.get("arrears"))
    as_on = _num(b.get("arrears_as_on"))
    after = _num(b.get("arrears_after"))
    if as_on is not None or after is not None:
        s = round((as_on or 0) + (after or 0), 2)
        if arrears is None or not _close(arrears, s, tol=0.05):
            b["arrears"] = s
        return b
    if printed is None or total_due is None or arrears is None:
        return b
    gap = round(total_due - printed, 2)
    if abs(gap) <= 1.0 and abs(arrears - gap) > 0.5:
        b["arrears"] = max(0.0, gap)
        notes.append(
            f"auto-correct chesam: arrears ₹{arrears:.2f} snapped to ₹{b['arrears']:.2f} "
            f"(Total Due − Bill Amount) / బకాయిలు సరిచేసాం"
        )
    return b


def apply_thermal_repairs(bill: Dict[str, Any], notes: Optional[List[str]] = None) -> Tuple[Dict[str, Any], List[str]]:
    """Run the thermal-layout repairs. Caller still runs reconcile_line_sum after."""
    b = bill
    notes = list(notes or [])
    raw_days = _num(b.get("days"))
    b = repair_days_units_swap(b, notes, raw_days=raw_days)
    b = repair_readings_from_energy(b, notes)
    b = repair_thermal_label_shift(b, notes)
    b = snap_arrears(b, notes)
    return b, notes

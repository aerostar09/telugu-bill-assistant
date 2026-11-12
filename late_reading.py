"""Late / early meter-reading detector and billing-days helpers.

Days
----
Preferred source: present_reading_date − prev_reading_date (calendar days).
If a printed Days value is also present and differs by at most 1 (common
off-by-one, e.g. jay6 09/Sep/23→09/Oct/23 computed 30, printed 29), keep
the printed value. If they differ by more than 1, prefer the date-computed
value and flag it. If dates are missing, use the printed Days field.

Late-reading extra rupees (slab push)
-------------------------------------
TG bills apply *unprorated* slab thresholds even when the cycle is not
30 days (verified: Lakshmi Nov 154 units / 31 days energy = ₹599.20).

The fair 30-day-equivalent energy keeps the *same billed units* but
widens (or narrows) slab thresholds by days/30 — the same `pro_rate=True`
path in tariff.py:

    fair = energy_charges(units, category, days=days, pro_rate=True)
    extra = actual_energy − fair

Lakshmi Nov: actual 599.20 − fair 594.53 = ₹4.67.

This is NOT the same as scaling units to 30 days and re-rating at
unprorated slabs (154 × 30/31 = 148.39 units → ₹572.26). That figure
mixes a usage-normalization with the slab effect; we report it as a
secondary `units_scaled_30d` view but the 'extra rupees caused by
days>30 slab push' is the ₹4.67 prorated-threshold gap.

Due-date safety
---------------
A due date is accepted only if it falls on or after the bill date
(or present reading date if the bill date is missing) and within
45 days of that anchor. Dates that look like arrears cut-offs
(e.g. 01-04-2026 on a November bill) are rejected (set to null).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional, Tuple

from tariff import energy_charges, infer_category, parse_bill_date, _num

DUE_DATE_MAX_DAYS_AFTER = 45
DAYS_PRINT_TOL = 1  # keep printed if |computed − printed| <= 1


def days_from_reading_dates(prev_date: Any, present_date: Any) -> Optional[int]:
    a = parse_bill_date(prev_date)
    b = parse_bill_date(present_date)
    if a is None or b is None:
        return None
    delta = (b - a).days
    if delta <= 0 or delta > 120:
        return None
    return int(delta)


def resolve_billing_days(bill: Dict[str, Any]) -> Dict[str, Any]:
    printed = _num(bill.get("days"))
    if printed is not None:
        if printed <= 0 or printed > 120:
            printed = None
        else:
            printed = int(round(printed)) if abs(printed - round(printed)) < 0.05 else printed
    computed = days_from_reading_dates(
        bill.get("prev_reading_date") or bill.get("previous_reading_date"),
        bill.get("present_reading_date") or bill.get("current_reading_date"),
    )
    if computed is not None and printed is not None:
        if abs(computed - printed) <= DAYS_PRINT_TOL:
            days, source = printed, "printed"
            note = None
            if computed != printed:
                note = (
                    f"printed days {printed} vs dates {computed} (off-by-one); kept printed"
                )
        else:
            days, source = computed, "reading_dates"
            note = (
                f"printed days {printed} disagreed with reading dates ({computed}); "
                f"used dates"
            )
    elif computed is not None:
        days, source, note = computed, "reading_dates", None
    elif printed is not None:
        days, source, note = printed, "printed", None
    else:
        days, source, note = None, None, "days not readable"
    return {
        "days": days,
        "source": source,
        "printed_days": printed,
        "computed_days": computed,
        "note": note,
    }


def due_date_is_safe(
    due: Any,
    bill_date: Any = None,
    present_reading_date: Any = None,
) -> Tuple[bool, Optional[str], Optional[date]]:
    due_d = parse_bill_date(due)
    if due is None or due == "":
        return True, None, None
    if due_d is None:
        return False, "unparseable due date", None
    anchor = parse_bill_date(bill_date) or parse_bill_date(present_reading_date)
    if anchor is None:
        return True, "no anchor date to check", due_d
    if due_d < anchor:
        return False, f"due date {due_d.isoformat()} is before bill/reading {anchor.isoformat()}", due_d
    gap = (due_d - anchor).days
    if gap > DUE_DATE_MAX_DAYS_AFTER:
        return False, (
            f"due date {due_d.isoformat()} is {gap} days after bill/reading "
            f"{anchor.isoformat()} (max {DUE_DATE_MAX_DAYS_AFTER})"
        ), due_d
    return True, None, due_d


def apply_due_date_safety(bill: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    """Return a shallow copy with an unsafe due_date cleared."""
    b = dict(bill)
    ok, reason, _ = due_date_is_safe(
        b.get("due_date"),
        b.get("bill_date"),
        b.get("present_reading_date"),
    )
    if ok:
        return b, None
    old = b.get("due_date")
    b["due_date"] = None
    b["due_date_rejected"] = old
    return b, f"due-date safety: rejected {old} ({reason})"


def late_reading_effect(bill: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extra energy rupees from unprorated slabs on a non-30-day cycle."""
    resolved = resolve_billing_days(bill)
    days = resolved["days"]
    units = _num(bill.get("units"))
    if days is None or units is None or units < 0 or days <= 0:
        return None
    cat = infer_category(units, bill.get("category"))
    actual = _num(bill.get("energy_charges"))
    if actual is None:
        actual = energy_charges(units, cat, days=days, pro_rate=False)
    fair = energy_charges(units, cat, days=days, pro_rate=True)
    extra = round(float(actual) - fair, 2)
    units_30 = round(float(units) * 30.0 / float(days), 2)
    # Secondary view only — not the headline extra.
    scaled_energy = energy_charges(units_30, infer_category(units_30, None), days=30, pro_rate=False)
    return {
        "days": days,
        "days_source": resolved["source"],
        "days_note": resolved["note"],
        "printed_days": resolved["printed_days"],
        "computed_days": resolved["computed_days"],
        "units": units,
        "units_30d": units_30,
        "category": cat,
        "actual_energy": round(float(actual), 2),
        "fair_energy_prorated": fair,
        "extra_rupees": extra,
        "is_late": bool(days > 30),
        "is_early": bool(days < 30),
        "units_scaled_energy": scaled_energy,
        "method": (
            "Actual energy uses unprorated official slabs (as printed on TG bills). "
            "Fair 30-day-equivalent energy keeps the same units and scales slab "
            "thresholds by days/30 (tariff.energy_charges pro_rate=True). "
            "extra_rupees = actual − fair. "
            "Scaling units to 30 days and re-rating at unprorated slabs is a "
            "different number and is reported only as units_scaled_energy."
        ),
    }

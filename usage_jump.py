"""Unusual usage-jump alert for the citizen page (screening flag, not a diagnosis).

Fires when this month's units are >= 50% above the average of the available
past months AND at least 50 units higher. Past months come from, in order:
  1. history rows before this bill's month (printed unit history or user
     history input), using the most recent up to 3 months;
  2. a compared previous bill's units;
  3. the bill's printed 'Average Month Units'.
No past data → no alert.

Units are compared on a 30-day basis when a billing period is known and
falls outside 25–35 days (so a 57-day cycle is not treated as a jump just
because raw units are higher). Missing days keep the raw figure. History
rows and a previous bill are scaled the same way when they carry a days
value; printed Average Month Units is already a monthly figure.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from scenarios import COMPLAINT_1912, OFFICIAL_WA_DISPLAY
from tariff import parse_bill_date

JUMP_PCT = 0.50
JUMP_MIN_UNITS = 50.0
RECENT_MONTHS = 3
# Treat 25–35 day cycles as a normal month; scale anything outside that.
NORMAL_DAYS_LO = 25.0
NORMAL_DAYS_HI = 35.0
MONTH_DAYS = 30.0


def _f(v: Any) -> Optional[float]:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def monthly_equivalent(units: float, days: Any = None) -> Tuple[float, bool]:
    """Scale units to a 30-day month when days is known and outside 25–35.

    Returns (comparable_units, was_normalised). Missing or non-positive days
    leave the raw units unchanged.
    """
    d = _f(days)
    if d is None or d <= 0 or NORMAL_DAYS_LO <= d <= NORMAL_DAYS_HI:
        return units, False
    return units * MONTH_DAYS / d, True


def past_units(
    bill: Dict[str, Any],
    history: Optional[List[Dict[str, Any]]] = None,
    prev_bill: Optional[Dict[str, Any]] = None,
) -> List[float]:
    dt = parse_bill_date(bill.get("bill_date")) or parse_bill_date(bill.get("present_reading_date"))
    rows = []
    for r in history or []:
        u = _f(r.get("units"))
        y, m = r.get("year"), r.get("month")
        if u is None or y is None or m is None or r.get("label") == "current":
            continue
        if dt is not None and (int(y), int(m)) >= (dt.year, dt.month):
            continue
        monthly, _ = monthly_equivalent(u, r.get("days"))
        rows.append(((int(y), int(m)), monthly))
    if rows:
        rows.sort()
        return [u for _, u in rows[-RECENT_MONTHS:]]
    pu = _f((prev_bill or {}).get("units"))
    if pu is not None:
        monthly, _ = monthly_equivalent(pu, (prev_bill or {}).get("days"))
        return [monthly]
    avg = _f(bill.get("average_month_units"))
    if avg is not None:
        return [avg]
    return []


def usage_jump_alert(
    bill: Dict[str, Any],
    history: Optional[List[Dict[str, Any]]] = None,
    prev_bill: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    cur = _f(bill.get("units"))
    past = [u for u in past_units(bill, history, prev_bill) if u is not None and u >= 0]
    if cur is None or not past:
        return None
    avg = sum(past) / len(past)
    if avg <= 0:
        return None
    comparable, normalised = monthly_equivalent(cur, bill.get("days"))
    if comparable < avg * (1 + JUMP_PCT) or (comparable - avg) < JUMP_MIN_UNITS:
        return None
    days = _f(bill.get("days"))
    if normalised and days is not None:
        text = (
            f"⚠️ ఈ బిల్లు {int(round(days))} రోజులకు {int(round(cur))} యూనిట్లు "
            f"(నెలకు సుమారు {int(round(comparable))} యూనిట్లు) — మామూలు కంటే చాలా ఎక్కువ "
            f"(గత నెలల సగటు సుమారు {int(round(avg))} యూనిట్లు). "
            "బిల్లులోని 'Present' రీడింగ్‌ని మీ ఇంటి మీటర్‌పై ఉన్న నంబర్‌తో పోల్చి చూడండి. "
            f"తప్పుగా ఉంటే {COMPLAINT_1912} కి కాల్ చేయండి లేదా TGSPDCL అధికారిక WhatsApp "
            f"{OFFICIAL_WA_DISPLAY} కి ఫిర్యాదు చేయండి."
        )
    else:
        text = (
            f"⚠️ ఈ నెల {int(round(cur))} యూనిట్లు — మామూలు కంటే చాలా ఎక్కువ "
            f"(గత నెలల సగటు సుమారు {int(round(avg))} యూనిట్లు). "
            "బిల్లులోని 'Present' రీడింగ్‌ని మీ ఇంటి మీటర్‌పై ఉన్న నంబర్‌తో పోల్చి చూడండి. "
            f"తప్పుగా ఉంటే {COMPLAINT_1912} కి కాల్ చేయండి లేదా TGSPDCL అధికారిక WhatsApp "
            f"{OFFICIAL_WA_DISPLAY} కి ఫిర్యాదు చేయండి."
        )
    return {
        "current_units": cur,
        "monthly_units": round(comparable, 1),
        "normalised": normalised,
        "past_average": round(avg, 1),
        "n_past": len(past),
        "ratio": round(comparable / avg, 2),
        "text_te": text,
    }

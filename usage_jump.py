"""Unusual usage-jump alert for the citizen page (screening flag, not a diagnosis).

Fires when this month's units are >= 50% above the average of the available
past months AND at least 50 units higher. Past months come from, in order:
  1. history rows before this bill's month (printed unit history or user
     history input), using the most recent up to 3 months;
  2. a compared previous bill's units;
  3. the bill's printed 'Average Month Units'.
No past data → no alert.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from scenarios import COMPLAINT_1912, OFFICIAL_WA_DISPLAY
from tariff import parse_bill_date

JUMP_PCT = 0.50
JUMP_MIN_UNITS = 50.0
RECENT_MONTHS = 3


def _f(v: Any) -> Optional[float]:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


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
        rows.append(((int(y), int(m)), u))
    if rows:
        rows.sort()
        return [u for _, u in rows[-RECENT_MONTHS:]]
    pu = _f((prev_bill or {}).get("units"))
    if pu is not None:
        return [pu]
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
    if cur < avg * (1 + JUMP_PCT) or (cur - avg) < JUMP_MIN_UNITS:
        return None
    text = (
        f"⚠️ ఈ నెల {int(round(cur))} యూనిట్లు — మామూలు కంటే చాలా ఎక్కువ "
        f"(గత నెలల సగటు సుమారు {int(round(avg))} యూనిట్లు). "
        "బిల్లులోని 'Present' రీడింగ్‌ని మీ ఇంటి మీటర్‌పై ఉన్న నంబర్‌తో పోల్చి చూడండి. "
        f"తప్పుగా ఉంటే {COMPLAINT_1912} కి కాల్ చేయండి లేదా TGSPDCL అధికారిక WhatsApp "
        f"{OFFICIAL_WA_DISPLAY} కి ఫిర్యాదు చేయండి."
    )
    return {
        "current_units": cur,
        "past_average": round(avg, 1),
        "n_past": len(past),
        "ratio": round(cur / avg, 2),
        "text_te": text,
    }

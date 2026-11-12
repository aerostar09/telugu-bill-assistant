"""Build a unit-history series from past bill photos, a DISCOM history-table
screenshot, or a manual month/units table. Pure Python, no LLM.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from tariff import parse_bill_date, _num
from forecast import normalize_history, _parse_month_label, _month_num

MAX_PAST_BILLS = 6
SOURCE_DEMO = "demo"
SOURCE_USER = "user"
LABEL_DEMO = "Demo data"
LABEL_DEMO_TE = "డెమో డేటా"
LABEL_USER = "Your bills"
LABEL_USER_TE = "మీ బిల్లులు"
BACKTEST_MIN_REAL_MONTHS = 6


def bill_to_history_row(bill: Dict[str, Any], source: str = "bill_photo") -> Optional[Dict[str, Any]]:
    """units + calendar month from a single extracted bill (date, units, amount)."""
    if not bill:
        return None
    dt = parse_bill_date(bill.get("bill_date")) or parse_bill_date(bill.get("present_reading_date"))
    units = _num(bill.get("units"))
    if dt is None or units is None or units < 0:
        return None
    row = {
        "year": dt.year,
        "month": dt.month,
        "units": float(units),
        "amount": _num(bill.get("bill_amount")),
        "estimated": False,
        "source": source,
    }
    return row


def parse_history_table_payload(raw: Any) -> List[Dict[str, Any]]:
    """Normalize a vision-model 'Bill History' table: {rows:[{month, units, amount}]}."""
    if not raw:
        return []
    if isinstance(raw, dict) and "rows" in raw:
        items = raw.get("rows") or []
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    out: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        y = item.get("year")
        m = _month_num(item.get("month"))
        if y is None or m is None:
            # "Nov 2026" / "2026-11" in month or label
            y2, m2 = _parse_month_label(item.get("month") or item.get("label") or item.get("bill_month"))
            y = y if y is not None else y2
            m = m if m is not None else m2
        try:
            y = int(y) if y is not None else None
        except (TypeError, ValueError):
            y = None
        if y is not None and y < 100:
            y += 2000
        units = _num(item.get("units") if item.get("units") is not None else item.get("kwh"))
        if y is None or m is None or units is None or units < 0:
            continue
        out.append({
            "year": int(y),
            "month": int(m),
            "units": float(units),
            "amount": _num(item.get("amount") if item.get("amount") is not None else item.get("bill_amount")),
            "estimated": bool(item.get("estimated")),
            "source": "history_table",
        })
    return normalize_history(out)


def parse_manual_rows(rows: Iterable[Any]) -> List[Dict[str, Any]]:
    """Manual form rows: month (2026-10 / Oct 2026), units, optional amount."""
    items = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        month_val = item.get("month") or item.get("label")
        y, m = None, _month_num(item.get("month")) if isinstance(item.get("month"), (int, float)) else None
        if item.get("year") is not None:
            try:
                y = int(item["year"])
            except (TypeError, ValueError):
                y = None
        if y is None or m is None:
            y2, m2 = _parse_month_label(month_val)
            y = y if y is not None else y2
            m = m if m is not None else m2
        units = _num(item.get("units"))
        if y is None or m is None or units is None or units < 0:
            continue
        if y < 100:
            y += 2000
        items.append({
            "year": int(y),
            "month": int(m),
            "units": float(units),
            "amount": _num(item.get("amount")),
            "estimated": False,
            "source": "manual",
        })
    return normalize_history(items)


def merge_history_rows(
    *groups: Iterable[Dict[str, Any]],
    current_bill: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Chronological unique-by-(year, month). Later groups override earlier ones.
    The current bill, if given, wins for its month."""
    uniq: Dict[tuple, Dict[str, Any]] = {}
    for group in groups:
        for row in group or []:
            if not isinstance(row, dict) or row.get("units") is None:
                continue
            # allow already-normalized rows
            y, m = row.get("year"), row.get("month")
            if y is None or m is None:
                continue
            uniq[(int(y), int(m))] = dict(row)
    if current_bill:
        cur = bill_to_history_row(current_bill, source="current_bill")
        if cur:
            uniq[(cur["year"], cur["month"])] = cur
    return [uniq[k] for k in sorted(uniq)]


def history_display_meta(rows: Optional[List[Dict[str, Any]]], is_demo: bool) -> Dict[str, Any]:
    """Chart/forecast source label, and whether backtest should be shown."""
    n = len(rows or [])
    if is_demo:
        return {
            "source": SOURCE_DEMO,
            "source_label": LABEL_DEMO,
            "source_label_te": LABEL_DEMO_TE,
            "n_real": 0,
            "n_rows": n,
            "show_backtest": False,
            "is_demo": True,
        }
    return {
        "source": SOURCE_USER,
        "source_label": LABEL_USER,
        "source_label_te": LABEL_USER_TE,
        "n_real": n,
        "n_rows": n,
        "show_backtest": n >= BACKTEST_MIN_REAL_MONTHS,
        "is_demo": False,
    }


GRUHA_JYOTHI_NOTE_TE = (
    "గృహ జ్యోతి (Gruha Jyothi) ఉచిత 200 యూనిట్లు కేవలం అర్హులైన లబ్ధిదారులకు మాత్రమే "
    "(సాధారణంగా ఆధార్‌తో లింక్ అయిన వైట్ రేషన్ / Food Security కార్డు, ఇంటికి ఒక కనెక్షన్). "
    "200 యూనిట్లు దాటితే అర్హులైనా మొత్తం బిల్లు వసూలు అవుతుంది — మిగిలిన యూనిట్లు మాత్రమే కాదు. "
    "అర్హత లేనివారు 200 లోపు ఉన్నా సాధారణ టారిఫ్ చెల్లిస్తారు."
)

GRUHA_JYOTHI_NOTE_EN = (
    "Gruha Jyothi free 200 units/month applies only to eligible beneficiaries. "
    "If a beneficiary exceeds 200 units, the entire bill is charged (not only the excess). "
    "Non-beneficiaries pay the normal tariff even below 200."
)

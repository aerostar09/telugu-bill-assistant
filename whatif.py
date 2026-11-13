"""Deterministic what-if / units slider estimate. Labelled simulation only."""
from __future__ import annotations

from typing import Any, Dict, Optional

from tariff import quote_bill, trueup_rate_for_next_bill, trueup_rate_for_bill_date, infer_category, customer_charges_for_units
from terms import TARIFF_VERSION, t


def _num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def whatif_for_units(
    bill: Dict[str, Any],
    units: float,
    *,
    days: float = 30,
) -> Dict[str, Any]:
    """Tariff quote for a chosen unit count. Not a forecast of actual usage.

    Next-bill true-up rate is used (30p in Nov 2026, 50p thereafter).
    DPS is excluded (assume on-time payment), same as the forecast.
    Customer charge follows the official table for the simulated units.
    """
    u = float(units)
    load = _num(bill.get("contracted_load_kw")) or 1.0
    rate = trueup_rate_for_next_bill(bill.get("bill_date"))
    q = quote_bill(
        units=u,
        load_kw=load,
        days=days,
        category=None,
        customer_charges=customer_charges_for_units(u),
        trueup_units=_num(bill.get("trueup_units")),
        trueup_rate=rate,
        pro_rate=False,
    )
    current = _num(bill.get("bill_amount"))
    if current is None:
        current = _num(bill.get("total_due"))
    diff = None if current is None else round(q["total"] - current, 2)
    return {
        "units": u,
        "days": days,
        "quote": q,
        "total": q["total"],
        "difference": diff,
        "category": q.get("category") or infer_category(u),
        "label": "simulation / estimate",
        "label_te": t("simulation"),
        "note": t("simulation_note"),
        "tariff_version": TARIFF_VERSION,
        "current_bill": current,
    }



def same_units_delta_note(bill: Dict[str, Any], whatif: Dict[str, Any]) -> Optional[str]:
    """One-line reason when the what-if total at the *same* units differs from the printed bill.

    Typical case: this month's true-up is 30p (Nov 2026) and the next bill is 50p.
    The wording is computed from the official rates, never hardcoded.
    """
    bu = _num(bill.get("units"))
    wu = _num(whatif.get("units"))
    if bu is None or wu is None or abs(wu - bu) > 0.05:
        return None
    printed = _num(whatif.get("current_bill"))
    if printed is None:
        printed = _num(bill.get("bill_amount")) or _num(bill.get("total_due"))
    total = _num(whatif.get("total"))
    if printed is None or total is None or abs(total - printed) < 0.5:
        return None
    curr = trueup_rate_for_bill_date(bill.get("bill_date"))
    nxt = trueup_rate_for_next_bill(bill.get("bill_date"))
    nxt_paise = int(round(float(nxt) * 100))
    if nxt > curr + 0.001 and total > printed:
        return f"వచ్చే నెల ట్రూ-అప్ {nxt_paise} పైసలు కాబట్టి కొంచెం ఎక్కువ"
    if nxt < curr - 0.001 and total < printed:
        return f"వచ్చే నెల ట్రూ-అప్ {nxt_paise} పైసలు కాబట్టి కొంచెం తక్కువ"
    direction = "ఎక్కువ" if total > printed else "తక్కువ"
    return f"ఇదే యూనిట్లకు సిమ్యులేషన్ ₹{total:.0f} ({direction})"

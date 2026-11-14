"""Pure-Python Telangana domestic (LT-I) tariff helpers — no LLM.

DRAFT: slabs are the published-style 1A / 1B(i) / 1B(ii) rates used on
Lakshmi's Nov 2026 bill. Pro-rating of slab thresholds by days/30 is
OPTIONAL and OFF by default, because the real Nov bill (154 units, 31 days)
uses unprorated 100/200 thresholds (energy = 100×3.40 + 54×4.80 = ₹599.20).

True-up (PP cost adjustment) is 30p/unit on Nov 2026 bills and 50p/unit
thereafter, applied to FY 2022-23 true-up units printed on the bill
(NOT this month's consumption).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

ED_RATE = 0.06
FIXED_PER_KW = 10.0
FIXED_PER_KW_ABOVE_800 = 50.0  # TGERC RST FY2026-27: LT-I(B)(ii) last row, units > 800

# Official LT-I Domestic customer charges (Rs/month) by billed units.
# Source: TGERC Retail Supply Tariff Order FY 2026-27, Appendix A, item 7,
# page 294 (TGERC_Tariff_Schedule_2026-27.pdf / research/official/sched-6.png).
CUSTOMER_CHARGE_SLABS = [
    (50, 40.0),
    (100, 70.0),
    (200, 90.0),
    (300, 100.0),
    (400, 120.0),
    (800, 140.0),
    (None, 160.0),
]

# Delayed Payment Surcharge if paid after due date.
# Source: TGERC Retail Supply Tariff Order FY 2026-27, Appendix A, item 8,
# page 295 (sched-7.png). LT-I(A) Rs.10/month; LT-I(B) Rs.25/month.
DPS_LT_IA = 10.0
DPS_LT_IB = 25.0
TRUEUP_RATE_NOV_2026 = 0.30
TRUEUP_RATE_AFTER_NOV_2026 = 0.50

# 1A last-slab extension is only used for counterfactual "if category hadn't jumped".
CAT_1A_SLABS = [(50, 1.95), (50, 3.10)]  # 0-50, 51-100; extend last if needed
CAT_1BI_SLABS = [(100, 3.40), (100, 4.80)]
CAT_1BII_SLABS = [(200, 5.10), (100, 7.70), (100, 9.00), (400, 9.50), (None, 10.00)]


def _num(v: Any) -> Optional[float]:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def category_label_is_specific(category: Optional[str]) -> bool:
    """True if the string names a 1A / 1B slab, not a title or bare 'Domestic'."""
    if not category:
        return False
    s = str(category).lower()
    compact = s.replace(" ", "").replace("_", "")
    if any(tok in compact for tok in (
        "bill-cum", "billcum", "lt-electricity", "ltelectricity",
        "electricitybill",
    )) or "electricity bill" in s:
        return False
    return re.search(r"1\s*a|1\s*b", s) is not None


def normalize_extracted_category(
    category: Optional[str] = None, units: Optional[float] = None
) -> str:
    """Return a canonical 1A / 1B(i) / 1B(ii) slab.

    Junk labels (document title, bare 'DOMESTIC', '3A DOMESTIC') are ignored
    and the slab is inferred from billed units when those are present.
    """
    if category_label_is_specific(category):
        return infer_category(units, category)
    return infer_category(units, None)


def infer_category(units: Optional[float] = None, category: Optional[str] = None) -> str:
    """Return one of '1A', '1B(i)', '1B(ii)'."""
    if category and category_label_is_specific(category):
        s = str(category).lower().replace(" ", "")
        s = s.replace("lt-i", "").replace("lt1", "").replace("domestic", "")
        if "1b(ii)" in s or "1b(2)" in s or "1b2" in s or "1bii" in s:
            return "1B(ii)"
        if "1b(i)" in s or "1b(1)" in s or "1bi" in s or "1b1" in s or "1b" in s:
            # plain 1B / 1B(1) is 1B(i) when units <= 200
            if units is not None and units > 200:
                return "1B(ii)"
            return "1B(i)"
        if "1a" in s:
            return "1A"
    if units is None:
        return "1A"
    if units <= 100:
        return "1A"
    if units <= 200:
        return "1B(i)"
    return "1B(ii)"


def _slabs_for(cat: str) -> List[Tuple[Optional[float], float]]:
    if cat == "1A":
        return list(CAT_1A_SLABS)
    if cat == "1B(ii)":
        return list(CAT_1BII_SLABS)
    return list(CAT_1BI_SLABS)


def energy_charges(
    units: float,
    category: Optional[str] = None,
    days: Optional[float] = None,
    pro_rate: bool = False,
    extend_last_slab: bool = True,
) -> float:
    """Energy charges for `units` in the given category.

    pro_rate=False (default) uses official 50/100/200… thresholds as printed
    on real TG bills (verified: 154 units / 31 days → ₹599.20).
    pro_rate=True scales thresholds by days/30 (assumption only; does not
    match the Lakshmi Nov 2026 bill).
    """
    u = max(0.0, float(units) or 0.0)
    cat = infer_category(u, category)
    slabs = _slabs_for(cat)
    factor = 1.0
    if pro_rate and days is not None and days > 0 and abs(days - 30) > 0.05:
        factor = float(days) / 30.0

    remaining = u
    total = 0.0
    last_rate = slabs[-1][1]
    for width, rate in slabs:
        last_rate = rate
        if remaining <= 0:
            break
        cap = (width * factor) if width is not None else remaining
        used = min(remaining, cap)
        total += used * rate
        remaining -= used
    if remaining > 0 and extend_last_slab:
        total += remaining * last_rate
    return round(total, 2)


def fixed_charges(load_kw: Optional[float], units: Optional[float] = None) -> float:
    """₹10/kW normally; ₹50/kW when billed units are above 800 (official RST FY2026-27)."""
    kw = max(0.0, _num(load_kw) or 0.0)
    u = _num(units)
    rate = FIXED_PER_KW_ABOVE_800 if (u is not None and u > 800) else FIXED_PER_KW
    return round(kw * rate, 2)


def electricity_duty(units: float) -> float:
    return round(max(0.0, float(units) or 0.0) * ED_RATE, 2)


def customer_charges_for_units(units: Optional[float]) -> float:
    """Official LT-I domestic customer charge (Rs/month) from billed units.

    Source: TGERC RST Order FY 2026-27 Appendix A item 7 (p.294 / sched-6.png).
    """
    u = _num(units)
    if u is None or u < 0:
        u = 0.0
    for cap, amt in CUSTOMER_CHARGE_SLABS:
        if cap is None or u <= cap:
            return float(amt)
    return 160.0


def delayed_payment_surcharge(
    units: Optional[float] = None,
    category: Optional[str] = None,
) -> float:
    """DPS if the bill is paid after the due date. Not applied in forecasts
    (we assume on-time payment).

    Source: TGERC RST Order FY 2026-27 Appendix A item 8 (p.295 / sched-7.png).
    LT-I(A) (≤100 units) ₹10/month; LT-I(B) ₹25/month.
    """
    cat = infer_category(units, category)
    return DPS_LT_IA if cat == "1A" else DPS_LT_IB


def parse_bill_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d",
                "%d-%b-%Y", "%d-%b-%y", "%d %b %Y",
                "%d/%b/%Y", "%d/%b/%y", "%d-%B-%Y", "%d/%B/%y", "%d/%B/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # 10-02-2026 already covered; 06/11/26 covered by %d/%m/%y
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def trueup_rate_for_bill_date(bill_date: Any) -> float:
    """30p on Nov 2026 bills; 50p from Dec 2026 onward. Unknown date → 30p (current)."""
    dt = parse_bill_date(bill_date)
    if dt is None:
        return TRUEUP_RATE_NOV_2026
    if (dt.year, dt.month) <= (2026, 11):
        return TRUEUP_RATE_NOV_2026
    return TRUEUP_RATE_AFTER_NOV_2026


def trueup_rate_for_next_bill(bill_date: Any) -> float:
    """Rate that will apply on the *next* cycle after this bill's date."""
    dt = parse_bill_date(bill_date)
    if dt is None:
        return TRUEUP_RATE_AFTER_NOV_2026
    if dt.month == 12:
        nxt = date(dt.year + 1, 1, 1)
    else:
        nxt = date(dt.year, dt.month + 1, 1)
    return trueup_rate_for_bill_date(nxt)


def trueup_charges(trueup_units: Optional[float], bill_date: Any = None, rate: Optional[float] = None) -> float:
    n = _num(trueup_units)
    if n is None or n <= 0:
        return 0.0
    r = TRUEUP_RATE_NOV_2026 if rate is None else float(rate)
    if rate is None:
        r = trueup_rate_for_bill_date(bill_date)
    return round(n * r, 2)


def quote_bill(
    units: float,
    load_kw: float = 1.0,
    days: Optional[float] = 30,
    category: Optional[str] = None,
    customer_charges: Optional[float] = None,
    trueup_units: Optional[float] = None,
    bill_date: Any = None,
    pro_rate: bool = False,
    trueup_rate: Optional[float] = None,
) -> Dict[str, Any]:
    """Itemized estimate from tariff (customer charge taken from the bill when given)."""
    cat = infer_category(units, category)
    energy = energy_charges(units, cat, days=days, pro_rate=pro_rate)
    fixed = fixed_charges(load_kw, units)
    duty = electricity_duty(units)
    # Bill-extracted customer charge wins when provided; otherwise official table.
    if customer_charges is None:
        cust = customer_charges_for_units(units)
    else:
        cust = float(customer_charges)
    tu = trueup_charges(trueup_units, bill_date=bill_date, rate=trueup_rate)
    total = round(energy + fixed + duty + cust + tu, 2)
    return {
        "category": cat,
        "units": units,
        "days": days,
        "pro_rate": pro_rate,
        "energy_charges": energy,
        "fixed_charges": fixed,
        "customer_charges": cust,
        "electricity_duty": duty,
        "trueup_charges": tu,
        "trueup_rate": (
            trueup_rate if trueup_rate is not None else trueup_rate_for_bill_date(bill_date)
        ),
        "total": total,
    }


# -----------------------------------------------------------------------------
# Jump breakdown: prev → curr. Components sum to bill difference + residual.
# -----------------------------------------------------------------------------
_OTHER_KEYS = (
    "interest_on_ed", "surcharge", "fsa_fca", "subsidy", "adjustment", "loss_gain", "arrears",
)


def _line(bill: Dict[str, Any], key: str, default: float = 0.0) -> float:
    v = _num(bill.get(key))
    return default if v is None else v


def jump_breakdown(
    prev_bill: Optional[Dict[str, Any]],
    curr_bill: Dict[str, Any],
    pro_rate: bool = False,
) -> Dict[str, Any]:
    """Rupee components of (curr bill_amount − prev bill_amount).

    (a) extra units at old category rate
    (b) category change effect (e.g. 1A → 1B re-rating of all units)
    (c) true-up added
    (d) fixed / customer / ED / other changes
    (e) residual (openly shown; components + residual == difference)

    If previous line items are missing, they are filled from the tariff
    (energy/fixed/ED). Any gap versus a known previous total goes to residual.
    """
    curr_units = _num(curr_bill.get("units")) or 0.0
    curr_days = _num(curr_bill.get("days"))
    curr_load = _num(curr_bill.get("contracted_load_kw")) or 1.0
    curr_cat = infer_category(curr_units, curr_bill.get("category"))
    curr_energy = _num(curr_bill.get("energy_charges"))
    curr_total = _num(curr_bill.get("bill_amount"))
    if curr_total is None:
        curr_total = _num(curr_bill.get("total_due"))

    prev = dict(prev_bill or {})
    prev_units = _num(prev.get("units"))
    prev_was_computed = False
    if prev_units is None:
        # cannot do a volume/category split without previous units
        prev_units = 0.0

    prev_cat = infer_category(prev_units, prev.get("category"))
    prev_days = _num(prev.get("days"))
    prev_load = _num(prev.get("contracted_load_kw")) or curr_load

    # Fill missing previous energy/fixed/ED from tariff
    if _num(prev.get("energy_charges")) is None and prev_units:
        prev["energy_charges"] = energy_charges(
            prev_units, prev_cat, days=prev_days, pro_rate=pro_rate
        )
        prev_was_computed = True
    if _num(prev.get("fixed_charges")) is None:
        prev["fixed_charges"] = fixed_charges(prev_load, prev_units)
        prev_was_computed = True
    if _num(prev.get("electricity_duty")) is None and prev_units:
        prev["electricity_duty"] = electricity_duty(prev_units)
        prev_was_computed = True
    if _num(prev.get("trueup_charges")) is None:
        tu_u = _num(prev.get("trueup_units"))
        prev["trueup_charges"] = trueup_charges(tu_u, prev.get("bill_date")) if tu_u else 0.0

    prev_energy = _line(prev, "energy_charges")
    # Counterfactual: current units at the *previous* category (extend last slab
    # so 1A can be applied above 100 for the "if category hadn't jumped" story).
    energy_new_at_old = energy_charges(
        curr_units, prev_cat, days=curr_days, pro_rate=pro_rate, extend_last_slab=True
    )
    energy_curr = curr_energy if curr_energy is not None else energy_charges(
        curr_units, curr_cat, days=curr_days, pro_rate=pro_rate
    )

    extra_units_old_rate = round(energy_new_at_old - prev_energy, 2)
    category_change = round(energy_curr - energy_new_at_old, 2)
    if prev_cat == curr_cat:
        # still report category_change (should be ~0 if tariff matches actual)
        pass

    trueup_added = round(_line(curr_bill, "trueup_charges") - _line(prev, "trueup_charges"), 2)

    other_delta = 0.0
    other_parts: Dict[str, float] = {}
    for key, label in (
        ("fixed_charges", "fixed"),
        ("customer_charges", "customer"),
        ("electricity_duty", "ed"),
    ):
        d = round(_line(curr_bill, key) - _line(prev, key), 2)
        other_parts[label] = d
        other_delta += d
    for key in _OTHER_KEYS:
        d = round(_line(curr_bill, key) - _line(prev, key), 2)
        # subsidy is a reduction: stored positive on bills, already subtracted in totals
        if key == "subsidy":
            d = -d
        if abs(d) > 0.0001:
            other_parts[key] = d
        other_delta += d
    other_delta = round(other_delta, 2)

    prev_total = _num(prev.get("bill_amount"))
    if prev_total is None:
        prev_total = _num(prev.get("total_due"))
    if prev_total is None:
        # reconstructed previous total from lines we have
        prev_total = round(
            _line(prev, "energy_charges")
            + _line(prev, "fixed_charges")
            + _line(prev, "customer_charges")
            + _line(prev, "electricity_duty")
            + _line(prev, "trueup_charges")
            + sum(_line(prev, k) for k in _OTHER_KEYS if k != "subsidy")
            - _line(prev, "subsidy"),
            2,
        )
        prev_was_computed = True

    difference = None if curr_total is None else round(curr_total - prev_total, 2)
    explained = round(extra_units_old_rate + category_change + trueup_added + other_delta, 2)
    residual = None if difference is None else round(difference - explained, 2)

    return {
        "prev_units": prev_units,
        "curr_units": curr_units,
        "prev_category": prev_cat,
        "curr_category": curr_cat,
        "prev_total": prev_total,
        "curr_total": curr_total,
        "difference": difference,
        "extra_units_old_rate": extra_units_old_rate,
        "category_change": category_change,
        "trueup_added": trueup_added,
        "other_changes": other_delta,
        "other_parts": other_parts,
        "residual": residual,
        "explained": explained,
        "prev_computed_from_tariff": prev_was_computed,
        "energy_prev": prev_energy,
        "energy_curr": energy_curr,
        "energy_curr_at_old_category": energy_new_at_old,
        "pro_rate": pro_rate,
    }


def check_jump_breakdown(breakdown: Dict[str, Any], tol: float = 0.01) -> Dict[str, Any]:
    """Self-check: components + residual == bill difference."""
    diff = breakdown.get("difference")
    residual = breakdown.get("residual")
    parts = (
        (breakdown.get("extra_units_old_rate") or 0)
        + (breakdown.get("category_change") or 0)
        + (breakdown.get("trueup_added") or 0)
        + (breakdown.get("other_changes") or 0)
        + (0.0 if residual is None else residual)
    )
    ok = diff is not None and residual is not None and abs(round(parts, 2) - diff) <= tol
    return {
        "ok": ok,
        "difference": diff,
        "parts_plus_residual": round(parts, 2) if diff is not None else None,
        "residual": residual,
    }


# -----------------------------------------------------------------------------
# Cliff warning: within 15 units of 100 or 200, from above.
# -----------------------------------------------------------------------------
def cliff_warning(
    bill: Dict[str, Any],
    pro_rate: bool = False,
    window: int = 15,
) -> Optional[Dict[str, Any]]:
    """If units are just over 100 or 200, say how many to cut to save ₹Y."""
    units = _num(bill.get("units"))
    if units is None:
        return None
    days = _num(bill.get("days"))
    load = _num(bill.get("contracted_load_kw")) or 1.0
    customer = _num(bill.get("customer_charges"))
    trueup_u = _num(bill.get("trueup_units"))
    bdate = bill.get("bill_date")

    def _tot(u: float, cat: str) -> float:
        q = quote_bill(
            u, load_kw=load, days=days, category=cat,
            customer_charges=customer, trueup_units=trueup_u,
            bill_date=bdate, pro_rate=pro_rate,
        )
        return q["total"]

    if 100 < units <= 100 + window:
        x = round(units - 100, 1)
        y = round(_tot(units, "1B(i)") - _tot(100, "1A"), 2)
        return {
            "threshold": 100,
            "units_to_cut": x,
            "save_inr": max(0.0, y),
            "from_category": "1B(i)",
            "to_category": "1A",
        }
    if 200 < units <= 200 + window:
        x = round(units - 200, 1)
        y = round(_tot(units, "1B(ii)") - _tot(200, "1B(i)"), 2)
        return {
            "threshold": 200,
            "units_to_cut": x,
            "save_inr": max(0.0, y),
            "from_category": "1B(ii)",
            "to_category": "1B(i)",
        }
    # Approaching a cliff from below (informational; no 'taggiste' save)
    if 100 - window <= units <= 100:
        return {
            "threshold": 100,
            "units_to_cut": 0,
            "units_headroom": round(100 - units, 1),
            "save_inr": None,
            "from_category": "1A",
            "to_category": "1B(i)",
            "approaching": True,
        }
    if 200 - window <= units <= 200:
        return {
            "threshold": 200,
            "units_to_cut": 0,
            "units_headroom": round(200 - units, 1),
            "save_inr": None,
            "from_category": "1B(i)",
            "to_category": "1B(ii)",
            "approaching": True,
        }
    return None


def estimate_next_with_trueup(
    bill: Dict[str, Any],
    pro_rate: bool = False,
) -> Optional[Dict[str, Any]]:
    """Anchana: scale this bill's energy to 30 days, carry fixed/customer/ED,
    and add next-cycle true-up at 50p (after Nov 2026) on FY22-23 units."""
    units = _num(bill.get("units"))
    days = _num(bill.get("days"))
    energy = _num(bill.get("energy_charges"))
    if not units or not days or days <= 0 or energy is None or units <= 0:
        return None
    est_units = (units / days) * 30
    epu = energy / units
    est_energy = round(est_units * epu, 2)
    other = (
        (_num(bill.get("fixed_charges")) or 0)
        + (_num(bill.get("customer_charges")) or 0)
        + (_num(bill.get("electricity_duty")) or 0)
    )
    tu_units = _num(bill.get("trueup_units"))
    next_rate = trueup_rate_for_next_bill(bill.get("bill_date"))
    tu = trueup_charges(tu_units, rate=next_rate) if tu_units else 0.0
    total = round(est_energy + other + tu, 2)
    return {
        "est_units_30d": round(est_units, 1),
        "est_energy": est_energy,
        "est_other": round(other, 2),
        "est_trueup": tu,
        "est_trueup_rate": next_rate,
        "est_trueup_units": tu_units,
        "est_total": total,
        "note": (
            f"anchana; next-cycle true-up at {int(next_rate*100)}p"
            " on FY 2022-23 units (not this month's usage); "
            "excludes Delayed Payment Surcharge (assumes on-time payment)"
        ),
    }

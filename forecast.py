"""Next-month unit/rupee forecast from a customer's own bill history.

Pure Python, no LLM. Short history falls back gracefully.

Method
------
likely units = blend of:
  (a) seasonal: same month last year, scaled by the YoY ratio of the
      most recent overlapping months (up to 3);
  (b) recent trend: last month plus the average month-to-month change
      over the last up to 3 months before the target.

Weights: 0.55 seasonal + 0.45 trend when both exist; otherwise whichever
is available; with only one month, likely = that month's units (scaled
to 30 days if days are known and != 30).

Range (low/high) is likely ± half-width, where half-width is
max(12% of likely, |seasonal − trend| / 2, 8 units), or ±20% when only
one month is available. low is clamped at 0.

Rupees go through tariff.quote_bill. Category is inferred from the
forecast units. True-up uses 50p from Dec 2026 on the FY 2022-23 units
printed on the bill (not this month's usage). Customer charge is taken
from the current bill unless the inferred category changes, in which
case a typical observed charge for that category is used (assumption).

Backtest: rolling one-step-ahead over the history (need at least one
prior month). MAE in units and rupees, and % of actuals inside [low, high].
"""
from __future__ import annotations

import math

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from tariff import (
    infer_category,
    parse_bill_date,
    quote_bill,
    trueup_rate_for_bill_date,
    customer_charges_for_units,
)

SEASONAL_WEIGHT = 0.55
TREND_WEIGHT = 0.45
MIN_HALF_WIDTH_UNITS = 8.0
PCT_HALF_WIDTH = 0.12
SHORT_HISTORY_PCT = 0.20

# Customer charges for forecast quotes: official LT-I table in tariff.customer_charges_for_units.

MONTH_ALIASES = {
    "jan": 1, "january": 1, "januari": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def _num(v: Any) -> Optional[float]:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _month_num(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        m = int(v)
        return m if 1 <= m <= 12 else None
    s = str(v).strip().lower().replace(".", "")
    if s.isdigit():
        m = int(s)
        return m if 1 <= m <= 12 else None
    return MONTH_ALIASES.get(s[:3] if s[:3] in MONTH_ALIASES else s)


def normalize_history(raw: Any) -> List[Dict[str, Any]]:
    """Accept a list of dicts or a month→units map; drop unreadable rows. Do not invent."""
    if not raw:
        return []
    rows: List[Dict[str, Any]] = []
    if isinstance(raw, dict) and not any(k in raw for k in ("units", "kwh", "year", "month")):
        # {"Nov-2025": 148, "2026-01": 82} or {"2025-11": 148}
        items = raw.items()
        parsed = []
        for k, v in items:
            y, m = _parse_month_label(k)
            u = _num(v) if not isinstance(v, dict) else _num((v or {}).get("units"))
            est = bool((v or {}).get("estimated")) if isinstance(v, dict) else False
            if y and m and u is not None and u >= 0:
                parsed.append({"year": y, "month": m, "units": float(u), "estimated": est})
        rows = parsed
    elif isinstance(raw, (list, tuple)):
        for item in raw:
            if not isinstance(item, dict):
                continue
            y = item.get("year")
            m = _month_num(item.get("month") or item.get("mon"))
            if y is None and item.get("label"):
                y, m2 = _parse_month_label(item.get("label"))
                m = m or m2
            try:
                y = int(y) if y is not None else None
            except (TypeError, ValueError):
                y = None
            if y is not None and y < 100:
                y += 2000
            u = _num(item.get("units") if item.get("units") is not None else item.get("kwh"))
            if y is None or m is None or u is None or u < 0:
                continue
            row = {
                "year": int(y),
                "month": int(m),
                "units": float(u),
                "estimated": bool(item.get("estimated") or item.get("average") or item.get("avg_billed")),
                "label": item.get("label"),
            }
            amt = _num(item.get("amount") if item.get("amount") is not None else item.get("bill_amount"))
            if amt is not None:
                row["amount"] = amt
            if item.get("source"):
                row["source"] = item.get("source")
            rows.append(row)
    # unique by (year, month), last write wins, chronological
    uniq: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for r in rows:
        uniq[(r["year"], r["month"])] = r
    return [uniq[k] for k in sorted(uniq)]


def _parse_month_label(label: Any) -> Tuple[Optional[int], Optional[int]]:
    if label is None:
        return None, None
    s = str(label).strip()
    import re
    m = re.search(r"(20\d{2}|'\d{2}|\d{2})[-/\s](\d{1,2})", s)
    if m and int(m.group(2)) <= 12:
        y = int(m.group(1).replace("'", ""))
        if y < 100:
            y += 2000
        return y, int(m.group(2))
    m = re.search(r"([A-Za-z]{3,9})[-/\s,]*(\d{2,4})", s)
    if m:
        mon = _month_num(m.group(1))
        y = int(m.group(2))
        if y < 100:
            y += 2000
        return y, mon
    m = re.search(r"(\d{1,2})[-/\s](\d{4})", s)
    if m and int(m.group(1)) <= 12:
        return int(m.group(2)), int(m.group(1))
    return None, None


def history_from_bill(bill: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize printed history and append the current bill month if missing."""
    hist = normalize_history(bill.get("unit_history") or bill.get("consumption_history"))
    units = _num(bill.get("units"))
    dt = parse_bill_date(bill.get("bill_date")) or parse_bill_date(bill.get("present_reading_date"))
    if units is not None and dt is not None:
        key = (dt.year, dt.month)
        have = {(p["year"], p["month"]) for p in hist}
        if key not in have:
            hist.append({
                "year": dt.year,
                "month": dt.month,
                "units": float(units),
                "estimated": False,
                "label": "current",
            })
            hist.sort(key=lambda p: (p["year"], p["month"]))
        else:
            # prefer the actual current units over a stale history row
            for p in hist:
                if (p["year"], p["month"]) == key:
                    p["units"] = float(units)
                    p["estimated"] = False
    return hist


def _lookup(hist: Sequence[Dict[str, Any]], year: int, month: int) -> Optional[float]:
    for p in hist:
        if p["year"] == year and p["month"] == month:
            return float(p["units"])
    return None


def _shift(year: int, month: int, delta: int) -> Tuple[int, int]:
    i = year * 12 + (month - 1) + delta
    return i // 12, i % 12 + 1


def _recent_window(hist: Sequence[Dict[str, Any]], target_y: int, target_m: int, width: int = 3) -> List[Dict[str, Any]]:
    """Up to `width` calendar months immediately before the target, that exist in hist."""
    out = []
    for d in range(1, 12):
        y, m = _shift(target_y, target_m, -d)
        u = _lookup(hist, y, m)
        if u is not None:
            out.append({"year": y, "month": m, "units": u})
        if len(out) >= width:
            break
    out.reverse()
    return out


def _mean(xs: Sequence[float]) -> Optional[float]:
    return (sum(xs) / len(xs)) if xs else None


def _seasonal_prediction(hist: Sequence[Dict[str, Any]], target_y: int, target_m: int) -> Optional[float]:
    smly = _lookup(hist, target_y - 1, target_m)
    if smly is None:
        return None
    recent = _recent_window(hist, target_y, target_m, width=3)
    if not recent:
        return float(smly)
    prior = []
    for p in recent:
        u = _lookup(hist, p["year"] - 1, p["month"])
        if u is not None:
            prior.append((p["units"], u))
    if prior:
        rec_avg = _mean([a for a, _ in prior])
        old_avg = _mean([b for _, b in prior])
        if rec_avg is not None and old_avg and old_avg > 0:
            return float(smly) * (rec_avg / old_avg)
    return float(smly)


def _trend_prediction(hist: Sequence[Dict[str, Any]], target_y: int, target_m: int) -> Optional[float]:
    recent = _recent_window(hist, target_y, target_m, width=3)
    if not recent:
        return None
    if len(recent) == 1:
        return float(recent[0]["units"])
    slope = (recent[-1]["units"] - recent[0]["units"]) / (len(recent) - 1)
    return float(recent[-1]["units"] + slope)


def forecast_units(
    history: Any,
    target_year: Optional[int] = None,
    target_month: Optional[int] = None,
    current_days: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Return low/likely/high units and method, or None if no history."""
    hist = normalize_history(history) if not (
        history and isinstance(history, list) and history and "year" in history[0]
    ) else list(history)
    # if already normalized list without going through normalize (missing keys) — still normalize
    if history is not None:
        hist = normalize_history(history) or hist
        # If hist was already a clean list of dicts, normalize_history will re-parse it.
        if not hist and history:
            hist = [dict(p) for p in history if isinstance(p, dict) and p.get("units") is not None]

    hist = normalize_history(history)
    if not hist:
        return None

    last = hist[-1]
    if target_year is None or target_month is None:
        target_year, target_month = _shift(last["year"], last["month"], 1)

    seasonal = _seasonal_prediction(hist, target_year, target_month)
    trend = _trend_prediction(hist, target_year, target_month)

    # Single-month fallback: optionally scale to 30 days
    if seasonal is None and trend is None:
        return None
    if seasonal is None and trend is not None and len(hist) == 1 and current_days and current_days > 0:
        trend = trend * 30.0 / float(current_days)

    if seasonal is not None and trend is not None:
        likely = SEASONAL_WEIGHT * seasonal + TREND_WEIGHT * trend
        method = "blend_seasonal_trend"
    elif seasonal is not None:
        likely = seasonal
        method = "same_month_last_year"
    else:
        likely = trend
        method = "recent_trend" if len(_recent_window(hist, target_year, target_month, 3)) >= 2 else "last_month"

    likely = max(0.0, float(likely))
    if method == "last_month" or (seasonal is None and len(hist) == 1):
        half = max(MIN_HALF_WIDTH_UNITS, SHORT_HISTORY_PCT * likely)
        method = "last_month"
    else:
        spread = abs((seasonal or likely) - (trend or likely)) / 2.0
        half = max(MIN_HALF_WIDTH_UNITS, PCT_HALF_WIDTH * likely, spread)

    low = max(0.0, likely - half)
    high = likely + half
    return {
        "target_year": target_year,
        "target_month": target_month,
        "likely": round(likely, 1),
        "low": round(low, 1),
        "high": round(high, 1),
        "method": method,
        "seasonal": None if seasonal is None else round(float(seasonal), 1),
        "trend": None if trend is None else round(float(trend), 1),
        "n_history": len(hist),
        "half_width": round(half, 1),
    }


def customer_charge_for(bill: Dict[str, Any], units: float) -> float:
    """Official RST customer charge for the *forecast* units.

    Extracted bill values are used only when rendering the current bill
    (quote_bill still prefers a provided customer_charges). Forecast quotes
    use the official unit-band table so a category/band change is priced
    correctly. DPS is not included (on-time assumption).
    """
    return customer_charges_for_units(units)


def _quote_for_units(
    units: float,
    bill: Dict[str, Any],
    bill_date: Any,
    days: float = 30,
) -> Dict[str, Any]:
    load = _num(bill.get("contracted_load_kw")) or 1.0
    tu_u = _num(bill.get("trueup_units"))
    cust = customer_charge_for(bill, units)
    return quote_bill(
        units,
        load_kw=load,
        days=days,
        category=None,  # infer from units
        customer_charges=cust,
        trueup_units=tu_u,
        bill_date=bill_date,
        pro_rate=False,
    )


def _next_month_date(bill: Dict[str, Any]) -> date:
    dt = parse_bill_date(bill.get("bill_date")) or parse_bill_date(bill.get("present_reading_date"))
    if dt is None:
        return date(2026, 12, 1)
    y, m = _shift(dt.year, dt.month, 1)
    return date(y, m, 1)


def forecast_bill(
    bill: Dict[str, Any],
    history: Any = None,
    target_year: Optional[int] = None,
    target_month: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Units range + rupee quotes (true-up at the rate for the *next* bill date)."""
    hist = history_from_bill(bill) if history is None else normalize_history(history)
    if history is None:
        pass
    elif not hist:
        hist = history_from_bill(bill)
    # If a standalone history was passed, still merge current month from the bill
    if history is not None:
        merged = dict(bill)
        merged["unit_history"] = hist
        hist = history_from_bill(merged)

    fc = forecast_units(hist, target_year, target_month, current_days=_num(bill.get("days")))
    if not fc:
        # last-ditch: current units only
        u = _num(bill.get("units"))
        if u is None:
            return None
        avg = _num(bill.get("average_month_units"))
        base = avg if avg else u
        days = _num(bill.get("days"))
        if avg is None and days and days > 0 and abs(days - 30) > 0.5:
            base = u * 30.0 / days
        fc = {
            "target_year": target_year,
            "target_month": target_month,
            "likely": round(base, 1),
            "low": round(max(0.0, base * (1 - SHORT_HISTORY_PCT)), 1),
            "high": round(base * (1 + SHORT_HISTORY_PCT), 1),
            "method": "average_month_units" if avg else "last_month",
            "seasonal": None,
            "trend": None if avg else round(base, 1),
            "n_history": 1,
            "half_width": round(SHORT_HISTORY_PCT * base, 1),
        }
        nxt = _next_month_date(bill)
        if fc["target_year"] is None:
            fc["target_year"], fc["target_month"] = nxt.year, nxt.month

    nxt = date(fc["target_year"], fc["target_month"], 1)
    quotes = {}
    for key in ("low", "likely", "high"):
        quotes[key] = _quote_for_units(fc[key], bill, nxt, days=30)
    return {
        **fc,
        "quotes": quotes,
        "trueup_rate": trueup_rate_for_bill_date(nxt),
        "trueup_units": _num(bill.get("trueup_units")),
        "next_bill_date": nxt.isoformat(),
        "history": hist,
        "history_is_demo": bool(bill.get("history_is_demo")),
    }


def backtest(
    history: Any,
    bill: Optional[Dict[str, Any]] = None,
    min_prior: int = 1,
) -> Dict[str, Any]:
    """Rolling one-step-ahead forecast vs actual, over available history."""
    hist = normalize_history(history)
    bill = bill or {}
    rows = []
    for i in range(min_prior, len(hist)):
        past = hist[:i]
        actual = hist[i]
        fc = forecast_units(past, actual["year"], actual["month"])
        if not fc:
            continue
        actual_u = float(actual["units"])
        err_u = fc["likely"] - actual_u
        within = fc["low"] - 1e-9 <= actual_u <= fc["high"] + 1e-9
        # Rupees: same tariff context, dated as that month (true-up rate follows the date)
        as_of = date(actual["year"], actual["month"], 1)
        q_hat = _quote_for_units(fc["likely"], bill, as_of)
        q_act = _quote_for_units(actual_u, bill, as_of)
        err_r = q_hat["total"] - q_act["total"]
        rows.append({
            "year": actual["year"],
            "month": actual["month"],
            "actual_units": actual_u,
            "estimated_month": bool(actual.get("estimated")),
            "likely": fc["likely"],
            "low": fc["low"],
            "high": fc["high"],
            "method": fc["method"],
            "error_units": round(err_u, 1),
            "abs_error_units": round(abs(err_u), 1),
            "actual_rupees": q_act["total"],
            "likely_rupees": q_hat["total"],
            "abs_error_rupees": round(abs(err_r), 2),
            "within_range": within,
        })

    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "mae_units": None,
            "mae_rupees": None,
            "pct_within_range": None,
            "rows": [],
        }
    def _summ(rs):
        k = len(rs)
        if k == 0:
            return {"n": 0, "mae_units": None, "mae_rupees": None, "pct_within_range": None}
        return {
            "n": k,
            "mae_units": round(sum(r["abs_error_units"] for r in rs) / k, 2),
            "mae_rupees": round(sum(r["abs_error_rupees"] for r in rs) / k, 2),
            "pct_within_range": round(100.0 * sum(1 for r in rs if r["within_range"]) / k, 1),
        }

    mae_u = round(sum(r["abs_error_units"] for r in rows) / n, 2)
    mae_r = round(sum(r["abs_error_rupees"] for r in rows) / n, 2)
    pct = round(100.0 * sum(1 for r in rows if r["within_range"]) / n, 1)
    by_method = {}
    for r in rows:
        by_method.setdefault(r["method"], []).append(r)
    return {
        "n": n,
        "mae_units": mae_u,
        "mae_rupees": mae_r,
        "pct_within_range": pct,
        "by_method": {m: _summ(rs) for m, rs in by_method.items()},
        "rows": rows,
    }


def round_rupee_range(low: Any, high: Any, step: int = 100) -> Optional[Dict[str, Any]]:
    """Round a rupee interval to a clean band (default ₹100), never paise.

    Example: 520.32–791.99 → ₹500–₹800. If the band would collapse, expand
    by one step so the range is still a range.
    """
    if low is None or high is None:
        return None
    try:
        lo = float(low)
        hi = float(high)
    except (TypeError, ValueError):
        return None
    if lo > hi:
        lo, hi = hi, lo
    step = int(step) if step else 100
    rlo = int(math.floor(lo / step) * step)
    rhi = int(math.ceil(hi / step) * step)
    if rhi <= rlo:
        rhi = rlo + step
    return {"low": rlo, "high": rhi, "step": step}


def forecast_display_range(fc: Optional[Dict[str, Any]], step: int = 100) -> Optional[Dict[str, Any]]:
    """Public display range + basis sentence. Precise quotes stay on fc['quotes']."""
    if not fc or not fc.get("quotes"):
        return None
    quotes = fc["quotes"]
    lo = (quotes.get("low") or {}).get("total")
    hi = (quotes.get("high") or {}).get("total")
    rng = round_rupee_range(lo, hi, step=step)
    if not rng:
        return None
    likely = (quotes.get("likely") or {}).get("total")
    src = "నమూనా డేటా" if fc.get("history_is_demo") else "మీ గత బిల్లులు"
    rng["low_exact"] = lo
    rng["high_exact"] = hi
    rng["likely_exact"] = likely
    rng["likely_display"] = round_nearest_rupees(likely)
    rng["basis"] = (
        f"ఈ అంచనా {src} ఆధారంగా, టారిఫ్ FY 2026-27 TGERC. "
        f"సుమారు ₹{rng['low']}–₹{rng['high']} "
        f"(పైసల వరకు కాదు). సమయానికి చెల్లిస్తే ఆలస్య రుసుము లేదు."
    )
    return rng




def round_nearest_rupees(value: Any, step: int = 10) -> Optional[int]:
    """Round a rupee amount to the nearest `step` (default ₹10). No paise."""
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    step = int(step) if step else 10
    return int(round(n / step) * step)


def format_rupee_range(low: Any, high: Any) -> Optional[str]:
    """Consumer-facing range, e.g. '₹600–₹900'."""
    if low is None or high is None:
        return None
    try:
        return f"₹{int(low)}–₹{int(high)}"
    except (TypeError, ValueError):
        return None


def consumer_forecast_range(
    forecast: Optional[Dict[str, Any]] = None,
    forecast_range: Optional[Dict[str, Any]] = None,
    step: int = 100,
) -> Optional[Dict[str, Any]]:
    """The same rounded range the hero card and share PNG use.

    Prefer a full forecast (with quotes) so every surface stays in sync.
    A pre-rounded forecast_range (with a 'step' key) is passed through.
    Raw paise lows/highs are re-banded with round_rupee_range.
    """
    if forecast:
        rng = forecast_display_range(forecast, step=step)
        if rng:
            rng["likely_display"] = round_nearest_rupees(rng.get("likely_exact"))
            return rng
    if forecast_range and forecast_range.get("low") is not None and forecast_range.get("high") is not None:
        if forecast_range.get("step") is not None:
            out = dict(forecast_range)
            if out.get("likely_display") is None:
                out["likely_display"] = round_nearest_rupees(
                    out.get("likely_exact") or out.get("likely")
                )
            return out
        rng = round_rupee_range(forecast_range.get("low"), forecast_range.get("high"), step=step)
        if rng:
            rng["likely_display"] = round_nearest_rupees(
                forecast_range.get("likely_exact") or forecast_range.get("likely")
            )
            return rng
    return None

"""Post-OCR correction rules for TG electricity bills.

Apply AFTER vision extraction and BEFORE self-checks.
Never invent true-up from a ₹10/₹25 surcharge-type amount unless it equals N × 0.30.
Never copy true-up units into consumption units.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from tariff import parse_bill_date

TRUEUP_TOL = 0.5
PLAUSIBLE_UNITS_MAX = 5000
SURCHARGE_TYPICAL = {10, 10.0, 25, 25.0}


def _num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _close(a: Optional[float], b: Optional[float], tol: float = TRUEUP_TOL) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def _is_typical_surcharge(v: Optional[float]) -> bool:
    if v is None:
        return False
    return any(abs(float(v) - s) <= 0.05 for s in SURCHARGE_TYPICAL)


def _leading_digit_variants(value: int) -> List[int]:
    s = str(int(abs(value)))
    if len(s) < 2:
        return []
    rest = s[1:]
    out = []
    for d in range(1, 10):  # keep same number of digits
        new = int(str(d) + rest)
        if new != int(value):
            out.append(new)
    return out


def apply_post_ocr_corrections(bill: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Return a shallow-copied bill plus bilingual auto-correct notes."""
    b = dict(bill)
    notes: List[str] = []

    # ------------------------------------------------------------------
    # 1. True-up: only from FY-2022-23 / PP TRUEUP = N × 0.30
    # ------------------------------------------------------------------
    n = _num(b.get("trueup_units"))
    if n is not None and n <= 0:
        n = None
        b["trueup_units"] = None
    t = _num(b.get("trueup_charges"))
    if t is not None and t == 0:
        t = None
        # leave 0 in place until we maybe replace it
    expected = round(n * 0.30, 2) if n is not None else None

    # Never keep a ₹10/₹25 surcharge-type value as true-up if it doesn't match N×0.30
    if t is not None and _is_typical_surcharge(t) and not _close(t, expected):
        if _num(b.get("surcharge")) in (None, 0):
            b["surcharge"] = t
            notes.append(
                f"auto-correct chesam: ₹{t:.2f} looks like a surcharge (DPS), not PP TRUEUP — moved to surcharge"
                f" / ₹{t:.2f} సర్‌ఛార్జ్ లా ఉంది, true-up కాదు"
            )
        b["trueup_charges"] = None
        t = None

    if expected is None or not _close(t, expected):
        # Fields that sometimes receive the true-up amount by mistake
        candidates = [
            ("surcharge", _num(b.get("surcharge"))),
            ("adjustment", _num(b.get("adjustment"))),
            ("fsa_fca", _num(b.get("fsa_fca"))),
            ("loss_gain", _num(b.get("loss_gain"))),
        ]
        # Also scan units-as-charges? no.
        found_key = None
        found_val = None
        for key, val in candidates:
            if _close(val, expected):
                found_key, found_val = key, val
                break
        # If N is missing, infer N from a candidate that is a clean multiple of 0.30
        # (never from a typical ₹10/₹25 surcharge).
        if found_key is None:
            for key, val in candidates:
                if val is None or val <= 0 or _is_typical_surcharge(val):
                    continue
                q = val / 0.30
                if abs(q - round(q)) <= 0.05:
                    qi = int(round(q))
                    if 1 <= qi <= PLAUSIBLE_UNITS_MAX:
                        found_key, found_val = key, val
                        n = float(qi)
                        expected = round(n * 0.30, 2)
                        b["trueup_units"] = qi
                        break

        if found_key is not None and found_val is not None:
            old_t = t
            b["trueup_charges"] = found_val
            # put the old true-up back only if it looks like a surcharge, else 0
            if found_key == "surcharge":
                if old_t is not None and old_t != 0 and not _close(old_t, expected):
                    b["surcharge"] = old_t
                else:
                    b["surcharge"] = 0
            else:
                # clear the field we stole the true-up from if it was a mislabel
                if old_t is not None and old_t != 0 and not _close(old_t, expected):
                    b[found_key] = old_t
                else:
                    b[found_key] = 0
            t = found_val
            notes.append(
                f"auto-correct chesam: true-up ₹{found_val:.2f} was in {found_key}; "
                f"moved to PP TRUEUP ({n:g} × 0.30 = ₹{expected:.2f})"
                f" / true-up {found_key} నుండి PP TRUEUP కి మార్చాం"
            )

    # ------------------------------------------------------------------
    # 2. Readings: if present < previous, swap
    # ------------------------------------------------------------------
    prev = _num(b.get("prev_reading"))
    pres = _num(b.get("present_reading"))
    if prev is not None and pres is not None and pres < prev:
        b["prev_reading"], b["present_reading"] = pres, prev
        prev, pres = pres, prev
        notes.append(
            "auto-correct chesam: swapped present/previous readings (present was < previous)"
            " / ప్రెజెంట్ < ప్రివియస్ కాబట్టి రీడింగ్స్ కూర్చాం"
        )

    extracted_units = _num(b.get("units"))

    # ------------------------------------------------------------------
    # 3. Leading-digit misreads (only if delta is implausible)
    # ------------------------------------------------------------------
    if prev is not None and pres is not None:
        delta = pres - prev
        if (delta < 0 or delta > PLAUSIBLE_UNITS_MAX) and extracted_units is not None:
            target = extracted_units
            if 0 <= target <= PLAUSIBLE_UNITS_MAX:
                matches: List[Tuple[str, int, int]] = []
                for new_prev in _leading_digit_variants(int(prev)):
                    d = pres - new_prev
                    if _close(d, target, tol=0.05) and 0 <= d <= PLAUSIBLE_UNITS_MAX:
                        matches.append(("prev_reading", new_prev, int(d)))
                for new_pres in _leading_digit_variants(int(pres)):
                    d = new_pres - prev
                    if _close(d, target, tol=0.05) and 0 <= d <= PLAUSIBLE_UNITS_MAX:
                        matches.append(("present_reading", new_pres, int(d)))
                if len(matches) == 1:
                    field, new_val, d = matches[0]
                    old = b[field]
                    b[field] = new_val
                    if field == "prev_reading":
                        prev = float(new_val)
                    else:
                        pres = float(new_val)
                    notes.append(
                        f"auto-correct chesam: leading digit on {field} {old:g} → {new_val} "
                        f"so units={d}"
                        f" / {field} మొదటి అంకె సరిచేసాం"
                    )

    # ------------------------------------------------------------------
    # 4. Units: never fall back to true-up units; prefer reading difference
    # ------------------------------------------------------------------
    n = _num(b.get("trueup_units"))  # may still be used for the copy-detect
    prev = _num(b.get("prev_reading"))
    pres = _num(b.get("present_reading"))
    units = _num(b.get("units"))

    reading_delta = None
    if prev is not None and pres is not None:
        reading_delta = pres - prev

    # If units was clearly copied from true-up units and we have no reliable readings
    if (
        units is not None
        and n is not None
        and _close(units, n, tol=0.05)
        and (reading_delta is None or not (0 <= reading_delta <= PLAUSIBLE_UNITS_MAX) or not _close(units, reading_delta, 0.05))
    ):
        b["units"] = None
        units = None
        notes.append(
            f"auto-correct chesam: units {n:g} was copied from true-up units — set to null (don't guess)"
            " / యూనిట్లు true-up నుండి కాపీ అయ్యాయి, null పెట్టాం"
        )

    # units <= 0 is not readable when energy charges are present
    energy = _num(b.get("energy_charges"))
    if units is not None and units <= 0 and energy and energy > 0:
        b["units"] = None
        units = None
        notes.append(
            "auto-correct chesam: units was 0 but energy charges are present — set to null (don't guess)"
            " / యూనిట్లు 0 గా వచ్చాయి, కరెంట్ ఛార్జీ ఉంది కాబట్టి null పెట్టాం"
        )

    if reading_delta is not None and 0 < reading_delta <= PLAUSIBLE_UNITS_MAX:
        rd = int(reading_delta) if float(reading_delta) == int(reading_delta) else reading_delta
        if units is None:
            b["units"] = rd
            notes.append(
                f"auto-correct chesam: units set from readings ({_fmt(pres)} − {_fmt(prev)} = {rd})"
                f" / యూనిట్లు రీడింగ్ తేడా నుండి పెట్టాం"
            )
        elif not _close(units, reading_delta, 0.05):
            b["units"] = rd
            notes.append(
                f"auto-correct chesam: extracted units {units:g} disagreed with readings "
                f"({_fmt(pres)} − {_fmt(prev)} = {rd}); preferred the reading difference"
                f" / యూనిట్లు రీడింగ్ తేడాతో సరిపోలలేదు, తేడానే తీసుకున్నాం"
            )

    # ------------------------------------------------------------------
    # 5. Old layout: payable = Net Amount / Total Due (rounded)
    # ------------------------------------------------------------------
    printed = _num(b.get("bill_amount"))
    net = _num(b.get("total_due"))
    if net is not None and printed is not None and not _close(printed, net, tol=0.005):
        # typical: bill 514.37, net 514.00 (rounding / loss-gain)
        if abs(printed - net) <= 1.0 or abs(round(printed) - net) <= 0.05 or abs(printed - round(net)) <= 0.05:
            b["bill_amount_printed"] = printed
            b["bill_amount"] = net
            notes.append(
                f"auto-correct chesam: payable bill_amount set to Net/Total ₹{net:.2f}; "
                f"printed Bill Amount kept as ₹{printed:.2f}"
                f" / చెల్లించాల్సింది Net Amount ₹{net:.2f}"
            )

    # ------------------------------------------------------------------
    # 6. Alias reading-date / ACD / history keys; compute days; due-date safety
    # ------------------------------------------------------------------
    _alias = {
        "previous_reading_date": "prev_reading_date",
        "prev_date": "prev_reading_date",
        "current_reading_date": "present_reading_date",
        "present_date": "present_reading_date",
        "acd_surcharge": "acd_surcharge",
        "acd": "acd_due",
        "acd_charges": "acd_due",
        "consumption_history": "unit_history",
        "avg_month_units": "average_month_units",
    }
    for src, dst in _alias.items():
        if b.get(dst) in (None, "") and b.get(src) not in (None, ""):
            b[dst] = b[src]

    # Normalize history if present — never invent rows
    raw_hist = b.get("unit_history")
    if raw_hist:
        try:
            from forecast import normalize_history
            norm = normalize_history(raw_hist)
            b["unit_history"] = norm or None
        except Exception:
            pass

    from late_reading import resolve_billing_days, apply_due_date_safety

    resolved = resolve_billing_days(b)
    if resolved.get("days") is not None:
        printed = resolved.get("printed_days")
        if printed is None:
            b["days"] = resolved["days"]
            b["days_source"] = resolved["source"]
            notes.append(
                f"auto-correct chesam: days {resolved['days']} set from reading dates"
                f" / రోజులు రీడింగ్ తేదీల నుండి పెట్టాం"
            )
        elif resolved.get("source") == "reading_dates" and printed != resolved["days"]:
            b["days"] = resolved["days"]
            b["days_source"] = resolved["source"]
            if resolved.get("note"):
                notes.append("auto-correct chesam: " + resolved["note"] + " / రోజులు రీడింగ్ తేదీల నుండి సరిచేసాం")
        else:
            b["days"] = resolved["days"]
            b["days_source"] = resolved["source"]
            if resolved.get("note"):
                notes.append("auto-correct chesam: " + resolved["note"])

    b, due_note = apply_due_date_safety(b)
    if due_note:
        notes.append(
            "auto-correct chesam: " + due_note
            + " / డ్యూ డేట్ బిల్లు తేదీకి సరిపోలలేదు, తీసివేసాం"
        )

    return b, notes


def _fmt(v: Optional[float]) -> str:
    if v is None:
        return "?"
    if float(v) == int(v):
        return str(int(v))
    return f"{v:g}"

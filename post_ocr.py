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


DPS_SNAP_TOL = 1.0  # rupees — OCR slip around a known ₹10 / ₹25 DPS


def snap_typical_surcharge(bill: Dict[str, Any], notes: Optional[List[str]] = None) -> Tuple[Dict[str, Any], List[str]]:
    """Snap DPS/surcharge to ₹10 or ₹25 when it is within ±₹1 of one of them."""
    b = dict(bill)
    notes = list(notes or [])
    v = _num(b.get("surcharge"))
    if v is None or abs(v) < 0.005 or _is_typical_surcharge(v):
        return b, notes
    hits = [(s, abs(float(v) - s)) for s in SURCHARGE_TYPICAL if abs(float(v) - s) <= DPS_SNAP_TOL]
    if not hits:
        return b, notes
    hits.sort(key=lambda x: x[1])
    if len(hits) > 1 and abs(hits[0][1] - hits[1][1]) < 0.005:
        return b, notes
    snapped = float(hits[0][0])
    b["surcharge"] = snapped
    notes.append(
        f"auto-correct chesam: surcharge ₹{v:.2f} snapped to typical DPS ₹{snapped:.2f}"
        f" / ఆలస్య రుసుము ₹{snapped:.2f} కి సరిచేసాం"
    )
    return b, notes


# Line items that add toward the printed bill (subsidy is subtracted).
SUM_KEYS = (
    "energy_charges", "fixed_charges", "customer_charges", "electricity_duty",
    "interest_on_ed", "surcharge", "trueup_charges", "fsa_fca", "adjustment",
    "interest_on_cd", "loss_gain",
)
# Prefer to keep these if a duplicate must be dropped.
KEEP_PRIORITY = {
    "energy_charges": 0,
    "fixed_charges": 1,
    "customer_charges": 2,
    "electricity_duty": 3,
    "trueup_charges": 4,
    "loss_gain": 5,
    "surcharge": 6,
    "fsa_fca": 7,
    "adjustment": 8,
    "interest_on_ed": 9,
}
# Optional / often-zero lines we may set to 0 when that uniquely fixes the sum.
OPTIONAL_ZERO_KEYS = ("surcharge", "fsa_fca", "adjustment", "interest_on_ed")
SUM_MATCH_TOL = 1.0  # rupees


def line_sum(bill: Dict[str, Any]) -> float:
    """Signed sum of charge lines minus subsidy. 0 is kept; only None is skipped."""
    total = 0.0
    for k in SUM_KEYS:
        v = _num(bill.get(k))
        if v is not None:
            total += v
    sub = _num(bill.get("subsidy"))
    if sub:
        total -= sub
    return round(total, 2)


def printed_bill_amount(bill: Dict[str, Any]) -> Optional[float]:
    for k in ("bill_amount", "bill_amount_printed", "total_due"):
        v = _num(bill.get(k))
        if v is not None:
            return v
    return None


def _sum_matches(bill: Dict[str, Any], printed: float, tol: float = SUM_MATCH_TOL) -> bool:
    return abs(line_sum(bill) - printed) <= tol


def _priority(key: str) -> int:
    return KEEP_PRIORITY.get(key, 50)


def reconcile_line_sum(bill: Dict[str, Any], notes: Optional[List[str]] = None) -> Tuple[Dict[str, Any], List[str]]:
    """Fix duplicated or extra line items when the printed total does not add up.

    If one component equals another (e.g. surcharge copied from PP TRUEUP) or
    setting exactly one optional component to 0 makes the sum match within ₹1,
    auto-correct and record a note. Genuine unexplained mismatches are left
    for self-checks / the 1912 warning.
    Also snaps Loss/Gain to a residual of at most ₹1 (rounding).
    """
    b = dict(bill)
    notes = list(notes or [])
    printed = printed_bill_amount(b)
    if printed is None:
        return b, notes

    # Snap a near-DPS surcharge before any Loss/Gain residual is computed,
    # so a ₹0.20 slip cannot be absorbed into rounding.
    b, notes = snap_typical_surcharge(b, notes)

    if not _sum_matches(b, printed):
        # (a) duplicated value across two lines — drop the lower-priority copy
        values = {k: _num(b.get(k)) for k in SUM_KEYS}
        trials: List[str] = []
        seen_pairs = set()
        for k1, v1 in values.items():
            if v1 is None or abs(v1) <= 0.005:
                continue
            for k2, v2 in values.items():
                if k2 <= k1 or v2 is None:
                    continue
                if not _close(v1, v2, tol=0.05):
                    continue
                drop = k1 if _priority(k1) > _priority(k2) else k2
                if drop in seen_pairs:
                    continue
                seen_pairs.add(drop)
                trial = dict(b)
                trial[drop] = 0
                if _sum_matches(trial, printed):
                    trials.append(drop)
        # Prefer dropping surcharge when it is a copy of true-up
        if "surcharge" in trials:
            trials = ["surcharge"]
        elif len(set(trials)) == 1:
            trials = [trials[0]]
        else:
            trials = list(dict.fromkeys(trials))
            if len(trials) != 1:
                trials = []
        if len(trials) == 1:
            drop = trials[0]
            old = _num(b.get(drop))
            b[drop] = 0
            notes.append(
                f"auto-correct chesam: {drop} ₹{old:.2f} was a duplicate of another line; "
                f"set to ₹0 so charges sum to ₹{printed:.2f}"
                f" / {drop} ఒకే మొత్తం రెండు లైన్లలో వచ్చింది, ₹0 పెట్టాం"
            )

        # (b) setting exactly one optional component to 0 uniquely fixes the sum
        if not _sum_matches(b, printed):
            zero_hits = []
            for k in OPTIONAL_ZERO_KEYS:
                v = _num(b.get(k))
                if v is None or abs(v) <= 0.005:
                    continue
                # Keep a typical ₹10/₹25 DPS unless it is clearly a duplicate
                # (already handled above). Do not wipe a real late-payment fee.
                if k == "surcharge" and _is_typical_surcharge(v):
                    continue
                trial = dict(b)
                trial[k] = 0
                if _sum_matches(trial, printed):
                    zero_hits.append(k)
            if len(zero_hits) == 1:
                k = zero_hits[0]
                old = _num(b.get(k))
                b[k] = 0
                notes.append(
                    f"auto-correct chesam: {k} ₹{old:.2f} set to ₹0 so charges sum to ₹{printed:.2f}"
                    f" / {k} ₹0 పెట్టాం, మొత్తం సరిపోయింది"
                )

    # (c) Loss/Gain rounding residual (at most ₹1)
    if _sum_matches(b, printed):
        current_lg = _num(b.get("loss_gain"))
        without = line_sum({**b, "loss_gain": 0})
        residual = round(printed - without, 2)
        if abs(residual) <= SUM_MATCH_TOL:
            if current_lg is None or not _close(current_lg, residual, tol=0.005):
                # Only write a tiny rounding residual; don't invent a missing charge.
                b["loss_gain"] = residual
                if current_lg is None or not _close(current_lg, residual, tol=0.05):
                    notes.append(
                        f"auto-correct chesam: Loss/Gain set to ₹{residual:.2f} so the rounding "
                        f"matches the printed bill ₹{printed:.2f}"
                        f" / రౌండింగ్ (Loss/Gain) ₹{residual:.2f} పెట్టాం"
                    )

    return b, notes


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
    try:
        from tariff import trueup_rate_for_bill_date
        tu_rate = float(trueup_rate_for_bill_date(b.get("bill_date")))
    except Exception:
        tu_rate = 0.30
    expected = round(n * tu_rate, 2) if n is not None else None

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
                for rate in (0.30, 0.50):
                    q = val / rate
                    if abs(q - round(q)) <= 0.05:
                        qi = int(round(q))
                        if 1 <= qi <= PLAUSIBLE_UNITS_MAX:
                            found_key, found_val = key, val
                            n = float(qi)
                            expected = round(n * rate, 2)
                            tu_rate = rate
                            b["trueup_units"] = qi
                            break
                if found_key is not None:
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
                f"moved to PP TRUEUP ({n:g} × {tu_rate:.2f} = ₹{expected:.2f})"
                f" / true-up {found_key} నుండి PP TRUEUP కి మార్చాం"
            )

    # If FY units were read but the amount is missing or 0, recompute
    # units × official paise (30p in Nov 2026, 50p from December) — unless
    # the printed total already matches with a zero true-up.
    t = _num(b.get("trueup_charges"))
    n = _num(b.get("trueup_units"))
    if n is not None and n > 0 and (t is None or abs(t) < 0.005):
        try:
            from tariff import trueup_rate_for_bill_date
            tu_rate = float(trueup_rate_for_bill_date(b.get("bill_date")))
        except Exception:
            tu_rate = 0.30
        expected = round(float(n) * tu_rate, 2)
        printed_now = printed_bill_amount(b)
        trial_zero = dict(b)
        trial_zero["trueup_charges"] = 0.0
        already_ok = printed_now is not None and _sum_matches(trial_zero, printed_now)
        if already_ok:
            if t is None:
                b["trueup_charges"] = 0.0
        elif expected > 0:
            b["trueup_charges"] = expected
            notes.append(
                f"auto-correct chesam: true-up amount missing/0; "
                f"set to {n:g} × {tu_rate:.2f} = ₹{expected:.2f}"
                f" / ట్రూ-అప్ {n:g} × {int(round(tu_rate*100))}పైసలు పెట్టాం"
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
    # 2b. Thermal layout: days-as-units + energy-guided reading repair
    # ------------------------------------------------------------------
    from thermal_repair import repair_days_units_swap, repair_readings_from_energy
    raw_days = _num(b.get("days"))
    b = repair_days_units_swap(b, notes, raw_days=raw_days)
    b = repair_readings_from_energy(b, notes)
    prev = _num(b.get("prev_reading"))
    pres = _num(b.get("present_reading"))
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
            # Prefer the reading delta only when it explains the energy charges
            # (or the current units do not). A compressed thermal photo can
            # yield a plausible but wrong delta that must not overwrite
            # energy-consistent units (e.g. Days=154, energy ₹599.20).
            from thermal_repair import energy_matches
            energy = _num(b.get("energy_charges"))
            cat = b.get("category")
            if energy_matches(reading_delta, energy, cat) or not energy_matches(units, energy, cat):
                b["units"] = rd
                notes.append(
                    f"auto-correct chesam: extracted units {units:g} disagreed with readings "
                    f"({_fmt(pres)} − {_fmt(prev)} = {rd}); preferred the reading difference"
                    f" / యూనిట్లు రీడింగ్ తేడాతో సరిపోలలేదు, తేడానే తీసుకున్నాం"
                )
            else:
                notes.append(
                    f"auto-correct chesam: kept units {units:g} because energy charges match "
                    f"it, not the reading difference {rd:g}"
                    f" / రీడింగ్ తేడా కాదు, ఎనర్జీకి సరిపోయే యూనిట్లు ఉంచాం"
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

    # ------------------------------------------------------------------
    # 6b. Thermal column-shift + arrears snap (needs final units)
    # ------------------------------------------------------------------
    from thermal_repair import repair_thermal_label_shift, snap_arrears
    b = repair_thermal_label_shift(b, notes)
    b = snap_arrears(b, notes)
    # Snap a 5–10 paise true-up OCR slip to N × official rate when N is known.
    n = _num(b.get("trueup_units"))
    t = _num(b.get("trueup_charges"))
    if n and t is not None and n > 0:
        try:
            from tariff import trueup_rate_for_bill_date
            rate = float(trueup_rate_for_bill_date(b.get("bill_date")))
        except Exception:
            rate = 0.30
        expected = round(n * rate, 2)
        if 0.005 < abs(t - expected) <= 0.10:
            b["trueup_charges"] = expected
            notes.append(
                f"auto-correct chesam: true-up ₹{t:.2f} snapped to ₹{expected:.2f} "
                f"({n:g} × {rate:.2f}) / ట్రూ-అప్ పైసలు సరిచేసాం"
            )

    # ------------------------------------------------------------------
    # 6c. Canonical category slab (drop title leaks / bare "DOMESTIC")
    # ------------------------------------------------------------------
    from tariff import normalize_extracted_category, category_label_is_specific
    raw_cat = b.get("category")
    units_now = _num(b.get("units"))
    if units_now is not None or category_label_is_specific(raw_cat):
        new_cat = normalize_extracted_category(raw_cat, units_now)
        if raw_cat != new_cat:
            b["category"] = new_cat
            if raw_cat and not category_label_is_specific(raw_cat):
                notes.append(
                    f"auto-correct chesam: category '{raw_cat}' is not a slab label; "
                    f"inferred {new_cat} from units"
                    f" / కేటగిరీ {new_cat} యూనిట్ల నుండి పెట్టాం"
                )
            else:
                b["category"] = new_cat

    # ------------------------------------------------------------------
    # 7. Reconcile line-item sum vs printed bill (duplicates, optional zeros,
    #    Loss/Gain rounding). Must run after other field moves.
    # ------------------------------------------------------------------
    b, notes = reconcile_line_sum(b, notes)

    return b, notes


def _fmt(v: Optional[float]) -> str:
    if v is None:
        return "?"
    if float(v) == int(v):
        return str(int(v))
    return f"{v:g}"


def payable_amount(bill: Dict[str, Any]) -> Optional[float]:
    from bill_lines import payable_amount as _payable
    return _payable(bill)

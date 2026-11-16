"""Gruha Jyothi (free power up to 200 units) — consumer self-declared checkbox.

Rules used (TGERC O.P.No.6 of 2024 dated 16.03.2024, quoting
G.O.Ms.No.7 Energy (Power.I) dated 26.02.2024):
  * "free electricity of up to 200 units of domestic consumption per month
    for one service connection" (white ration card + Aadhaar + Praja Palana).
  * "Each eligible household whose consumption for a particular month is up
    to 200 units will receive a zero bill for that month."
  * The order does not itemise components (a *zero bill*), says nothing
    about arrears / ACD, and does not cover the 2026 true-up (it predates
    the TGERC true-up order of 05.10.2026).

App logic (pure, no Streamlit):
  1. A printed Subsidy line on the bill always wins over the checkbox.
  2. Ticked and units <= 200, no printed subsidy → subsidised view: this
     month's Bill Amount would be a zero bill; arrears / ACD stay payable.
     True-up: DISCOM statements of Nov 2026 say the government bears it too
     (not in the GO) — worded cautiously.
  3. Ticked and units > 200 → the WHOLE bill is payable (not only the
     units above 200).
  4. Forecast warning when the next-month estimate is 196–200 units
     (or crosses 200 from a bill that is still within 200).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from bill_lines import effective_arrears, payable_amount

GJ_CAP_UNITS = 200
GJ_WARN_FROM_UNITS = 196

GJ_CHECKBOX_LABEL_TE = "నాకు గృహ జ్యోతి స్కీమ్ వర్తిస్తుంది (200 యూనిట్ల వరకు ఉచిత కరెంట్)"
GJ_CHECKBOX_HINT_EN = (
    "Tick only if your connection is enrolled in Gruha Jyothi. "
    "Leave it unticked if you are not sure."
)
GJ_TRUEUP_NOTE_TE = (
    "ట్రూ-అప్ కూడా ప్రభుత్వమే భరిస్తుందని DISCOM అధికారులు నవంబర్ 2026లో చెప్పారు. "
    "ఇది GO లో లేదు — మీ బిల్లులో చూసి నిర్ధారించుకోండి."
)


def _f(v: Any) -> Optional[float]:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _rs(v: Optional[float]) -> str:
    v = float(v or 0)
    return f"₹{v:,.0f}" if abs(v - round(v)) < 0.005 else f"₹{v:,.2f}"


def printed_subsidy(bill: Dict[str, Any]) -> Optional[float]:
    s = _f(bill.get("subsidy"))
    if s is None or abs(s) < 0.005:
        return None
    return abs(s)


def gruha_jyothi_view(bill: Dict[str, Any], ticked: bool) -> Optional[Dict[str, Any]]:
    """What to show for Gruha Jyothi. None → nothing extra on screen."""
    sub = printed_subsidy(bill)
    units = _f(bill.get("units"))
    if sub is not None:
        if not ticked:
            return None
        return {
            "mode": "printed",
            "payable": payable_amount(bill),
            "note_te": f"బిల్లులోనే సబ్సిడీ −{_rs(sub)} ముద్రించారు — బిల్లులో ఉన్న మొత్తమే ఫైనల్.",
        }
    if not ticked:
        return None
    if units is None:
        return {
            "mode": "unknown",
            "payable": payable_amount(bill),
            "note_te": "యూనిట్లు చదవలేకపోయాం — గృహ జ్యోతి వర్తిస్తుందో చెప్పలేం.",
        }
    bill_amt = _f(bill.get("bill_amount"))
    arrears = effective_arrears(bill)
    acd = _f(bill.get("acd_due")) or 0.0
    if units <= GJ_CAP_UNITS:
        still_due = round((arrears or 0.0) + (acd or 0.0), 2)
        note = (
            f"గృహ జ్యోతి: {int(round(units))} యూనిట్లు (200 లోపు) — అర్హులైతే ఈ నెల బిల్లు ₹0 (జీరో బిల్లు). "
            f"బిల్లులో సబ్సిడీ లైన్ కనిపించలేదు; సాధారణ టారిఫ్ ప్రకారం {_rs(bill_amt)}."
        )
        if still_due >= 1.0:
            note += f" బకాయిలు/ACD {_rs(still_due)} మాత్రం చెల్లించాలి."
        return {
            "mode": "free",
            "payable": still_due,
            "normal_amount": bill_amt,
            "note_te": note,
            "trueup_note_te": GJ_TRUEUP_NOTE_TE if (_f(bill.get("trueup_charges")) or 0) > 0.005 else None,
            "check_te": "మీ బిల్లులో ఇంకా మొత్తం చూపిస్తే 1912 / CSC లో అడగండి.",
        }
    pay = payable_amount(bill)
    return {
        "mode": "over",
        "payable": pay,
        "note_te": (
            f"గృహ జ్యోతి: {int(round(units))} యూనిట్లు — 200 దాటింది. ఈ నెల ఉచితం వర్తించదు; "
            f"మొత్తం బిల్లు {_rs(pay)} చెల్లించాలి (200 పైన యూనిట్లకే కాదు)."
        ),
    }


def gruha_jyothi_forecast_warning(
    bill: Dict[str, Any], forecast: Optional[Dict[str, Any]], ticked: bool
) -> Optional[str]:
    """Warn a ticked beneficiary when next month looks like 196–200 units (or >200)."""
    if not ticked or not forecast:
        return None
    likely = _f(forecast.get("likely"))
    if likely is None:
        return None
    units = _f(bill.get("units"))
    if GJ_WARN_FROM_UNITS <= likely <= GJ_CAP_UNITS:
        return (
            f"⚠️ గృహ జ్యోతి: వచ్చే నెల సుమారు {int(round(likely))} యూనిట్లు — 200కి దగ్గర. "
            "ఒక్క యూనిట్ దాటినా మొత్తం బిల్లు కట్టాలి."
        )
    if likely > GJ_CAP_UNITS and (units is None or units <= GJ_CAP_UNITS):
        return (
            f"⚠️ గృహ జ్యోతి: వచ్చే నెల సుమారు {int(round(likely))} యూనిట్లు — 200 దాటే అవకాశం. "
            "దాటితే మొత్తం బిల్లు కట్టాలి."
        )
    return None

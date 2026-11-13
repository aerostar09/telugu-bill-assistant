"""Centralized conversational Telugu terms for the bill-assistant UI.

Keep wording simple and spoken, not bureaucratic. Import `t("key")` rather
than scattering new copy. Numbers stay as digits; money is rounded rupees
unless a function is showing a printed paise line.
"""
from __future__ import annotations

from typing import Any, Optional

# Official tariff label shown on the calculation tab.
TARIFF_VERSION = "FY 2026-27 TGERC"

TERMS = {
    "app_title": "మీ విద్యుత్ బిల్లు సహాయకుడు",
    "app_tagline": "బిల్లు ఫోటో పెడితే ఈ నెల మొత్తం, ఎందుకు పెరిగింది, వచ్చే నెల అంచనా చూపిస్తాం.",
    "tab_citizen": "పౌరుడు / Citizen",
    "tab_whatsapp": "WhatsApp డెమో",
    "tab_discom": "DISCOM dashboard",
    "nav_understand": "బిల్లు అర్థం చేసుకోండి",
    "nav_understand_en": "Understand the bill",
    "nav_compare": "గత నెలలతో పోలిక",
    "nav_compare_en": "Comparison with past months",
    "nav_estimate": "వచ్చే నెల అంచనా",
    "nav_estimate_en": "Next month's estimate",
    "nav_calculated": "ఎలా లెక్కించాం",
    "nav_calculated_en": "How it was calculated",
    "nav_suggestions": "మీ కోసం సూచనలు",
    "nav_suggestions_en": "Suggestions for me",
    "upload_label": "బిల్లు ఫోటో అప్‌లోడ్ చేయండి",
    "upload_button": "బిల్లు చదవండి",
    "upload_hint": "స్పష్టమైన JPG లేదా PNG పెట్టండి. పేరు, ఫోన్, చిరునామా స్క్రీన్‌పై చూపించం.",
    "this_month_bill": "ఈ నెల బిల్లు",
    "units": "యూనిట్లు",
    "due_date": "చెల్లించాల్సిన తేదీ",
    "confidence": "నమ్మకం",
    "confidence_green": "స్పష్టంగా చదివాం",
    "confidence_yellow": "కొన్ని అంకెలు సరిచేశాం",
    "confidence_red": "లెక్కల్లో తేడా ఉంది",
    "calc_matches": "లెక్క సరిపోయింది ✅",
    "calc_mismatch": "లెక్కల్లో తేడా ఉంది — 1912కి చూపించండి",
    "why_up": "ఎందుకు పెరిగింది?",
    "why_down": "ఎందుకు తగ్గింది?",
    "no_prev": "గత బిల్లు ఉంటే, ఎందుకు మారిందో ఇక్కడ చెప్తాం.",
    "voice": "తెలుగులో వినండి",
    "energy": "కరెంట్ ఛార్జీ",
    "fixed": "ఫిక్స్‌డ్ ఛార్జీ",
    "customer": "కస్టమర్ ఛార్జీ",
    "customer_plain": "నెలవారీ సర్వీస్ ఫీ",
    "ed": "ఎలక్ట్రిసిటీ డ్యూటీ",
    "ed_plain": "ప్రభుత్వానికి పన్ను",
    "trueup": "ట్రూ-అప్",
    "surcharge": "ఆలస్య రుసుము",
    "estimate": "అంచనా",
    "simulation": "సిమ్యులేషన్ / అంచనా",
    "simulation_note": "ఇది సిమ్యులేషన్ / అంచనా — అసలు బిల్లు కాదు. లెక్క FY 2026-27 TGERC టారిఫ్‌తో.",
    "tariff_version": TARIFF_VERSION,
    "printed": "బిల్లులో ఉన్నది",
    "calculated": "మేము లెక్కించింది",
    "technical": "టెక్నికల్ వివరాలు",
    "demo_data": "నమూనా డేటా",
    "your_bills": "మీ బిల్లులు",
    "try_sample": "నమూనా బిల్లు చూడండి",
    "settings": "సెట్టింగ్స్",
    "demo_mode": "డెమో మోడ్ (నమూనా డేటా, PII లేదు)",
}


def t(key: str, **kwargs: Any) -> str:
    text = TERMS[key]
    return text.format(**kwargs) if kwargs else text


def rupees_spoken(n: Any) -> str:
    """Rounded whole rupees for voice, e.g. '757 రూపాయలు'."""
    if n is None:
        return ""
    return f"{int(round(float(n)))} రూపాయలు"


def rupees_display(n: Any) -> str:
    """Rounded whole rupees for the hero card, e.g. '₹757'."""
    if n is None:
        return "—"
    return f"₹{int(round(float(n)))}"


def word_count(text: str) -> int:
    return len((text or "").split())

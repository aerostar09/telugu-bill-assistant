"""WhatsApp-style simulator for the Telugu bill assistant.

This is a proposed integration with the official TGSPDCL WhatsApp chatbot
87124 41912 (launched 22 Feb 2026). It is a simulation — not the official bot.
No DISCOM logo is used.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import quote

from scenarios import get_scenario, OFFICIAL_WA_DISPLAY, OFFICIAL_WA_DIGITS, COMPLAINT_1912
from voice import render_voice_note, synthesize_te

WA_ME_OFFICIAL = f"https://wa.me/91{OFFICIAL_WA_DIGITS}"
SHARE_MAX = 700

BANNER_HTML = """
<div class="wa-banner">
  <strong>ఇది సిమ్యులేషన్ — అధికారిక బాట్ కాదు.</strong><br>
  Proposed integration with the official TGSPDCL WhatsApp chatbot
  <strong>87124 41912</strong> (launched 22 Feb 2026). This screen is a demo of how
  a bill explainer could sit next to that official channel. It is <em>not</em>
  the official TGSPDCL bot, and it does not use a DISCOM logo.
</div>
"""

CHAT_CSS = """
.wa-banner { background:#fff8e6; border:1px solid #f5d48a; border-radius:12px; padding:0.85rem 1rem; margin:0 0 1rem 0; color:#5c4a12; font-size:0.92rem; line-height:1.5; }
.wa-frame { max-width: 420px; margin: 0 auto; background:#ece5dd; border-radius:18px; border:8px solid #111; box-shadow:0 8px 24px rgba(0,0,0,.12); overflow:hidden; }
.wa-head { background:#075e54; color:#fff; padding:0.7rem 1rem; font-weight:600; }
.wa-head small { display:block; font-weight:400; opacity:.85; font-size:0.75rem; }
.wa-body { min-height: 420px; max-height: 640px; overflow-y:auto; padding:0.8rem 0.7rem 1rem; }
.wa-row { display:flex; margin:0.35rem 0; }
.wa-row.user { justify-content:flex-end; }
.wa-bubble { max-width: 85%; border-radius:14px; padding:0.55rem 0.75rem; font-size:0.92rem; line-height:1.45; white-space:pre-wrap; }
.wa-bubble.bot { background:#fff; color:#111; border-top-left-radius:4px; }
.wa-bubble.user { background:#d9fdd3; color:#111; border-top-right-radius:4px; }
"""

MENU_TE = (
    "నమస్తే! నేను బిల్లు వివరణ సహాయకుడు (సిమ్యులేషన్).\n"
    "ఏం కావాలి?\n"
    "1) బిల్లు వివరణ (Explain my bill)\n"
    "2) సీనారియో A / B / C చూడండి\n"
    "3) ఫిర్యాదు మార్గదర్శకం"
)


def _share_url(text: str) -> str:
    body = (text or "").strip()
    if len(body) > SHARE_MAX:
        body = body[: SHARE_MAX - 1] + "…"
    return "https://wa.me/?text=" + quote(body)


def _complaint_text() -> str:
    return (
        "ఫిర్యాదు / స్పష్టత:\n"
        f"• {COMPLAINT_1912} కి కాల్ చేయండి.\n"
        f"• లేదా అధికారిక TGSPDCL WhatsApp {OFFICIAL_WA_DISPLAY} ({WA_ME_OFFICIAL}) కి రాయండి.\n"
        "ఈ సిమ్యులేషన్ ఫిర్యాదు నమోదు చేయదు — అధికారిక ఛానెల్‌లు మాత్రమే చేస్తాయి."
    )


def render_wa_simulator(current_result: Optional[Dict[str, Any]] = None) -> None:
    import streamlit as st

    st.markdown(f"<style>{CHAT_CSS}</style>", unsafe_allow_html=True)
    st.markdown(BANNER_HTML, unsafe_allow_html=True)

    if "wa_messages" not in st.session_state:
        st.session_state["wa_messages"] = [
            {"role": "bot", "text": MENU_TE},
        ]

    msgs: List[Dict[str, str]] = st.session_state["wa_messages"]

    bubbles = []
    for m in msgs:
        role = "user" if m.get("role") == "user" else "bot"
        text = (m.get("text") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        bubbles.append(
            f'<div class="wa-row {role}"><div class="wa-bubble {role}">{text}</div></div>'
        )
    st.markdown(
        '<div class="wa-frame"><div class="wa-head">బిల్లు సహాయకుడు'
        "<small>simulation · not the official TGSPDCL bot</small></div>"
        f'<div class="wa-body">{"".join(bubbles)}</div></div>',
        unsafe_allow_html=True,
    )

    def _push(role: str, text: str) -> None:
        st.session_state["wa_messages"].append({"role": role, "text": text})

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Hi", key="wa_hi"):
        _push("user", "Hi")
        _push("bot", MENU_TE)
        st.rerun()
    if c2.button("బిల్లు వివరణ", key="wa_explain"):
        _push("user", "బిల్లు వివరణ (Explain my bill)")
        if current_result and current_result.get("telugu"):
            body = current_result["telugu"]
            label = current_result.get("display_name") or current_result.get("label") or ""
            _push("bot", (label + "\n" + body).strip())
        else:
            _push(
                "bot",
                "ఒక సీనారియో ఎంచుకోండి (A / B / C), లేదా Citizen ట్యాబ్‌లో బిల్లు ఫోటో / డెమో లోడ్ చేయండి. "
                "అప్పుడు ఇక్కడే వివరణ + వాయిస్ కనిపిస్తాయి.",
            )
        st.rerun()
    if c3.button("ఫిర్యాదు", key="wa_complaint"):
        _push("user", "ఫిర్యాదు మార్గదర్శకం")
        _push("bot", _complaint_text())
        st.rerun()
    if c4.button("చాట్ క్లియర్", key="wa_clear"):
        st.session_state["wa_messages"] = [{"role": "bot", "text": MENU_TE}]
        st.rerun()

    st.caption("సీనారియోలు — రూపాయలు tariff.py నుంచి, నమూనా డేటా")
    s1, s2, s3 = st.columns(3)
    for col, key in ((s1, "A"), (s2, "B"), (s3, "C")):
        sc = get_scenario(key)
        if col.button(sc["title_te"], key=f"wa_sc_{key}"):
            _push("user", sc["title_te"])
            _push("bot", sc["telugu"])
            st.session_state["wa_last_voice"] = sc["telugu"]
            st.session_state["wa_last_share"] = sc["telugu"]
            st.rerun()

    last_bot = next((m["text"] for m in reversed(msgs) if m.get("role") == "bot"), "")
    if last_bot:
        render_voice_note(last_bot)
        share = _share_url(last_bot)
        st.markdown(
            f"[WhatsAppలో షేర్ చేయండి]({share}) · "
            f"[అధికారిక TGSPDCL WhatsApp {OFFICIAL_WA_DISPLAY}]({WA_ME_OFFICIAL})"
        )
        st.caption("షేర్ లింక్ ముందుగా నింపిన టెక్స్ట్‌తో wa.me. ఫిర్యాదు నమోదు కాదు.")

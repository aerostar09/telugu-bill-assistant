"""WhatsApp-style simulator for a proposed 'Explain my bill' option.

Demo / Concept – not an official TGSPDCL service.
This is a simulation of how a bill explainer could sit on the official
WhatsApp channel (87124 41912). It is not the official bot, and it does
not use a DISCOM or government logo.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from scenarios import get_scenario, OFFICIAL_WA_DISPLAY, OFFICIAL_WA_DIGITS, COMPLAINT_1912
from voice import render_voice_note

WA_ME_OFFICIAL = f"https://wa.me/91{OFFICIAL_WA_DIGITS}"
SHARE_MAX = 700
APP_URL = "https://telugu-electricitybill-assistant.streamlit.app/"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
THUMB_PATH = ASSETS_DIR / "demo_bill_thumb.png"

CONCEPT_EN = "Demo / Concept – not an official TGSPDCL service"
CONCEPT_TE = (
    "సిమ్యులేషన్ – TGSPDCL WhatsApp (87124 41912) లో "
    "'Explain my bill' ఆప్షన్‌గా జోడించవచ్చు"
)

BANNER_HTML = f"""
<div class="wa-banner">
  <strong>{CONCEPT_TE}</strong><br>
  {CONCEPT_EN}. This screen is a demo of how a short Telugu bill
  explanation and voice note could appear inside that official channel.
  It is <em>not</em> the official TGSPDCL bot, and it does not use a
  DISCOM or government logo.
</div>
"""

CHAT_CSS = """
.wa-banner { background:#fff8e6; border:1px solid #f5d48a; border-radius:12px; padding:0.85rem 1rem; margin:0 0 1rem 0; color:#5c4a12; font-size:0.92rem; line-height:1.5; }
.wa-frame { max-width: 420px; width: 100%; margin: 0 auto; background:#ece5dd; border-radius:18px; border:8px solid #111; box-shadow:0 8px 24px rgba(0,0,0,.12); overflow:hidden; box-sizing:border-box; }
.wa-head { background:#075e54; color:#fff; padding:0.7rem 1rem; font-weight:600; }
.wa-head small { display:block; font-weight:400; opacity:.85; font-size:0.75rem; }
.wa-body { min-height: 420px; max-height: 640px; overflow-y:auto; padding:0.8rem 0.7rem 1rem; }
.wa-row { display:flex; margin:0.35rem 0; }
.wa-row.user { justify-content:flex-end; }
.wa-bubble { max-width: 85%; border-radius:14px; padding:0.55rem 0.75rem; font-size:0.92rem; line-height:1.45; white-space:pre-wrap; }
.wa-bubble.bot { background:#fff; color:#111; border-top-left-radius:4px; }
.wa-bubble.user { background:#d9fdd3; color:#111; border-top-right-radius:4px; }
.wa-thumb { width: 168px; max-width: 100%; height: auto; border-radius:10px; display:block; margin:0 0 0.4rem 0; background:#fff; }
.wa-voice { max-width: 420px; width: 100%; margin: 0.35rem auto 0.8rem; }
.wa-time { display:block; font-size:0.68rem; color:#667; margin-top:0.25rem; text-align:right; }
"""

MENU_TE = (
    "నమస్తే! నేను బిల్లు వివరణ సహాయకుడు (సిమ్యులేషన్).\n"
    "ఏం కావాలి?\n"
    "1) బిల్లు వివరణ (Explain my bill)\n"
    "2) సీనారియో A / B / C చూడండి\n"
    "3) ఫిర్యాదు మార్గదర్శకం"
)

USER_PHOTO_CAPTION = "బిల్లు ఫోటో (నమూనా)"


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


def _esc(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _result_key(result: Optional[Dict[str, Any]]) -> str:
    if not result or not result.get("bill"):
        return "demo-default"
    bill = result["bill"]
    return (
        f"{result.get('display_name') or result.get('scenario') or 'bill'}"
        f"|{bill.get('units')}|{bill.get('bill_amount')}"
    )


def build_wa_reply(result: Optional[Dict[str, Any]] = None) -> str:
    """Short Telugu chat reply: amount, units, top reason, next-bill range.

    Reuses citizen_summary.build_voice_summary. No paid API calls.
    Falls back to the PII-free Lakshmi demo when no result is loaded.
    """
    from citizen_summary import top_reasons, build_voice_summary
    from forecast import forecast_display_range
    from dashboard import build_dashboard_model
    from self_checks import run_all_checks
    from demo_data import lakshmi_demo_bundle

    model = None
    if result:
        model = result.get("model")
        if model is None and result.get("bill"):
            model = build_dashboard_model(
                result["bill"], result.get("prev_bill"), result.get("checks")
            )
    if model is None:
        bundle = lakshmi_demo_bundle()
        checks = run_all_checks(bundle["bill"])
        model = build_dashboard_model(bundle["bill"], bundle["prev_bill"], checks)
    bill = model["bill"]
    reasons = top_reasons(model.get("jump"), model.get("late"), bill, max_n=3)
    rng = forecast_display_range(model.get("forecast"))
    return build_voice_summary(bill, reasons=reasons, forecast_range=rng)


def default_wa_thread(result: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Preset Demo Day conversation: greeting, sample bill photo, short reply."""
    return [
        {"role": "bot", "text": MENU_TE},
        {"role": "user", "text": USER_PHOTO_CAPTION, "image": "thumb"},
        {"role": "bot", "text": build_wa_reply(result), "audio": True},
    ]


def _thumb_data_uri() -> str:
    if THUMB_PATH.exists():
        raw = THUMB_PATH.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        return f"data:image/png;base64,{b64}"
    return ""


def _render_messages(msgs: List[Dict[str, Any]], audio_uri: str, thumb_uri: str) -> str:
    bubbles: List[str] = []
    for m in msgs:
        role = "user" if m.get("role") == "user" else "bot"
        inner: List[str] = []
        if m.get("image") == "thumb" and thumb_uri:
            inner.append(
                f'<img class="wa-thumb" alt="Sample electricity bill (fictional, no PII)" src="{thumb_uri}">'
            )
        inner.append(_esc(m.get("text") or ""))
        if m.get("audio") and audio_uri:
            inner.append(
                f'<audio controls preload="none" src="{audio_uri}"></audio>'
            )
        bubbles.append(
            f'<div class="wa-row {role}"><div class="wa-bubble {role}">'
            f'{"".join(inner)}</div></div>'
        )
    return (
        '<div class="wa-frame" data-testid="wa-frame">'
        '<div class="wa-head">బిల్లు సహాయకుడు'
        f"<small>WhatsApp డెమో · {CONCEPT_EN}</small></div>"
        f'<div class="wa-body">{"".join(bubbles)}</div></div>'
    )


def render_wa_simulator(current_result: Optional[Dict[str, Any]] = None) -> None:
    import streamlit as st

    st.markdown(f"<style>{CHAT_CSS}</style>", unsafe_allow_html=True)
    st.markdown(BANNER_HTML, unsafe_allow_html=True)

    key = _result_key(current_result)
    if st.session_state.get("wa_result_key") != key or "wa_messages" not in st.session_state:
        st.session_state["wa_result_key"] = key
        st.session_state["wa_messages"] = default_wa_thread(current_result)

    msgs: List[Dict[str, Any]] = st.session_state["wa_messages"]
    last_audio = next(
        (m.get("text") or "" for m in reversed(msgs) if m.get("role") == "bot" and m.get("audio")),
        "",
    )
    # Only the short reply is synthesised — never the long template, never Sarvam.
    # Keep the phone frame in st.markdown (thumb data-URI works). Do not embed
    # <audio src="data:..."> — Streamlit / CSP leaves that player at 0:00.
    # A real gTTS clip is played with st.audio immediately under the frame.
    st.markdown(
        _render_messages(msgs, audio_uri="", thumb_uri=_thumb_data_uri()),
        unsafe_allow_html=True,
    )
    if last_audio:
        st.markdown('<div class="wa-voice">', unsafe_allow_html=True)
        render_voice_note(last_audio, label="🔊 వాయిస్ నోట్ · తెలుగులో వినండి")
        st.markdown("</div>", unsafe_allow_html=True)

    def _push(role: str, text: str, **extra: Any) -> None:
        item: Dict[str, Any] = {"role": role, "text": text}
        item.update(extra)
        st.session_state["wa_messages"].append(item)

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Hi", key="wa_hi"):
        _push("user", "Hi")
        _push("bot", MENU_TE)
        st.rerun()
    if c2.button("బిల్లు వివరణ", key="wa_explain"):
        _push("user", USER_PHOTO_CAPTION, image="thumb")
        _push("bot", build_wa_reply(current_result), audio=True)
        st.rerun()
    if c3.button("ఫిర్యాదు", key="wa_complaint"):
        _push("user", "ఫిర్యాదు మార్గదర్శకం")
        _push("bot", _complaint_text())
        st.rerun()
    if c4.button("చాట్ క్లియర్", key="wa_clear"):
        st.session_state["wa_messages"] = default_wa_thread(current_result)
        st.rerun()

    st.caption("సీనారియోలు — రూపాయలు tariff.py నుంచి, నమూనా డేటా")
    s1, s2, s3 = st.columns(3)
    for col, skey in ((s1, "A"), (s2, "B"), (s3, "C")):
        sc = get_scenario(skey)
        if col.button(sc["title_te"], key=f"wa_sc_{skey}"):
            _push("user", sc["title_te"])
            # Keep the chat short: use the same voice-summary helper on the
            # scenario bill rather than the long template dump.
            _push("bot", build_wa_reply({"bill": sc["bill"], "prev_bill": sc.get("prev_bill")}), audio=True)
            st.rerun()

    last_bot = next((m.get("text") or "" for m in reversed(msgs) if m.get("role") == "bot"), "")
    if last_bot:
        share = _share_url(last_bot)
        st.markdown(
            f"[WhatsAppలో షేర్ చేయండి]({share}) · "
            f"[అధికారిక TGSPDCL WhatsApp {OFFICIAL_WA_DISPLAY}]({WA_ME_OFFICIAL})"
        )
        st.caption("షేర్ లింక్ ముందుగా నింపిన టెక్స్ట్‌తో wa.me. ఫిర్యాదు నమోదు కాదు.")

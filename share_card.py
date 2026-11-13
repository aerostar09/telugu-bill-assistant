"""PII-free shareable bill-summary PNG + a short WhatsApp text."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from PIL import Image, ImageDraw, ImageFont, features

from bill_lines import nonzero_rows, payable_amount
from receipt_ui import next_units_cliff

APP_URL = "https://telugu-electricitybill-assistant.streamlit.app/"
ASSETS = Path(__file__).resolve().parent / "assets"
FONTS = ASSETS / "fonts"
QR_PATH = ASSETS / "qr_app.png"
CONCEPT = "Demo / Concept – not an official TGSPDCL service"

TEAL = (15, 110, 98)
TEAL_DARK = (11, 85, 76)
INK = (18, 32, 58)
MUTED = (91, 107, 128)
LINE = (215, 222, 232)
WHITE = (255, 255, 255)
BG = (243, 246, 250)
AMBER = (255, 246, 217)
AMBER_LINE = (232, 197, 107)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONTS / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _te(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return _font("NotoSansTelugu-Bold.ttf" if bold else "NotoSansTelugu-Regular.ttf", size)


def _lat(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return _font("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _is_te_char(ch: str, prev_te: bool = False) -> bool:
    o = ord(ch)
    if 0x0C00 <= o <= 0x0C7F:
        return True
    if ch in ("‌", "‍"):
        return True
    import unicodedata
    # Keep combining marks with a Telugu run so conjuncts stay intact.
    if prev_te and unicodedata.category(ch) == "Mn":
        return True
    return False


def _script_runs(text: str):
    """Split mixed Telugu + Latin so each run can use the right font."""
    runs = []
    buf: list[str] = []
    mode = None
    for ch in text:
        te = _is_te_char(ch, prev_te=(mode == "te"))
        want = "te" if te else "lat"
        if mode is None:
            mode = want
        elif want != mode:
            runs.append((mode, "".join(buf)))
            buf = []
            mode = want
        buf.append(ch)
    if buf:
        runs.append((mode or "lat", "".join(buf)))
    return runs


def _mixed_width(draw: ImageDraw.ImageDraw, text: str, size: int, bold: bool = False) -> int:
    te, lat = _te(size, bold), _lat(size, bold)
    w = 0
    for mode, chunk in _script_runs(text):
        font = te if mode == "te" else lat
        tw, _ = _text_size(draw, chunk, font)
        w += tw
    return w


def _draw_mixed(draw: ImageDraw.ImageDraw, xy, text: str, size: int, fill, *, bold: bool = False) -> int:
    """Draw Telugu with Noto and Latin/punctuation/emoji-fallback with DejaVu.

    Returns the final x after the last glyph (for measuring).
    """
    x, y = xy
    te, lat = _te(size, bold), _lat(size, bold)
    te_ascent = te.getmetrics()[0]
    lat_ascent = lat.getmetrics()[0]
    for mode, chunk in _script_runs(text):
        font = te if mode == "te" else lat
        # Align baselines of the two fonts.
        dy = (te_ascent - lat_ascent) if mode == "lat" else 0
        draw.text((x, y + dy), chunk, font=font, fill=fill)
        tw, _ = _text_size(draw, chunk, font)
        x += tw
    return x


def short_share_text(
    bill: Dict[str, Any],
    *,
    forecast_range: Optional[Dict[str, Any]] = None,
    spoken_summary: Optional[str] = None,
    include_link: bool = True,
    totals_ok: Optional[bool] = None,
) -> str:
    """Short structured Telugu + emoji. No name, USC, address, or meter numbers."""
    pay = payable_amount(bill)
    units = bill.get("units")
    due = bill.get("due_date") or "—"
    lines = []
    if pay is not None:
        unit_bit = f" ({int(round(float(units)))} యూనిట్లు)" if units is not None else ""
        lines.append(f"⚡ ఈ నెల బిల్లు ₹{int(round(pay))}{unit_bit}")
    lines.append(f"📅 చెల్లించాల్సిన తేదీ {due}")
    if totals_ok:
        lines.append("✅ లెక్క సరిపోయింది")
    for r in nonzero_rows(bill)[:8]:
        sign = "−" if r["amount"] < 0 or r["key"] == "subsidy" else ""
        lines.append(f"• {r['name_te']} {sign}₹{abs(r['amount']):,.2f}")
    from forecast import consumer_forecast_range, format_rupee_range
    rng = consumer_forecast_range(forecast_range=forecast_range)
    if rng:
        band = format_rupee_range(rng["low"], rng["high"])
        if band:
            lines.append(f"📈 వచ్చే నెల అంచనా {band}")
    cliff = next_units_cliff(bill.get("units"))
    if cliff and cliff.get("headroom"):
        lines.append(f"💡 {cliff['message_te']}")
    if include_link:
        lines.append(f"🔗 {APP_URL}")
    text = "\n".join(l for l in lines if l)
    return text


def whatsapp_share_url(text: str) -> str:
    return "https://wa.me/?text=" + quote(text, safe="")


def render_telugu_ok() -> bool:
    """True when PIL can shape Telugu conjuncts (libraqm)."""
    try:
        return bool(features.check("raqm"))
    except Exception:
        return False


def make_share_png(
    bill: Dict[str, Any],
    *,
    forecast_range: Optional[Dict[str, Any]] = None,
) -> bytes:
    from forecast import consumer_forecast_range, format_rupee_range
    forecast_range = consumer_forecast_range(forecast_range=forecast_range)
    W = 1080
    rows = nonzero_rows(bill)
    # Header + amount + meta + rows + tip + QR + footer. Keep the rounded card intact.
    H = 230 + 150 + 60 + 16 + len(rows) * 62 + 8 + 70 + 210 + 80
    if forecast_range and forecast_range.get("low") is not None:
        H += 90
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 40, W - 40, H - 40), radius=28, fill=WHITE, outline=LINE, width=2)
    d.rounded_rectangle((40, 40, W - 40, 200), radius=28, fill=TEAL)
    d.rectangle((40, 140, W - 40, 200), fill=TEAL)
    _draw_mixed(d, (70, 62), "మీ విద్యుత్ బిల్లు", 36, WHITE, bold=True)
    d.text((70, 120), CONCEPT, font=_lat(18), fill=(220, 240, 236))

    # Demo pill
    d.rounded_rectangle((W - 200, 62, W - 70, 108), radius=12, fill=AMBER, outline=AMBER_LINE)
    tw, _ = _text_size(d, "DEMO", _lat(18, True))
    d.text((W - 200 + (130 - tw) / 2, 72), "DEMO", font=_lat(18, True), fill=(92, 74, 18))

    y = 230
    pay = payable_amount(bill)
    if pay is not None:
        _draw_mixed(d, (70, y), "ఈ నెల మొత్తం", 26, MUTED)
        y += 44
        d.text((70, y), f"₹{int(round(pay))}", font=_lat(72, True), fill=TEAL_DARK)
        y += 100
    meta = []
    if bill.get("units") is not None:
        meta.append(f"{int(round(float(bill['units'])))} యూనిట్లు")
    if bill.get("due_date"):
        meta.append(f"గడువు {bill['due_date']}")
    if meta:
        _draw_mixed(d, (70, y), "  ·  ".join(meta), 28, INK)
        y += 56

    d.line((70, y, W - 70, y), fill=LINE, width=2)
    y += 16
    for r in rows:
        _draw_mixed(d, (70, y), r["name_te"], 26, INK, bold=True)
        _draw_mixed(d, (70, y + 34), r["meaning_te"], 20, MUTED)
        sign = "−" if r["amount"] < 0 or r["key"] == "subsidy" else ""
        amt = f"{sign}₹{abs(r['amount']):,.2f}"
        aw, _ = _text_size(d, amt, _lat(26, True))
        d.text((W - 70 - aw, y + 8), amt, font=_lat(26, True), fill=INK)
        y += 62
        d.line((70, y - 8, W - 70, y - 8), fill=LINE, width=1)

    y += 8
    if forecast_range and forecast_range.get("low") is not None:
        d.rounded_rectangle((70, y, W - 70, y + 70), radius=14, fill=(240, 253, 250))
        _draw_mixed(
            d, (90, y + 16),
            f"వచ్చే నెల అంచనా  {format_rupee_range(forecast_range['low'], forecast_range['high'])}",
            26,
            TEAL_DARK,
            bold=True,
        )
        y += 90

    cliff = next_units_cliff(bill.get("units"))
    tip = cliff["message_te"] if cliff and cliff.get("headroom") else "సమయానికి చెల్లిస్తే ఆలస్య రుసుము ఉండదు."
    _draw_mixed(d, (70, y), "సూచన: " + tip, 24, INK)
    y += 60

    # QR
    if QR_PATH.exists():
        qr = Image.open(QR_PATH).convert("RGB").resize((180, 180), Image.Resampling.NEAREST)
        img.paste(qr, (70, y))
        _draw_mixed(d, (270, y + 40), "స్కాన్ చేసి యాప్ తెరవండి", 24, INK, bold=True)
        d.text((270, y + 86), APP_URL.replace("https://", ""), font=_lat(16), fill=TEAL_DARK)
        d.text((270, y + 118), CONCEPT, font=_lat(14), fill=MUTED)
        y += 200

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_share_controls(
    model: Dict[str, Any],
    *,
    spoken_summary: Optional[str] = None,
    forecast_range: Optional[Dict[str, Any]] = None,
) -> None:
    import streamlit as st
    bill = model["bill"]
    checks = model.get("checks") or {}
    totals_ok = checks.get("consumer_ok")
    if totals_ok is None:
        totals_ok = checks.get("ok")
    from forecast import consumer_forecast_range
    forecast_range = consumer_forecast_range(
        forecast=model.get("forecast"), forecast_range=forecast_range
    )
    text = short_share_text(
        bill,
        forecast_range=forecast_range,
        spoken_summary=spoken_summary,
        totals_ok=bool(totals_ok),
    )
    png = make_share_png(bill, forecast_range=forecast_range)
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "చిత్రం డౌన్‌లోడ్",
            data=png,
            file_name="telugu-bill-summary.png",
            mime="image/png",
            key="share_png_dl",
            width="stretch",
        )
    with c2:
        st.markdown(
            f'<a href="{whatsapp_share_url(text)}" target="_blank" rel="noopener" '
            f'data-testid="wa-share-link" '
            f'style="display:block;text-align:center;background:#128C7E;color:#fff;'
            f'padding:.65rem 1rem;border-radius:10px;text-decoration:none;font-weight:700;">'
            f"WhatsApp లో షేర్ చేయండి</a>",
            unsafe_allow_html=True,
        )
    st.caption("చిత్రంలో పేరు, చిరునామా, సర్వీస్ నంబర్ లేవు.")



def compact_extracted_summary(bill: Dict[str, Any]) -> List[tuple]:
    """PII-free extracted fields for the share tab (no USC, name, meter readings)."""
    rows: List[tuple] = []
    labels = [
        ("category", "కేటగిరీ"),
        ("contracted_load_kw", "కాంట్రాక్టెడ్ లోడ్ (kW)"),
        ("units", "యూనిట్లు"),
        ("days", "రోజులు"),
        ("recorded_md", "Recorded MD"),
        ("bill_date", "బిల్లు తేదీ"),
        ("due_date", "గడువు"),
        ("disc_date", "Disc Date"),
        ("last_paid_date", "Last Paid"),
    ]
    for key, label in labels:
        val = bill.get(key)
        if val is None or val == "":
            continue
        rows.append((label, str(val)))
    for r in nonzero_rows(bill):
        sign = "−" if r["amount"] < 0 or r["key"] == "subsidy" else ""
        rows.append((r["name_te"], f"{sign}₹{abs(r['amount']):,.2f}"))
    pay = payable_amount(bill)
    if pay is not None:
        rows.append(("మొత్తం చెల్లింపు", f"₹{int(round(pay))}"))
    return rows


def render_web_share_button(png: bytes, text: str, *, key: str = "webshare") -> None:
    """Try navigator.share with the PNG; fall back to wa.me in the same click."""
    import base64
    import json
    import streamlit.components.v1 as components
    b64 = base64.b64encode(png).decode("ascii")
    payload = json.dumps({"text": text, "url": whatsapp_share_url(text), "b64": b64})
    # JSON is inserted as a JS literal; quotes are escaped by json.dumps.
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body{{margin:0;font-family:sans-serif;}}
  button{{width:100%;background:#128C7E;color:#fff;border:0;border-radius:10px;
    padding:.7rem 1rem;font-weight:700;font-size:1rem;cursor:pointer;}}
  button:active{{background:#0b554c;}}
</style></head>
<body>
<button id="s" type="button">చిత్రాన్ని షేర్ చేయండి</button>
<script>
const P = {payload};
async function go() {{
  try {{
    const resp = await fetch("data:image/png;base64," + P.b64);
    const blob = await resp.blob();
    const file = new File([blob], "telugu-bill-summary.png", {{type: "image/png"}});
    const data = {{files: [file], title: "మీ విద్యుత్ బిల్లు", text: P.text}};
    if (navigator.canShare && navigator.canShare({{files: [file]}})) {{
      await navigator.share(data);
      return;
    }}
    if (navigator.share) {{
      await navigator.share({{title: "మీ విద్యుత్ బిల్లు", text: P.text}});
      return;
    }}
  }} catch (e) {{
    if (e && e.name === "AbortError") return;
  }}
  window.open(P.url, "_blank", "noopener");
}}
document.getElementById("s").addEventListener("click", go);
</script>
</body></html>"""
    components.html(html, height=58, scrolling=False)


def render_share_tab(result: Optional[Dict[str, Any]] = None, *, on_try_demo=None) -> None:
    """Share / WhatsApp tab: uses the bill already uploaded in the citizen tab."""
    import streamlit as st
    from citizen_summary import build_voice_summary, top_reasons
    from forecast import consumer_forecast_range
    from voice import render_voice_note

    if not result or not result.get("bill"):
        st.info("ముందు పౌరుడు ట్యాబ్‌లో బిల్లు ఫోటో అప్‌లోడ్ చేయండి. అప్పుడు ఇక్కడే షేర్ చిత్రం వస్తుంది.")
        if on_try_demo is not None and st.button("నమూనా బిల్లు చూడండి", key="share_try_demo"):
            on_try_demo()
        st.caption("కాన్సెప్ట్: TGSPDCL WhatsApp 87124 41912 లోకి ప్లగ్ చేయవచ్చు.")
        return

    model = result.get("model") or {"bill": result["bill"], "checks": result.get("checks")}
    bill = model["bill"]
    rng = consumer_forecast_range(
        forecast=model.get("forecast"),
        forecast_range=None,
    )
    checks = model.get("checks") or result.get("checks") or {}
    totals_ok = checks.get("consumer_ok")
    if totals_ok is None:
        totals_ok = checks.get("ok")
    reasons = top_reasons(model.get("jump"), model.get("late"), bill)
    spoken = build_voice_summary(bill, reasons=reasons, forecast_range=rng)
    text = short_share_text(bill, forecast_range=rng, totals_ok=bool(totals_ok))
    png = make_share_png(bill, forecast_range=rng)

    st.image(png, width="stretch")
    render_web_share_button(png, text)
    render_share_controls(model, spoken_summary=spoken, forecast_range=rng)
    if spoken:
        st.markdown("##### వినండి / Listen in Telugu")
        render_voice_note(spoken)
    st.markdown("##### సారాంశం")
    parts = ['<div class="receipt" data-testid="share-extract">']
    for label, val in compact_extracted_summary(bill):
        parts.append(
            f'<div class="rc-row" style="display:flex;justify-content:space-between;'
            f'padding:6px 0;line-height:1.2;border-bottom:1px dashed #e5eeec;">'
            f'<span>{label}</span><span class="rc-amt">{val}</span></div>'
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)
    st.caption("కాన్సెప్ట్: TGSPDCL WhatsApp 87124 41912 లోకి ప్లగ్ చేయవచ్చు.")
    st.caption("చిత్రంలో పేరు, చిరునామా, సర్వీస్ నంబర్, మీటర్ రీడింగ్ లేవు.")

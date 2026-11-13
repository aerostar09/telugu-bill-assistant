#!/usr/bin/env python3
"""Generate pitch/demo rollout assets (QR, caption poster, fictional bill, thumb).

All outputs are labelled Demo / Concept – not an official TGSPDCL service.
No official logos. Fictional sample data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import qrcode
from qrcode.constants import ERROR_CORRECT_H

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
APP_URL = "https://telugu-electricitybill-assistant.streamlit.app/"
SHORT_URL = "telugu-electricitybill-assistant.streamlit.app"
CONCEPT_EN = "Demo / Concept – not an official TGSPDCL service"
CAPTION_TE = "బిల్లు ఫోటో తీయండి – తెలుగులో అర్థం చేసుకోండి"
BILL_SCAN_TE = "ఈ బిల్లు అర్థం కాలేదా? స్కాన్ చేయండి"

TE_REG = Path("/home/box/.fonts/NotoSansTelugu-Regular.ttf")
TE_BOLD = Path("/home/box/.fonts/NotoSansTelugu-Bold.ttf")
LAT_REG = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
LAT_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

TEAL = (15, 110, 98)
TEAL_DARK = (11, 85, 76)
INK = (18, 32, 58)
MUTED = (91, 107, 128)
LINE = (215, 222, 232)
AMBER = (255, 246, 217)
AMBER_LINE = (232, 197, 107)
WHITE = (255, 255, 255)
BG = (243, 246, 250)


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def text_size(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def make_qr(url: str, min_side: int = 1100) -> Image.Image:
    """Build a QR whose module size is an integer, so it stays scannable.

    Non-integer resizes (e.g. 784 → 1100) break the module grid and OpenCV
    / many phone cameras then fail to decode.
    """
    probe = qrcode.QRCode(error_correction=ERROR_CORRECT_H, box_size=1, border=4)
    probe.add_data(url)
    probe.make(fit=True)
    grid = probe.modules_count + 8  # modules plus quiet border
    box = max(1, (min_side + grid - 1) // grid)
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H, box_size=box, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return img


def centered(draw: ImageDraw.ImageDraw, text: str, y: int, fnt, width: int, fill=INK) -> int:
    w, h = text_size(draw, text, fnt)
    draw.text(((width - w) // 2, y), text, font=fnt, fill=fill)
    return y + h


def write_qr_plain(path: Path) -> Image.Image:
    img = make_qr(APP_URL, min_side=1100)
    img.save(path, "PNG")
    print(f"wrote {path} {img.size}")
    return img


def write_qr_caption(path: Path, qr: Image.Image) -> Image.Image:
    # Poster: concept label, QR, Telugu caption, short URL
    qr_fit = qr
    qr_side = qr_fit.size[0]
    pad = 70
    width = qr_side + pad * 2
    # Measure first on a scratch canvas
    scratch = Image.new("RGB", (width, 200), WHITE)
    sd = ImageDraw.Draw(scratch)
    f_concept = font(LAT_REG, 22)
    f_cap = font(TE_BOLD, 36)
    f_url = font(LAT_BOLD, 26)
    f_note = font(LAT_REG, 18)

    # Wrap caption if needed — prefer two balanced lines
    cap_lines = ["బిల్లు ఫోటో తీయండి", "తెలుగులో అర్థం చేసుకోండి"]
    height = pad + 36 + 16 + qr_side + 36 + 52 + 52 + 40 + 40 + pad
    img = Image.new("RGB", (width, height), WHITE)
    d = ImageDraw.Draw(img)
    y = pad
    y = centered(d, CONCEPT_EN, y, f_concept, width, MUTED) + 18
    x_qr = (width - qr_side) // 2
    img.paste(qr_fit, (x_qr, y))
    y += qr_side + 28
    for line in cap_lines:
        y = centered(d, line, y, f_cap, width, INK) + 10
    y += 10
    y = centered(d, SHORT_URL, y, f_url, width, TEAL_DARK) + 16
    centered(d, "Not an official DISCOM or government service.", y, f_note, width, MUTED)
    img.save(path, "PNG")
    print(f"wrote {path} {img.size}")
    return img


def write_bill_with_qr(path: Path, qr: Image.Image) -> Image.Image:
    W, H = 1080, 1560
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    def f(kind: str, size: int):
        return font(TE_BOLD if kind == "teb" else TE_REG if kind.startswith("te") else LAT_BOLD if kind == "lb" else LAT_REG, size)

    # Outer card
    card = (48, 48, W - 48, H - 48)
    d.rounded_rectangle(card, radius=18, fill=WHITE, outline=LINE, width=2)
    # Teal header (generic, no logo)
    d.rounded_rectangle((48, 48, W - 48, 200), radius=18, fill=TEAL)
    d.rectangle((48, 160, W - 48, 200), fill=TEAL)
    d.text((80, 70), "ELECTRICITY BILL", font=f("lb", 36), fill=WHITE)
    d.text((80, 118), "Sample bill (concept) · not an official DISCOM bill", font=f("l", 20), fill=(220, 240, 236))

    # Concept banner
    d.rounded_rectangle((80, 220, W - 80, 300), radius=10, fill=AMBER, outline=AMBER_LINE)
    d.text((100, 238), CONCEPT_EN, font=f("l", 20), fill=(92, 74, 18))
    d.text((100, 264), "Fictional data only. No official logo or endorsement.", font=f("l", 16), fill=(92, 74, 18))

    y = 330
    f_k, f_v = f("l", 22), f("lb", 22)
    rows = [
        ("Consumer name", "Sample Customer"),
        ("Service no.", "DEMO-0000-1234"),
        ("Meter no.", "000000154"),
        ("Category", "LT-I Domestic  1B(i)"),
        ("Contracted load", "3.0 kW  ·  1 phase"),
        ("Bill date", "06/11/2026"),
        ("Due date", "20-11-2026"),
        ("Units consumed", "154"),
    ]
    left, right = 80, W - 80
    for k, v in rows:
        d.text((left, y), k, font=f_k, fill=MUTED)
        tw, _ = text_size(d, v, f_v)
        d.text((right - tw, y), v, font=f_v, fill=INK)
        y += 38
        d.line((left, y - 8, right, y - 8), fill=LINE, width=1)

    y += 8
    d.text((left, y), "Charges (sample)", font=f("lb", 22), fill=INK)
    y += 40
    charges = [
        ("Energy charges", "₹599.20"),
        ("Fixed charges", "₹30.00"),
        ("Customer charges", "₹90.00"),
        ("Electricity duty", "₹9.24"),
        ("True-up", "₹28.80"),
    ]
    for k, v in charges:
        d.text((left, y), k, font=f("l", 22), fill=MUTED)
        tw, _ = text_size(d, v, f_v)
        d.text((right - tw, y), v, font=f_v, fill=INK)
        y += 36

    y += 8
    d.rounded_rectangle((left, y, right, y + 70), radius=10, fill=(232, 247, 244))
    d.text((left + 20, y + 18), "Total payable", font=f("lb", 24), fill=TEAL_DARK)
    tot = "₹757"
    tw, _ = text_size(d, tot, f("lb", 36))
    d.text((right - 20 - tw, y + 12), tot, font=f("lb", 36), fill=TEAL_DARK)
    y += 92

    # QR + Telugu scan line
    # 49 modules * 7 px = 343, an integer scale of the same matrix
    qr_small = make_qr(APP_URL, min_side=343)
    qr_side = qr_small.size[0]
    img.paste(qr_small, (left, y))
    tx = left + qr_side + 24
    d.text((tx, y + 40), BILL_SCAN_TE, font=f("teb", 28), fill=INK)
    d.text((tx, y + 90), SHORT_URL, font=f("l", 18), fill=TEAL_DARK)
    d.text((tx, y + 120), CONCEPT_EN, font=f("l", 14), fill=MUTED)
    d.text((tx, y + 148), "Scan to open the Telugu bill assistant.", font=f("l", 16), fill=MUTED)

    img.save(path, "PNG")
    print(f"wrote {path} {img.size}")
    return img


def write_thumb(path: Path) -> Image.Image:
    """Compact PII-free bill thumbnail for the WhatsApp user bubble."""
    W, H = 420, 560
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 86), fill=TEAL)
    d.text((16, 14), "ELECTRICITY BILL", font=font(LAT_BOLD, 20), fill=WHITE)
    d.text((16, 44), "SAMPLE  ·  CONCEPT", font=font(LAT_REG, 14), fill=(220, 240, 236))
    d.rounded_rectangle((12, 98, W - 12, 148), radius=8, fill=AMBER, outline=AMBER_LINE)
    d.text((22, 112), "Demo / Concept – not official", font=font(LAT_REG, 14), fill=(92, 74, 18))

    def row(y, k, v, bold=False):
        d.text((20, y), k, font=font(LAT_REG, 16), fill=MUTED)
        vf = font(LAT_BOLD, 16 if not bold else 22)
        tw, _ = text_size(d, v, vf)
        d.text((W - 20 - tw, y), v, font=vf, fill=INK)

    y = 168
    for k, v in (
        ("Name", "Sample Customer"),
        ("Service no.", "DEMO-0000-1234"),
        ("Units", "154"),
        ("Energy", "₹599.20"),
        ("Fixed", "₹30.00"),
        ("Customer", "₹90.00"),
        ("Duty", "₹9.24"),
        ("True-up", "₹28.80"),
    ):
        row(y, k, v)
        y += 32
        d.line((20, y - 8, W - 20, y - 8), fill=LINE, width=1)
    row(y + 6, "Total", "₹757", bold=True)
    d.text((20, H - 48), "Fictional sample · no PII", font=font(LAT_REG, 13), fill=MUTED)
    img.save(path, "PNG")
    print(f"wrote {path} {img.size}")
    return img


def screenshot_portal() -> None:
    html = ASSETS / "mock_discom_portal.html"
    if not html.exists():
        raise SystemExit(f"missing {html}")
    uri = html.resolve().as_uri()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("skip portal screenshots: playwright is not installed in this environment")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            channel="chrome",
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        for name, width, height in (
            ("mock_discom_portal_mobile.png", 420, 900),
            ("mock_discom_portal_desktop.png", 1280, 800),
        ):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(uri, wait_until="networkidle")
            out = ASSETS / name
            page.screenshot(path=str(out), full_page=True)
            print(f"wrote {out} {width}px viewport")
            page.close()
        browser.close()


def _decode_qr(im) -> str:
    import cv2
    # Classic QRCodeDetector often misses large, high-res codes; Aruco is reliable.
    for cls in (getattr(cv2, "QRCodeDetectorAruco", None), cv2.QRCodeDetector):
        if cls is None:
            continue
        data, _, _ = cls().detectAndDecode(im)
        if data:
            return data
    # Last resort: downscale and retry the classic detector.
    import numpy as np
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY) if im.ndim == 3 else im
    det = cv2.QRCodeDetector()
    h, w = gray.shape[:2]
    for scale in (0.5, 0.4, 0.35, 0.3, 0.25):
        im2 = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        data, _, _ = det.detectAndDecode(im2)
        if data:
            return data
    return ""


def verify_qr(paths: list[Path]) -> None:
    try:
        import cv2
    except Exception as exc:
        print(f"skip cv2 verify: {exc}")
        return
    for path in paths:
        im = cv2.imread(str(path))
        if im is None:
            raise SystemExit(f"could not read {path} for QR verify")
        data = _decode_qr(im)
        print(f"decode {path.name}: {data!r}")
        if data != APP_URL:
            raise SystemExit(f"QR in {path} decoded to {data!r}, expected {APP_URL!r}")


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    qr = write_qr_plain(ASSETS / "qr_app.png")
    write_qr_caption(ASSETS / "qr_app_caption.png", qr)
    write_bill_with_qr(ASSETS / "bill_with_qr.png", qr)
    write_thumb(ASSETS / "demo_bill_thumb.png")
    screenshot_portal()
    verify_qr([
        ASSETS / "qr_app.png",
        ASSETS / "qr_app_caption.png",
        ASSETS / "bill_with_qr.png",
    ])
    return 0


if __name__ == "__main__":
    sys.exit(main())

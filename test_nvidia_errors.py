"""NVIDIA error classification, downscale payload, timeout fallback (mocked — 0 live calls)."""
import io
import unittest
from unittest.mock import patch

from PIL import Image

from nvidia_pipeline import (
    NvidiaCallError,
    format_nvidia_user_message,
    jpeg_payload_info,
    downscale_jpeg_image,
    call_nvidia_once,
    extract_bill_pipeline,
    MAX_SIDE,
    JPEG_QUALITY,
    NIM_TIMEOUT,
    NIM_FALLBACK_MODEL,
    NIM_MODEL,
)


class FormatErrorTests(unittest.TestCase):
    def test_auth_401_bilingual(self):
        msg = format_nvidia_user_message(NvidiaCallError("auth", "NVIDIA HTTP 401", status=401, elapsed_s=1.2))
        self.assertIn("API కీ సమస్య", msg)
        self.assertIn("API key problem", msg)
        self.assertIn("401", msg)
        self.assertNotIn("nvapi", msg.lower())

    def test_auth_403(self):
        msg = format_nvidia_user_message(NvidiaCallError("auth", "NVIDIA HTTP 403", status=403, elapsed_s=0.4))
        self.assertIn("API key problem", msg)
        self.assertIn("403", msg)

    def test_timeout_slow_server(self):
        msg = format_nvidia_user_message(NvidiaCallError("timeout", "NVIDIA timeout after 60.00s", elapsed_s=60))
        self.assertIn("సర్వర్ నెమ్మదిగా ఉంది", msg)
        self.assertIn("timed out", msg.lower())

    def test_other_http_shows_code(self):
        msg = format_nvidia_user_message(NvidiaCallError("http", "NVIDIA HTTP 429", status=429, elapsed_s=2))
        self.assertIn("HTTP 429", msg)

    def test_missing_key(self):
        msg = format_nvidia_user_message(NvidiaCallError("missing_key", "NVIDIA_API_KEY missing"))
        self.assertIn("NVIDIA_API_KEY లేదు", msg)

    def test_plain_timeout_string(self):
        msg = format_nvidia_user_message(RuntimeError("HTTPSConnectionPool timed out"))
        self.assertIn("సర్వర్ నెమ్మదిగా ఉంది", msg)


class SelectedModelsTests(unittest.TestCase):
    def test_primary_and_fallback_are_live_models(self):
        self.assertEqual(NIM_MODEL, "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
        self.assertEqual(NIM_FALLBACK_MODEL, "minimaxai/minimax-m3.1-flash")
        self.assertNotIn("llama-3.2-90b", NIM_MODEL)
        self.assertNotIn("gemma-4-31b", NIM_FALLBACK_MODEL)


class DownscaleTests(unittest.TestCase):
    def test_long_side_and_payload(self):
        img = Image.new("RGB", (4000, 1200), color=(200, 180, 40))
        jpeg = downscale_jpeg_image(img)
        out = Image.open(io.BytesIO(jpeg))
        self.assertLessEqual(max(out.size), MAX_SIDE)
        self.assertEqual(max(out.size), MAX_SIDE)
        info = jpeg_payload_info(jpeg)
        self.assertEqual(info["jpeg_bytes"], len(jpeg))
        self.assertGreater(info["b64_bytes"], info["jpeg_bytes"])
        # q85 1600px should stay well under a few MB
        self.assertLess(info["jpeg_bytes"], 800_000)
        self.assertEqual(JPEG_QUALITY, 85)
        self.assertEqual(NIM_TIMEOUT, 60)


class FallbackOnTimeoutTests(unittest.TestCase):
    def test_timeout_then_fallback_model(self):
        img = Image.new("RGB", (200, 200), color=(20, 20, 20))
        calls = []

        def fake_once(image_bytes, mime="image/jpeg", prompt=None, model=None, timeout=None):
            calls.append({"model": model, "timeout": timeout})
            if model == NIM_MODEL or model is None:
                raise NvidiaCallError("timeout", "NVIDIA timeout after 60.00s", elapsed_s=60, model=model)
            # fallback: return a barely valid bill so pipeline can keep it
            raw = {
                "discom": "TGSPDCL", "usc_no": None, "category": "1B(i)",
                "contracted_load_kw": 3, "phase": "1", "bill_date": "06/11/2026",
                "prev_reading": 100, "present_reading": 254, "units": 154,
                "days": 31, "energy_charges": 599.20, "fixed_charges": 30,
                "customer_charges": 90, "electricity_duty": 9.24, "interest_on_ed": 0,
                "surcharge": 0, "trueup_charges": 28.80, "trueup_units": 96,
                "fsa_fca": 0, "subsidy": 0, "adjustment": 0, "loss_gain": -0.24,
                "bill_amount": 757, "bill_amount_printed": 757, "total_due": 757,
                "due_date": "20/11/2026",
            }
            return raw, 1.2, "{}"

        with patch("nvidia_pipeline.call_nvidia_once", side_effect=fake_once):
            out = extract_bill_pipeline(img)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["model"], NIM_MODEL)
        self.assertEqual(calls[0]["timeout"], 60)
        self.assertEqual(calls[1]["model"], NIM_FALLBACK_MODEL)
        self.assertEqual(out["kept_model"], NIM_FALLBACK_MODEL)
        self.assertEqual(out["attempts_used"], 2)

    def test_auth_does_not_fallback(self):
        img = Image.new("RGB", (100, 100), color=(10, 10, 10))
        calls = []

        def fake_once(image_bytes, mime="image/jpeg", prompt=None, model=None, timeout=None):
            calls.append(model)
            raise NvidiaCallError("auth", "NVIDIA HTTP 401", status=401, elapsed_s=0.3, model=model)

        with patch("nvidia_pipeline.call_nvidia_once", side_effect=fake_once):
            with self.assertRaises(NvidiaCallError) as ctx:
                extract_bill_pipeline(img)
        self.assertEqual(ctx.exception.kind, "auth")
        self.assertEqual(ctx.exception.status, 401)
        self.assertEqual(calls, [NIM_MODEL])  # no second model


if __name__ == "__main__":
    unittest.main()

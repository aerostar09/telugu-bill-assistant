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
    extract_bill_pipeline_cached,
    save_cached_extract,
    load_cached_extract,
    _log_nvidia,
    _MEMORY_CACHE,
    get_cache_dir,
    MAX_SIDE,
    JPEG_QUALITY,
    MAX_TOKENS,
    ENABLE_THINKING,
    NIM_TIMEOUT,
    NIM_FALLBACK_TIMEOUT,
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


class ThinkingAndCacheTests(unittest.TestCase):
    def test_payload_disables_thinking_and_caps_tokens(self):
        captured = {}

        class FakeResp:
            status_code = 200
            def json(self):
                return {
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30,
                              "completion_tokens_details": {"reasoning_tokens": 0}},
                    "choices": [{"finish_reason": "stop", "message": {"content": "{\"units\": 82}"}}],
                }

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["json"] = json
            captured["timeout"] = timeout
            return FakeResp()

        img_bytes = b"fake-jpeg"
        with patch("nvidia_pipeline.requests.post", side_effect=fake_post):
            with patch("nvidia_pipeline.get_nvidia_api_key", return_value="x" * 8):
                raw, latency, content = call_nvidia_once(img_bytes)
        self.assertFalse(captured["json"]["chat_template_kwargs"]["enable_thinking"])
        self.assertFalse(ENABLE_THINKING)
        self.assertEqual(captured["json"]["max_tokens"], MAX_TOKENS)
        self.assertEqual(MAX_TOKENS, 1600)
        self.assertEqual(raw.get("units"), 82)
        self.assertGreaterEqual(NIM_FALLBACK_TIMEOUT, 60)

    def test_log_includes_token_counts_not_keys(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _log_nvidia(
                "http",
                status=200,
                elapsed_s=7.9,
                prompt_tokens=1529,
                completion_tokens=430,
                reasoning_tokens=0,
                api_key="should-not-appear",
                NVIDIA_API_KEY="should-not-appear",
            )
        out = buf.getvalue()
        self.assertIn("prompt_tokens=1529", out)
        self.assertIn("completion_tokens=430", out)
        self.assertIn("reasoning_tokens=0", out)
        self.assertNotIn("should-not-appear", out)
        self.assertNotIn("api_key=", out)

    def test_successful_extract_is_cached_and_replayed(self):
        import os, tempfile, shutil
        from nvidia_pipeline import _MEMORY_CACHE as mem
        img = Image.new("RGB", (200, 200), color=(30, 30, 30))
        tmp = tempfile.mkdtemp(prefix="tisc-cache-")
        calls = {"n": 0}

        def fake_once(image_bytes, mime="image/jpeg", prompt=None, model=None, timeout=None):
            calls["n"] += 1
            raw = {
                "discom": "TGSPDCL", "usc_no": None, "category": "1A",
                "contracted_load_kw": 3, "phase": "1", "bill_date": "04/02/2026",
                "prev_reading": 100, "present_reading": 182, "units": 82,
                "days": 30, "energy_charges": 199, "fixed_charges": 30,
                "customer_charges": 70, "electricity_duty": 4.92, "interest_on_ed": 0,
                "surcharge": 10, "trueup_charges": 0, "trueup_units": None,
                "fsa_fca": 0, "subsidy": 0, "adjustment": 0, "loss_gain": 0.08,
                "bill_amount": 314, "bill_amount_printed": 314, "total_due": 314,
                "due_date": "18-02-2026",
            }
            return raw, 1.1, "{}"

        mem.clear()
        try:
            with patch.dict(os.environ, {"TISC_EXTRACT_CACHE": tmp}):
                with patch("nvidia_pipeline.call_nvidia_once", side_effect=fake_once):
                    first = extract_bill_pipeline_cached(img, use_cache=True)
                    second = extract_bill_pipeline_cached(img, use_cache=True)
            self.assertFalse(first.get("from_cache"))
            self.assertTrue(second.get("from_cache"))
            self.assertEqual(first["bill"]["units"], 82)
            self.assertEqual(second["bill"]["bill_amount"], 314)
            self.assertEqual(second["bill"]["surcharge"], 10)
            self.assertEqual(calls["n"], 1)
            # disk file exists
            files = [n for n in os.listdir(tmp) if n.endswith(".json")]
            self.assertEqual(len(files), 1)
        finally:
            mem.clear()
            shutil.rmtree(tmp, ignore_errors=True)

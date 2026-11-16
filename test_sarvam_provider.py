"""PROVIDER=sarvam switch: mocked HTTP only (no network, no key value printed)."""
import json
import os
import unittest
from unittest.mock import patch, MagicMock

from PIL import Image

import sarvam_provider as sp
from nvidia_pipeline import NvidiaCallError, extract_bill_pipeline, VISION_PROMPT, _cache_key

BILL = {
    "discom": "TGSPDCL", "category": "1B(i)", "contracted_load_kw": 3, "bill_date": "06/11/2026",
    "prev_reading": 11000, "present_reading": 11154, "units": 154, "days": 31,
    "energy_charges": 599.20, "fixed_charges": 30, "customer_charges": 90, "electricity_duty": 9.24,
    "interest_on_ed": 0, "surcharge": 0, "trueup_charges": 28.80, "trueup_units": 96,
    "fsa_fca": 0, "subsidy": 0, "adjustment": 0, "interest_on_cd": 0, "loss_gain": -0.24,
    "bill_amount": 757, "total_due": 757, "due_date": "20-11-26",
    "is_electricity_bill": True, "image_quality": "clear",
}


def _resp(status=200, content=None, usage=None):
    r = MagicMock()
    r.status_code = status
    body = {"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": usage or {"prompt_tokens": 2000, "completion_tokens": 1000,
                               "completion_tokens_details": {"reasoning_tokens": 600}}}
    r.json.return_value = body
    r.text = json.dumps(body)
    return r


ENV = {"PROVIDER": "sarvam", "SARVAM_API_KEY": "test-key-not-real"}


class ProviderSwitchTests(unittest.TestCase):
    def test_default_is_nvidia(self):
        with patch.dict(os.environ, {"PROVIDER": ""}):
            self.assertEqual(sp.get_provider(), "nvidia")
        with patch.dict(os.environ, {"PROVIDER": "bogus"}):
            self.assertEqual(sp.get_provider(), "nvidia")
        with patch.dict(os.environ, {"PROVIDER": "Sarvam"}):
            self.assertEqual(sp.get_provider(), "sarvam")

    def test_sarvam_pipeline_uses_same_prompt_and_post_ocr(self):
        img = Image.new("RGB", (300, 300), (240, 240, 240))
        with patch.dict(os.environ, ENV), \
                patch("sarvam_provider.requests.post",
                      return_value=_resp(content=json.dumps({**BILL, "trueup_charges": 28.88}))) as post:
            out = extract_bill_pipeline(img)
        self.assertEqual(post.call_count, 1)
        url = post.call_args.args[0]
        payload = post.call_args.kwargs["json"]
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(url, "https://api.sarvam.ai/v2/chat/completions")
        self.assertEqual(payload["model"], "glm5.3-flash")
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertEqual(payload["messages"][0]["content"][0]["text"], VISION_PROMPT)
        self.assertTrue(payload["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertIn("test-key-not-real", headers["Authorization"])
        self.assertEqual(out["provider"], "sarvam")
        self.assertEqual(out["kept_model"], "glm5.3-flash")
        self.assertEqual(out["bill"]["trueup_charges"], 28.80)  # post-OCR snap still applied
        self.assertTrue(out["checks"]["consumer_ok"])
        cost = out["attempts"][0]["cost_inr"]
        self.assertAlmostEqual(cost, (2000 * 13.5 + 1000 * 45.0) / 1e6, places=6)

    def test_fallback_to_gemma_on_http_error(self):
        img = Image.new("RGB", (200, 200), (200, 200, 200))
        seq = [_resp(status=503, content=None), _resp(content=json.dumps(BILL))]
        with patch.dict(os.environ, ENV), patch("sarvam_provider.requests.post", side_effect=seq) as post:
            out = extract_bill_pipeline(img)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[1].kwargs["json"]["model"], "gemma4")
        self.assertNotIn("reasoning_effort", post.call_args_list[1].kwargs["json"])
        self.assertEqual(out["kept_model"], "gemma4")

    def test_missing_key_raises_without_http(self):
        img = Image.new("RGB", (100, 100))
        env = {"PROVIDER": "sarvam", "SARVAM_API_KEY": ""}
        with patch.dict(os.environ, env), patch("sarvam_provider.get_sarvam_api_key", return_value=None), \
                patch("sarvam_provider.requests.post") as post:
            with self.assertRaises(NvidiaCallError) as ctx:
                extract_bill_pipeline(img)
        self.assertEqual(ctx.exception.kind, "missing_key")
        post.assert_not_called()

    def test_auth_error_message_has_no_key(self):
        with patch.dict(os.environ, ENV), patch("sarvam_provider.requests.post", return_value=_resp(status=401)):
            with self.assertRaises(NvidiaCallError) as ctx:
                sp.call_sarvam_once(b"\xff\xd8\xff", model="glm5.3-flash")
        self.assertNotIn("test-key-not-real", str(ctx.exception))
        self.assertEqual(ctx.exception.kind, "auth")

    def test_cache_key_differs_by_provider_nvidia_unchanged(self):
        import hashlib
        data = b"abc"
        with patch.dict(os.environ, {"PROVIDER": ""}):
            self.assertEqual(_cache_key(data), hashlib.sha256(data).hexdigest())
        with patch.dict(os.environ, {"PROVIDER": "sarvam"}):
            self.assertNotEqual(_cache_key(data), hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main()

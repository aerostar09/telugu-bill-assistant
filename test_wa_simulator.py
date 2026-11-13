"""WhatsApp demo chat: short reply, concept labels, no PII, no paid APIs."""
from __future__ import annotations

import unittest

from demo_data import lakshmi_demo_bundle
from dashboard import build_dashboard_model
from self_checks import run_all_checks
from wa_simulator import (
    CONCEPT_EN,
    CONCEPT_TE,
    BANNER_HTML,
    USER_PHOTO_CAPTION,
    build_wa_reply,
    default_wa_thread,
    _result_key,
    _render_messages,
)


class WhatsAppDemoTests(unittest.TestCase):
    def test_concept_labels_are_explicit(self):
        self.assertIn("Demo / Concept", CONCEPT_EN)
        self.assertIn("not an official TGSPDCL service", CONCEPT_EN)
        self.assertIn("సిమ్యులేషన్", CONCEPT_TE)
        self.assertIn("87124 41912", CONCEPT_TE)
        self.assertIn("Explain my bill", CONCEPT_TE)
        self.assertIn(CONCEPT_TE, BANNER_HTML)
        self.assertIn(CONCEPT_EN, BANNER_HTML)

    def test_lakshmi_reply_is_the_short_summary(self):
        bundle = lakshmi_demo_bundle()
        model = build_dashboard_model(
            bundle["bill"], bundle["prev_bill"], run_all_checks(bundle["bill"])
        )
        result = {"bill": bundle["bill"], "prev_bill": bundle["prev_bill"], "model": model}
        text = build_wa_reply(result)
        self.assertIn("757", text)
        self.assertIn("154", text)
        self.assertIn("రూపాయలు", text)
        # Must stay the short voice script, not the long charge template.
        self.assertNotIn("599.20", text)
        self.assertNotIn("కస్టమర్ ఛార్జీ", text)
        # Default (no result) uses the same PII-free demo numbers.
        self.assertEqual(build_wa_reply(None), text)

    def test_default_thread_has_photo_and_short_reply(self):
        thread = default_wa_thread(None)
        self.assertEqual(thread[1]["role"], "user")
        self.assertEqual(thread[1]["image"], "thumb")
        self.assertEqual(thread[1]["text"], USER_PHOTO_CAPTION)
        self.assertTrue(thread[2].get("audio"))
        self.assertIn("757", thread[2]["text"])
        # Fictional sample only — never a real consumer name or USC.
        blob = " ".join(str(m.get("text") or "") for m in thread)
        self.assertNotIn("Jayaram", blob)
        self.assertNotIn("Mamidi", blob)
        self.assertNotRegex(blob, r"\bUSC\b")

    def test_render_includes_thumb_and_concept_header(self):
        html = _render_messages(
            default_wa_thread(None),
            audio_uri="",
            thumb_uri="data:image/png;base64,AAA",
        )
        self.assertIn("data-testid=\"wa-frame\"", html)
        self.assertIn("wa-thumb", html)
        self.assertIn(CONCEPT_EN, html)
        self.assertIn("WhatsApp డెమో", html)
        self.assertIn("fictional, no PII", html)

    def test_result_key_changes_with_units(self):
        a = {"bill": {"units": 154, "bill_amount": 757}, "display_name": "demo"}
        b = {"bill": {"units": 82, "bill_amount": 314}, "display_name": "demo"}
        self.assertNotEqual(_result_key(a), _result_key(b))
        self.assertEqual(_result_key(None), "demo-default")


if __name__ == "__main__":
    unittest.main()

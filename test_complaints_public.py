"""Anonymised public complaints set used by the DISCOM tab."""
import unittest

from discom_dashboard import (
    load_complaints, issue_counts, sample_map_rows, sample_anomaly_rows, queries_avoided_concept,
    SOURCE_LABEL, TG_DISTRICT_HQ,
)


class ComplaintsPublicTests(unittest.TestCase):
    def test_n_71_and_no_pii_columns(self):
        rows = load_complaints()
        self.assertEqual(len(rows), 71)
        keys = set(rows[0].keys())
        self.assertNotIn("url", keys)
        self.assertNotIn("quote_or_summary", keys)
        blob = " ".join(" ".join(r.values()) for r in rows).lower()
        self.assertNotIn("http", blob)
        self.assertNotIn("@", blob)
        self.assertIn("n=71", SOURCE_LABEL)

    def test_trueup_is_top_theme(self):
        counts = {r["specific_issue"]: r["count"] for r in issue_counts()}
        self.assertEqual(counts["true-up"], 16)
        self.assertEqual(sum(counts.values()), 71)

    def test_sample_map_and_anomalies_labelled(self):
        self.assertEqual(len(TG_DISTRICT_HQ), 33)
        self.assertEqual(len(sample_map_rows()), 33)
        rows = sample_anomaly_rows()
        self.assertTrue(all(r["service_no"].startswith("XXXX") for r in rows))
        self.assertTrue(all(r["status"] == "sample" for r in rows))

    def test_queries_avoided_is_concept_not_kpi(self):
        c = queries_avoided_concept()
        self.assertEqual(c["n"], 71)
        self.assertIn("not a measured", c["note"].lower())
        self.assertEqual(c["yes"] + c["partial"] <= 71, True)


if __name__ == "__main__":
    unittest.main()

import csv
import hashlib
import io
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pairglass.core import compare


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.baseline = Path(self.directory.name) / "baseline.csv"
        self.candidate = Path(self.directory.name) / "candidate.csv"

    def write(self, path, header, rows):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)

    def pair(self, header, before, after):
        self.write(self.baseline, header, before)
        self.write(self.candidate, header, after)

    def demo(self):
        before, after = [], []
        for language, count, b_pass, c_pass in (("hi", 40, 36, 24), ("en", 320, 252, 284), ("es", 40, 32, 32)):
            for index in range(count):
                common = [f"{language}-{index:03}", language, "even" if index % 2 == 0 else "odd"]
                before.append([common[0], index < b_pass, *common[1:]])
                after.append([common[0], index < c_pass, *common[1:]])
        self.pair(["id", "passed", "language", "task"], before, after)

    def test_hidden_slice_regression_and_all_eligible_hypotheses(self):
        self.demo()
        report = compare(self.baseline, self.candidate, slices=["task", "language"])
        self.assertEqual(report["schema_version"], "pairglass/v1")
        self.assertEqual(report["summary"]["n"], 400)
        self.assertEqual(report["summary"]["baseline_rate"], 0.8)
        self.assertEqual(report["summary"]["candidate_rate"], 0.85)
        self.assertEqual(report["summary"]["delta"], 0.05)
        self.assertEqual(report["summary"]["wins"], 32)
        self.assertEqual(report["summary"]["losses"], 12)
        self.assertEqual(report["summary"]["both_pass"], 308)
        self.assertEqual(report["summary"]["both_fail"], 48)
        self.assertEqual(report["summary"]["flagged_slices"], 1)
        self.assertFalse(report["gate_passed"])
        self.assertEqual(report["regressions"], ['["language","hi"]'])
        groups = report["groups"]
        self.assertEqual(groups[0]["key"], "__overall__")
        self.assertEqual(groups[0]["decision"], "improved")
        self.assertEqual([(item["column"], item["value"]) for item in groups[1:]], [
            ("language", "en"), ("language", "es"), ("language", "hi"), ("task", "even"), ("task", "odd")
        ])
        hi = groups[3]
        self.assertEqual(hi["n"], 40)
        self.assertEqual(hi["delta"], -0.3)
        self.assertAlmostEqual(hi["p_value"], 1 / 4096)
        # Positive/stable groups still count toward the multiplicity family.
        self.assertAlmostEqual(hi["adjusted_p_value"], 6 / 4096)
        self.assertEqual(hi["decision"], "regression")

    def test_support_is_only_eligibility_rule(self):
        self.demo()
        report = compare(self.baseline, self.candidate, slices=("language", "task"), min_pairs=41)
        hi = next(group for group in report["groups"] if group["value"] == "hi")
        self.assertFalse(hi["tested"])
        self.assertIsNone(hi["adjusted_p_value"])
        self.assertAlmostEqual(hi["p_value"], 1 / 4096)
        self.assertEqual(hi["decision"], "insufficient")
        self.assertTrue(report["gate_passed"])

    def test_decision_requires_effect_and_statistical_evidence(self):
        before = [[str(index), 1] for index in range(100)]
        self.pair(["id", "passed"], before, [[str(index), int(index >= 6)] for index in range(100)])
        report = compare(self.baseline, self.candidate)
        self.assertEqual(report["groups"][0]["decision"], "regression")
        self.assertEqual(report["regressions"], ["__overall__"])
        self.assertEqual(report["summary"]["flagged_slices"], 0)
        report = compare(self.baseline, self.candidate, max_drop=0.1)
        self.assertEqual(report["groups"][0]["decision"], "watch")
        self.pair(["id", "passed"], before, [[str(index), int(index >= 2)] for index in range(100)])
        report = compare(self.baseline, self.candidate, max_drop=0.01)
        self.assertEqual(report["groups"][0]["decision"], "watch")

    def test_exact_threshold_is_inclusive(self):
        before = [[str(index), 1] for index in range(100)]
        self.pair(["id", "passed"], before, [[str(index), int(index >= 5)] for index in range(100)])
        report = compare(self.baseline, self.candidate, max_drop=0.05, alpha=0.03125)
        self.assertEqual(report["groups"][0]["decision"], "regression")

    def test_sorted_cases_pass_tokens_notes_and_means(self):
        header = [" id ", "passed", "language", "cost_usd", "latency_ms", "note", "unused"]
        before = [
            [" z ", "PASS", "hi", 2, 50, "quoted, note\nnext line", "old"],
            ["a", "false", "en", 0, 100, "<script>", "old"],
            ["m", "True", "hi", 4, 150, "", "old"],
            ["b", "0", "en", 2, 100, "", "old"],
        ]
        after = [
            ["b", "FaIl", "en", 2, 120, "", "new"],
            ["z", "0", "hi", 2, 60, "loss note", "new"],
            ["m", "1", "hi", 4, 180, "", "new"],
            ["a", " pass ", "en", 4, 120, "win note", "new"],
        ]
        self.pair(header, before, after)
        report = compare(self.baseline, self.candidate, slices=["language"], min_pairs=1)
        cases = report["cases"]
        self.assertEqual([case["id"] for case in cases], ["a", "b", "m", "z"])
        self.assertEqual([case["outcome"] for case in cases], ["win", "stable-fail", "stable-pass", "loss"])
        self.assertEqual(cases[-1]["baseline_note"], "quoted, note\nnext line")
        self.assertEqual(cases[-1]["candidate_note"], "loss note")
        self.assertEqual(cases[0]["slices"], {"language": "en"})
        self.assertEqual(cases[0]["baseline_cost_usd"], 0)
        self.assertEqual(cases[0]["candidate_cost_usd"], 4)
        self.assertEqual(report["metrics"]["cost_usd"], {"baseline": 2, "candidate": 3, "delta": 1})
        self.assertEqual(report["metrics"]["latency_ms"], {"baseline": 100, "candidate": 120, "delta": 20})
        self.assertEqual(report["groups"][0]["decision"], "stable")

    def test_byte_hash_audit_and_repeatability(self):
        raw = b"\xef\xbb\xbfid,passed\r\nb,true\r\na,false\r\n"
        self.baseline.write_bytes(raw)
        self.candidate.write_bytes(raw)
        report = compare(self.baseline, self.candidate)
        self.assertEqual(report, compare(self.baseline, self.candidate))
        for role, name in (("baseline", "baseline.csv"), ("candidate", "candidate.csv")):
            self.assertEqual(report["inputs"][role], {"name": name, "sha256": hashlib.sha256(raw).hexdigest(), "rows": 2})
        self.assertNotIn(self.directory.name, json.dumps(report))
        self.assertIsNone(report["metrics"]["cost_usd"])
        self.assertIsNone(report["cases"][0]["baseline_latency_ms"])
        json.dumps(report, allow_nan=False)

    def test_ignored_metadata_can_change_and_does_not_create_slices(self):
        self.pair(["id", "passed", "metadata"], [["a", 1, "before"]], [["a", 0, "after"]])
        report = compare(self.baseline, self.candidate)
        self.assertEqual(len(report["groups"]), 1)
        self.assertEqual(report["cases"][0]["slices"], {})
        self.assertEqual(report["groups"][0]["decision"], "insufficient")
        self.assertTrue(report["gate_passed"])
        with self.assertRaisesRegex(ValueError, "metadata differs"):
            compare(self.baseline, self.candidate, slices=["metadata"])

    def test_slice_keys_are_unambiguous_and_values_preserved(self):
        self.pair(["id", "passed", "a=b", "a"], [["x", 1, "c", "b=c"]], [["x", 1, "c", "b=c"]])
        groups = compare(self.baseline, self.candidate, slices=["a=b", "a"])["groups"]
        self.assertNotEqual(groups[1]["key"], groups[2]["key"])
        self.assertEqual(json.loads(groups[1]["key"]), ["a", "b=c"])

    def test_invalid_csv_schema_rows_and_values(self):
        self.candidate.write_text("id,passed\na,1\n", encoding="utf-8")
        examples = [
            ("", "empty"),
            ("id,passed\n", "no data rows"),
            ("id,,passed\na,x,1\n", "blank header"),
            ("id,passed, id \na,1,b\n", "duplicate headers"),
            ("id,result\na,1\n", "missing required column"),
            ("id,passed\n ,1\n", "blank id"),
            ("id,passed\na,1\na,0\n", "duplicate id"),
            ("id,passed\na,1\n a ,0\n", "duplicate id"),
            ("id,passed\na,yes\n", "invalid passed"),
            ("id,passed\na,1,extra\n", "fields"),
            ("id,passed\na\n", "fields"),
            ("id,passed\n\n", "fields"),
            ('id,passed\na,"true', "malformed"),
        ]
        for text, message in examples:
            with self.subTest(text=text):
                self.baseline.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    compare(self.baseline, self.candidate)

    def test_exact_id_matching(self):
        self.pair(["id", "passed"], [["a", 1], ["b", 1]], [["a", 1], ["c", 1]])
        with self.assertRaisesRegex(ValueError, "id sets must match exactly"):
            compare(self.baseline, self.candidate)

    def test_optional_metrics_must_match_and_be_complete(self):
        self.write(self.baseline, ["id", "passed", "cost_usd"], [["a", 1, 1]])
        self.write(self.candidate, ["id", "passed"], [["a", 1]])
        with self.assertRaisesRegex(ValueError, "metric columns must be present in both"):
            compare(self.baseline, self.candidate)
        for metric in ("cost_usd", "latency_ms"):
            for value in ("", "NaN", "inf", "-1", "bad"):
                with self.subTest(metric=metric, value=value):
                    self.pair(["id", "passed", metric], [["a", 1, value]], [["a", 1, 0]])
                    with self.assertRaisesRegex(ValueError, metric):
                        compare(self.baseline, self.candidate)

    def test_large_finite_metric_means_do_not_overflow(self):
        self.pair(["id", "passed", "cost_usd"], [["a", 1, 1e308], ["b", 1, 1e308]], [["a", 1, 0], ["b", 1, 0]])
        mean = compare(self.baseline, self.candidate)["metrics"]["cost_usd"]
        self.assertEqual(mean["baseline"], 1e308)
        self.assertEqual(mean["delta"], -1e308)
        largest = sys.float_info.max
        for count in (3, 7):
            with self.subTest(count=count):
                before = [[str(index), 1, largest] for index in range(count)]
                after = [[str(index), 1, 0] for index in range(count)]
                self.pair(["id", "passed", "cost_usd"], before, after)
                report = compare(self.baseline, self.candidate)
                self.assertEqual(report["metrics"]["cost_usd"]["baseline"], largest)
                self.assertEqual(report["metrics"]["cost_usd"]["delta"], -largest)
                json.dumps(report, allow_nan=False)
        smallest = math.ldexp(1.0, -1074)
        self.pair(["id", "passed", "cost_usd"], [["a", 1, smallest]], [["a", 1, smallest]])
        self.assertEqual(compare(self.baseline, self.candidate)["metrics"]["cost_usd"]["baseline"], smallest)

    def test_invalid_options(self):
        self.pair(["id", "passed"], [["a", 1]], [["a", 1]])
        options = [
            {"slices": "language"}, {"slices": [""]}, {"slices": [" x"]},
            {"slices": [1]}, {"slices": ["x", "x"]}, {"slices": ["missing"]},
        ]
        options += [{"min_pairs": value} for value in (0, -1, 1.2, "1", True)]
        for name in ("max_drop", "alpha"):
            options += [{name: value} for value in (0, -0.1, 1.1, float("nan"), float("inf"), "0.05", True, 10**1000)]
        for option in options:
            with self.subTest(option=option), self.assertRaises(ValueError):
                compare(self.baseline, self.candidate, **option)

    def test_missing_paths_utf8_and_limits(self):
        self.candidate.write_text("id,passed\na,1\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "could not read baseline"):
            compare(self.baseline, self.candidate)
        with self.assertRaisesRegex(ValueError, "CSV file path"):
            compare(None, self.candidate)
        self.baseline.write_bytes(b"id,passed\na,\xff\n")
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            compare(self.baseline, self.candidate)
        self.baseline.write_bytes(b"x" * (20 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, "20 MiB"):
            compare(self.baseline, self.candidate)
        self.pair(["id", "passed"], [["a", 1], ["b", 0]], [["a", 1], ["b", 0]])
        with patch("pairglass.core.MAX_ROWS", 1), self.assertRaisesRegex(ValueError, "row limit"):
            compare(self.baseline, self.candidate)
        rows = [[str(index), 1, str(index)] for index in range(101)]
        self.pair(["id", "passed", "group"], rows, rows)
        with self.assertRaisesRegex(ValueError, "100 slice-group"):
            compare(self.baseline, self.candidate, slices=["group"])

    def test_no_more_than_100_groups_across_all_slice_columns(self):
        rows = [[str(index), 1, str(index), str(index)] for index in range(51)]
        self.pair(["id", "passed", "one", "two"], rows, rows)
        with self.assertRaisesRegex(ValueError, "100 slice-group"):
            compare(self.baseline, self.candidate, slices=["one", "two"])


if __name__ == "__main__":
    unittest.main()

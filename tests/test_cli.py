import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from pairglass.cli import main

ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def call(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = main(args)
        return result, out.getvalue(), err.getvalue()

    def test_demo_exports_and_failure_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = ["demo", "--output", str(root / "audit.html"), "--json", str(root / "audit.json"),
                    "--markdown", str(root / "audit.md"), "--losses", str(root / "losses.csv")]
            result, out, err = self.call(args)
            self.assertEqual(result, 0, err)
            self.assertIn("80.0% → 85.0%", out)
            report = json.loads((root / "audit.json").read_text())
            self.assertEqual(report["example"], "synthetic")
            self.assertIn("Synthetic example", (root / "audit.html").read_text())
            self.assertFalse(report["gate_passed"])
            self.assertEqual(report["summary"]["n"], 400)
            self.assertEqual(report["summary"]["wins"], 32)
            self.assertEqual(report["summary"]["losses"], 12)
            hi = next(group for group in report["groups"] if group["column"] == "language" and group["value"] == "hi")
            self.assertAlmostEqual(hi["adjusted_p_value"], 6 / 4096)
            self.assertEqual(hi["decision"], "regression")
            self.assertEqual(len((root / "losses.csv").read_text().splitlines()), 13)
            self.assertIn("Pairglass", (root / "audit.html").read_text())
            self.assertIn("language", (root / "audit.md").read_text())
            self.assertIn("Synthetic example", (root / "audit.md").read_text())
            self.assertEqual(self.call(args + ["--fail-on-regression"])[0], 1)

    def test_invalid_config_preserves_output(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "audit.html"
            target.write_text("previous report")
            result, _, err = self.call(["demo", "-o", str(target), "--alpha", "nan"])
            self.assertEqual(result, 2)
            self.assertTrue(err)
            self.assertEqual(target.read_text(), "previous report")

    def test_input_output_and_hardlink_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "run.csv"
            original = "id,passed\na,1\n"
            source.write_text(original)
            target = root / "alias.csv"
            os.link(source, target)
            for output in (source, target):
                result, _, err = self.call(["compare", str(source), str(source), "-o", str(output)])
                self.assertEqual(result, 2, err)
                self.assertEqual(source.read_text(), original)

    def test_duplicate_destinations_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "report"
            result, _, err = self.call(["demo", "-o", str(target), "--json", str(target)])
            self.assertEqual(result, 2, err)
            self.assertFalse(target.exists())

    def test_different_ids_rejected_without_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.csv").write_text("id,passed\na,1\n")
            (root / "b.csv").write_text("id,passed\nb,1\n")
            result, _, err = self.call(["compare", str(root / "a.csv"), str(root / "b.csv"), "-o", str(root / "report.html")])
            self.assertEqual(result, 2, err)
            self.assertFalse((root / "report.html").exists())

    def test_low_support_is_reported_but_does_not_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.csv").write_text("id,passed\na,1\n")
            (root / "b.csv").write_text("id,passed\na,0\n")
            result, out, err = self.call(["compare", str(root / "a.csv"), str(root / "b.csv"), "-o", str(root / "report.html"), "--fail-on-regression"])
            self.assertEqual(result, 0, err)
            self.assertIn("cannot fail", out)

    def test_loss_csv_formula_escaped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.csv").write_text("id,passed,note\n=1+2,1,@SUM(A1)\n")
            (root / "b.csv").write_text("id,passed,note\n=1+2,0,+cmd\n")
            result, _, err = self.call(["compare", str(root / "a.csv"), str(root / "b.csv"), "-o", str(root / "report.html"), "--losses", str(root / "losses.csv")])
            self.assertEqual(result, 0, err)
            contents = (root / "losses.csv").read_text()
            self.assertIn("'=1+2", contents)
            self.assertIn("'@SUM(A1)", contents)


if __name__ == "__main__":
    unittest.main()

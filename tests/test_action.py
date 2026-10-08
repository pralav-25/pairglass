import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ActionTests(unittest.TestCase):
    def test_regression_writes_summary_and_reports_before_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = dict(os.environ, PAIRGLASS_BASELINE=str(ROOT / "examples/baseline.csv"),
                       PAIRGLASS_CANDIDATE=str(ROOT / "examples/candidate.csv"),
                       PAIRGLASS_SLICES="language,task", PAIRGLASS_MAX_DROP="0.05",
                       PAIRGLASS_MIN_PAIRS="20", PAIRGLASS_ALPHA="0.05",
                       PAIRGLASS_REPORT_DIR=str(root / "audit"),
                       GITHUB_STEP_SUMMARY=str(root / "summary.md"))
            result = subprocess.run([sys.executable, str(ROOT / "scripts/run_action.py")],
                                    env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse(json.loads((root / "audit/report.json").read_text())["gate_passed"])
            self.assertIn("Gate failed", (root / "summary.md").read_text())
            for name in ("report.html", "report.md", "losses.csv"):
                self.assertTrue((root / "audit" / name).exists())


if __name__ == "__main__":
    unittest.main()

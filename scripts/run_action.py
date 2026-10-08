"""Composite-action adapter. Inputs are argv data, never interpolated shell code."""

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pairglass.cli import main  # noqa: E402

directory = Path(os.environ["PAIRGLASS_REPORT_DIR"])
args = [
    "compare", os.environ["PAIRGLASS_BASELINE"], os.environ["PAIRGLASS_CANDIDATE"],
    "--output", str(directory / "report.html"), "--json", str(directory / "report.json"),
    "--markdown", str(directory / "report.md"), "--losses", str(directory / "losses.csv"),
    "--max-drop", os.environ["PAIRGLASS_MAX_DROP"],
    "--min-pairs", os.environ["PAIRGLASS_MIN_PAIRS"],
    "--alpha", os.environ["PAIRGLASS_ALPHA"],
    "--fail-on-regression",
]
for column in os.environ["PAIRGLASS_SLICES"].split(","):
    if column.strip():
        args.extend(["--slice", column.strip()])
code = main(args)
if code in (0, 1) and os.environ.get("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
        handle.write((directory / "report.md").read_text(encoding="utf-8"))
raise SystemExit(code)

"""Generate synthetic paired evaluation results; no real user data or model calls."""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ["id", "passed", "language", "task", "cost_usd", "latency_ms", "note"]


def generate() -> None:
    runs = {"baseline": [], "candidate": []}
    for language, size, base_passes, wins, losses in [
        ("en", 320, 252, 32, 0), ("hi", 40, 36, 0, 12), ("es", 40, 32, 0, 0)
    ]:
        for index in range(size):
            baseline = index < base_passes
            candidate = baseline
            if baseline and index < losses:
                candidate = False
            if not baseline and index < base_passes + wins:
                candidate = True
            task = "retrieval" if index % 2 == 0 else "reasoning"
            changed = baseline != candidate
            for run, passed in (("baseline", baseline), ("candidate", candidate)):
                if language == "hi" and changed:
                    note = "Expected policy section retrieved" if run == "baseline" else "Retrieved the wrong policy section"
                elif changed:
                    note = "Expected answer not found" if run == "baseline" else "Exact-match answer recovered"
                else:
                    note = "Synthetic benchmark case"
                runs[run].append([
                    f"{language}-{index + 1:03d}", int(passed), language, task,
                    f"{0.004 if run == 'baseline' else 0.003:.4f}",
                    800 + index % 120 if run == "baseline" else 620 + index % 100,
                    note,
                ])
    for directory in (ROOT / "examples", ROOT / "src" / "pairglass" / "data"):
        directory.mkdir(parents=True, exist_ok=True)
        for run, rows in runs.items():
            with (directory / f"{run}.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(HEADER)
                writer.writerows(rows)


if __name__ == "__main__":
    generate()

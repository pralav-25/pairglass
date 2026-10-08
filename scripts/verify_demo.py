"""Check the published example against the paired-case counts, not a screenshot."""

import json
from pathlib import Path

from pairglass import compare

ROOT = Path(__file__).resolve().parents[1]
report = compare(ROOT / "examples/baseline.csv", ROOT / "examples/candidate.csv", slices=["language", "task"])
summary = report["summary"]
assert summary["n"] == 400
assert summary["baseline_rate"] == 0.8
assert summary["candidate_rate"] == 0.85
assert summary["wins"] == 32 and summary["losses"] == 12
assert summary["both_pass"] == 308 and summary["both_fail"] == 48
hi = next(group for group in report["groups"] if group["column"] == "language" and group["value"] == "hi")
assert hi["n"] == 40 and hi["baseline_rate"] == 0.9 and hi["candidate_rate"] == 0.6
assert hi["losses"] == 12 and hi["wins"] == 0
assert abs(hi["adjusted_p_value"] - 6 / 4096) < 1e-12
assert hi["decision"] == "regression" and not report["gate_passed"]
for name in ("baseline.csv", "candidate.csv"):
    assert (ROOT / "examples" / name).read_bytes() == (ROOT / "src/pairglass/data" / name).read_bytes()
snapshot = ROOT / "docs/demo.json"
if snapshot.exists():
    report["example"] = "synthetic"
    assert report == json.loads(snapshot.read_text()), "Published demo JSON is stale"
print("Reproduced: 400 pairs; overall +5 pp; hi −30 pp; adjusted p = 0.00146484375.")

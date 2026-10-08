# Check an evaluation change in GitHub Actions

Generate both runs with your existing evaluator, then audit the same case IDs. Pairglass does not run models or assign correctness labels.

```yaml
name: Evaluation regression check
on: [push, pull_request]
permissions:
  contents: read
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5
        with:
          python-version: '3.12'
      # Produce baseline.csv and candidate.csv before this step.
      - uses: pralav-25/pairglass@v0.1.0
        with:
          baseline: results/baseline.csv
          candidate: results/candidate.csv
          slices: language,task
      - name: Keep reports even when the gate fails
        if: always()
        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4
        with:
          name: evaluation-audit
          path: pairglass-artifacts/
          if-no-files-found: ignore
```

Pin Pairglass to a reviewed commit SHA for reproducible use. The action uses Python 3.10+ already available on the runner, needs no runtime packages, writes a job summary, and exports HTML, JSON, Markdown and pass-to-fail cases. It makes no API calls and posts no PR comments.

The gate fails only when a supported overall or declared slice group has a pass-rate drop of **at least** `max-drop` and Holm-adjusted one-sided p ≤ `alpha`. Defaults: `max-drop: '0.05'`, `min-pairs: '20'`, `alpha: '0.05'`. Small groups remain visible without failing the gate. Use the same case definitions, correctness evaluator, and slice metadata in both runs.

Exit 1 means regression evidence under the configured rule. Exit 2 means invalid input, configuration, or output. Inspect the job error and reports to distinguish the outcomes. Each report file is replaced atomically, but a set of report files is not a multi-file transaction. Reports include case IDs and optional notes: choose what you include before sharing artifacts.

The checked-in synthetic example intentionally fails this gate. To demonstrate it locally:

```bash
pairglass demo --fail-on-regression --output report.html
# Exit 1, with a usable report.
```

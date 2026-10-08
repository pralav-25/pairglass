# Contributing to Pairglass

Pairglass aims to make a model-change audit easy to reproduce and review. Contributions should preserve a small offline tool with understandable behavior.

## Get started

```sh
git clone https://github.com/pralav-25/pairglass.git
cd pairglass
python -m pip install -e .
python -m unittest discover -s tests
python scripts/verify_demo.py
pairglass demo --output report.html
```

Use Python 3.10 or later. The runtime uses the standard library. Open the demo report in a browser when changing the report renderer.

## Useful contributions

- Clearer errors for malformed evaluation exports, with a tiny CSV reproducer.
- More accessible report interactions and improvements for narrow screens.
- Documentation examples from real evaluation workflows, using shareable or synthetic data.
- Input adapters for a specific task or evaluation harness, with an explicit case-pairing contract.
- Numerical and edge-case tests against independently computed expected results.

Continuous-score adapters and clustered evaluation support are future work. Discuss their assumptions in an issue before implementing them; the current gate handles independent binary outcomes only.

## Report a bug

Include your Python version, Pairglass version, exact command, observed result and expected result. A minimal pair of synthetic CSVs is more useful than a screenshot alone. For statistical bugs, include the pass/fail transition counts and the independent calculation you expected.

## Submit a change

1. Keep the pull request focused on one behavior.
2. Explain the concrete problem and resulting behavior.
3. Add a meaningful regression test for a behavioral fix.
4. Run the test suite and synthetic demo verification.
5. Update the relevant documentation when a contract, flag or interpretation changes.

For report changes, inspect search, slice filtering, case details and JSON download in the standalone HTML. Avoid external fonts, scripts, analytics or assets that would require network access.

## Statistical changes

Read [the methodology](docs/methodology.md). Show the formula, its assumptions and the intended error-control guarantee. Include independently calculated reference cases, numerical edge cases and a calibration plan when adding a new inference method.

Preserve the distinction between an observed drop, statistical evidence and the user-selected practical threshold. Do not label a passing gate as proof that a model is equivalent, fair or safe. All support-eligible groups belong to the correction family, whether or not they look worse.

## Project boundaries

Prefer clear functions and small changes over additional infrastructure. Dependencies need a concrete benefit that justifies installation and maintenance costs. Evaluation runners, hosted dashboards, model training and account systems are outside the current scope.

Be respectful, explain your reasoning and leave room for different experience levels. Contributions are licensed under the project's [MIT license](LICENSE).

# Launch Pairglass with evidence

The goal is to make Pairglass easy to try, verify and discuss. Recognition is uncertain; a reproducible useful project gives people a concrete reason to look at the work.

## Before announcing

- Run `python -m unittest discover -s tests` and `python scripts/verify_demo.py`.
- Open the standalone demo and verify search, slice filtering, case review and JSON download.
- Check that the README screenshot matches the current synthetic report.
- Check the public [repository](https://github.com/pralav-25/pairglass) and [demo](https://pralav-25.github.io/pairglass/) while signed out.
- Label the example synthetic and keep its source CSVs reproducible.
- Ensure the installation instructions use the repository checkout until a PyPI release exists.

## Repository presentation

Suggested description:

> Offline paired evaluation audits: find subgroup regressions hidden by improving model averages, inspect lost cases, and export a standalone HTML report.

Suggested topics: `machine-learning`, `model-evaluation`, `regression-testing`, `data-science`, `python`, `cli`, `statistics`.

Pin the repository on your profile when you want it to represent your current work. Use a short release note with the concrete feature set, installation route, reproducible demo and current limits. Do not describe the first release as statistically novel or production-proven.

## Ready-to-edit announcement

> I built Pairglass to answer: “Your model improved. Who did it get worse for?”
>
> Feed it two evaluation CSVs with the same case IDs. It shows pass/fail transitions, compares declared subgroups, applies an exact paired test with Holm correction, and exports one interactive HTML file that works offline.
>
> The synthetic demo improves overall accuracy from 80% to 85%, while one language slice falls from 90% to 60%. You can inspect the exact cases behind that regression.
>
> Python 3.10+, no runtime dependencies or API key. I'm looking for feedback on CSV integration and whether the report helps you review model changes.
>
> Repository: https://github.com/pralav-25/pairglass
> Demo: https://pralav-25.github.io/pairglass/

This is draft copy for the author to post. It is not an instruction to send messages or contact maintainers.

## First week

1. Ask a small number of willing evaluation users to try their own CSVs. Request a concrete stumbling point, not a star.
2. Record problems as issues with small reproducible inputs.
3. Fix the highest-friction pairing, installation or report problem.
4. Add one documented integration only after its format and case identity rules are understood.
5. Publish a short follow-up showing what changed from actual feedback.

## Measure usefulness

Track reproducible bug reports, successful external uses, time to the first report and the most common format requests. Keep a small public changelog of completed improvements. Avoid manufactured engagement, unsolicited promotional pull requests or claims of adoption that have not occurred.

A later PyPI release can simplify installation after the package metadata and release process are verified. Continuous-score task adapters and clustered evaluation methods are possible follow-ups, not current features.

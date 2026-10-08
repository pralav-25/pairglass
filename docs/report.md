# Pairglass evaluation audit

**Synthetic example:** generated cases; no real model was evaluated.

**Gate failed** · 400 paired cases · 1 regression groups

The average doesn't tell the whole story.

| Measure | Baseline | Candidate | Change |
| --- | ---: | ---: | ---: |
| Pass rate | 80.0% | 85.0% | +5.0 pp |
| Mean cost / case | $0.0040 | $0.0030 | -0.0010 USD |
| Mean latency / case | 847.5 ms | 661.5 ms | -186.0 ms |

**Transitions:** 32 wins (fail → pass), 12 losses (pass → fail), 308 both pass, 48 both fail.

## Overall and declared slices

| Group | Pairs | Baseline | Candidate | Change | Holm p | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Overall | 400 | 80.0% | 85.0% | +5.0 pp | 1.0000 | improved |
| language = en | 320 | 78.8% | 88.8% | +10.0 pp | 1.0000 | improved |
| language = es | 40 | 80.0% | 80.0% | +0.0 pp | 1.0000 | stable |
| language = hi | 40 | 90.0% | 60.0% | -30.0 pp | 0.0015 | regression |
| task = reasoning | 200 | 80.0% | 85.0% | +5.0 pp | 1.0000 | improved |
| task = retrieval | 200 | 80.0% | 85.0% | +5.0 pp | 1.0000 | improved |

## Method and inputs

- Minimum support: 20 paired cases.
- Tolerated pass-rate drop: 5 percentage points.
- Significance threshold: 0.05; Holm correction across the tested overall and declared slice groups.
- The one-sided exact paired McNemar test uses discordant outcomes (wins and losses) to test for regression. Overall and declared slice groups are checked by the gate.
- Regression requires at least minimum support, a pass-rate drop at least as large as the tolerance, and Holm-adjusted p at or below the significance threshold. Any regression group fails the gate.
- Watch indicates a negative change that does not meet the regression rule. Improved indicates a positive change; stable indicates zero change. These are descriptive labels, not significance claims.
- Insufficient indicates too few paired cases; the group stays visible, is not tested, and does not fail the gate.
- Declared slice columns: language, task.

| Input | Name | Rows | SHA256 |
| --- | --- | ---: | --- |
| Baseline | baseline.csv | 400 | cc0c25dd0f253eacc0fa4bf0cd8f1e5e6ac973cc1759a2bd382457d54488be45 |
| Candidate | candidate.csv | 400 | 548b42187a8981d6b46bd374ee71753157b660c0bf2a7bd71687acae20faface |

Schema: pairglass/v1

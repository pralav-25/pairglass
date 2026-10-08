# How Pairglass decides that a group regressed

Pairglass compares existing binary evaluation outcomes for the same cases. It separates the observed effect size, statistical evidence and practical gate policy.

## Pairing and data contract

Each CSV contains one nonempty unique `id` and one binary `passed` value per case. Accepted outcome representations are `0`/`1`, `true`/`false` and `pass`/`fail`. Header names and IDs are trimmed; outcome tokens are trimmed and case-insensitive. Both runs must contain the exact same ID set; their row order may differ.

Values in each declared slice column are preserved exactly and must match across runs. Blank slice values are allowed as an explicit category. This ensures, for example, that a case cannot move from `language=hi` to `language=en` between the two evaluations. Optional `cost_usd` and `latency_ms` columns must appear in both headers when supplied; their values must be complete, numeric, finite and nonnegative. CSVs must use UTF-8.

The tool cannot verify that your ground truth or grading rubric stayed constant. Keep both fixed when comparing runs. A changed rubric, a changed evaluation set or selectively missing cases creates a different comparison question.

## Observed transitions

For any group of `n` paired cases, each case belongs to one of four categories:

| Baseline | Candidate | Transition |
| --- | --- | --- |
| Pass | Pass | Retained pass |
| Fail | Fail | Retained fail |
| Fail | Pass | Win |
| Pass | Fail | Loss |

Let `w` be wins and `l` be losses. Candidate accuracy minus baseline accuracy is `(w − l) / n`. A positive displayed change means improvement. The drop used by the gate is `(l − w) / n`, so a positive drop means deterioration.

Unchanged cases contribute to accuracy and support. Only discordant cases, `d = w + l`, contribute to the paired significance test.

## One-sided exact paired test

The question is directional: is the candidate more likely to turn a pass into a fail than the reverse?

Under the null of equal transition probabilities, losses among `d` discordant pairs follow a binomial distribution with probability `0.5`. Pairglass computes:

```text
p = P[Binomial(d, 0.5) >= l]
  = sum(comb(d, k) * 0.5**d for k in range(l, d + 1))
```

For `d = 0`, Pairglass assigns `p = 1`. The implementation evaluates the tail numerically rather than relying on a large-sample chi-square approximation.

This is the one-sided exact binomial formulation of the paired binary McNemar comparison. It differs from the usual two-sided McNemar p-value. References: [SciPy's exact binomial test and directional alternatives](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html), and [statsmodels' exact McNemar formulation](https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html).

## Which hypotheses are corrected together?

The family contains:

- Overall performance, when it meets the minimum support.
- Every value of every declared slice column that meets the minimum support.

`--slice language --slice task` analyzes individual language groups and individual task groups. It does not add language/task intersections. Groups that improve, tie or have no discordant cases remain in the family when they have sufficient support. Displaying or filtering the report does not change the family.

The support rule depends on `n`, not on the observed drop or p-value. Groups below `--min-pairs` remain descriptive and do not participate in the gate or multiplicity correction. Current input limits are 100,000 rows, 20 MiB per CSV and at most 100 declared slice-value groups plus overall.

## Holm correction

Sort the family's `m` raw p-values from smallest to largest. For the value at rank `i`, starting at 1, its Holm-adjusted value is:

```text
adjusted_p[i] = min(1, max((m - j + 1) * p[j] for j in 1..i))
```

Restore these adjusted values to their original groups. Holm's step-down procedure controls the family-wise probability of one or more false rejections when the individual p-values are valid; it does not require the slice hypotheses to be independent. See [the statsmodels multiple-testing reference](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html).

Correction applies within this one comparison. Repeatedly trying different slice definitions or rerunning until an attractive result appears creates additional selection that this family does not cover. Declare slices before inspecting outcomes when using the p-values as confirmatory evidence.

## The gate is a policy

A group is flagged only if all conditions hold:

```text
n >= min_pairs
baseline_accuracy - candidate_accuracy >= max_drop
holm_adjusted_p <= alpha
```

Defaults are `min_pairs=20`, `max_drop=0.05` and `alpha=0.05`. `0.05` is a five-percentage-point absolute drop. It is not a five-percent relative change.

The test asks about a deterioration from equal performance. It does not test the null that the true deterioration is at most the practical threshold. The threshold is a separate filter on the observed effect size. Choose it according to the consequences and evaluation design of your project.

Cost and latency summaries are descriptive. Pairglass does not test them for significance or use them to fail the binary-outcome gate.

## Worked synthetic example

The demo has 400 cases, of which the baseline passes 320 and the candidate passes 340. Overall accuracy rises from 80% to 85%.

Within `language=hi`, the baseline passes 36 of 40 and the candidate passes 24 of 40. There are 12 losses and zero wins:

```text
drop = (12 - 0) / 40 = 0.30
p = P[Binomial(12, 0.5) >= 12] = 1 / 4096 = 0.000244140625
```

With language and task slices there are six support-eligible comparisons, including overall. This group's raw p-value is the smallest in the family, so its adjusted p-value is `6 / 4096 = 0.00146484375`, which is below `0.05`. Its 30-percentage-point drop and 40 paired cases also satisfy the default policy.

The overall improvement and local regression can therefore both be true. Inspecting the 12 lost cases helps explain the observed result; the test does not identify its cause.

## Interpretation limits

- **Independent cases:** repeated answers for one prompt, related documents and shared users can violate the binomial model. Clustered inference is not implemented.
- **Binary outcomes:** numeric loss, F1, ranking scores and free-text quality require different methods or a justified pass/fail grading rule.
- **Fixed evaluations:** the result describes this paired evaluation set and depends on its relevance to future use.
- **Limited power:** a small or nearly unchanged group may fail to produce evidence despite a real deterioration.
- **No equivalence conclusion:** a passing gate means no tested group met this rule. It does not prove equal performance, absence of harm or fairness.
- **No causal explanation:** a slice regression identifies where to investigate. It does not establish why a model changed.

Pairglass implements established methods in a focused audit workflow. More general uncertainty analysis, repeated-run sensitivity and clustered comparisons are available in tools such as [evalstats](https://github.com/clavis-systems/evalstats).

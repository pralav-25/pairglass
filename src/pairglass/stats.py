"""Deterministic, dependency-free statistics for paired binary evaluations."""

from __future__ import annotations

import math
from collections.abc import Sequence
from functools import lru_cache


@lru_cache(maxsize=256)
def _mode_log_probability(total: int) -> float:
    half = total // 2
    # C(2m, m) / 2**(2m) = product((2i - 1) / (2i), i=1..m).
    # Summing log1p terms avoids subtracting large, nearly equal lgamma values.
    value = math.fsum(math.log1p(-1 / (2 * index)) for index in range(1, half + 1))
    if total % 2:
        value += math.log1p(-1 / (total + 1))
    return value


def _binomial_log_mass(total: int, successes: int) -> float:
    successes = min(successes, total - successes)
    half = total // 2
    return _mode_log_probability(total) + math.fsum(
        math.log(index / (total - index + 1))
        for index in range(successes + 1, half + 1)
    )


def paired_regression_p(wins: int, losses: int) -> float:
    """Return the exact one-sided binomial p-value for a paired regression.

    Only discordant pairs enter the test. Under the null, each discordance is
    equally likely to be a win or loss, so this is P[X >= losses] for
    X ~ Binomial(wins + losses, 0.5). It is 1 when there are no discordances.

    The shorter tail is summed with probability ratios and a log-space anchor.
    This avoids overflowing binomial coefficients and remains stable at the
    CSV limit of 100,000 pairs, including extremely small probabilities.
    """
    for name, value in (("wins", wins), ("losses", losses)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    total = wins + losses
    if total == 0 or losses == 0:
        return 1.0
    if wins == 0:
        return math.ldexp(1.0, -losses)
    if total <= 1024:
        # Small discordance sets are common and have exactly representable
        # dyadic tails. Integer summation preserves inclusive alpha boundaries.
        denominator = 1 << total
        if losses <= total // 2:
            index = losses - 1
            term = math.comb(total, index)
            weight = term
            while index > 0:
                term = term * index // (total - index + 1)
                weight += term
                index -= 1
            return (denominator - weight) / denominator
        index = losses
        term = math.comb(total, index)
        weight = term
        while index < total:
            term = term * (total - index) // (index + 1)
            weight += term
            index += 1
        return weight / denominator

    if losses > total // 2:
        anchor = losses

        def ratios():
            term = 1.0
            yield term
            for index in range(anchor, total):
                term *= (total - index) / (index + 1)
                yield term

        complement = False
    else:
        anchor = losses - 1

        def ratios():
            term = 1.0
            yield term
            for index in range(anchor, 0, -1):
                term *= index / (total - index + 1)
                yield term

        complement = True

    log_mass = _binomial_log_mass(total, anchor)
    tail = math.exp(log_mass + math.log(math.fsum(ratios())))
    result = 1.0 - tail if complement else tail
    return min(1.0, max(0.0, result))


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    """Return Holm-adjusted p-values in the input order.

    The caller supplies every eligible hypothesis, including the overall
    comparison. Eligibility must be based on support, never observed direction.
    """
    values: list[float] = []
    for value in p_values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("p-values must be finite numbers between 0 and 1")
        try:
            number = float(value)
        except (ValueError, OverflowError) as error:
            raise ValueError("p-values must be finite numbers between 0 and 1") from error
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise ValueError("p-values must be finite numbers between 0 and 1")
        values.append(number)

    adjusted = [1.0] * len(values)
    previous = 0.0
    for rank, index in enumerate(sorted(range(len(values)), key=values.__getitem__)):
        previous = max(previous, min(1.0, (len(values) - rank) * values[index]))
        adjusted[index] = previous
    return adjusted

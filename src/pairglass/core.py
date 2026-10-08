"""Strict CSV ingestion and an auditable paired-regression report."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path

from .stats import holm_adjust, paired_regression_p

MAX_ROWS = 100_000
MAX_BYTES = 20 * 1024 * 1024
MAX_SLICE_GROUPS = 100
METRIC_COLUMNS = ("cost_usd", "latency_ms")
_PASS_VALUES = {"1": True, "0": False, "true": True, "false": False, "pass": True, "fail": False}


@dataclass(frozen=True)
class _Row:
    passed: bool
    slices: dict[str, str]
    note: str
    cost_usd: float | None
    latency_ms: float | None


@dataclass(frozen=True)
class _Input:
    name: str
    sha256: str
    rows: dict[str, _Row]
    metrics: frozenset[str]


def _configuration(slices, min_pairs, max_drop, alpha) -> tuple[list[str], float, float]:
    if not isinstance(slices, (list, tuple)):
        raise ValueError("slices must be a list or tuple of column names")
    selected: list[str] = []
    for column in slices:
        if not isinstance(column, str) or not column.strip():
            raise ValueError("slice column names must be nonblank strings")
        if column != column.strip():
            raise ValueError("slice column names must not have surrounding whitespace")
        if column in selected:
            raise ValueError(f"duplicate slice column: {column!r}")
        selected.append(column)
    if isinstance(min_pairs, bool) or not isinstance(min_pairs, int) or min_pairs < 1:
        raise ValueError("min_pairs must be a positive integer")

    options: list[float] = []
    for name, value in (("max_drop", max_drop), ("alpha", alpha)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a finite number greater than 0 and at most 1")
        try:
            number = float(value)
        except (OverflowError, ValueError) as error:
            raise ValueError(f"{name} must be a finite number greater than 0 and at most 1") from error
        if not math.isfinite(number) or not 0.0 < number <= 1.0:
            raise ValueError(f"{name} must be a finite number greater than 0 and at most 1")
        options.append(number)
    return selected, options[0], options[1]


def _read_csv(path: str | Path, role: str, slices: list[str]) -> _Input:
    if not isinstance(path, (str, Path)):
        raise ValueError(f"{role} must be a CSV file path")
    file = Path(path)
    try:
        with file.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
    except (OSError, ValueError) as error:
        reason = error.strerror if isinstance(error, OSError) else str(error)
        raise ValueError(f"could not read {role} CSV {file.name!r}: {reason}") from error
    if len(raw) > MAX_BYTES:
        raise ValueError(f"{role} CSV exceeds the 20 MiB file limit")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(f"{role} CSV must be UTF-8; invalid bytes near offset {error.start}") from error

    reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
    rows: dict[str, _Row] = {}
    groups: set[tuple[str, str]] = set()
    try:
        raw_header = next(reader, None)
        if raw_header is None:
            raise ValueError(f"{role} CSV is empty; expected an id,passed header")
        header = [value.strip() for value in raw_header]
        if not header or any(not column for column in header):
            raise ValueError(f"{role} CSV has a blank header")
        if len(header) != len(set(header)):
            raise ValueError(f"{role} CSV has duplicate headers")
        for required in ("id", "passed", *slices):
            if required not in header:
                raise ValueError(f"{role} CSV is missing required column {required!r}")
        positions = {name: index for index, name in enumerate(header)}
        metrics = frozenset(column for column in METRIC_COLUMNS if column in positions)
        for values in reader:
            line = reader.line_num
            if len(values) != len(header):
                raise ValueError(
                    f"{role} CSV line {line} has {len(values)} fields; expected {len(header)}"
                )
            if len(rows) >= MAX_ROWS:
                raise ValueError(f"{role} CSV exceeds the 100,000 row limit")
            identifier = values[positions["id"]].strip()
            if not identifier:
                raise ValueError(f"{role} CSV line {line} has a blank id")
            if identifier in rows:
                raise ValueError(f"{role} CSV line {line} has duplicate id {identifier!r}")
            passed_value = values[positions["passed"]].strip().casefold()
            if passed_value not in _PASS_VALUES:
                raise ValueError(
                    f"{role} CSV line {line} has invalid passed value; "
                    "use 1, 0, true, false, pass, or fail"
                )
            slice_values = {column: values[positions[column]] for column in slices}
            groups.update(slice_values.items())
            if len(groups) > MAX_SLICE_GROUPS:
                raise ValueError(f"{role} CSV exceeds the 100 slice-group limit")
            metric_values: dict[str, float | None] = dict.fromkeys(METRIC_COLUMNS)
            for column in metrics:
                value = values[positions[column]].strip()
                if not value:
                    raise ValueError(f"{role} CSV line {line} has blank {column}; the column must be fully populated")
                try:
                    number = float(value)
                except (ValueError, OverflowError) as error:
                    raise ValueError(f"{role} CSV line {line} has invalid {column}; expected a finite nonnegative number") from error
                if not math.isfinite(number) or number < 0:
                    raise ValueError(f"{role} CSV line {line} has invalid {column}; expected a finite nonnegative number")
                metric_values[column] = number
            note = values[positions["note"]] if "note" in positions else ""
            rows[identifier] = _Row(
                passed=_PASS_VALUES[passed_value],
                slices=slice_values,
                note=note,
                cost_usd=metric_values["cost_usd"],
                latency_ms=metric_values["latency_ms"],
            )
    except csv.Error as error:
        raise ValueError(f"{role} CSV is malformed near line {reader.line_num}: {error}") from error
    if not rows:
        raise ValueError(f"{role} CSV contains no data rows")
    return _Input(file.name, hashlib.sha256(raw).hexdigest(), rows, metrics)


def _group(key, label, column, value, identifiers, baseline, candidate, min_pairs):
    wins = losses = both_pass = both_fail = 0
    for identifier in identifiers:
        before, after = baseline[identifier].passed, candidate[identifier].passed
        if before and after:
            both_pass += 1
        elif before:
            losses += 1
        elif after:
            wins += 1
        else:
            both_fail += 1
    n = wins + losses + both_pass + both_fail
    baseline_rate = (losses + both_pass) / n
    candidate_rate = (wins + both_pass) / n
    return {
        "key": key,
        "label": label,
        "column": column,
        "value": value,
        "n": n,
        "baseline_rate": baseline_rate,
        "candidate_rate": candidate_rate,
        "delta": (wins - losses) / n,
        "wins": wins,
        "losses": losses,
        "both_pass": both_pass,
        "both_fail": both_fail,
        "p_value": paired_regression_p(wins, losses),
        "adjusted_p_value": None,
        "tested": n >= min_pairs,
        "decision": "insufficient",
    }


def _mean_metric(rows: dict[str, _Row], column: str) -> float:
    # Nonnegative observations have a finite mean bounded by their maximum.
    # Scaling avoids both overflowing the total and a divide-first total that
    # rounds just above the largest representable float.
    scale = max(getattr(row, column) for row in rows.values())
    if scale == 0:
        return 0.0
    return scale * (math.fsum(getattr(row, column) / scale for row in rows.values()) / len(rows))


def compare(
    baseline: str | Path,
    candidate: str | Path,
    *,
    slices: list[str] | tuple[str, ...] = (),
    min_pairs: int = 20,
    max_drop: float = 0.05,
    alpha: float = 0.05,
) -> dict:
    """Compare paired binary CSV evaluations and return a JSON-ready report.

    Both files must contain the same unique, nonblank IDs. Only explicitly
    selected slice columns are used; their metadata must agree for each ID.
    Header and ID whitespace is trimmed, pass tokens are case-insensitive, and
    notes and slice values are preserved. Optional metrics must be present in
    both files and fully populated with finite, nonnegative values.

    Holm correction includes every group with sufficient pairs, including the
    overall comparison. A gate fails only for an adequately supported negative
    change meeting both the configured drop and adjusted significance limits.
    """
    selected, max_drop, alpha = _configuration(slices, min_pairs, max_drop, alpha)
    before = _read_csv(baseline, "baseline", selected)
    after = _read_csv(candidate, "candidate", selected)
    if before.metrics != after.metrics:
        mismatched = sorted(before.metrics.symmetric_difference(after.metrics))
        raise ValueError(f"metric columns must be present in both CSVs: {', '.join(mismatched)}")
    before_ids, after_ids = set(before.rows), set(after.rows)
    if before_ids != after_ids:
        missing = sorted(before_ids - after_ids)
        extra = sorted(after_ids - before_ids)
        details = []
        if missing:
            details.append(f"candidate missing {len(missing)} id(s), for example {missing[0]!r}")
        if extra:
            details.append(f"candidate has {len(extra)} extra id(s), for example {extra[0]!r}")
        raise ValueError("CSV id sets must match exactly; " + "; ".join(details))
    identifiers = sorted(before_ids)
    memberships: dict[tuple[str, str], list[str]] = {}
    cases = []
    for identifier in identifiers:
        b, c = before.rows[identifier], after.rows[identifier]
        for column in selected:
            if b.slices[column] != c.slices[column]:
                raise ValueError(f"slice metadata differs for id {identifier!r}, column {column!r}")
            memberships.setdefault((column, b.slices[column]), []).append(identifier)
        if b.passed and c.passed:
            outcome = "stable-pass"
        elif b.passed:
            outcome = "loss"
        elif c.passed:
            outcome = "win"
        else:
            outcome = "stable-fail"
        cases.append({
            "id": identifier,
            "baseline_pass": b.passed,
            "candidate_pass": c.passed,
            "outcome": outcome,
            "slices": dict(b.slices),
            "baseline_note": b.note,
            "candidate_note": c.note,
            "baseline_cost_usd": b.cost_usd,
            "candidate_cost_usd": c.cost_usd,
            "baseline_latency_ms": b.latency_ms,
            "candidate_latency_ms": c.latency_ms,
        })

    groups = [_group("__overall__", "Overall", None, None, identifiers, before.rows, after.rows, min_pairs)]
    for (column, value), members in sorted(memberships.items()):
        key = json.dumps([column, value], ensure_ascii=False, separators=(",", ":"))
        groups.append(_group(key, f"{column} = {value}", column, value, members, before.rows, after.rows, min_pairs))
    eligible = [group for group in groups if group["tested"]]
    for group, adjusted in zip(eligible, holm_adjust([group["p_value"] for group in eligible])):
        group["adjusted_p_value"] = adjusted
        delta = group["delta"]
        if delta < 0 and delta <= -max_drop + 1e-12 and adjusted <= alpha:
            group["decision"] = "regression"
        elif delta < 0:
            group["decision"] = "watch"
        elif delta > 0:
            group["decision"] = "improved"
        else:
            group["decision"] = "stable"
    regressions = [group["key"] for group in groups if group["decision"] == "regression"]
    overall = groups[0]
    summary = {name: overall[name] for name in (
        "n", "baseline_rate", "candidate_rate", "delta", "wins", "losses", "both_pass", "both_fail"
    )}
    summary["flagged_slices"] = sum(group["decision"] == "regression" for group in groups[1:])
    metrics = {}
    for column in METRIC_COLUMNS:
        if column in before.metrics:
            b_mean = _mean_metric(before.rows, column)
            c_mean = _mean_metric(after.rows, column)
            metrics[column] = {"baseline": b_mean, "candidate": c_mean, "delta": c_mean - b_mean}
        else:
            metrics[column] = None
    return {
        "schema_version": "pairglass/v1",
        "inputs": {
            "baseline": {"name": before.name, "sha256": before.sha256, "rows": len(before.rows)},
            "candidate": {"name": after.name, "sha256": after.sha256, "rows": len(after.rows)},
        },
        "config": {"slices": selected, "min_pairs": min_pairs, "max_drop": max_drop, "alpha": alpha},
        "groups": groups,
        "gate_passed": not regressions,
        "regressions": regressions,
        "summary": summary,
        "metrics": metrics,
        "cases": cases,
    }

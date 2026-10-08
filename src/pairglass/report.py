"""Self-contained, safely escaped report rendering using the Python standard library."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any


_TEMPLATE = Path(__file__).parent / "templates" / "report.html"
_DECISIONS = {"regression", "watch", "improved", "stable", "insufficient"}


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _number(value: Any, digits: int = 1) -> str:
    return f"{float(value):,.{digits}f}"


def _rate(value: Any) -> str:
    return f"{_number(float(value) * 100)}%"


def _delta(value: Any) -> str:
    return f"{float(value) * 100:+.1f} pp"


def _p(value: Any) -> str:
    if value is None:
        return "—"
    value = float(value)
    return "<0.0001" if value < 0.0001 else f"{value:.4f}"


def _decision(group: dict[str, Any]) -> str:
    value = group.get("decision", "insufficient")
    return value if value in _DECISIONS else "insufficient"


def _badge(group: dict[str, Any]) -> str:
    decision = _decision(group)
    return f'<span class="badge {decision}">{_escape(decision)}</span>'


def _slice_label(group: dict[str, Any]) -> str:
    return str(group.get("label", group.get("key", "Slice")))


def _bar_scale(groups: list[dict[str, Any]], max_drop: float) -> float:
    """Return a readable symmetric scale in percentage points."""
    largest = max([abs(float(g["delta"])) * 100 for g in groups] + [max_drop * 100, 1])
    return max(5, ((largest + 4.999999) // 5) * 5)


def _evidence_rows(groups: list[dict[str, Any]], scale: float) -> str:
    rows = []
    for group in groups:
        delta = float(group["delta"]) * 100
        width = min(abs(delta) / scale * 50, 50)
        left = 50 if delta >= 0 else 50 - width
        direction = "positive" if delta >= 0 else "negative"
        tested = bool(group.get("tested"))
        support = f'{int(group["n"]):,} pairs'
        adjusted = f'Holm p {_p(group.get("adjusted_p_value"))}' if tested else "Below minimum support"
        rows.append(
            f'<button class="evidence-row" type="button" data-group="{_escape(group["key"])}" '
            f'aria-pressed="false" aria-label="Explore {_escape(_slice_label(group))} cases">'
            f'<span class="group-copy"><strong>{_escape(_slice_label(group))}</strong>'
            f'<span class="muted">{support} <span class="middot">·</span> {_escape(adjusted)}</span></span>'
            f'<span class="delta-chart" aria-label="Pass-rate change {_delta(group["delta"])}">'
            f'<span class="chart-track"></span><span class="chart-zero"></span>'
            f'<span class="chart-bar {direction}" style="left:{left:.4f}%;width:{width:.4f}%"></span>'
            f'<span class="chart-dot {direction}" style="left:{50 + (width if delta >= 0 else -width):.4f}%"></span>'
            '</span>'
            f'<span class="group-rates"><strong class="{direction}">{_delta(group["delta"])}</strong>'
            f'<span class="muted">{_rate(group["baseline_rate"])} → {_rate(group["candidate_rate"])}</span></span>'
            f'{_badge(group)}<span class="row-arrow" aria-hidden="true">↗</span></button>'
        )
    return "\n".join(rows)


def _case_rows(cases: list[dict[str, Any]]) -> str:
    rows = []
    for case in cases[:25]:
        slices = ", ".join(f"{key}: {value}" for key, value in case.get("slices", {}).items())
        outcome = case.get("outcome", "stable-fail")
        label = {"loss": "Loss", "win": "Win", "stable-pass": "Both pass", "stable-fail": "Both fail"}.get(outcome, outcome)
        rows.append(
            f'<tr><td><strong class="case-id">{_escape(case["id"])}</strong>'
            f'<span class="case-slices">{_escape(slices) or "No declared slices"}</span></td>'
            f'<td><span class="pass-state {"pass" if case["baseline_pass"] else "fail"}">'
            f'{"Pass" if case["baseline_pass"] else "Fail"}</span>'
            f'<span class="case-note">{_escape(case.get("baseline_note") or "—")}</span></td>'
            f'<td><span class="pass-state {"pass" if case["candidate_pass"] else "fail"}">'
            f'{"Pass" if case["candidate_pass"] else "Fail"}</span>'
            f'<span class="case-note">{_escape(case.get("candidate_note") or "—")}</span></td>'
            f'<td><span class="outcome {"loss" if outcome == "loss" else "win" if outcome == "win" else "unchanged"}">'
            f'{_escape(label)}</span></td></tr>'
        )
    return "\n".join(rows)


def _metric_cards(metrics: dict[str, Any]) -> str:
    cards = []
    for key, label, unit in (("cost_usd", "Mean cost / case", "$"), ("latency_ms", "Mean latency / case", "ms")):
        metric = metrics.get(key)
        if metric is None:
            continue
        def display(value: Any) -> str:
            return f"${float(value):.4f}" if unit == "$" else f"{_number(value)} ms"
        change = float(metric["delta"])
        delta = f"{change:+.4f} USD" if unit == "$" else f"{change:+.1f} ms"
        cards.append(
            f'<div class="metric-card"><span class="eyebrow">{label}</span>'
            f'<div class="metric-values"><span>{display(metric["baseline"])}</span>'
            f'<span class="metric-arrow" aria-hidden="true">→</span><strong>{display(metric["candidate"])}</strong></div>'
            f'<span class="metric-change">{delta} <span class="muted">candidate minus baseline</span></span></div>'
        )
    if not cards:
        return ""
    return '<section class="metrics-grid" aria-label="Optional performance metrics">' + "".join(cards) + "</section>"


def _input_row(label: str, info: dict[str, Any]) -> str:
    return (f'<div class="input-row"><span class="eyebrow">{label}</span>'
            f'<strong>{_escape(info.get("name", label))}</strong>'
            f'<span class="muted">{int(info.get("rows", 0)):,} rows</span>'
            f'<code aria-label="SHA256 fingerprint">{_escape(info.get("sha256", "Unavailable"))}</code></div>')


def render_html(report: dict[str, Any]) -> str:
    """Render a portable HTML report. No user data is evaluated as HTML or JS."""
    summary = report["summary"]
    config = report["config"]
    groups = [g for g in report["groups"] if g["key"] != "__overall__"]
    scale = _bar_scale(groups, float(config["max_drop"]))
    passed = bool(report["gate_passed"])
    flagged = len(report.get("regressions", []))
    gate_detail = ("No evaluation group met all regression criteria." if passed else
                   f'{flagged} evaluation {"group met" if flagged == 1 else "groups met"} all regression criteria.')
    decision_counts = {key: sum(_decision(group) == key for group in groups) for key in _DECISIONS}
    overview = report.get("groups", [{}])[0]
    if overview.get("key") != "__overall__":
        overview = next((g for g in report["groups"] if g["key"] == "__overall__"), {})
    p_text = _p(overview.get("adjusted_p_value"))
    data = json.dumps(report, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    for unsafe, safe in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        data = data.replace(unsafe, safe)
    replacements = {
        "@@REPORT_JSON@@": data,
        "@@EXAMPLE_NOTICE@@": (
            '<p class="example-notice"><strong>Synthetic example.</strong> '
            '400 generated cases illustrate a hidden regression. No real model was evaluated.</p>'
            if report.get("example") == "synthetic" else ""
        ),
        "@@BASELINE_NAME@@": _escape(report["inputs"]["baseline"].get("name", "Baseline")),
        "@@CANDIDATE_NAME@@": _escape(report["inputs"]["candidate"].get("name", "Candidate")),
        "@@BASELINE_RATE@@": _rate(summary["baseline_rate"]),
        "@@CANDIDATE_RATE@@": _rate(summary["candidate_rate"]),
        "@@OVERALL_DELTA@@": _delta(summary["delta"]),
        "@@OVERALL_DIRECTION@@": "negative" if float(summary["delta"]) < 0 else "positive",
        "@@GATE_CLASS@@": "gate-pass" if passed else "gate-fail",
        "@@GATE_ICON@@": "✓" if passed else "!",
        "@@GATE_LABEL@@": "Gate passed" if passed else "Gate failed",
        "@@GATE_DETAIL@@": gate_detail,
        "@@PAIR_COUNT@@": f'{int(summary["n"]):,}',
        "@@WIN_COUNT@@": f'{int(summary["wins"]):,}',
        "@@LOSS_COUNT@@": f'{int(summary["losses"]):,}',
        "@@BOTH_PASS@@": f'{int(summary["both_pass"]):,}',
        "@@BOTH_FAIL@@": f'{int(summary["both_fail"]):,}',
        "@@UNCHANGED_COUNT@@": f'{int(summary["both_pass"]) + int(summary["both_fail"]):,}',
        "@@REGRESSION_COUNT@@": str(decision_counts["regression"]),
        "@@WATCH_COUNT@@": str(decision_counts["watch"]),
        "@@IMPROVED_COUNT@@": str(decision_counts["improved"]),
        "@@STABLE_COUNT@@": str(decision_counts["stable"]),
        "@@INSUFFICIENT_COUNT@@": str(decision_counts["insufficient"]),
        "@@GROUP_COUNT@@": str(len(groups)),
        "@@SCALE@@": _number(scale, 0),
        "@@POSITIVE_SCALE@@": _number(scale, 0),
        "@@EVIDENCE_ROWS@@": _evidence_rows(groups, scale),
        "@@EVIDENCE_EMPTY@@": "" if groups else '<div class="empty-state"><strong>No slices declared</strong><p>Declare slice columns when comparing runs to inspect changes within each group.</p></div>',
        "@@CASE_ROWS@@": _case_rows(report["cases"]),
        "@@INITIAL_CASE_COUNT@@": f'{min(len(report["cases"]), 25):,}',
        "@@CASE_TOTAL@@": f'{len(report["cases"]):,}',
        "@@METRIC_CARDS@@": _metric_cards(report.get("metrics", {})),
        "@@MIN_PAIRS@@": str(int(config["min_pairs"])),
        "@@MAX_DROP@@": f'{float(config["max_drop"]) * 100:g}',
        "@@ALPHA@@": f'{float(config["alpha"]):g}',
        "@@OVERALL_P@@": _escape(p_text),
        "@@OVERALL_BADGE@@": _badge(overview),
        "@@DECLARED_SLICES@@": _escape(", ".join(str(v) for v in config.get("slices", [])) or "None"),
        "@@BASELINE_INPUT@@": _input_row("Baseline", report["inputs"]["baseline"]),
        "@@CANDIDATE_INPUT@@": _input_row("Candidate", report["inputs"]["candidate"]),
        "@@SCHEMA_VERSION@@": _escape(report.get("schema_version", "pairglass/v1")),
    }
    template = _TEMPLATE.read_text(encoding="utf-8")
    for marker in replacements:
        count = template.count(marker)
        if count != 1:
            raise ValueError(f"Report template marker {marker!r} appears {count} times; expected exactly once")
    # Substitute the original template in one pass. User strings containing
    # markers are literal data, never another template substitution.
    return re.sub(r"@@[A-Z_]+@@", lambda match: replacements[match.group(0)], template)


def _md(value: Any) -> str:
    """Keep arbitrary labels inside one Markdown table cell or text line."""
    value = str(value).replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    value = html.escape(value, quote=False)
    for char in ("\\", "`", "*", "_", "[", "]", "|", "#"):
        value = value.replace(char, "\\" + char)
    return value


def render_markdown(report: dict[str, Any]) -> str:
    """Render a concise GitHub-friendly report with auditable inputs and method."""
    summary, config = report["summary"], report["config"]
    groups = report["groups"]
    passed = bool(report["gate_passed"])
    lines = [
        "# Pairglass evaluation audit", "",
        f'**{"Gate passed" if passed else "Gate failed"}** · {int(summary["n"]):,} paired cases · '
        f'{len(report.get("regressions", []))} regression groups', "",
        "The average doesn't tell the whole story.", "",
        "| Measure | Baseline | Candidate | Change |", "| --- | ---: | ---: | ---: |",
        f'| Pass rate | {_rate(summary["baseline_rate"])} | {_rate(summary["candidate_rate"])} | {_delta(summary["delta"])} |',
    ]
    if report.get("example") == "synthetic":
        lines[2:2] = ["**Synthetic example:** generated cases; no real model was evaluated.", ""]
    for key, label, unit in (("cost_usd", "Mean cost / case", "$"), ("latency_ms", "Mean latency / case", "ms")):
        metric = report.get("metrics", {}).get(key)
        if metric is not None:
            if unit == "$":
                values = (f'${float(metric["baseline"]):.4f}', f'${float(metric["candidate"]):.4f}', f'{float(metric["delta"]):+.4f} USD')
            else:
                values = (f'{float(metric["baseline"]):.1f} ms', f'{float(metric["candidate"]):.1f} ms', f'{float(metric["delta"]):+.1f} ms')
            lines.append(f"| {label} | {' | '.join(values)} |")
    lines.extend([
        "", f'**Transitions:** {int(summary["wins"]):,} wins (fail → pass), '
        f'{int(summary["losses"]):,} losses (pass → fail), '
        f'{int(summary["both_pass"]):,} both pass, {int(summary["both_fail"]):,} both fail.', "",
        "## Overall and declared slices", "",
        "| Group | Pairs | Baseline | Candidate | Change | Holm p | Decision |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for group in groups:
        lines.append(f'| {_md(_slice_label(group))} | {int(group["n"]):,} | {_rate(group["baseline_rate"])} | '
                     f'{_rate(group["candidate_rate"])} | {_delta(group["delta"])} | '
                     f'{_md(_p(group.get("adjusted_p_value")))} | {_md(_decision(group))} |')
    if not groups:
        lines.append("| No evaluation groups | — | — | — | — | — | — |")
    lines.extend([
        "", "## Method and inputs", "",
        f'- Minimum support: {int(config["min_pairs"])} paired cases.',
        f'- Tolerated pass-rate drop: {float(config["max_drop"]) * 100:g} percentage points.',
        f'- Significance threshold: {float(config["alpha"]):g}; Holm correction across the tested overall and declared slice groups.',
        "- The one-sided exact paired McNemar test uses discordant outcomes (wins and losses) to test for regression. Overall and declared slice groups are checked by the gate.",
        "- Regression requires at least minimum support, a pass-rate drop at least as large as the tolerance, and Holm-adjusted p at or below the significance threshold. Any regression group fails the gate.",
        "- Watch indicates a negative change that does not meet the regression rule. Improved indicates a positive change; stable indicates zero change. These are descriptive labels, not significance claims.",
        "- Insufficient indicates too few paired cases; the group stays visible, is not tested, and does not fail the gate.",
        f'- Declared slice columns: {_md(", ".join(str(v) for v in config.get("slices", [])) or "None")}.', "",
        "| Input | Name | Rows | SHA256 |", "| --- | --- | ---: | --- |",
    ])
    for key, label in (("baseline", "Baseline"), ("candidate", "Candidate")):
        info = report["inputs"][key]
        lines.append(f'| {label} | {_md(info.get("name", label))} | {int(info.get("rows", 0)):,} | {_md(info.get("sha256", "Unavailable"))} |')
    lines.extend(["", f'Schema: {_md(report.get("schema_version", "pairglass/v1"))}', ""])
    return "\n".join(lines)

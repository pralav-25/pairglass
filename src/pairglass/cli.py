"""A small local CLI. No model calls, network requests, or telemetry."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from importlib.resources import files

from . import __version__
from .core import compare
from .report import render_html, render_markdown


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pairglass", description="Reveal regressions hidden by an overall evaluation pass rate."
    )
    parser.add_argument("--version", action="version", version=f"Pairglass {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    real = commands.add_parser("compare", help="Audit two ID-paired CSV evaluation runs")
    real.add_argument("baseline", type=Path)
    real.add_argument("candidate", type=Path)
    real.add_argument("--slice", action="append", default=[], dest="slices", metavar="COLUMN")
    demo = commands.add_parser("demo", help="Run the reproducible synthetic hidden-regression example")
    for command in (real, demo):
        command.add_argument("--output", "-o", type=Path, default=Path("pairglass-report.html"))
        command.add_argument("--json", type=Path, dest="json_output", metavar="PATH")
        command.add_argument("--markdown", type=Path, dest="markdown_output", metavar="PATH")
        command.add_argument("--losses", type=Path, metavar="PATH", help="Export pass-to-fail cases as CSV")
        command.add_argument("--min-pairs", type=int, default=20)
        command.add_argument("--max-drop", type=float, default=0.05, help="Minimum pass-rate drop as a proportion (default: 0.05 = 5 pp)")
        command.add_argument("--alpha", type=float, default=0.05)
        command.add_argument("--fail-on-regression", action="store_true", help="Exit 1 if a supported group meets the regression rule")
    return parser


def _safe_cell(value: str) -> str:
    # A leading apostrophe prevents exported text from becoming a spreadsheet formula.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r")):
        return "'" + value
    return value


def _loss_csv(report: dict) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    slices = report["config"]["slices"]
    writer.writerow(["id", "baseline_pass", "candidate_pass", *slices, "baseline_note", "candidate_note"])
    for case in report["cases"]:
        if case["outcome"] == "loss":
            writer.writerow([
                _safe_cell(case["id"]), "1", "0",
                *[_safe_cell(case["slices"][column]) for column in slices],
                _safe_cell(case["baseline_note"]), _safe_cell(case["candidate_note"]),
            ])
    return stream.getvalue()


def _same_file(left: Path, right: Path) -> bool:
    if left.resolve() == right.resolve():
        return True
    try:
        return left.samefile(right)
    except FileNotFoundError:
        return False


def _write_reports(outputs: list[tuple[Path, str]], protected: list[Path]) -> None:
    """Stage every file first; replace each destination atomically after staging."""
    destinations: list[Path] = []
    for destination, _ in outputs:
        if any(_same_file(destination, source) for source in protected):
            raise ValueError(f"Output would overwrite an input CSV: {destination}")
        if any(_same_file(destination, other) for other in destinations):
            raise ValueError("Report output paths must be distinct")
        if destination.is_dir():
            raise ValueError(f"Output is a directory: {destination}")
        destinations.append(destination)
    staged: list[tuple[Path, Path]] = []
    try:
        for destination, content in outputs:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", prefix=".pairglass-",
                dir=destination.parent, delete=False,
            ) as handle:
                temporary = Path(handle.name)
                staged.append((temporary, destination))
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        for temporary, destination in staged:
            os.replace(temporary, destination)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def _run(args: argparse.Namespace, baseline: Path, candidate: Path, slices: list[str]) -> int:
    report = compare(
        baseline, candidate, slices=slices, min_pairs=args.min_pairs,
        max_drop=args.max_drop, alpha=args.alpha,
    )
    if args.command == "demo":
        report["example"] = "synthetic"
    outputs = [(args.output, render_html(report))]
    if args.json_output:
        outputs.append((args.json_output, json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"))
    if args.markdown_output:
        outputs.append((args.markdown_output, render_markdown(report)))
    if args.losses:
        outputs.append((args.losses, _loss_csv(report)))
    _write_reports(outputs, [baseline, candidate])
    summary = report["summary"]
    if args.command == "demo":
        print("Synthetic example: no model calls or real user data.")
    print(
        f"{summary['n']} paired cases · "
        f"{summary['baseline_rate']:.1%} → {summary['candidate_rate']:.1%} · "
        f"{summary['delta'] * 100:+.1f} pp"
    )
    flagged = [group for group in report["groups"] if group["decision"] == "regression"]
    if flagged:
        print(f"Regression evidence in {len(flagged)} group(s):")
        for group in flagged:
            print(f"  {group['label']}: {group['delta'] * 100:+.1f} pp, n={group['n']}, adjusted p={group['adjusted_p_value']:.6g}")
    else:
        print("No group meets the regression rule. This is not proof of equivalence.")
    insufficient = sum(group["decision"] == "insufficient" for group in report["groups"])
    if insufficient:
        print(f"{insufficient} group(s) have fewer than {args.min_pairs} pairs and cannot fail this gate.")
    print(f"Report: {args.output.resolve()}")
    return 1 if args.fail_on_regression and not report["gate_passed"] else 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "demo":
            with tempfile.TemporaryDirectory(prefix="pairglass-demo-") as directory:
                root = Path(directory)
                for name in ("baseline.csv", "candidate.csv"):
                    (root / name).write_bytes(files("pairglass").joinpath("data", name).read_bytes())
                return _run(args, root / "baseline.csv", root / "candidate.csv", ["language", "task"])
        return _run(args, args.baseline, args.candidate, args.slices)
    except (ValueError, OSError, csv.Error) as error:
        print(f"pairglass: {error}", file=sys.stderr)
        return 2

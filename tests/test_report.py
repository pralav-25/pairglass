import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from pairglass.report import render_html, render_markdown


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts = []
        self.tags = []
        self.current_script = None

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == "script":
            self.current_script = {"attrs": dict(attrs), "text": ""}

    def handle_data(self, data):
        if self.current_script is not None:
            self.current_script["text"] += data

    def handle_endtag(self, tag):
        if tag == "script" and self.current_script is not None:
            self.scripts.append(self.current_script)
            self.current_script = None


def fixture():
    overall = {
        "key": "__overall__", "label": "Overall", "column": None, "value": None,
        "n": 40, "baseline_rate": 0.8, "candidate_rate": 0.85, "delta": 0.05,
        "wins": 4, "losses": 2, "both_pass": 30, "both_fail": 4,
        "p_value": 0.890625, "adjusted_p_value": 1.0, "tested": True,
        "decision": "improved",
    }
    group = dict(overall, key='["language","hi"]', label="language = hi",
                 column="language", value="hi", n=20, baseline_rate=0.9,
                 candidate_rate=0.6, delta=-0.3, wins=0, losses=6,
                 both_pass=12, both_fail=2, p_value=0.015625,
                 adjusted_p_value=0.03125, decision="regression")
    return {
        "schema_version": "pairglass/v1",
        "inputs": {
            "baseline": {"name": "baseline.csv", "sha256": "a" * 64, "rows": 40},
            "candidate": {"name": "candidate.csv", "sha256": "b" * 64, "rows": 40},
        },
        "config": {"slices": ["language"], "min_pairs": 20, "max_drop": 0.05, "alpha": 0.05},
        "groups": [overall, group], "gate_passed": False,
        "regressions": [group["key"]],
        "summary": {key: overall[key] for key in (
            "n", "baseline_rate", "candidate_rate", "delta", "wins", "losses", "both_pass", "both_fail"
        )} | {"flagged_slices": 1},
        "metrics": {"cost_usd": None, "latency_ms": None},
        "cases": [{
            "id": f"case-{index:03}", "baseline_pass": True, "candidate_pass": index > 5,
            "outcome": "loss" if index <= 5 else "stable-pass",
            "slices": {"language": "hi" if index < 20 else "en"},
            "baseline_note": "First note", "candidate_note": "Second note",
            "baseline_cost_usd": None, "candidate_cost_usd": None,
            "baseline_latency_ms": None, "candidate_latency_ms": None,
        } for index in range(40)],
    }


class ReportTests(unittest.TestCase):
    def parsed(self, document):
        parser = ReportParser()
        parser.feed(document)
        return parser

    def test_html_keeps_data_and_descriptive_report_without_javascript(self):
        report = fixture()
        document = render_html(report)
        parser = self.parsed(document)
        embedded = next(script["text"] for script in parser.scripts
                        if script["attrs"].get("id") == "pairglass-data")
        self.assertEqual(json.loads(embedded), report)
        self.assertEqual(len(parser.scripts), 2)
        self.assertIn("80.0%", document)
        self.assertIn("85.0%", document)
        self.assertIn("+5.0 pp", document)
        self.assertIn("Gate failed", document)
        self.assertIn("Overall Holm p: 1.0000", document)
        self.assertIn("language = hi", document)
        self.assertIn("0.0312", document)
        self.assertIn('class="badge improved"', document)
        self.assertIn("one-sided exact paired McNemar", document)
        self.assertNotRegex(document, r"@@[A-Z_]+@@")
        table = re.search(r'<tbody id="case-body">(.*?)</tbody>', document, re.S).group(1)
        self.assertEqual(table.count("<tr>"), 25)
        self.assertIn("case-024", table)
        self.assertNotIn("case-025", table)
        self.assertIn("<noscript>", document)

    def test_script_breaking_data_never_creates_html_or_an_extra_script(self):
        report = fixture()
        attack = '</script><script>alert("x")</script><img src=x onerror=alert(1)>&\u2028\u2029'
        report["cases"][0]["id"] = attack
        report["cases"][0]["baseline_note"] = attack
        report["cases"][0]["candidate_note"] = attack
        report["cases"][0]["slices"] = {attack: attack}
        report["groups"][1]["label"] = attack
        report["groups"][1]["key"] = attack
        report["inputs"]["baseline"]["name"] = attack
        report["inputs"]["candidate"]["sha256"] = attack
        report["config"]["slices"] = [attack]
        document = render_html(report)
        parser = self.parsed(document)
        self.assertEqual(len(parser.scripts), 2)
        self.assertFalse(any(tag == "img" for tag, _ in parser.tags))
        self.assertFalse(any(key.startswith("on") for _, attrs in parser.tags for key in attrs))
        data = next(script["text"] for script in parser.scripts if script["attrs"].get("id") == "pairglass-data")
        self.assertNotIn("<", data)
        self.assertNotIn(">", data)
        self.assertNotIn("&", data)
        self.assertNotIn("\u2028", data)
        self.assertNotIn("\u2029", data)
        self.assertEqual(json.loads(data), report)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", document)

    def test_user_data_containing_template_markers_stays_literal(self):
        report = fixture()
        report["inputs"]["baseline"]["name"] = "@@CASE_ROWS@@ @@BASELINE_RATE@@"
        report["cases"][0]["baseline_note"] = "@@ALPHA@@ @@REPORT_JSON@@"
        report["groups"][1]["label"] = "@@UNKNOWN_MARKER@@"
        document = render_html(report)
        self.assertIn('<span class="run-name">@@CASE_ROWS@@ @@BASELINE_RATE@@</span>', document)
        self.assertIn('<span class="case-note">@@ALPHA@@ @@REPORT_JSON@@</span>', document)
        self.assertIn("<strong>@@UNKNOWN_MARKER@@</strong>", document)
        data = next(script["text"] for script in self.parsed(document).scripts
                    if script["attrs"].get("id") == "pairglass-data")
        self.assertEqual(json.loads(data), report)

    def test_template_markers_are_validated_on_original_template(self):
        from pairglass import report as renderer
        original = renderer._TEMPLATE.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "template.html"
            target.write_text(original + "@@ALPHA@@", encoding="utf-8")
            with patch.object(renderer, "_TEMPLATE", target):
                with self.assertRaisesRegex(ValueError, "appears 2 times"):
                    render_html(fixture())

    def test_markdown_escapes_html_pipes_newlines_and_link_syntax(self):
        report = fixture()
        report["groups"][1]["label"] = 'slice | [click](https://example.org) *bold*\n# heading <script>'
        report["inputs"]["baseline"]["name"] = "file|name\r\nnext.csv"
        document = render_markdown(report)
        self.assertIn('slice \\| \\[click\\](https://example.org) \\*bold\\* \\# heading &lt;script&gt;', document)
        self.assertIn("file\\|name next.csv", document)
        self.assertNotIn("<script>", document)
        self.assertNotIn("\n# heading", document)
        self.assertIn("| Overall | 40 |", document)
        self.assertIn("| +5.0 pp | 1.0000 | improved |", document)
        self.assertIn("overall and declared slice groups", document)
        self.assertIn("drop at least as large as the tolerance", document)
        self.assertIn("descriptive labels, not significance claims", document)

    def test_overall_regression_is_explicit_without_declared_slices(self):
        report = fixture()
        report["groups"] = [dict(report["groups"][0], decision="regression")]
        report["config"]["slices"] = []
        report["regressions"] = ["__overall__"]
        document = render_html(report)
        self.assertIn("1 evaluation group met all regression criteria.", document)
        self.assertIn("No slices declared", document)
        self.assertIn('Overall Holm p: 1.0000 <span class="badge regression">regression</span>', document)
        markdown = render_markdown(report)
        self.assertIn("1 regression groups", markdown)
        self.assertIn("| Overall |", markdown)

    def test_metric_cards_only_show_supplied_means(self):
        report = fixture()
        self.assertNotIn('<section class="metrics-grid"', render_html(report))
        report["metrics"]["cost_usd"] = {"baseline": 0.002, "candidate": 0.003, "delta": 0.001}
        report["metrics"]["latency_ms"] = {"baseline": 100, "candidate": 80, "delta": -20}
        document = render_html(report)
        self.assertIn("$0.0020", document)
        self.assertIn("+0.0010 USD", document)
        self.assertIn("80.0 ms", document)
        self.assertIn("-20.0 ms", document)
        self.assertIn("| Mean cost / case | $0.0020 | $0.0030 | +0.0010 USD |", render_markdown(report))

    def test_nonfinite_report_values_are_rejected(self):
        report = fixture()
        report["cases"][0]["baseline_cost_usd"] = float("nan")
        with self.assertRaises(ValueError):
            render_html(report)

    def test_report_has_no_external_resources_or_unsafe_dom_insertion(self):
        parser = self.parsed(render_html(fixture()))
        for tag, attrs in parser.tags:
            if tag in {"script", "img", "link", "iframe", "audio", "video"}:
                self.assertNotIn("src", attrs)
                self.assertNotIn("href", attrs)
            if tag == "a":
                href = attrs.get("href", "")
                self.assertTrue(href.startswith("#") or href == "https://github.com/pralav-25/pairglass")
                if href.startswith("https://"):
                    self.assertIn("noopener", attrs.get("rel", ""))
                    self.assertIn("noreferrer", attrs.get("rel", ""))
        script = next(script["text"] for script in parser.scripts if not script["attrs"].get("type"))
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("insertAdjacentHTML", script)
        self.assertIn("textContent", script)


if __name__ == "__main__":
    unittest.main()

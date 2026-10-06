#!/usr/bin/env python3
"""Turn the pipeline's raw reports into one readable QA summary.

    python scripts/qa_report.py --reports backend/reports --output qa-summary.md

Reads JUnit XML (pytest and Playwright) and coverage XML, and writes Markdown
suitable for a GitHub step summary or a pull-request comment. Missing inputs
are reported as "not run" rather than crashing the pipeline: the summary must
still render when an earlier job failed.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Suite:
    name: str
    tests: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    time: float = 0.0
    missing: bool = False

    @property
    def passed(self) -> int:
        return max(self.tests - self.failures - self.errors - self.skipped, 0)

    @property
    def ok(self) -> bool:
        return not self.missing and self.failures == 0 and self.errors == 0

    @property
    def verdict(self) -> str:
        if self.missing:
            return "not run"
        return "pass" if self.ok else "FAIL"


def read_junit(path: Path, name: str) -> Suite:
    if not path.exists():
        return Suite(name=name, missing=True)
    root = ET.parse(path).getroot()
    # pytest writes <testsuites><testsuite>…; Playwright writes <testsuites> too.
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]
    suite = Suite(name=name)
    for element in suites:
        suite.tests += int(element.get("tests", 0))
        suite.failures += int(element.get("failures", 0))
        suite.errors += int(element.get("errors", 0))
        suite.skipped += int(element.get("skipped", 0))
        suite.time += float(element.get("time", 0.0))
    return suite


def read_coverage(path: Path) -> tuple[float | None, int, int]:
    """Return (line rate as a percentage, covered lines, total lines)."""
    if not path.exists():
        return None, 0, 0
    root = ET.parse(path).getroot()
    rate = float(root.get("line-rate", 0)) * 100
    covered = int(root.get("lines-covered", 0))
    valid = int(root.get("lines-valid", 0))
    return rate, covered, valid


def render(suites: list[Suite], coverage, floor: float) -> tuple[str, bool]:
    rate, covered, valid = coverage
    total = sum(s.tests for s in suites if not s.missing)
    failed = sum(s.failures + s.errors for s in suites if not s.missing)
    duration = sum(s.time for s in suites if not s.missing)

    coverage_ok = rate is None or rate >= floor
    overall_ok = failed == 0 and coverage_ok and any(not s.missing for s in suites)

    lines = [
        "## QA summary",
        "",
        f"**{'PASS' if overall_ok else 'FAIL'}** — {total} tests, {failed} failing, "
        f"{duration:.1f}s"
        + (f", {rate:.1f}% line coverage" if rate is not None else ""),
        "",
        "| Layer | Tests | Passed | Failed | Skipped | Time | Result |",
        "|-------|------:|-------:|-------:|--------:|-----:|--------|",
    ]
    for suite in suites:
        if suite.missing:
            lines.append(f"| {suite.name} | — | — | — | — | — | not run |")
        else:
            lines.append(
                f"| {suite.name} | {suite.tests} | {suite.passed} | "
                f"{suite.failures + suite.errors} | {suite.skipped} | "
                f"{suite.time:.1f}s | {suite.verdict} |"
            )

    lines += ["", "### Coverage", ""]
    if rate is None:
        lines.append("No coverage report was produced.")
    else:
        lines.append(
            f"{covered} of {valid} statements covered — **{rate:.1f}%** "
            f"(floor {floor:.0f}%): {'pass' if coverage_ok else 'BELOW FLOOR'}"
        )

    return "\n".join(lines) + "\n", overall_ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reports",
        default="backend/reports",
        type=Path,
        help="directory holding the JUnit and coverage XML",
    )
    parser.add_argument("--e2e-report", default="e2e/reports/e2e-junit.xml", type=Path)
    parser.add_argument("--output", default="qa-summary.md", type=Path)
    parser.add_argument("--coverage-floor", default=85.0, type=float)
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="exit non-zero when a suite failed or coverage is below the floor",
    )
    args = parser.parse_args()

    suites = [
        read_junit(args.reports / "unit-junit.xml", "Unit"),
        read_junit(args.reports / "integration-junit.xml", "Integration"),
        read_junit(args.reports / "api-junit.xml", "API"),
        read_junit(args.e2e_report, "End-to-end"),
    ]
    coverage = read_coverage(args.reports / "coverage.xml")

    summary, ok = render(suites, coverage, args.coverage_floor)
    args.output.write_text(summary, encoding="utf-8")
    print(summary)
    return 0 if ok or not args.fail_on_error else 1


if __name__ == "__main__":
    sys.exit(main())

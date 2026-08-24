#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025-2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import pathlib
import shutil
import sys
import xml.etree.ElementTree as ET  # nosec


def count_errors(junit_file):
    error_counter = 0
    tree = ET.parse(junit_file)  # noqa: S314
    root = tree.getroot()
    testsuites = root.findall("testsuite") if root.tag == "testsuites" else [root]

    for testsuite in testsuites:
        errors = int(testsuite.attrib.get("errors", "0"))
        failures = int(testsuite.attrib.get("failures", "0"))
        error_counter += errors + failures
    return error_counter


def clean_junit_xml(junit_file):
    """
    gitlab refuses to parse large junit files.
    This removes stdout and stderr from sucessful tests to decrease the file size.
    """
    tree = ET.parse(junit_file)  # noqa: S314
    root = tree.getroot()
    testsuites = root.findall("testsuite") if root.tag == "testsuites" else [root]

    for testsuite in testsuites:
        errors = int(testsuite.attrib.get("errors", "0"))
        failures = int(testsuite.attrib.get("failures", "0"))
        if errors == 0 and failures == 0:
            for testcase in testsuite.findall("testcase"):
                for tag in ["system-out", "system-err"]:
                    elem = testcase.find(tag)
                    if elem is not None:
                        testcase.remove(elem)

    tree.write(junit_file, encoding="utf-8", xml_declaration=True)


def collect_for_allure(junit_file, results_root, target_dir):
    """
    Copy a JUnit report into one flat directory for Allure.

    Allure reads JUnit XML only from the files lying directly in a directory it
    is given, never from a subdirectory, so the
    'results/<host>/test-reports/<section>/<test>.xml' tree ucs-test leaves
    behind is invisible to it and every integration test was missing from the
    report. The path becomes part of the file name, which keeps the copies
    unique; what the report shows comes from the XML, not from its name.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    flat_name = junit_file.relative_to(results_root).as_posix().replace("/", ".")
    shutil.copyfile(junit_file, target_dir / flat_name)


if __name__ == "__main__":
    test_report_path = pathlib.Path("./results")
    allure_path = pathlib.Path("./integration-results")
    error_counter = 0
    collected = 0
    for junit_file in test_report_path.glob("*/test-reports/**/*.xml"):
        print(f"Parsing {junit_file}")
        error_counter += count_errors(junit_file)
        clean_junit_xml(junit_file)
        collect_for_allure(junit_file, test_report_path, allure_path)
        collected += 1
    print(f"Collected {collected} JUnit reports in {allure_path} for Allure.")
    if error_counter > 0:
        print(f"Found {error_counter} errors.")
        sys.exit(1)

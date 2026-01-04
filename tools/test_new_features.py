#!/usr/bin/env python3
"""Comprehensive test suite for all newly added features (Phases 1-3).

Tests all features added during the refactoring sessions:
- Phase 1.5: Rollback safety and benchmarks
- Phase 2: Code quality and refactoring
- Phase 3: Observability and developer experience
"""

import sys
import subprocess
from pathlib import Path


def print_header(title: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_test(name: str, status: str, details: str = ""):
    """Print test result."""
    status_str = f"[{status}]"
    if details:
        print(f"{status_str:8} {name:40} {details}")
    else:
        print(f"{status_str:8} {name}")


def test_phase_1_5():
    """Test Phase 1.5 features: Rollback safety and benchmarks."""
    print_header("Phase 1.5: Rollback Safety & Baselines")

    # Test 1: Rollback documentation
    rollback_doc = Path("docs/ROLLBACK.md")
    if rollback_doc.exists():
        content = rollback_doc.read_text()
        procedures = content.count("## Procedure")
        print_test(
            "Rollback documentation", "PASS", f"{procedures} procedures documented"
        )
    else:
        print_test("Rollback documentation", "FAIL", "File not found")

    # Test 2: Benchmark suite
    benchmark_script = Path("tests/benchmarks/run_benchmarks.py")
    if benchmark_script.exists() and benchmark_script.is_file():
        print_test("Benchmark suite exists", "PASS", str(benchmark_script))
    else:
        print_test("Benchmark suite exists", "FAIL", "Script not found")

    # Test 3: Benchmark comparison tool
    bench_report = Path("tools/bench_report.py")
    if bench_report.exists():
        print_test("Benchmark comparison tool", "PASS", str(bench_report))
    else:
        print_test("Benchmark comparison tool", "FAIL", "Tool not found")

    # Test 4: Baseline data
    baseline = Path("benchmarks/baseline.json")
    if baseline.exists():
        print_test(
            "Baseline benchmark data", "PASS", f"{baseline.stat().st_size} bytes"
        )
    else:
        print_test("Baseline benchmark data", "FAIL", "No baseline found")

    # Test 5: Documentation organization
    mds_readme = Path("mds/README.md")
    if mds_readme.exists():
        print_test("Documentation organization", "PASS", "mds/README.md exists")
    else:
        print_test("Documentation organization", "FAIL", "README missing")


def test_phase_2():
    """Test Phase 2 features: Code quality and refactoring."""
    print_header("Phase 2: Code Quality & Refactor")

    # Test 1: PDF utils module
    pdf_utils = Path("pdf/utils.py")
    if pdf_utils.exists():
        content = pdf_utils.read_text()
        functions = content.count("def ")
        print_test("PDF utils module", "PASS", f"{functions} functions")
    else:
        print_test("PDF utils module", "FAIL", "Module not found")

    # Test 2: Deck parser module
    deck_parser = Path("deck/parser.py")
    if deck_parser.exists():
        content = deck_parser.read_text()
        functions = content.count("def ")
        print_test("Deck parser module", "PASS", f"{functions} functions")
    else:
        print_test("Deck parser module", "FAIL", "Module not found")

    # Test 3: Error hierarchy
    errors_module = Path("errors.py")
    if errors_module.exists():
        content = errors_module.read_text()
        classes = content.count("class ")
        print_test("Error hierarchy", "PASS", f"{classes} exception classes")
    else:
        print_test("Error hierarchy", "FAIL", "Module not found")

    # Test 4: Pytest configuration
    pytest_ini = Path("pytest.ini")
    if pytest_ini.exists():
        content = pytest_ini.read_text()
        has_durations = "--durations" in content
        print_test(
            "Pytest configuration",
            "PASS" if has_durations else "WARN",
            "Duration reporting configured" if has_durations else "Missing durations",
        )
    else:
        print_test("Pytest configuration", "FAIL", "File not found")

    # Test 5: CI workflow
    ci_workflow = Path(".github/workflows/test.yml")
    if ci_workflow.exists():
        content = ci_workflow.read_text()
        jobs = content.count("run:")
        print_test("CI workflow", "PASS", f"{jobs} job steps")
    else:
        print_test("CI workflow", "FAIL", "Workflow not found")

    # Test 6: Import new modules
    try:
        from pdf.utils import sanitize_profile_name, slugify
        from deck.parser import parse_deck_file
        from errors import ProxyError, NetworkError

        print_test("Module imports", "PASS", "All new modules importable")
    except ImportError as e:
        print_test("Module imports", "FAIL", str(e))


def test_phase_3():
    """Test Phase 3 features: Observability and developer experience."""
    print_header("Phase 3: Observability & Developer Experience")

    # Test 1: Logging enhancements
    logging_config = Path("tools/logging_config.py")
    if logging_config.exists():
        content = logging_config.read_text()
        has_context = "LogContext" in content
        has_context_vars = "ContextVar" in content
        print_test(
            "Structured logging",
            "PASS" if has_context else "WARN",
            "LogContext available" if has_context else "Missing context",
        )
    else:
        print_test("Structured logging", "FAIL", "Module not found")

    # Test 2: Coverage badge generator
    coverage_badge = Path("tools/generate_coverage_badge.py")
    if coverage_badge.exists():
        print_test("Coverage badge generator", "PASS", str(coverage_badge))
    else:
        print_test("Coverage badge generator", "FAIL", "Tool not found")

    # Test 3: CLI documentation generator
    cli_docs_gen = Path("tools/generate_cli_docs.py")
    if cli_docs_gen.exists():
        print_test("CLI docs generator", "PASS", str(cli_docs_gen))
    else:
        print_test("CLI docs generator", "FAIL", "Tool not found")

    # Test 4: Schema documentation generator
    schema_docs_gen = Path("tools/generate_schema_docs.py")
    if schema_docs_gen.exists():
        print_test("Schema docs generator", "PASS", str(schema_docs_gen))
    else:
        print_test("Schema docs generator", "FAIL", "Tool not found")

    # Test 5: Error tracker
    error_tracker = Path("tools/error_tracker.py")
    if error_tracker.exists():
        content = error_tracker.read_text()
        has_tracker = "ErrorTracker" in content
        print_test(
            "Error tracking",
            "PASS" if has_tracker else "WARN",
            "ErrorTracker class available" if has_tracker else "Missing tracker",
        )
    else:
        print_test("Error tracking", "FAIL", "Module not found")

    # Test 6: Generated documentation
    cli_docs = Path("docs/cli.md")
    if cli_docs.exists():
        lines = len(cli_docs.read_text().split("\n"))
        print_test("Generated CLI docs", "PASS", f"{lines} lines")
    else:
        print_test("Generated CLI docs", "WARN", "Not generated yet (run generator)")


def test_integrations():
    """Test that all features integrate correctly."""
    print_header("Integration Tests")

    # Test 1: Run AI recommendations test suite
    print_test("Running AI recommendations tests", "INFO", "This may take a moment...")
    try:
        result = subprocess.run(
            [sys.executable, "tools/test_ai_recommendations.py"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            # Count passed tests
            passed = result.stdout.count("[PASS]")
            print_test("AI recommendations tests", "PASS", f"{passed} tests passed")
        else:
            print_test("AI recommendations tests", "FAIL", "Some tests failed")
    except Exception as e:
        print_test("AI recommendations tests", "FAIL", str(e))

    # Test 2: Run benchmarks
    print_test("Running benchmarks", "INFO", "This may take a moment...")
    try:
        result = subprocess.run(
            [sys.executable, "tests/benchmarks/run_benchmarks.py"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            # Extract summary
            if "Passed:" in result.stdout:
                summary_line = [
                    line for line in result.stdout.split("\n") if "Passed:" in line
                ][0]
                print_test("Benchmark suite", "PASS", summary_line.strip())
            else:
                print_test("Benchmark suite", "PASS", "All benchmarks completed")
        else:
            print_test("Benchmark suite", "FAIL", "Benchmarks failed")
    except Exception as e:
        print_test("Benchmark suite", "FAIL", str(e))

    # Test 3: Test imports work
    try:
        from tools.logging_config import LogContext, log_info
        from tools.error_tracker import ErrorTracker, record_error

        print_test("New module imports", "PASS", "All Phase 3 modules importable")
    except ImportError as e:
        print_test("New module imports", "FAIL", str(e))


def test_tui_enhancements():
    """Test TUI improvements."""
    print_header("TUI Enhancements")

    # Test 1: Check for beautified menu function
    create_pdf = Path("create_pdf.py")
    if create_pdf.exists():
        content = create_pdf.read_text()

        # Check for menu beautification
        has_boxed_menu = "_print_boxed_menu" in content
        has_colors = 'fg="cyan"' in content or 'fg="bright_cyan"' in content
        has_single_key = "_get_key_choice" in content

        print_test(
            "Beautified menus",
            "PASS" if has_boxed_menu else "FAIL",
            "Boxed menu function exists" if has_boxed_menu else "Missing",
        )
        print_test(
            "Colored output",
            "PASS" if has_colors else "FAIL",
            "Color styling present" if has_colors else "Missing",
        )
        print_test(
            "Single-key navigation",
            "PASS" if has_single_key else "FAIL",
            "Key choice function exists" if has_single_key else "Missing",
        )

        # Check for double-digit options (should be replaced with letters)
        has_double_digit = "[10]" in content or "[11]" in content
        print_test(
            "No inaccessible options",
            "PASS" if not has_double_digit else "WARN",
            "All options accessible" if not has_double_digit else "Found [10] or [11]",
        )
    else:
        print_test("TUI enhancements", "FAIL", "create_pdf.py not found")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("  COMPREHENSIVE NEW FEATURES TEST SUITE")
    print("  Testing Phases 1.5, 2, and 3")
    print("=" * 70)

    test_phase_1_5()
    test_phase_2()
    test_phase_3()
    test_integrations()
    test_tui_enhancements()

    print("\n" + "=" * 70)
    print("  TEST SUITE COMPLETE")
    print("=" * 70)
    print("\nAll new features have been tested.")
    print("Review any FAIL or WARN statuses above.\n")


if __name__ == "__main__":
    main()

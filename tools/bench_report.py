#!/usr/bin/env python3
"""Compare benchmark results and detect regressions.

Usage:
    python tools/bench_report.py benchmarks/baseline.json benchmarks/current.json
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, Tuple


def load_results(filepath: str) -> Dict[str, Any]:
    """Load benchmark results from JSON file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Benchmark file not found: {filepath}")

    with open(path) as f:
        return json.load(f)


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 0.001:
        return f"{seconds * 1000000:.2f}μs"
    elif seconds < 1:
        return f"{seconds * 1000:.2f}ms"
    else:
        return f"{seconds:.2f}s"


def format_memory(bytes_val: int) -> str:
    """Format memory in human-readable format."""
    if bytes_val < 1024:
        return f"{bytes_val}B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.2f}KB"
    else:
        return f"{bytes_val / 1024 / 1024:.2f}MB"


def calculate_change(baseline: float, current: float) -> Tuple[float, str]:
    """Calculate percentage change and format with sign."""
    if baseline == 0:
        return 0.0, "N/A"

    change = ((current - baseline) / baseline) * 100
    sign = "+" if change > 0 else ""
    return change, f"{sign}{change:.1f}%"


def compare_benchmarks(
    baseline: Dict[str, Any], current: Dict[str, Any]
) -> Dict[str, Any]:
    """Compare two benchmark results."""
    comparison = {
        "baseline_timestamp": baseline.get("timestamp", "unknown"),
        "current_timestamp": current.get("timestamp", "unknown"),
        "benchmarks": [],
        "regressions": [],
        "improvements": [],
        "summary": {},
    }

    # Match benchmarks by name
    baseline_map = {b["name"]: b for b in baseline.get("benchmarks", [])}
    current_map = {b["name"]: b for b in current.get("benchmarks", [])}

    for name in baseline_map:
        if name not in current_map:
            continue

        base_bench = baseline_map[name]
        curr_bench = current_map[name]

        # Calculate changes
        duration_change, duration_pct = calculate_change(
            base_bench["duration_seconds"], curr_bench["duration_seconds"]
        )

        memory_change, memory_pct = calculate_change(
            base_bench["memory_peak_bytes"], curr_bench["memory_peak_bytes"]
        )

        bench_comparison = {
            "name": name,
            "baseline_duration": base_bench["duration_seconds"],
            "current_duration": curr_bench["duration_seconds"],
            "duration_change_pct": duration_change,
            "duration_change_str": duration_pct,
            "baseline_memory": base_bench["memory_peak_bytes"],
            "current_memory": curr_bench["memory_peak_bytes"],
            "memory_change_pct": memory_change,
            "memory_change_str": memory_pct,
            "is_regression": duration_change > 5.0 or memory_change > 10.0,
            "is_improvement": duration_change < -5.0 or memory_change < -10.0,
        }

        comparison["benchmarks"].append(bench_comparison)

        if bench_comparison["is_regression"]:
            comparison["regressions"].append(name)
        if bench_comparison["is_improvement"]:
            comparison["improvements"].append(name)

    # Overall summary
    total_regressions = len(comparison["regressions"])
    total_improvements = len(comparison["improvements"])

    comparison["summary"] = {
        "total_benchmarks": len(comparison["benchmarks"]),
        "regressions": total_regressions,
        "improvements": total_improvements,
        "stable": len(comparison["benchmarks"])
        - total_regressions
        - total_improvements,
        "has_regressions": total_regressions > 0,
    }

    return comparison


def print_comparison(comparison: Dict[str, Any]):
    """Print comparison results."""
    print("=" * 70)
    print("  BENCHMARK COMPARISON")
    print("=" * 70)
    print(f"Baseline: {comparison['baseline_timestamp']}")
    print(f"Current:  {comparison['current_timestamp']}")
    print()

    # Print each benchmark
    for bench in comparison["benchmarks"]:
        print(f"{bench['name']}:")
        print(
            f"  Duration: {format_duration(bench['baseline_duration'])} → {format_duration(bench['current_duration'])} ({bench['duration_change_str']})"
        )
        print(
            f"  Memory:   {format_memory(bench['baseline_memory'])} → {format_memory(bench['current_memory'])} ({bench['memory_change_str']})"
        )

        if bench["is_regression"]:
            print("  [REGRESSION] Performance degraded")
        elif bench["is_improvement"]:
            print("  [IMPROVEMENT] Performance improved")
        else:
            print("  [STABLE] Within acceptable variance")
        print()

    # Print summary
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    summary = comparison["summary"]
    print(f"Total benchmarks: {summary['total_benchmarks']}")
    print(f"Regressions:      {summary['regressions']}")
    print(f"Improvements:     {summary['improvements']}")
    print(f"Stable:           {summary['stable']}")
    print()

    if summary["has_regressions"]:
        print("[FAIL] Performance regressions detected:")
        for name in comparison["regressions"]:
            print(f"  - {name}")
        return 1
    else:
        print("[PASS] No performance regressions")
        return 0


def main():
    """Compare benchmark results."""
    if len(sys.argv) != 3:
        print("Usage: python tools/bench_report.py <baseline.json> <current.json>")
        return 1

    baseline_file = sys.argv[1]
    current_file = sys.argv[2]

    try:
        baseline = load_results(baseline_file)
        current = load_results(current_file)

        comparison = compare_benchmarks(baseline, current)
        exit_code = print_comparison(comparison)

        return exit_code

    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

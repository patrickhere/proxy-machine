"""Unit tests for Result[T] type.

Tests the structured error handling type and helper functions.
"""

import pytest
from result import (
    Result,
    success,
    failure,
    from_exception,
    try_operation,
    unwrap,
    unwrap_or,
    map_result,
)


class TestResultCreation:
    """Tests for creating Result instances."""

    def test_success_creates_ok_result(self):
        """success() should create Result with ok=True."""
        result = success(42)

        assert result["ok"] is True
        assert result["value"] == 42
        assert result["error"] is None

    def test_failure_creates_error_result(self):
        """failure() should create Result with ok=False."""
        result = failure("Something went wrong")

        assert result["ok"] is False
        assert result["value"] is None
        assert result["error"] == "Something went wrong"

    def test_from_exception_converts_exception(self):
        """from_exception() should convert exception to Result."""
        exc = ValueError("Invalid input")
        result = from_exception(exc)

        assert result["ok"] is False
        assert result["value"] is None
        assert "ValueError" in result["error"]
        assert "Invalid input" in result["error"]


class TestTryOperation:
    """Tests for try_operation() helper."""

    def test_try_operation_success(self):
        """try_operation() should return success for successful operation."""

        def good_operation():
            return 42

        result = try_operation(good_operation)

        assert result["ok"] is True
        assert result["value"] == 42

    def test_try_operation_failure(self):
        """try_operation() should return failure for failing operation."""

        def bad_operation():
            raise ValueError("Oops")

        result = try_operation(bad_operation)

        assert result["ok"] is False
        assert "ValueError" in result["error"]
        assert "Oops" in result["error"]


class TestUnwrap:
    """Tests for unwrap() and unwrap_or() helpers."""

    def test_unwrap_success(self):
        """unwrap() should return value for successful Result."""
        result = success(42)
        value = unwrap(result)

        assert value == 42

    def test_unwrap_failure_raises(self):
        """unwrap() should raise for failed Result."""
        result = failure("Error")

        with pytest.raises(ValueError, match="Error"):
            unwrap(result)

    def test_unwrap_or_success(self):
        """unwrap_or() should return value for successful Result."""
        result = success(42)
        value = unwrap_or(result, 0)

        assert value == 42

    def test_unwrap_or_failure_returns_default(self):
        """unwrap_or() should return default for failed Result."""
        result = failure("Error")
        value = unwrap_or(result, 0)

        assert value == 0


class TestMapResult:
    """Tests for map_result() transformation."""

    def test_map_result_success(self):
        """map_result() should transform successful value."""
        result = success(5)
        doubled = map_result(result, lambda x: x * 2)

        assert doubled["ok"] is True
        assert doubled["value"] == 10

    def test_map_result_failure_preserves_error(self):
        """map_result() should preserve error for failed Result."""
        result = failure("Original error")
        doubled = map_result(result, lambda x: x * 2)

        assert doubled["ok"] is False
        assert doubled["error"] == "Original error"

    def test_map_result_function_raises(self):
        """map_result() should catch exceptions in transform function."""
        result = success(5)

        def bad_transform(x):
            raise ValueError("Transform failed")

        transformed = map_result(result, bad_transform)

        assert transformed["ok"] is False
        assert "ValueError" in transformed["error"]
        assert "Transform failed" in transformed["error"]


class TestResultPatterns:
    """Tests demonstrating Result usage patterns."""

    def test_chaining_with_map(self):
        """Results can be chained with map_result."""
        result = success(5)
        result = map_result(result, lambda x: x * 2)
        result = map_result(result, lambda x: x + 3)

        assert result["ok"] is True
        assert result["value"] == 13

    def test_early_return_on_failure(self):
        """Can check ok and return early."""

        def process_data(data: str) -> Result[int]:
            if not data:
                return failure("Empty data")

            try:
                value = int(data)
                return success(value)
            except ValueError:
                return failure("Invalid number")

        # Success case
        result1 = process_data("42")
        assert result1["ok"] is True
        assert result1["value"] == 42

        # Failure cases
        result2 = process_data("")
        assert result2["ok"] is False
        assert result2["error"] == "Empty data"

        result3 = process_data("abc")
        assert result3["ok"] is False
        assert "Invalid number" in result3["error"]

    def test_aggregating_results(self):
        """Can aggregate multiple Results."""
        results = [
            success(1),
            success(2),
            success(3),
        ]

        all_ok = all(r["ok"] for r in results)
        assert all_ok is True

        values = [r["value"] for r in results if r["ok"]]
        assert values == [1, 2, 3]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Result type for structured error handling without exceptions.

Provides a Result[T] type for operations that can fail, avoiding exception-based
control flow and enabling explicit error handling.
"""

from typing import TypedDict, Optional, TypeVar, Callable, Any

T = TypeVar("T")
U = TypeVar("U")


class Result(TypedDict):
    """Result type for operations that can succeed or fail.

    Note: In Python 3.9, TypedDict cannot be combined with Generic.
    The 'value' field is typed as Any for compatibility.

    Attributes:
        ok: True if operation succeeded, False if it failed
        value: The successful result value (None if failed)
        error: Error message (None if succeeded)
    """

    ok: bool
    value: Optional[Any]
    error: Optional[str]


def success(value: T) -> Result:
    """Create a successful result.

    Args:
        value: The successful result value

    Returns:
        Result with ok=True and the value
    """
    return Result(ok=True, value=value, error=None)


def failure(error: str) -> Result:
    """Create a failed result.

    Args:
        error: Error message describing the failure

    Returns:
        Result with ok=False and the error message
    """
    return Result(ok=False, value=None, error=error)


def from_exception(exc: Exception) -> Result:
    """Create a failed result from an exception.

    Args:
        exc: The exception that occurred

    Returns:
        Result with ok=False and exception message
    """
    return failure(f"{type(exc).__name__}: {str(exc)}")


def try_operation(operation: Callable[[], T]) -> Result:
    """Execute an operation and return a Result.

    Args:
        operation: Function to execute

    Returns:
        Result with either the return value or error
    """
    try:
        value = operation()
        return success(value)
    except Exception as exc:
        return from_exception(exc)


def unwrap(result: Result) -> Any:
    """Extract value from Result or raise error.

    Args:
        result: Result to unwrap

    Returns:
        The value if ok=True

    Raises:
        ValueError: If ok=False
    """
    if result["ok"]:
        return result["value"]
    raise ValueError(result["error"])


def unwrap_or(result: Result, default: Any) -> Any:
    """Extract value from Result or return default.

    Args:
        result: Result to unwrap
        default: Default value if failed

    Returns:
        The value if ok=True, otherwise default
    """
    if result["ok"]:
        return result["value"]
    return default


def map_result(result: Result, func: Callable[[Any], Any]) -> Result:
    """Apply function to successful result value.

    Args:
        result: Input result
        func: Function to apply to value

    Returns:
        New result with transformed value, or original error
    """
    if result["ok"]:
        try:
            new_value = func(result["value"])
            return success(new_value)
        except Exception as exc:
            return from_exception(exc)
    return Result(ok=False, value=None, error=result["error"])


# Note: Type aliases removed for Python 3.9 compatibility
# In Python 3.10+, you can use: StrResult = Result[str], etc.

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional, Tuple


def _json_dump(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _default_progress_enabled(stream) -> bool:
    try:
        return stream.isatty()  # type: ignore[call-arg]
    except Exception:
        return False


@dataclass
class ProgressPrinter:
    """Render single-line progress updates in a TTY-friendly way."""

    stream: Any = field(default=sys.stdout)
    enabled: bool = field(default_factory=lambda: _default_progress_enabled(sys.stdout))
    keep_history: bool = False
    history: list[str] = field(default_factory=list, init=False)
    _last_len: int = field(default=0, init=False)

    def update(self, label: str, *, final: bool = False) -> None:
        if self.keep_history:
            self.history.append(label)

        if not self.enabled:
            if final:
                self.stream.write(label + os.linesep)
                self.stream.flush()
            return

        padding = max(0, self._last_len - len(label))
        self.stream.write(f"\r{label}{' ' * padding}")
        if final:
            self.stream.write(os.linesep)
            self._last_len = 0
        else:
            self._last_len = len(label)
        self.stream.flush()

    def close(self, label: str | None = None) -> None:
        closing_label = label or ""
        self.update(closing_label, final=True)


def resolve_output_path(path_value: str | Path | None) -> Path | None:
    if path_value is None:
        return None
    return Path(path_value).expanduser().resolve()


def ensure_paths_exist(paths: Iterable[Path | None]) -> None:
    for path in paths:
        if path is None:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)


def write_json_outputs(
    *,
    payload: Any,
    out_path: str | Path | None = None,
    summary_payload: Optional[Any] = None,
    summary_path: str | Path | None = None,
    emit_stdout: bool = False,
) -> Tuple[Path | None, Path | None]:
    out_resolved = resolve_output_path(out_path)
    summary_resolved = resolve_output_path(summary_path)

    ensure_paths_exist([out_resolved, summary_resolved])

    if out_resolved is not None:
        out_resolved.write_text(_json_dump(payload), encoding="utf-8")

    if summary_resolved is not None:
        summary_data = payload if summary_payload is None else summary_payload
        summary_resolved.write_text(_json_dump(summary_data), encoding="utf-8")

    if emit_stdout:
        print(_json_dump(payload).rstrip(os.linesep))

    return out_resolved, summary_resolved


def apply_pm_log_overrides(
    *,
    quiet: bool | None = None,
    verbose: bool | None = None,
    json_mode: bool | None = None,
) -> tuple[bool | None, bool | None, bool | None]:
    pm_log = (os.environ.get("PM_LOG") or "").strip().lower()
    if pm_log == "quiet":
        quiet = True if quiet is None else quiet
    if pm_log == "verbose":
        verbose = True if verbose is None else verbose
    if pm_log == "json":
        json_mode = True if json_mode is None else json_mode
    return quiet, verbose, json_mode


def exit_with_message(message: str, *, code: int = 0) -> None:
    stream = sys.stderr if code else sys.stdout
    stream.write(message + os.linesep)
    stream.flush()
    raise SystemExit(code)

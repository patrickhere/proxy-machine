"""CLI command handlers - extracted from monolithic cli() function.

Each handler is a pure function that takes parameters and returns a result.
This makes testing easier and reduces the cli() function to a thin dispatcher.
"""

import click
from typing import Optional
from result import Result, try_operation


def handle_library_health(
    fix_names: bool = False, fix_dupes: bool = False, hash_threshold: int = 6
) -> Result[dict]:
    """Handle library health check command.

    Args:
        fix_names: Whether to fix filename hygiene
        fix_dupes: Whether to remove duplicate files
        hash_threshold: Hamming distance threshold for duplicates

    Returns:
        Result containing health check statistics
    """

    def run_health_check():
        # Import here to avoid circular dependencies
        from create_pdf import _run_library_health_checks

        _run_library_health_checks(
            fix_names=fix_names, fix_dupes=fix_dupes, hash_threshold=hash_threshold
        )
        return {"status": "completed"}

    return try_operation(run_health_check)


def handle_random_commander(
    colors: Optional[str] = None,
    exact_match: bool = False,
    commander_legal_only: bool = False,
    type_filter: Optional[str] = None,
) -> Result[dict]:
    """Handle random commander selection command.

    Args:
        colors: Color identity filter (e.g., "wu", "bgr")
        exact_match: Whether to match colors exactly
        commander_legal_only: Only show commander-legal cards
        type_filter: Type filter (e.g., "legendary creature")

    Returns:
        Result containing commander card data
    """

    def run_random_commander():
        from create_pdf import _random_commander_flow

        _random_commander_flow(
            colors,
            exact_match=exact_match,
            commander_legal_only=commander_legal_only,
            type_filter=type_filter,
        )
        return {"status": "completed"}

    return try_operation(run_random_commander)


def handle_token_language_report(
    warn_languages: Optional[str] = None, output_json: bool = False
) -> Result[dict]:
    """Handle token language report command.

    Args:
        warn_languages: Language codes to warn about (comma-separated)
        output_json: Whether to output in JSON format

    Returns:
        Result containing language statistics
    """

    def run_report():
        from create_pdf import _token_language_report_cli

        _token_language_report_cli(warn_languages, output_json)
        return {"status": "completed"}

    return try_operation(run_report)


def handle_db_health_summary(
    coverage_set: Optional[str] = None,
    missing_only: bool = False,
    output_json: bool = False,
) -> Result[dict]:
    """Handle database health summary command.

    Args:
        coverage_set: Set code to check coverage for
        missing_only: Only show missing cards
        output_json: Whether to output in JSON format

    Returns:
        Result containing database health statistics
    """

    def run_summary():
        from create_pdf import _db_health_summary_cli

        _db_health_summary_cli(
            coverage_set=coverage_set,
            missing_only=missing_only,
            output_json=output_json,
        )
        return {"status": "completed"}

    return try_operation(run_summary)


def handle_token_pack_build(
    manifest_path: str,
    pack_name: Optional[str] = None,
    dry_run: bool = False,
    prefer_set: Optional[str] = None,
    prefer_frame: Optional[str] = None,
    prefer_artist: Optional[str] = None,
) -> Result[dict]:
    """Handle token pack building command.

    Args:
        manifest_path: Path to token pack manifest
        pack_name: Name for the token pack
        dry_run: Whether to do a dry run
        prefer_set: Preferred set code
        prefer_frame: Preferred frame type
        prefer_artist: Preferred artist name

    Returns:
        Result containing pack build statistics
    """

    def build_pack():
        from create_pdf import _build_token_pack

        _build_token_pack(
            manifest_path,
            pack_name,
            dry_run=dry_run,
            prefer_set=prefer_set,
            prefer_frame=prefer_frame,
            prefer_artist=prefer_artist,
        )
        return {"status": "completed"}

    return try_operation(build_pack)


def handle_notifications_test() -> Result[dict]:
    """Handle notifications test command.

    Returns:
        Result containing test status
    """

    def send_test_notification():
        from create_pdf import _notify

        _notify(
            "Proxy Machine Test",
            "This is a sample notification from CLI.",
            event="notifications_test",
        )
        click.echo(
            "Notification dispatched (check Notification Center and/or webhook)."
        )
        return {"status": "completed"}

    return try_operation(send_test_notification)


def handle_plugins_list() -> Result[dict]:
    """Handle plugins list command.

    Returns:
        Result containing plugin list
    """

    def list_plugins():
        from create_pdf import pm_list

        pm_list()
        return {"status": "completed"}

    return try_operation(list_plugins)


def handle_plugins_enable(plugin_name: str) -> Result[dict]:
    """Handle plugin enable command.

    Args:
        plugin_name: Name of plugin to enable

    Returns:
        Result containing enable status
    """

    def enable_plugin():
        from create_pdf import pm_enable

        pm_enable(plugin_name)
        return {"status": "completed"}

    return try_operation(enable_plugin)


def handle_plugins_disable(plugin_name: str) -> Result[dict]:
    """Handle plugin disable command.

    Args:
        plugin_name: Name of plugin to disable

    Returns:
        Result containing disable status
    """

    def disable_plugin():
        from create_pdf import pm_disable

        pm_disable(plugin_name)
        return {"status": "completed"}

    return try_operation(disable_plugin)

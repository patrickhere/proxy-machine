#!/usr/bin/env python3
"""
Proxy Machine Doctor - System Health Diagnostic Tool

Runs comprehensive system checks for:
- Database health and schema validation
- Directory structure integrity
- Symlink validation
- Plugin system compliance
- Python environment verification
- Dependency availability

Usage:
    python tools/doctor.py
    make doctor
"""

import sys
import sqlite3
import subprocess
from pathlib import Path
from typing import List, Optional
import importlib.util

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from constants import RARITIES, SPELL_TYPES, CARD_TYPES

    CONSTANTS_AVAILABLE = True
    CONSTANTS_DATA = {
        "RARITIES": RARITIES,
        "SPELL_TYPES": SPELL_TYPES,
        "CARD_TYPES": CARD_TYPES,
    }
except ImportError:
    CONSTANTS_AVAILABLE = False
    CONSTANTS_DATA = {}


class DiagnosticResult:
    """Result of a diagnostic check."""

    def __init__(
        self, name: str, status: str, message: str, details: Optional[str] = None
    ):
        self.name = name
        self.status = status  # "PASS", "WARN", "FAIL"
        self.message = message
        self.details = details


class ProxyMachineDoctor:
    """Comprehensive system health checker."""

    def __init__(self):
        self.script_dir = Path(__file__).parent.parent
        self.project_root = self.script_dir.parent
        self.results: List[DiagnosticResult] = []

    def run_all_checks(self) -> List[DiagnosticResult]:
        """Run all diagnostic checks."""
        print("🔍 Proxy Machine Doctor - System Health Check")
        print("=" * 50)

        # Core system checks
        self.check_python_version()
        self.check_dependencies()
        self.check_constants_module()

        # Directory structure checks
        self.check_directory_structure()
        self.check_symlinks()

        # Database checks
        self.check_database_health()
        self.check_database_schema()

        # Plugin system checks
        self.check_plugin_system()

        # Configuration checks
        self.check_makefile()
        self.check_uv_availability()

        # Print summary
        self.print_summary()

        return self.results

    def add_result(
        self, name: str, status: str, message: str, details: Optional[str] = None
    ):
        """Add a diagnostic result."""
        self.results.append(DiagnosticResult(name, status, message, details))

        # Print result immediately
        status_icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}[status]
        print(f"{status_icon} {name}: {message}")
        if details:
            print(f"   {details}")

    def check_python_version(self):
        """Check Python version compatibility."""
        version = sys.version_info
        if version >= (3, 9):
            self.add_result(
                "Python Version",
                "PASS",
                f"Python {version.major}.{version.minor}.{version.micro}",
            )
        elif version >= (3, 8):
            self.add_result(
                "Python Version",
                "WARN",
                f"Python {version.major}.{version.minor}.{version.micro} (3.9+ recommended)",
            )
        else:
            self.add_result(
                "Python Version",
                "FAIL",
                f"Python {version.major}.{version.minor}.{version.micro} (3.9+ required)",
            )

    def check_dependencies(self):
        """Check critical dependencies."""
        critical_deps = ["click", "requests"]
        optional_deps = ["psutil", "imagehash"]

        missing_critical = []
        missing_optional = []

        for dep in critical_deps:
            try:
                importlib.import_module(dep)
            except ImportError:
                missing_critical.append(dep)

        for dep in optional_deps:
            try:
                importlib.import_module(dep)
            except ImportError:
                missing_optional.append(dep)

        if not missing_critical and not missing_optional:
            self.add_result("Dependencies", "PASS", "All dependencies available")
        elif not missing_critical:
            self.add_result(
                "Dependencies",
                "WARN",
                f"Optional dependencies missing: {', '.join(missing_optional)}",
            )
        else:
            self.add_result(
                "Dependencies",
                "FAIL",
                f"Critical dependencies missing: {', '.join(missing_critical)}",
            )

    def check_constants_module(self):
        """Check constants module availability."""
        if CONSTANTS_AVAILABLE:
            rarity_count = len(CONSTANTS_DATA.get("RARITIES", []))
            spell_count = len(CONSTANTS_DATA.get("SPELL_TYPES", []))
            self.add_result(
                "Constants Module",
                "PASS",
                f"Available with {rarity_count} rarities, {spell_count} spell types",
            )
        else:
            self.add_result(
                "Constants Module", "FAIL", "constants.py not found or not importable"
            )

    def check_directory_structure(self):
        """Check critical directory structure."""
        critical_dirs = [
            "magic-the-gathering/shared/basic-lands",
            "magic-the-gathering/shared/non-basic-lands",
            "magic-the-gathering/shared/tokens",
            "magic-the-gathering/shared/bulk-data",
            "magic-the-gathering/proxied-decks",
        ]

        missing_dirs = []
        for dir_path in critical_dirs:
            full_path = self.project_root / dir_path
            if not full_path.exists():
                missing_dirs.append(dir_path)

        if not missing_dirs:
            self.add_result(
                "Directory Structure", "PASS", "All critical directories exist"
            )
        else:
            self.add_result(
                "Directory Structure",
                "WARN",
                f"Missing directories: {', '.join(missing_dirs)}",
            )

    def check_symlinks(self):
        """Check symlink integrity in profile directories."""
        proxied_decks_dir = self.project_root / "magic-the-gathering" / "proxied-decks"

        if not proxied_decks_dir.exists():
            self.add_result("Symlinks", "WARN", "No proxied-decks directory found")
            return

        broken_links = []
        total_links = 0

        for profile_dir in proxied_decks_dir.iterdir():
            if not profile_dir.is_dir():
                continue

            shared_cards_dir = profile_dir / "pictures-of-cards" / "shared-cards"
            if shared_cards_dir.exists():
                for item in shared_cards_dir.rglob("*"):
                    if item.is_symlink():
                        total_links += 1
                        if not item.exists():
                            broken_links.append(
                                str(item.relative_to(proxied_decks_dir))
                            )

        if total_links == 0:
            self.add_result("Symlinks", "WARN", "No symlinks found")
        elif not broken_links:
            self.add_result("Symlinks", "PASS", f"All {total_links} symlinks valid")
        else:
            self.add_result(
                "Symlinks", "WARN", f"{len(broken_links)}/{total_links} broken symlinks"
            )

    def check_database_health(self):
        """Check database file and basic connectivity."""
        db_path = (
            self.project_root
            / "magic-the-gathering"
            / "shared"
            / "bulk-data"
            / "bulk.db"
        )

        if not db_path.exists():
            self.add_result("Database File", "FAIL", "Database file not found")
            return

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Check if we can query the database
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
            table_count = cursor.fetchone()[0]

            # Check prints table if it exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='prints'"
            )
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) FROM prints")
                card_count = cursor.fetchone()[0]
                self.add_result(
                    "Database Health",
                    "PASS",
                    f"{table_count} tables, {card_count:,} cards",
                )
            else:
                self.add_result(
                    "Database Health",
                    "WARN",
                    f"{table_count} tables, no prints table found",
                )

            conn.close()

        except Exception as e:
            self.add_result("Database Health", "FAIL", f"Database error: {str(e)}")

    def check_database_schema(self):
        """Check database schema version and structure."""
        db_path = (
            self.project_root
            / "magic-the-gathering"
            / "shared"
            / "bulk-data"
            / "bulk.db"
        )

        if not db_path.exists():
            return

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Check schema version
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'"
            )
            if cursor.fetchone():
                cursor.execute("SELECT value FROM metadata WHERE key='schema_version'")
                result = cursor.fetchone()
                if result:
                    version = result[0]
                    self.add_result(
                        "Database Schema", "PASS", f"Schema version {version}"
                    )
                else:
                    self.add_result(
                        "Database Schema", "WARN", "No schema version found"
                    )
            else:
                self.add_result("Database Schema", "WARN", "No metadata table found")

            # Check critical tables
            expected_tables = ["prints", "card_relationships", "unique_artworks"]
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in cursor.fetchall()}

            missing_tables = [t for t in expected_tables if t not in existing_tables]
            if not missing_tables:
                self.add_result(
                    "Database Tables",
                    "PASS",
                    f"All {len(expected_tables)} critical tables exist",
                )
            else:
                self.add_result(
                    "Database Tables",
                    "WARN",
                    f"Missing tables: {', '.join(missing_tables)}",
                )

            conn.close()

        except Exception as e:
            self.add_result("Database Schema", "FAIL", f"Schema check error: {str(e)}")

    def check_plugin_system(self):
        """Check plugin system health."""
        plugins_dir = self.script_dir / "plugins"

        if not plugins_dir.exists():
            self.add_result("Plugin System", "FAIL", "Plugins directory not found")
            return

        # Check for registry system
        registry_file = plugins_dir / "registry.py"
        if registry_file.exists():
            self.add_result("Plugin Registry", "PASS", "Registry system available")
        else:
            self.add_result("Plugin Registry", "WARN", "Registry system not found")

        # Count plugins
        plugin_count = 0
        plugins_with_init = 0

        for item in plugins_dir.iterdir():
            if item.is_dir() and not item.name.startswith("_"):
                plugin_count += 1
                if (item / "__init__.py").exists():
                    plugins_with_init += 1

        if plugin_count > 0:
            self.add_result(
                "Plugin Discovery",
                "PASS",
                f"{plugin_count} plugins found, {plugins_with_init} with __init__.py",
            )
        else:
            self.add_result("Plugin Discovery", "WARN", "No plugins found")

    def check_makefile(self):
        """Check Makefile availability and key targets."""
        makefile_path = self.script_dir / "Makefile"

        if not makefile_path.exists():
            self.add_result("Makefile", "FAIL", "Makefile not found")
            return

        try:
            with open(makefile_path, "r") as f:
                content = f.read()

            # Check for key targets
            key_targets = ["setup", "deps", "pdf", "fetch-basics", "menu"]
            found_targets = [
                target for target in key_targets if f"{target}:" in content
            ]

            if len(found_targets) == len(key_targets):
                self.add_result(
                    "Makefile", "PASS", f"All {len(key_targets)} key targets available"
                )
            else:
                missing = [t for t in key_targets if t not in found_targets]
                self.add_result(
                    "Makefile", "WARN", f"Missing targets: {', '.join(missing)}"
                )

        except Exception as e:
            self.add_result("Makefile", "FAIL", f"Error reading Makefile: {str(e)}")

    def check_uv_availability(self):
        """Check UV package manager availability."""
        try:
            result = subprocess.run(
                ["uv", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                self.add_result("UV Package Manager", "PASS", f"Available: {version}")
            else:
                self.add_result("UV Package Manager", "WARN", "UV command failed")
        except FileNotFoundError:
            self.add_result("UV Package Manager", "WARN", "UV not found in PATH")
        except subprocess.TimeoutExpired:
            self.add_result("UV Package Manager", "WARN", "UV command timed out")
        except Exception as e:
            self.add_result("UV Package Manager", "WARN", f"UV check error: {str(e)}")

    def print_summary(self):
        """Print diagnostic summary."""
        print("\n" + "=" * 50)
        print("DIAGNOSTIC SUMMARY")
        print("=" * 50)

        pass_count = sum(1 for r in self.results if r.status == "PASS")
        warn_count = sum(1 for r in self.results if r.status == "WARN")
        fail_count = sum(1 for r in self.results if r.status == "FAIL")

        print(f"✓ PASS: {pass_count}")
        print(f"⚠ WARN: {warn_count}")
        print(f"✗ FAIL: {fail_count}")

        if fail_count > 0:
            print(f"\n❌ CRITICAL ISSUES FOUND ({fail_count})")
            for result in self.results:
                if result.status == "FAIL":
                    print(f"   • {result.name}: {result.message}")
            print("\nRecommendation: Address critical issues before proceeding.")

        elif warn_count > 0:
            print(f"\n⚠️  WARNINGS FOUND ({warn_count})")
            print("System is functional but some optimizations are recommended.")

        else:
            print("\n🎉 ALL CHECKS PASSED!")
            print("System is healthy and ready for use.")

        return fail_count == 0


def main():
    """Main entry point."""
    doctor = ProxyMachineDoctor()
    results = doctor.run_all_checks()

    # Exit with error code if there are failures
    fail_count = sum(1 for r in results if r.status == "FAIL")
    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()

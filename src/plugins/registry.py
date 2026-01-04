"""Centralized Plugin Registry System

This module provides a centralized registry for parsers, fetchers, and other plugin functionality.
It enables dynamic plugin discovery and clean API access for both CLI and programmatic use.
"""

import importlib
import importlib.util
from pathlib import Path
from typing import Dict, Any, Callable, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PluginInfo:
    """Information about a registered plugin."""

    name: str
    version: str
    description: str
    folder: str
    enabled: bool = True


class PluginRegistry:
    """Centralized registry for all plugin functionality."""

    def __init__(self):
        self.parsers: Dict[str, Callable] = {}
        self.fetchers: Dict[str, Callable] = {}
        self.plugins: Dict[str, PluginInfo] = {}
        self._loaded_modules: Dict[str, Any] = {}

    def register_parser(
        self, game: str, parser: Callable, plugin_name: Optional[str] = None
    ) -> None:
        """Register a deck parser for a specific game."""
        self.parsers[game.lower()] = parser
        logger.debug(
            f"Registered parser for game: {game} (plugin: {plugin_name or 'unknown'})"
        )

    def register_fetcher(
        self, game: str, fetcher: Callable, plugin_name: Optional[str] = None
    ) -> None:
        """Register a card fetcher for a specific game."""
        self.fetchers[game.lower()] = fetcher
        logger.debug(
            f"Registered fetcher for game: {game} (plugin: {plugin_name or 'unknown'})"
        )

    def register_plugin(self, plugin_info: PluginInfo) -> None:
        """Register plugin metadata."""
        self.plugins[plugin_info.name] = plugin_info
        logger.debug(f"Registered plugin: {plugin_info.name} v{plugin_info.version}")

    def get_parser(self, game: str) -> Optional[Callable]:
        """Get parser for a specific game."""
        return self.parsers.get(game.lower())

    def get_fetcher(self, game: str) -> Optional[Callable]:
        """Get fetcher for a specific game."""
        return self.fetchers.get(game.lower())

    def list_parsers(self) -> List[str]:
        """List all available parsers."""
        return list(self.parsers.keys())

    def list_fetchers(self) -> List[str]:
        """List all available fetchers."""
        return list(self.fetchers.keys())

    def list_plugins(self) -> List[PluginInfo]:
        """List all registered plugins."""
        return list(self.plugins.values())

    def autodiscover_plugins(self, plugins_dir: Optional[Path] = None) -> int:
        """Automatically discover and load plugins from directory structure."""
        if plugins_dir is None:
            plugins_dir = Path(__file__).parent

        loaded_count = 0

        for plugin_dir in plugins_dir.iterdir():
            if not plugin_dir.is_dir() or plugin_dir.name.startswith("_"):
                continue

            # Look for __init__.py with PLUGIN metadata
            init_file = plugin_dir / "__init__.py"
            if init_file.exists():
                loaded_count += self._load_plugin_from_init(plugin_dir, init_file)
            else:
                # Fallback: create minimal __init__.py and load individual modules
                loaded_count += self._load_plugin_modules(plugin_dir)

        logger.info(f"Autodiscovered {loaded_count} plugins")
        return loaded_count

    def _load_plugin_from_init(self, plugin_dir: Path, init_file: Path) -> int:
        """Load plugin from __init__.py with PLUGIN metadata."""
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugins.{plugin_dir.name}", str(init_file)
            )
            if not spec or not spec.loader:
                return 0

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._loaded_modules[plugin_dir.name] = module

            # Check for PLUGIN metadata
            plugin_meta = getattr(module, "PLUGIN", None)
            if isinstance(plugin_meta, dict):
                plugin_info = PluginInfo(
                    name=plugin_meta.get("name", plugin_dir.name),
                    version=plugin_meta.get("version", "1.0.0"),
                    description=plugin_meta.get("description", "No description"),
                    folder=plugin_dir.name,
                )
                self.register_plugin(plugin_info)

                # Auto-register parsers and fetchers if provided
                if hasattr(module, "register_with_registry"):
                    module.register_with_registry(self)

                return 1
        except Exception as e:
            logger.warning(f"Failed to load plugin {plugin_dir.name}: {e}")

        return 0

    def _load_plugin_modules(self, plugin_dir: Path) -> int:
        """Load plugin modules individually (fallback for plugins without __init__.py)."""
        try:
            # Look for common module patterns
            modules_loaded = 0

            # Check for deck_formats.py
            deck_formats_file = plugin_dir / "deck_formats.py"
            if deck_formats_file.exists():
                self._load_module_file(
                    plugin_dir.name, "deck_formats", deck_formats_file
                )
                modules_loaded += 1

            # Check for fetch.py
            fetch_file = plugin_dir / "fetch.py"
            if fetch_file.exists():
                self._load_module_file(plugin_dir.name, "fetch", fetch_file)
                modules_loaded += 1

            if modules_loaded > 0:
                # Create minimal plugin info
                plugin_info = PluginInfo(
                    name=plugin_dir.name,
                    version="1.0.0",
                    description=f"Auto-discovered plugin for {plugin_dir.name}",
                    folder=plugin_dir.name,
                )
                self.register_plugin(plugin_info)
                return 1

        except Exception as e:
            logger.warning(f"Failed to load plugin modules from {plugin_dir.name}: {e}")

        return 0

    def _load_module_file(
        self, plugin_name: str, module_name: str, module_file: Path
    ) -> None:
        """Load a specific module file from a plugin."""
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugins.{plugin_name}.{module_name}", str(module_file)
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Store reference
                module_key = f"{plugin_name}.{module_name}"
                self._loaded_modules[module_key] = module

                logger.debug(f"Loaded module: {module_key}")
        except Exception as e:
            logger.warning(f"Failed to load module {plugin_name}.{module_name}: {e}")


# Global registry instance
registry = PluginRegistry()


# Convenience functions for external use
def register_parser(
    game: str, parser: Callable, plugin_name: Optional[str] = None
) -> None:
    """Register a deck parser globally."""
    registry.register_parser(game, parser, plugin_name)


def register_fetcher(
    game: str, fetcher: Callable, plugin_name: Optional[str] = None
) -> None:
    """Register a card fetcher globally."""
    registry.register_fetcher(game, fetcher, plugin_name)


def get_parser(game: str) -> Optional[Callable]:
    """Get parser for a specific game."""
    return registry.get_parser(game)


def get_fetcher(game: str) -> Optional[Callable]:
    """Get fetcher for a specific game."""
    return registry.get_fetcher(game)


def list_available_games() -> Dict[str, Dict[str, bool]]:
    """List all games with their available functionality."""
    games = {}

    all_games = set(registry.list_parsers() + registry.list_fetchers())

    for game in sorted(all_games):
        games[game] = {
            "parser": game in registry.parsers,
            "fetcher": game in registry.fetchers,
        }

    return games


def autodiscover_and_load() -> int:
    """Convenience function to autodiscover and load all plugins."""
    return registry.autodiscover_plugins()


# Auto-load plugins when module is imported
if __name__ != "__main__":
    try:
        autodiscover_and_load()
    except Exception as e:
        logger.warning(f"Failed to auto-load plugins: {e}")

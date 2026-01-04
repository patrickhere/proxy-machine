#!/usr/bin/env python3
"""
Discord monitoring integration for The Proxy Machine.

Provides comprehensive collection monitoring, deck creation alerts,
and system performance tracking via Discord webhooks.
"""

import logging
import os
import sys
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

try:  # Optional dependency for webhook posting
    import requests  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    requests = None  # type: ignore[assignment]

if TYPE_CHECKING:
    import requests as _requests
else:  # pragma: no cover - runtime alias only
    _requests = None  # type: ignore[assignment]

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MemoryMonitor: Any | None = None


def _db_index_available() -> bool:
    return False


def _generate_art_type_report(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    return {
        "total_entries": 0,
        "unique_art_types": 0,
        "potential_collisions": 0,
        "performance": {},
    }


def _get_art_type_stats(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    return {}


def query_basic_lands(*args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
    return []


def query_non_basic_lands(*args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
    return []


def query_tokens(*args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
    return []


try:
    from create_pdf import (
        MemoryMonitor as _MemoryMonitor,
        _db_index_available as _db_index_available_real,
        _generate_art_type_report as _generate_art_type_report_real,
        _get_art_type_stats as _get_art_type_stats_real,
    )
    from db.bulk_index import (
        query_basic_lands as _query_basic_lands_real,
        query_non_basic_lands as _query_non_basic_lands_real,
        query_tokens as _query_tokens_real,
    )

    MemoryMonitor = _MemoryMonitor
    _db_index_available = _db_index_available_real
    _generate_art_type_report = _generate_art_type_report_real
    _get_art_type_stats = _get_art_type_stats_real
    query_basic_lands = _query_basic_lands_real
    query_non_basic_lands = _query_non_basic_lands_real
    query_tokens = _query_tokens_real
except ImportError as e:
    print(f"Warning: Could not import project modules: {e}")

logger = logging.getLogger(__name__)


class DiscordMonitor:
    """Discord integration for comprehensive Magic card collection monitoring."""

    def __init__(self, webhook_url: Optional[str] = None):
        resolved_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL") or None
        self.webhook_url: Optional[str] = resolved_url
        self.enabled = bool(resolved_url)

        if not self.enabled:
            logger.info("Discord monitoring disabled - no webhook URL configured")
        else:
            logger.info("Discord monitoring enabled")

    def send_message(self, content: str, embeds: Optional[List[Dict]] = None) -> bool:
        """Send message to Discord webhook."""
        if not self.enabled or requests is None:
            return False

        webhook_url = self.webhook_url
        if not webhook_url:
            return False

        payload: Dict[str, Any] = {"content": content}
        if embeds:
            payload["embeds"] = embeds

        try:
            response = requests.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
            return False

    def send_collection_stats(self) -> bool:
        """Send comprehensive collection statistics."""
        if not self.enabled or not _db_index_available():
            return False

        try:
            print("📊 Generating collection statistics...")

            # Generate reports with progress indication
            print("🏔️  Analyzing basic lands...")
            basic_data = query_basic_lands()
            print(f"    ✓ Loaded {len(basic_data):,} basic land entries")
            basic_report = _generate_art_type_report(basic_data, "basic_lands")

            print("🏞️  Analyzing non-basic lands...")
            nonbasic_data = query_non_basic_lands()
            print(f"    ✓ Loaded {len(nonbasic_data):,} non-basic land entries")
            nonbasic_report = _generate_art_type_report(
                nonbasic_data, "non_basic_lands"
            )

            print("🪙  Analyzing tokens...")
            token_data = query_tokens()
            print(f"    ✓ Loaded {len(token_data):,} token entries")
            token_report = _generate_art_type_report(token_data, "tokens")

            # Create Discord embed
            embed = {
                "title": "🎴 Magic Collection Statistics",
                "color": 0x5865F2,
                "timestamp": datetime.utcnow().isoformat(),
                "fields": [
                    {
                        "name": "🏔️ Basic Lands",
                        "value": f"Total: {basic_report['total_entries']:,}\nArt Types: {basic_report['unique_art_types']}\nCollisions: {basic_report['potential_collisions']}",
                        "inline": True,
                    },
                    {
                        "name": "🏞️ Non-Basic Lands",
                        "value": f"Total: {nonbasic_report['total_entries']:,}\nArt Types: {nonbasic_report['unique_art_types']}\nCollisions: {nonbasic_report['potential_collisions']}",
                        "inline": True,
                    },
                    {
                        "name": "🪙 Tokens",
                        "value": f"Total: {token_report['total_entries']:,}\nArt Types: {token_report['unique_art_types']}\nCollisions: {token_report['potential_collisions']}",
                        "inline": True,
                    },
                ],
            }

            # Add memory stats if available
            perf = basic_report.get("performance", {})
            if perf.get("memory_monitoring"):
                embed["fields"].append(
                    {
                        "name": "💾 System Memory",
                        "value": f"Available: {perf['system_memory_gb']}GB\nUsed: {perf['system_memory_used_percent']}%",
                        "inline": True,
                    }
                )

            # Add most common art types
            most_common = basic_report.get("most_common_art_type")
            if most_common:
                embed["fields"].append(
                    {
                        "name": "🎨 Most Common Art Type",
                        "value": f"{most_common[0]}: {most_common[1]:,} cards",
                        "inline": True,
                    }
                )

            print("📤 Sending statistics to Discord...")
            result = self.send_message("", [embed])
            if result:
                print("✅ Collection statistics sent successfully!")
            else:
                print("❌ Failed to send collection statistics to Discord")
            return result

        except Exception as e:
            logger.error(f"Failed to generate collection stats: {e}")
            print(f"❌ Error generating collection stats: {e}")
            return False

    def send_fetch_complete(self, fetch_type: str, stats: Dict[str, Any]) -> bool:
        """Send notification when fetch operation completes."""
        if not self.enabled:
            return False

        embed = {
            "title": f"📥 {fetch_type.title()} Fetch Complete",
            "color": 0x00FF00,
            "timestamp": datetime.utcnow().isoformat(),
            "fields": [
                {
                    "name": "Results",
                    "value": f"Saved: {stats.get('saved', 0)}\nSkipped: {stats.get('skipped', 0)}\nTotal: {stats.get('total', 0)}",
                    "inline": True,
                }
            ],
        }

        # Add memory usage if available
        if "memory_summary" in stats:
            mem = stats["memory_summary"]
            embed["fields"].append(
                {
                    "name": "Memory Usage",
                    "value": f"Peak: {mem.get('peak_memory_mb', 'N/A')}MB\nIncrease: +{mem.get('total_memory_increase_mb', 'N/A')}MB",
                    "inline": True,
                }
            )

        return self.send_message("", [embed])

    def send_deck_created(
        self, deck_name: str, card_count: int, token_count: int = 0
    ) -> bool:
        """Send notification when a new deck is created."""
        if not self.enabled:
            return False

        embed = {
            "title": "🃏 New Deck Created",
            "color": 0xFF6B00,
            "timestamp": datetime.utcnow().isoformat(),
            "fields": [
                {"name": "Deck Name", "value": deck_name, "inline": False},
                {"name": "Cards", "value": str(card_count), "inline": True},
            ],
        }

        if token_count > 0:
            embed["fields"].append(
                {"name": "Tokens", "value": str(token_count), "inline": True}
            )

        return self.send_message("", [embed])

    def send_system_alert(
        self, title: str, message: str, alert_type: str = "info"
    ) -> bool:
        """Send system alert with appropriate color coding."""
        if not self.enabled:
            return False

        colors = {
            "info": 0x5865F2,
            "warning": 0xFEE75C,
            "error": 0xED4245,
            "success": 0x57F287,
        }

        embed = {
            "title": f"🔔 {title}",
            "description": message,
            "color": colors.get(alert_type, colors["info"]),
            "timestamp": datetime.utcnow().isoformat(),
        }

        return self.send_message("", [embed])

    def send_daily_summary(self) -> bool:
        """Send daily collection summary."""
        if not self.enabled:
            return False

        try:
            print("📅 Generating daily collection summary...")
            # Generate comprehensive stats
            stats = self.get_collection_summary()

            embed = {
                "title": "📊 Daily Collection Summary",
                "color": 0x9A59C4,
                "timestamp": datetime.utcnow().isoformat(),
                "description": f"Collection status as of {datetime.now().strftime('%B %d, %Y')}",
                "fields": [],
            }

            # Add collection stats
            for category, data in stats.items():
                if isinstance(data, dict) and "total" in data:
                    embed["fields"].append(
                        {
                            "name": category.replace("_", " ").title(),
                            "value": f"Total: {data['total']:,}\nUnique Types: {data.get('unique_types', 'N/A')}",
                            "inline": True,
                        }
                    )

            print("📤 Sending daily summary to Discord...")
            result = self.send_message("", [embed])
            if result:
                print("✅ Daily summary sent successfully!")
            else:
                print("❌ Failed to send daily summary to Discord")
            return result

        except Exception as e:
            logger.error(f"Failed to send daily summary: {e}")
            print(f"❌ Error generating daily summary: {e}")
            return False

    def get_collection_summary(self) -> Dict[str, Any]:
        """Get comprehensive collection summary."""
        if not _db_index_available():
            print("❌ Database not available for collection summary")
            return {"status": "Database not available"}

        try:
            print("    🔍 Querying database for collection summary...")

            print("    🏔️  Loading basic lands data...")
            basic_data = query_basic_lands()
            print(f"        ✓ Found {len(basic_data):,} basic lands")

            print("    🏞️  Loading non-basic lands data...")
            nonbasic_data = query_non_basic_lands()
            print(f"        ✓ Found {len(nonbasic_data):,} non-basic lands")

            print("    🪙  Loading tokens data...")
            token_data = query_tokens()
            print(f"        ✓ Found {len(token_data):,} tokens")

            system_summary: Dict[str, Any] = {"database_available": True}
            try:
                if MemoryMonitor is not None:
                    system_summary["memory_monitoring"] = (
                        MemoryMonitor().check_memory().get("available", False)
                    )
                else:
                    system_summary["memory_monitoring"] = False
            except Exception:
                system_summary["memory_monitoring"] = False

            return {
                "basic_lands": {
                    "total": len(basic_data),
                    "unique_types": len(_get_art_type_stats(basic_data)),
                },
                "non_basic_lands": {
                    "total": len(nonbasic_data),
                    "unique_types": len(_get_art_type_stats(nonbasic_data)),
                },
                "tokens": {
                    "total": len(token_data),
                    "unique_types": len(_get_art_type_stats(token_data)),
                },
                "system": system_summary,
            }
        except Exception as e:
            logger.error(f"Failed to get collection summary: {e}")
            return {"error": str(e)}


def main():
    """CLI interface for Discord monitoring."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Discord monitoring for Magic collection"
    )
    parser.add_argument("--webhook-url", help="Discord webhook URL")
    parser.add_argument("--test", action="store_true", help="Send test message")
    parser.add_argument("--stats", action="store_true", help="Send collection stats")
    parser.add_argument("--daily", action="store_true", help="Send daily summary")
    parser.add_argument("--alert", help="Send system alert")
    parser.add_argument(
        "--alert-type", default="info", choices=["info", "warning", "error", "success"]
    )

    args = parser.parse_args()

    monitor = DiscordMonitor(args.webhook_url)

    if not monitor.enabled:
        print(
            "❌ Discord monitoring not configured. Set DISCORD_WEBHOOK_URL environment variable."
        )
        return 1

    if args.test:
        success = monitor.send_message(
            "🧪 Test message from The Proxy Machine Discord monitor!"
        )
        print("✅ Test message sent!" if success else "❌ Failed to send test message")

    if args.stats:
        success = monitor.send_collection_stats()
        print("✅ Collection stats sent!" if success else "❌ Failed to send stats")

    if args.daily:
        success = monitor.send_daily_summary()
        print("✅ Daily summary sent!" if success else "❌ Failed to send summary")

    if args.alert:
        success = monitor.send_system_alert("System Alert", args.alert, args.alert_type)
        print("✅ Alert sent!" if success else "❌ Failed to send alert")

    return 0


if __name__ == "__main__":
    sys.exit(main())

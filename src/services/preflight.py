"""Preflight Validation Service

Pre-operation checks for critical operations like PDF generation and card fetching.
Validates system state, estimates resource usage, and prevents costly mistakes.
"""

from typing import List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
import shutil
import logging

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """Validation severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationResult:
    """Result of a preflight validation check."""

    check_name: str
    level: ValidationLevel
    message: str
    details: Optional[str] = None
    suggested_action: Optional[str] = None


@dataclass
class ResourceEstimate:
    """Resource usage estimation."""

    disk_space_mb: float
    download_size_mb: float
    estimated_duration_minutes: float
    memory_usage_mb: float
    network_requests: int


class PreflightService:
    """Service for pre-operation validation and estimation."""

    def __init__(self):
        self.min_free_space_mb = 1000  # 1GB minimum free space
        self.max_reasonable_download_mb = 5000  # 5GB max reasonable download

    def validate_pdf_operation(
        self, profile_name: str, project_root: Path, estimated_cards: int = 0
    ) -> Tuple[List[ValidationResult], bool]:
        """Validate PDF generation operation."""
        results = []

        # Check profile directory structure
        profile_dir = (
            project_root / "magic-the-gathering" / "proxied-decks" / profile_name
        )
        results.extend(self._check_profile_structure(profile_dir))

        # Check for cards to print
        to_print_dir = profile_dir / "pictures-of-cards" / "to-print"
        results.extend(self._check_print_queue(to_print_dir, estimated_cards))

        # Check disk space
        results.extend(self._check_disk_space(profile_dir.parent))

        # Check output directory
        output_dir = profile_dir / "pdfs-of-decks"
        results.extend(self._check_output_directory(output_dir))

        # Determine if operation should proceed
        has_critical_errors = any(r.level == ValidationLevel.CRITICAL for r in results)

        return results, not has_critical_errors

    def validate_fetch_operation(
        self,
        estimated_downloads: int,
        target_directory: Path,
        estimated_size_mb: float = 0,
    ) -> Tuple[List[ValidationResult], bool]:
        """Validate card fetching operation."""
        results = []

        # Check target directory
        results.extend(self._check_target_directory(target_directory))

        # Check disk space
        results.extend(self._check_disk_space(target_directory, estimated_size_mb))

        # Check download size reasonableness
        results.extend(
            self._check_download_size(estimated_downloads, estimated_size_mb)
        )

        # Check network connectivity (basic)
        results.extend(self._check_network_connectivity())

        # Determine if operation should proceed
        has_critical_errors = any(r.level == ValidationLevel.CRITICAL for r in results)

        return results, not has_critical_errors

    def estimate_pdf_resources(
        self, card_count: int, profile_dir: Path, high_quality: bool = True
    ) -> ResourceEstimate:
        """Estimate resources needed for PDF generation."""

        # Estimate based on card count and quality settings
        if high_quality:
            # High quality: ~2MB per card in memory, 500KB per card in PDF
            memory_per_card_mb = 2.0
            pdf_size_per_card_mb = 0.5
        else:
            # Standard quality: ~1MB per card in memory, 300KB per card in PDF
            memory_per_card_mb = 1.0
            pdf_size_per_card_mb = 0.3

        estimated_memory = card_count * memory_per_card_mb
        estimated_pdf_size = card_count * pdf_size_per_card_mb

        # Duration estimate: ~0.5 seconds per card for processing
        estimated_duration = (card_count * 0.5) / 60  # Convert to minutes

        return ResourceEstimate(
            disk_space_mb=estimated_pdf_size,
            download_size_mb=0,  # No downloads for PDF generation
            estimated_duration_minutes=estimated_duration,
            memory_usage_mb=estimated_memory,
            network_requests=0,
        )

    def estimate_fetch_resources(
        self, job_count: int, concurrent_workers: int = 8
    ) -> ResourceEstimate:
        """Estimate resources needed for card fetching."""

        # Average card image size: ~850KB
        avg_image_size_mb = 0.85

        estimated_download_size = job_count * avg_image_size_mb
        estimated_disk_space = estimated_download_size * 1.1  # 10% overhead

        # Duration estimate: ~2MB/s total throughput
        estimated_duration = estimated_download_size / 2.0  # Minutes

        # Memory estimate: ~10MB per worker + image buffers
        estimated_memory = (concurrent_workers * 10) + (job_count * 0.1)

        return ResourceEstimate(
            disk_space_mb=estimated_disk_space,
            download_size_mb=estimated_download_size,
            estimated_duration_minutes=estimated_duration,
            memory_usage_mb=estimated_memory,
            network_requests=job_count,
        )

    def _check_profile_structure(self, profile_dir: Path) -> List[ValidationResult]:
        """Check profile directory structure."""
        results = []

        if not profile_dir.exists():
            results.append(
                ValidationResult(
                    check_name="Profile Directory",
                    level=ValidationLevel.CRITICAL,
                    message=f"Profile directory does not exist: {profile_dir}",
                    suggested_action="Create profile directory or check profile name",
                )
            )
            return results

        # Check required subdirectories
        required_dirs = [
            "pictures-of-cards",
            "pictures-of-cards/to-print",
            "pictures-of-cards/to-print/front",
            "pdfs-of-decks",
        ]

        missing_dirs = []
        for dir_name in required_dirs:
            dir_path = profile_dir / dir_name
            if not dir_path.exists():
                missing_dirs.append(dir_name)

        if missing_dirs:
            results.append(
                ValidationResult(
                    check_name="Profile Structure",
                    level=ValidationLevel.WARNING,
                    message=f"Missing directories: {', '.join(missing_dirs)}",
                    details=f"Profile: {profile_dir.name}",
                    suggested_action="Run profile setup or create directories manually",
                )
            )
        else:
            results.append(
                ValidationResult(
                    check_name="Profile Structure",
                    level=ValidationLevel.INFO,
                    message="Profile directory structure is complete",
                )
            )

        return results

    def _check_print_queue(
        self, to_print_dir: Path, estimated_cards: int
    ) -> List[ValidationResult]:
        """Check print queue for cards."""
        results = []

        if not to_print_dir.exists():
            results.append(
                ValidationResult(
                    check_name="Print Queue",
                    level=ValidationLevel.CRITICAL,
                    message="Print queue directory does not exist",
                    suggested_action="Create to-print directory structure",
                )
            )
            return results

        # Count cards in print queue
        front_dir = to_print_dir / "front"
        back_dir = to_print_dir / "back"
        double_sided_dir = to_print_dir / "double_sided"

        front_count = len(list(front_dir.glob("*.png"))) if front_dir.exists() else 0
        back_count = len(list(back_dir.glob("*.png"))) if back_dir.exists() else 0
        double_count = (
            len(list(double_sided_dir.glob("*.png")))
            if double_sided_dir.exists()
            else 0
        )

        total_cards = front_count + back_count + double_count

        if total_cards == 0:
            results.append(
                ValidationResult(
                    check_name="Print Queue",
                    level=ValidationLevel.WARNING,
                    message="No cards found in print queue",
                    suggested_action="Add cards to to-print directories before generating PDF",
                )
            )
        else:
            results.append(
                ValidationResult(
                    check_name="Print Queue",
                    level=ValidationLevel.INFO,
                    message=f"Found {total_cards} cards ready for printing",
                    details=f"Front: {front_count}, Back: {back_count}, Double-sided: {double_count}",
                )
            )

        # Check for reasonable card count
        if total_cards > 1000:
            results.append(
                ValidationResult(
                    check_name="Print Queue Size",
                    level=ValidationLevel.WARNING,
                    message=f"Large number of cards ({total_cards}) may take significant time to process",
                    suggested_action="Consider processing in smaller batches",
                )
            )

        return results

    def _check_disk_space(
        self, directory: Path, required_mb: float = 0
    ) -> List[ValidationResult]:
        """Check available disk space."""
        results = []

        try:
            # Get disk usage
            total, used, free = shutil.disk_usage(directory)
            free_mb = free / (1024 * 1024)

            required_space = max(required_mb, self.min_free_space_mb)

            if free_mb < required_space:
                results.append(
                    ValidationResult(
                        check_name="Disk Space",
                        level=ValidationLevel.CRITICAL,
                        message=f"Insufficient disk space: {free_mb:.1f}MB available, {required_space:.1f}MB required",
                        suggested_action="Free up disk space or choose different location",
                    )
                )
            elif free_mb < required_space * 2:
                results.append(
                    ValidationResult(
                        check_name="Disk Space",
                        level=ValidationLevel.WARNING,
                        message=f"Low disk space: {free_mb:.1f}MB available, {required_space:.1f}MB required",
                        suggested_action="Consider freeing up additional space",
                    )
                )
            else:
                results.append(
                    ValidationResult(
                        check_name="Disk Space",
                        level=ValidationLevel.INFO,
                        message=f"Sufficient disk space: {free_mb:.1f}MB available",
                    )
                )

        except OSError as e:
            results.append(
                ValidationResult(
                    check_name="Disk Space",
                    level=ValidationLevel.WARNING,
                    message=f"Could not check disk space: {e}",
                    suggested_action="Verify directory permissions and path",
                )
            )

        return results

    def _check_output_directory(self, output_dir: Path) -> List[ValidationResult]:
        """Check PDF output directory."""
        results = []

        try:
            output_dir.mkdir(parents=True, exist_ok=True)

            # Check write permissions
            test_file = output_dir / ".write_test"
            test_file.touch()
            test_file.unlink()

            results.append(
                ValidationResult(
                    check_name="Output Directory",
                    level=ValidationLevel.INFO,
                    message=f"Output directory is writable: {output_dir}",
                )
            )

        except OSError as e:
            results.append(
                ValidationResult(
                    check_name="Output Directory",
                    level=ValidationLevel.CRITICAL,
                    message=f"Cannot write to output directory: {e}",
                    suggested_action="Check directory permissions or choose different location",
                )
            )

        return results

    def _check_target_directory(self, target_dir: Path) -> List[ValidationResult]:
        """Check target directory for fetching."""
        results = []

        try:
            target_dir.mkdir(parents=True, exist_ok=True)

            # Check write permissions
            test_file = target_dir / ".write_test"
            test_file.touch()
            test_file.unlink()

            results.append(
                ValidationResult(
                    check_name="Target Directory",
                    level=ValidationLevel.INFO,
                    message=f"Target directory is writable: {target_dir}",
                )
            )

        except OSError as e:
            results.append(
                ValidationResult(
                    check_name="Target Directory",
                    level=ValidationLevel.CRITICAL,
                    message=f"Cannot write to target directory: {e}",
                    suggested_action="Check directory permissions or choose different location",
                )
            )

        return results

    def _check_download_size(
        self, download_count: int, estimated_mb: float
    ) -> List[ValidationResult]:
        """Check if download size is reasonable."""
        results = []

        if estimated_mb > self.max_reasonable_download_mb:
            results.append(
                ValidationResult(
                    check_name="Download Size",
                    level=ValidationLevel.WARNING,
                    message=f"Large download size: {estimated_mb:.1f}MB ({download_count} files)",
                    details="This may take significant time and bandwidth",
                    suggested_action="Consider downloading in smaller batches or using --limit",
                )
            )
        elif download_count > 1000:
            results.append(
                ValidationResult(
                    check_name="Download Count",
                    level=ValidationLevel.WARNING,
                    message=f"Large number of downloads: {download_count} files",
                    suggested_action="Consider using --limit to download in batches",
                )
            )
        else:
            results.append(
                ValidationResult(
                    check_name="Download Size",
                    level=ValidationLevel.INFO,
                    message=f"Reasonable download size: {estimated_mb:.1f}MB ({download_count} files)",
                )
            )

        return results

    def _check_network_connectivity(self) -> List[ValidationResult]:
        """Basic network connectivity check."""
        results = []

        try:
            import urllib.request

            # Quick connectivity test to Scryfall
            request = urllib.request.Request(
                "https://api.scryfall.com/", headers={"User-Agent": "ProxyMachine/1.0"}
            )

            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status == 200:
                    results.append(
                        ValidationResult(
                            check_name="Network Connectivity",
                            level=ValidationLevel.INFO,
                            message="Network connectivity to Scryfall confirmed",
                        )
                    )
                else:
                    results.append(
                        ValidationResult(
                            check_name="Network Connectivity",
                            level=ValidationLevel.WARNING,
                            message=f"Unexpected response from Scryfall: {response.status}",
                            suggested_action="Check network connection",
                        )
                    )

        except Exception as e:
            results.append(
                ValidationResult(
                    check_name="Network Connectivity",
                    level=ValidationLevel.WARNING,
                    message=f"Network connectivity check failed: {e}",
                    details="Downloads may fail without network access",
                    suggested_action="Check internet connection",
                )
            )

        return results


# Global service instance
preflight_service = PreflightService()

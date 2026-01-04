"""Card Fetching Service

Business logic for card image fetching, validation, and organization.
Separated from CLI interface for better testability and reusability.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
import logging
import urllib.request
import urllib.error
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class CardType(Enum):
    """Supported card types for fetching."""

    BASIC_LAND = "basic_land"
    NONBASIC_LAND = "nonbasic_land"
    TOKEN = "token"
    CREATURE = "creature"
    PLANESWALKER = "planeswalker"
    INSTANT = "instant"
    SORCERY = "sorcery"
    ARTIFACT = "artifact"
    ENCHANTMENT = "enchantment"
    ANY = "any"


@dataclass
class FetchJob:
    """Represents a card fetch operation."""

    card_id: str
    card_name: str
    image_url: str
    destination_path: Path
    set_code: Optional[str] = None
    collector_number: Optional[str] = None


@dataclass
class FetchResult:
    """Result of a fetch operation."""

    job: FetchJob
    success: bool
    error_message: Optional[str] = None
    file_size: Optional[int] = None
    duration: Optional[float] = None


@dataclass
class FetchSummary:
    """Summary of a batch fetch operation."""

    total_requested: int
    successful: int
    failed: int
    skipped: int
    total_size_bytes: int
    total_duration: float
    failed_jobs: List[FetchJob]

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_requested == 0:
            return 0.0
        return (self.successful / self.total_requested) * 100


class FetchService:
    """Service for card image fetching operations."""

    def __init__(self, max_workers: int = 8, timeout: int = 30, max_retries: int = 3):
        self.max_workers = max_workers
        self.timeout = timeout
        self.max_retries = max_retries

    def fetch_cards(
        self, jobs: List[FetchJob], dry_run: bool = False, skip_existing: bool = True
    ) -> FetchSummary:
        """Fetch multiple card images concurrently."""
        logger.info(f"Starting fetch operation: {len(jobs)} jobs, dry_run={dry_run}")

        if dry_run:
            return self._simulate_fetch(jobs)

        # Filter existing files if requested
        skipped_count = 0
        if skip_existing:
            original_count = len(jobs)
            jobs = [job for job in jobs if not job.destination_path.exists()]
            skipped_count = original_count - len(jobs)
            logger.info(
                f"Filtered to {len(jobs)} jobs (skipping {skipped_count} existing files)"
            )

        start_time = time.time()
        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all jobs
            future_to_job = {
                executor.submit(self._fetch_single_card, job): job for job in jobs
            }

            # Collect results
            for future in as_completed(future_to_job):
                job = future_to_job[future]
                try:
                    result = future.result()
                    results.append(result)

                    if result.success:
                        logger.debug(f"✓ Fetched {job.card_name}")
                    else:
                        logger.warning(
                            f"✗ Failed {job.card_name}: {result.error_message}"
                        )

                except Exception as e:
                    logger.error(f"✗ Exception fetching {job.card_name}: {e}")
                    results.append(FetchResult(job, False, str(e)))

        # Generate summary
        total_duration = time.time() - start_time
        successful_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]

        total_size = sum(r.file_size or 0 for r in successful_results)

        summary = FetchSummary(
            total_requested=len(jobs) + skipped_count,
            successful=len(successful_results),
            failed=len(failed_results),
            skipped=skipped_count,
            total_size_bytes=total_size,
            total_duration=total_duration,
            failed_jobs=[r.job for r in failed_results],
        )

        logger.info(
            f"Fetch complete: {summary.successful}/{summary.total_requested} successful "
            f"({summary.success_rate:.1f}%) in {summary.total_duration:.1f}s"
        )

        return summary

    def fetch_single_card(self, job: FetchJob, dry_run: bool = False) -> FetchResult:
        """Fetch a single card image."""
        if dry_run:
            return FetchResult(job, True, None, 0, 0.0)

        return self._fetch_single_card(job)

    def validate_fetch_jobs(self, jobs: List[FetchJob]) -> List[str]:
        """Validate fetch jobs and return list of issues."""
        issues = []

        if not jobs:
            issues.append("No fetch jobs provided")
            return issues

        # Check for duplicate destinations
        destinations = {}
        for job in jobs:
            dest_str = str(job.destination_path)
            if dest_str in destinations:
                issues.append(f"Duplicate destination: {dest_str}")
            else:
                destinations[dest_str] = job

        # Check for invalid URLs
        for job in jobs:
            if not job.image_url or not job.image_url.startswith(
                ("http://", "https://")
            ):
                issues.append(f"Invalid URL for {job.card_name}: {job.image_url}")

        # Check destination directories
        for job in jobs:
            parent_dir = job.destination_path.parent
            if not parent_dir.exists():
                try:
                    parent_dir.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    issues.append(f"Cannot create directory {parent_dir}: {e}")

        return issues

    def estimate_fetch_size(self, jobs: List[FetchJob]) -> Dict[str, Any]:
        """Estimate total download size and duration."""
        # Average card image sizes (rough estimates)
        avg_sizes = {
            CardType.BASIC_LAND: 800_000,  # 800KB
            CardType.NONBASIC_LAND: 850_000,  # 850KB
            CardType.TOKEN: 750_000,  # 750KB
            CardType.CREATURE: 900_000,  # 900KB
            CardType.PLANESWALKER: 950_000,  # 950KB
            CardType.INSTANT: 800_000,  # 800KB
            CardType.SORCERY: 800_000,  # 800KB
            CardType.ARTIFACT: 850_000,  # 850KB
            CardType.ENCHANTMENT: 850_000,  # 850KB
            CardType.ANY: 850_000,  # 850KB average
        }

        # Estimate based on job count (rough approximation)
        estimated_size = len(jobs) * avg_sizes[CardType.ANY]

        # Estimate duration (assuming 8 concurrent downloads at ~2MB/s total)
        estimated_duration = estimated_size / (2_000_000)  # 2MB/s total throughput

        return {
            "job_count": len(jobs),
            "estimated_size_bytes": estimated_size,
            "estimated_size_mb": estimated_size / 1_000_000,
            "estimated_duration_seconds": estimated_duration,
            "estimated_duration_minutes": estimated_duration / 60,
            "concurrent_workers": self.max_workers,
        }

    def _fetch_single_card(self, job: FetchJob) -> FetchResult:
        """Internal method to fetch a single card with retries."""
        start_time = time.time()
        error_msg = "Unknown error"

        for attempt in range(self.max_retries):
            try:
                # Ensure destination directory exists
                job.destination_path.parent.mkdir(parents=True, exist_ok=True)

                # Download image
                request = urllib.request.Request(
                    job.image_url, headers={"User-Agent": "ProxyMachine/1.0"}
                )

                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    if response.status == 200:
                        data = response.read()

                        # Write to file
                        with open(job.destination_path, "wb") as f:
                            f.write(data)

                        duration = time.time() - start_time
                        return FetchResult(job, True, None, len(data), duration)
                    else:
                        error_msg = f"HTTP {response.status}"

            except urllib.error.HTTPError as e:
                error_msg = f"HTTP {e.code}: {e.reason}"
            except urllib.error.URLError as e:
                error_msg = f"URL Error: {e.reason}"
            except Exception as e:
                error_msg = f"Unexpected error: {e}"

            # Retry with exponential backoff
            if attempt < self.max_retries - 1:
                wait_time = 2**attempt
                logger.debug(
                    f"Retrying {job.card_name} in {wait_time}s (attempt {attempt + 1})"
                )
                time.sleep(wait_time)

        duration = time.time() - start_time
        return FetchResult(job, False, error_msg, None, duration)

    def _simulate_fetch(self, jobs: List[FetchJob]) -> FetchSummary:
        """Simulate fetch operation for dry run."""
        logger.info("Simulating fetch operation (dry run)")

        # Simulate some processing time
        time.sleep(0.1)

        return FetchSummary(
            total_requested=len(jobs),
            successful=len(jobs),  # Assume all would succeed
            failed=0,
            skipped=0,
            total_size_bytes=len(jobs) * 850_000,  # Estimated average size
            total_duration=0.1,
            failed_jobs=[],
        )


# Global service instance
fetch_service = FetchService()

#!/usr/bin/env python3
"""
Image optimization tool for the proxy printer collection.

Performs lossless optimization on images in the shared directories to save disk space
while maintaining perfect quality. Ideal for hobby collections with hundreds of cards.

Features:
- Lossless PNG optimization using multiple algorithms
- JPEG optimization with quality preservation
- Batch processing with progress tracking
- Size reduction reporting
- Safe operations (backup originals if something goes wrong)
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor
import click

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
BACKUP_SUFFIX = ".backup-pre-optimization"


class ImageOptimizer:
    """Handles lossless image optimization for card collections."""

    def __init__(self, dry_run: bool = False, create_backups: bool = True):
        self.dry_run = dry_run
        self.create_backups = create_backups
        self.total_original_size = 0
        self.total_optimized_size = 0
        self.files_processed = 0
        self.files_improved = 0

    def check_dependencies(self) -> List[str]:
        """Check which optimization tools are available."""
        tools = []

        # Check for common optimization tools
        if shutil.which("optipng"):
            tools.append("optipng")
        if shutil.which("pngcrush"):
            tools.append("pngcrush")
        if shutil.which("jpegoptim"):
            tools.append("jpegoptim")
        if shutil.which("cjpeg"):
            tools.append("cjpeg")

        return tools

    def optimize_png(self, file_path: Path) -> Tuple[int, int]:
        """Optimize PNG file and return (original_size, new_size)."""
        original_size = file_path.stat().st_size

        if self.dry_run:
            # Estimate 10-20% savings for dry run
            estimated_savings = int(original_size * 0.15)
            return original_size, original_size - estimated_savings

        # Create backup if requested
        backup_path = None
        if self.create_backups:
            backup_path = file_path.with_suffix(file_path.suffix + BACKUP_SUFFIX)
            shutil.copy2(file_path, backup_path)

        try:
            # Try optipng first (best quality preservation)
            if shutil.which("optipng"):
                result = subprocess.run(
                    ["optipng", "-o2", "-quiet", str(file_path)], capture_output=True
                )
                if result.returncode == 0:
                    new_size = file_path.stat().st_size
                    # Remove backup if optimization successful
                    if backup_path:
                        backup_path.unlink(missing_ok=True)
                    return original_size, new_size

            # Fallback to pngcrush
            if shutil.which("pngcrush"):
                temp_path = file_path.with_suffix(".tmp" + file_path.suffix)
                result = subprocess.run(
                    ["pngcrush", "-q", str(file_path), str(temp_path)],
                    capture_output=True,
                )
                if result.returncode == 0 and temp_path.exists():
                    shutil.move(temp_path, file_path)
                    new_size = file_path.stat().st_size
                    if backup_path:
                        backup_path.unlink(missing_ok=True)
                    return original_size, new_size
                else:
                    temp_path.unlink(missing_ok=True)

        except Exception as e:
            click.echo(f"Warning: Failed to optimize {file_path.name}: {e}")
            # Restore from backup if something went wrong
            if backup_path and backup_path.exists():
                shutil.move(backup_path, file_path)

        return original_size, original_size

    def optimize_jpeg(self, file_path: Path) -> Tuple[int, int]:
        """Optimize JPEG file and return (original_size, new_size)."""
        original_size = file_path.stat().st_size

        if self.dry_run:
            # Estimate 5-15% savings for dry run
            estimated_savings = int(original_size * 0.10)
            return original_size, original_size - estimated_savings

        # Create backup if requested
        backup_path = None
        if self.create_backups:
            backup_path = file_path.with_suffix(file_path.suffix + BACKUP_SUFFIX)
            shutil.copy2(file_path, backup_path)

        try:
            # Use jpegoptim for lossless optimization
            if shutil.which("jpegoptim"):
                result = subprocess.run(
                    ["jpegoptim", "--strip-all", "--quiet", str(file_path)],
                    capture_output=True,
                )
                if result.returncode == 0:
                    new_size = file_path.stat().st_size
                    if backup_path:
                        backup_path.unlink(missing_ok=True)
                    return original_size, new_size

        except Exception as e:
            click.echo(f"Warning: Failed to optimize {file_path.name}: {e}")
            # Restore from backup if something went wrong
            if backup_path and backup_path.exists():
                shutil.move(backup_path, file_path)

        return original_size, original_size

    def optimize_file(self, file_path: Path) -> Optional[Tuple[int, int]]:
        """Optimize a single image file."""
        if not file_path.exists():
            return None

        ext = file_path.suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            return None

        if ext == ".png":
            return self.optimize_png(file_path)
        elif ext in {".jpg", ".jpeg"}:
            return self.optimize_jpeg(file_path)
        else:
            # For other formats, just return original size (no optimization)
            size = file_path.stat().st_size
            return size, size

    def optimize_directory(
        self, directory: Path, recursive: bool = True, jobs: int = 1
    ) -> None:
        """Optimize all images in a directory."""
        if not directory.exists():
            click.echo(f"Directory not found: {directory}")
            return

        click.echo(
            f"{'[DRY RUN] ' if self.dry_run else ''}Optimizing images in: {directory}"
        )

        # Collect all image files
        image_files = []
        if recursive:
            for ext in IMAGE_EXTENSIONS:
                image_files.extend(directory.rglob(f"*{ext}"))
        else:
            for ext in IMAGE_EXTENSIONS:
                image_files.extend(directory.glob(f"*{ext}"))

        if not image_files:
            click.echo("No image files found.")
            return

        total_files = len(image_files)
        click.echo(f"Found {total_files} image files to process...")

        max_workers = max(1, jobs)

        def worker(path: Path) -> Tuple[Path, Optional[Tuple[int, int]]]:
            try:
                return path, self.optimize_file(path)
            except Exception as exc:  # pragma: no cover - defensive
                click.echo(f"  Warning: Failed to process {path.name}: {exc}")
                return path, None

        executor = None
        if max_workers == 1:
            iterator = (worker(p) for p in image_files)
        else:
            executor = ThreadPoolExecutor(max_workers=max_workers)
            iterator = executor.map(worker, image_files)

        for i, (file_path, result) in enumerate(iterator, 1):
            if i % 50 == 0 or i == total_files:
                click.echo(f"Progress: {i}/{total_files} files processed")

            if not result:
                continue

            original_size, new_size = result
            self.total_original_size += original_size
            self.total_optimized_size += new_size
            self.files_processed += 1

            if new_size < original_size:
                self.files_improved += 1
                savings = original_size - new_size
                savings_pct = (savings / original_size) * 100
                click.echo(
                    f"  Optimized: {file_path.name} "
                    f"({self._format_size(original_size)} → {self._format_size(new_size)}, "
                    f"-{savings_pct:.1f}%)"
                )

        if executor is not None:
            executor.shutdown(wait=True)

    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human readable format."""
        size = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f}{unit}"
            size /= 1024.0
        return f"{size:.1f}TB"

    def print_summary(self) -> None:
        """Print optimization summary."""
        if self.files_processed == 0:
            click.echo("No files were processed.")
            return

        total_savings = self.total_original_size - self.total_optimized_size
        savings_pct = (
            (total_savings / self.total_original_size * 100)
            if self.total_original_size > 0
            else 0
        )

        click.echo(f"\n{'DRY RUN ' if self.dry_run else ''}OPTIMIZATION SUMMARY")
        click.echo("=" * 50)
        click.echo(f"Files processed: {self.files_processed}")
        click.echo(f"Files improved: {self.files_improved}")
        click.echo(f"Original size: {self._format_size(self.total_original_size)}")
        click.echo(f"Optimized size: {self._format_size(self.total_optimized_size)}")
        click.echo(
            f"Space saved: {self._format_size(total_savings)} ({savings_pct:.1f}%)"
        )

        if self.dry_run:
            click.echo(
                "\nDry run complete. Rerun without '--dry-run' to apply these optimizations."
            )


@click.command()
@click.option(
    "--directory",
    "-d",
    type=click.Path(exists=True, path_type=Path),
    help="Directory to optimize (default: all shared directories)",
)
@click.option(
    "--recursive",
    "-r",
    is_flag=True,
    default=True,
    help="Process directories recursively",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview which files would be optimized without making changes",
)
@click.option(
    "--no-backup",
    is_flag=True,
    default=False,
    help="Don't create backup files (faster but riskier)",
)
@click.option(
    "--jobs",
    "-j",
    type=int,
    default=0,
    help="Parallel worker count (0 = auto based on CPU cores)",
)
def main(
    directory: Optional[Path],
    recursive: bool,
    dry_run: bool,
    no_backup: bool,
    jobs: int,
):
    """Optimize images in card collection directories.

    Performs lossless optimization to reduce file sizes while maintaining perfect quality.
    Great for hobby collections to save disk space.

    Examples:
      python tools/optimize_images.py             # Optimize all shared directories
      python tools/optimize_images.py --dry-run   # Preview optimization
      python tools/optimize_images.py -d ~/shared/basic-lands
      python tools/optimize_images.py -j 4        # Optimize with 4 parallel workers
    """

    # Import here to avoid circular imports
    try:
        from create_pdf import (
            shared_basic_lands_path,
            shared_non_basic_lands_path,
            shared_tokens_path,
            shared_card_backs_path,
            shared_creatures_path,
            shared_enchantments_path,
            shared_artifacts_path,
            shared_instants_path,
            shared_sorceries_path,
            shared_planeswalkers_path,
        )
    except ImportError as e:
        click.echo(f"Error importing shared paths: {e}")
        click.echo("Make sure you're running this from the proxy-machine directory.")
        sys.exit(1)

    worker_count = jobs if jobs > 0 else max(1, os.cpu_count() or 4)

    optimizer = ImageOptimizer(dry_run=dry_run, create_backups=not no_backup)

    # Check for optimization tools
    available_tools = optimizer.check_dependencies()
    if not available_tools:
        click.echo("⚠️  No image optimization tools found!")
        click.echo("Install optimization tools for better results:")
        click.echo("  macOS: brew install optipng jpegoptim")
        click.echo("  Ubuntu: sudo apt install optipng jpegoptim")
        click.echo("  Arch: sudo pacman -S optipng jpegoptim")
        click.echo("\nContinuing with basic optimization...")
    else:
        click.echo(f"✅ Found optimization tools: {', '.join(available_tools)}")

    if directory:
        # Optimize specific directory
        optimizer.optimize_directory(directory, recursive=recursive, jobs=worker_count)
    else:
        # Optimize all shared directories
        shared_dirs = [
            Path(shared_basic_lands_path),
            Path(shared_non_basic_lands_path),
            Path(shared_card_backs_path),
            Path(shared_creatures_path),
            Path(shared_enchantments_path),
            Path(shared_artifacts_path),
            Path(shared_instants_path),
            Path(shared_sorceries_path),
            Path(shared_planeswalkers_path),
        ]

        for shared_dir in shared_dirs:
            if shared_dir.exists():
                optimizer.optimize_directory(
                    shared_dir, recursive=recursive, jobs=worker_count
                )

    optimizer.print_summary()

    if dry_run:
        click.echo(
            "\n💡 Run without '--dry-run' (or make optimize-images DRY_RUN=1) to apply changes."
        )


if __name__ == "__main__":  # pragma: no cover
    main()  # type: ignore[call-arg]

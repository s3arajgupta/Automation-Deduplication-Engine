"""Deduplication Engine CLI - High-performance file and directory deduplication."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

# Ensure UTF-8 output encoding on Windows consoles
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import typer
from rich.console import Console
from rich.prompt import Confirm

from dedup_engine.cleaner import CleanupEngine
from dedup_engine.core import DuplicateScanner
from dedup_engine.folder_hasher import FolderDeduplicator
from dedup_engine.models import RetentionStrategy
from dedup_engine.reporter import DuplicateReporter, format_bytes

app = typer.Typer(
    name="dedup",
    help="High-performance CLI for detecting duplicate files and directory clones.",
    add_completion=False,
)
console = Console()
reporter = DuplicateReporter(console=console)


@app.command()
def scan(
    path: Path = typer.Argument(
        Path("."),
        help="Directory path to scan for duplicate files.",
    ),
    algorithm: str = typer.Option(
        "sha256",
        "--algorithm",
        "-a",
        help="Cryptographic hash algorithm (sha256, md5, blake2b).",
    ),
    min_size: int = typer.Option(
        1,
        "--min-size",
        "-m",
        help="Minimum file size in bytes to consider.",
    ),
    ignore: Optional[str] = typer.Option(
        None,
        "--ignore",
        "-i",
        help="Comma-separated custom ignore glob patterns (e.g. '*.bak,temp/*').",
    ),
    tree: bool = typer.Option(
        True,
        "--tree/--no-tree",
        help="Display hierarchical visual cluster tree.",
    ),
    export: Optional[Path] = typer.Option(
        None,
        "--export",
        "-e",
        help="Export findings to file (.json, .csv, or .txt).",
    ),
) -> None:
    """Scan a directory for duplicate files using multi-stage hashing."""
    if not path.exists():
        console.print(f"[bold red]Error: Directory does not exist:[/bold red] {path}")
        raise typer.Exit(code=1)

    console.print(f"\n[bold cyan][*] Scanning for duplicate files in:[/bold cyan] {path.resolve()}")

    ignore_list = [p.strip() for p in ignore.split(",")] if ignore else None
    scanner = DuplicateScanner(
        algorithm=algorithm,
        min_size_bytes=min_size,
        ignore_patterns=ignore_list,
    )

    def on_progress(stage_msg: str, count: int):
        console.print(f"[dim]{stage_msg}[/dim]")

    groups = scanner.scan_directory(path.resolve(), progress_callback=on_progress)

    reporter.print_file_summary(groups)

    if tree and groups:
        reporter.print_file_tree(groups)

    if export:
        suffix = export.suffix.lower()
        if suffix == ".json":
            reporter.export_json(groups, export)
            console.print(f"[green]✔ Findings exported to JSON:[/green] {export}")
        elif suffix == ".csv":
            reporter.export_csv(groups, export)
            console.print(f"[green]✔ Findings exported to CSV:[/green] {export}")
        else:
            reporter.export_legacy_text(groups, export)
            console.print(f"[green]✔ Findings exported to text report:[/green] {export}")


@app.command()
def folders(
    path: Path = typer.Argument(
        Path("."),
        help="Root directory to scan for identical folder trees.",
    ),
    min_files: int = typer.Option(
        2,
        "--min-files",
        "-n",
        help="Minimum files required in a folder to consider it.",
    ),
    algorithm: str = typer.Option(
        "sha256",
        "--algorithm",
        "-a",
        help="Hash algorithm to use for tree signatures.",
    ),
    ignore: Optional[str] = typer.Option(
        None,
        "--ignore",
        "-i",
        help="Comma-separated ignore glob patterns.",
    ),
) -> None:
    """Detect entire duplicate directory trees and clone folders."""
    if not path.exists():
        console.print(f"[bold red]Error: Directory does not exist:[/bold red] {path}")
        raise typer.Exit(code=1)

    console.print(f"\n[bold magenta][*] Analyzing directory tree signatures in:[/bold magenta] {path.resolve()}")

    ignore_list = [p.strip() for p in ignore.split(",")] if ignore else None
    deduplicator = FolderDeduplicator(
        algorithm=algorithm,
        min_files=min_files,
        ignore_patterns=ignore_list,
    )

    def on_progress(stage_msg: str, count: int):
        console.print(f"[dim]{stage_msg}[/dim]")

    folder_groups = deduplicator.scan_folders(path.resolve(), progress_callback=on_progress)
    reporter.print_folder_summary(folder_groups)


@app.command()
def clean(
    path: Path = typer.Argument(
        Path("."),
        help="Target directory to clean duplicates from.",
    ),
    keep: RetentionStrategy = typer.Option(
        RetentionStrategy.NEWEST,
        "--keep",
        "-k",
        help="Which duplicate file to preserve: newest, oldest, or shortest-path.",
    ),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--execute",
        help="Simulate actions without deleting files. Use --execute for live cleanup.",
    ),
    quarantine: Optional[Path] = typer.Option(
        None,
        "--quarantine",
        "-q",
        help="Move duplicates to a safe quarantine directory instead of permanent deletion.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Bypass interactive confirmation prompt when --execute is active.",
    ),
) -> None:
    """Resolve duplicate files safely according to a retention policy."""
    console.print(f"\n[bold yellow][*] Planning duplicate cleanup in:[/bold yellow] {path.resolve()}")

    scanner = DuplicateScanner()
    groups = scanner.scan_directory(path.resolve())

    if not groups:
        console.print("[green]✔ No duplicate files found. Nothing to clean.[/green]")
        return

    cleaner = CleanupEngine(strategy=keep, quarantine_dir=quarantine)
    plan = cleaner.plan_cleanup(groups)

    reporter.print_cleanup_plan(plan, dry_run=dry_run)

    if dry_run:
        console.print("[bold yellow][INFO] Running in dry-run mode. Zero files were modified or deleted.[/bold yellow]")
        console.print("[dim]To execute this plan, pass: [bold cyan]dedup clean <DIR> --execute[/bold cyan][/dim]\n")
        return

    # If executing live, ask for user confirmation unless --force is set
    if not force:
        confirmed = Confirm.ask(
            f"Are you sure you want to delete {plan.total_files_to_delete} duplicate files to reclaim {format_bytes(plan.reclaimable_bytes)}?",
            default=False,
        )
        if not confirmed:
            console.print("[yellow]Cleanup aborted by user.[/yellow]")
            return

    def on_delete(file_path: Path):
        console.print(f"[red]  [-] Removed:[/red] {file_path}")

    deleted_count, reclaimed, errors = cleaner.execute_plan(
        plan,
        dry_run=False,
        progress_callback=on_delete,
    )

    console.print(
        f"\n[bold green]✔ Successfully processed {deleted_count} files. Reclaimed: {format_bytes(reclaimed)}[/bold green]"
    )
    if errors:
        console.print(f"\n[bold red]Warnings / Errors encountered ({len(errors)}):[/bold red]")
        for err in errors:
            console.print(f"  • {err}")


if __name__ == "__main__":
    app()

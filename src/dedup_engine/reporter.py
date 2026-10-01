"""Reporting, export formatting, and Rich visualizations for Deduplication Engine."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import List, Union

from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from dedup_engine.models import CleanupPlan, DuplicateFolderGroup, DuplicateGroup


def format_bytes(num_bytes: Union[int, float]) -> str:
    """Format bytes into human-readable binary units (B, KB, MB, GB, TB)."""
    val = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(val) < 1024.0:
            return f"{val:3.2f} {unit}"
        val /= 1024.0
    return f"{val:.2f} PB"


class DuplicateReporter:
    """Generates visual terminal tables, trees, and machine-readable exports."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def print_file_summary(self, groups: List[DuplicateGroup]) -> None:
        """Display an executive summary table of duplicate files."""
        total_groups = len(groups)
        total_duplicate_files = sum(g.count for g in groups)
        total_reclaimable = sum(g.reclaimable_bytes for g in groups)

        table = Table(title="Duplicate Files Scan Summary", show_header=True)
        table.add_column("Metric", style="bold cyan")
        table.add_column("Value", justify="right")

        table.add_row("Duplicate Clusters Found", str(total_groups))
        table.add_row("Total Redundant Files", str(total_duplicate_files))
        table.add_row("Total Reclaimable Space", f"[bold green]{format_bytes(total_reclaimable)}[/bold green]")

        self.console.print("\n", table)

    def print_file_tree(self, groups: List[DuplicateGroup], max_groups: int = 15) -> None:
        """Render a hierarchical tree of duplicate file clusters."""
        if not groups:
            self.console.print("[green]✔ No duplicate files found.[/green]")
            return

        root_tree = Tree("📁 [bold yellow]Duplicate File Clusters[/bold yellow]")

        for idx, group in enumerate(groups[:max_groups], start=1):
            short_hash = group.file_hash[:10]
            cluster = root_tree.add(
                f"[bold cyan]Cluster #{idx}[/bold cyan] "
                f"([dim]{short_hash}...[/dim]) - "
                f"[bold]{group.count} copies[/bold] x {format_bytes(group.size_per_file)} "
                f"([green]Reclaim: {format_bytes(group.reclaimable_bytes)}[/green])"
            )
            for f in group.files:
                cluster.add(f"[white]{f.path}[/white]")

        self.console.print(root_tree)
        if len(groups) > max_groups:
            self.console.print(f"[dim]... and {len(groups) - max_groups} more duplicate clusters.[/dim]")

    def print_folder_summary(self, groups: List[DuplicateFolderGroup]) -> None:
        """Display summary of duplicate directory trees."""
        total_groups = len(groups)
        total_reclaimable = sum(g.reclaimable_bytes for g in groups)

        table = Table(title="Duplicate Directory Trees Summary", show_header=True)
        table.add_column("Metric", style="bold magenta")
        table.add_column("Value", justify="right")

        table.add_row("Duplicate Directory Trees", str(total_groups))
        table.add_row("Total Redundant Space", f"[bold green]{format_bytes(total_reclaimable)}[/bold green]")
        self.console.print("\n", table)

        if not groups:
            self.console.print("[green]✔ No duplicate folder trees found.[/green]")
            return

        tree = Tree("🗂️ [bold yellow]Identical Directory Trees[/bold yellow]")
        for idx, group in enumerate(groups, start=1):
            branch = tree.add(
                f"[bold magenta]Mirror Group #{idx}[/bold magenta] "
                f"({group.file_count} files, {format_bytes(group.total_size_bytes)} each) - "
                f"[green]Reclaim: {format_bytes(group.reclaimable_bytes)}[/green]"
            )
            for f in group.folders:
                branch.add(f"[white]{f.path}[/white]")

        self.console.print(tree)

    def print_cleanup_plan(self, plan: CleanupPlan, dry_run: bool) -> None:
        """Show preview of actions before deletion."""
        label = "[bold yellow]DRY-RUN PREVIEW[/bold yellow]" if dry_run else "[bold red]LIVE EXECUTION[/bold red]"
        table = Table(title=f"Cleanup Action Plan ({label})", show_header=True)
        table.add_column("Action", style="bold")
        table.add_column("File Path")
        table.add_column("Size", justify="right")
        table.add_column("Reason", style="dim")

        for action in plan.actions[:25]:
            style = "green" if action.action == "KEEP" else "red"
            table.add_row(
                f"[{style}]{action.action}[/{style}]",
                str(action.path),
                format_bytes(action.size_bytes),
                action.reason,
            )

        self.console.print(table)
        if len(plan.actions) > 25:
            self.console.print(f"[dim]... and {len(plan.actions) - 25} more items.[/dim]")

        self.console.print(
            f"\nFiles to remove: [bold red]{plan.total_files_to_delete}[/bold red] | "
            f"Space to reclaim: [bold green]{format_bytes(plan.reclaimable_bytes)}[/bold green]\n"
        )

    def export_json(self, groups: List[DuplicateGroup], output_path: Path) -> None:
        """Export duplicates to a clean JSON structure."""
        data = [
            {
                "hash": g.file_hash,
                "file_size_bytes": g.size_per_file,
                "copies": g.count,
                "reclaimable_bytes": g.reclaimable_bytes,
                "files": [str(f.path) for f in g.files],
            }
            for g in groups
        ]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def export_csv(self, groups: List[DuplicateGroup], output_path: Path) -> None:
        """Export duplicates to CSV."""
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ClusterHash", "FileSize", "Path", "IsPrimary"])
            for g in groups:
                for idx, f in enumerate(g.files):
                    writer.writerow([g.file_hash, g.size_per_file, str(f.path), idx == 0])

    def export_legacy_text(self, groups: List[DuplicateGroup], output_path: Path) -> None:
        """Export in human-readable plain text matching legacy format."""
        with open(output_path, "w", encoding="utf-8") as f:
            for idx, g in enumerate(groups, start=1):
                f.write(f"Duplicate group {idx} ({format_bytes(g.size_per_file)} each):\n")
                for item in g.files:
                    f.write(f"  {item.path}\n")
                f.write("\n")

"""Safe deletion engine with retention policies and dry-run safety."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from dedup_engine.models import (
    CleanupAction,
    CleanupPlan,
    DuplicateGroup,
    FileEntry,
    RetentionStrategy,
)


class CleanupEngine:
    """Calculates and executes safe file deduplication plans."""

    def __init__(
        self,
        strategy: RetentionStrategy = RetentionStrategy.NEWEST,
        quarantine_dir: Optional[Path] = None,
    ) -> None:
        self.strategy = strategy
        self.quarantine_dir = quarantine_dir

    def plan_cleanup(self, groups: List[DuplicateGroup]) -> CleanupPlan:
        """Determines which files to keep and which to delete based on the retention rule."""
        actions: List[CleanupAction] = []
        total_reclaimable = 0
        total_deletions = 0

        for group in groups:
            if group.count < 2:
                continue

            # Select file to keep based on strategy
            kept_file = self._select_keep(group.files)

            for file_entry in group.files:
                if file_entry == kept_file:
                    actions.append(
                        CleanupAction(
                            path=file_entry.path,
                            action="KEEP",
                            reason=f"Selected by strategy: {self.strategy.value}",
                            size_bytes=file_entry.size,
                        )
                    )
                else:
                    actions.append(
                        CleanupAction(
                            path=file_entry.path,
                            action="DELETE",
                            reason=f"Duplicate of {kept_file.path.name}",
                            size_bytes=file_entry.size,
                        )
                    )
                    total_reclaimable += file_entry.size
                    total_deletions += 1

        return CleanupPlan(
            actions=actions,
            reclaimable_bytes=total_reclaimable,
            total_files_to_delete=total_deletions,
        )

    def _select_keep(self, files: List[FileEntry]) -> FileEntry:
        """Select single file to retain based on configured strategy."""
        if self.strategy == RetentionStrategy.NEWEST:
            # Sort by mtime descending (most recently modified first)
            return max(files, key=lambda f: f.mtime)
        elif self.strategy == RetentionStrategy.OLDEST:
            # Sort by mtime ascending (earliest created/modified first)
            return min(files, key=lambda f: f.mtime)
        elif self.strategy == RetentionStrategy.SHORTEST_PATH:
            # Shortest string representation of path (usually closest to root)
            return min(files, key=lambda f: len(str(f.path)))
        return files[0]

    def execute_plan(
        self,
        plan: CleanupPlan,
        dry_run: bool = True,
        progress_callback: Optional[Callable[[Path], None]] = None,
    ) -> Tuple[int, int, List[str]]:
        """
        Executes the deletion plan.
        Returns:
            (files_processed, bytes_reclaimed, error_messages)
        """
        if dry_run:
            return plan.total_files_to_delete, plan.reclaimable_bytes, []

        deleted_count = 0
        bytes_reclaimed = 0
        errors: List[str] = []

        if self.quarantine_dir:
            self.quarantine_dir.mkdir(parents=True, exist_ok=True)

        for action in plan.actions:
            if action.action != "DELETE":
                continue

            try:
                if progress_callback:
                    progress_callback(action.path)

                if self.quarantine_dir:
                    # Move to quarantine preserving filename with unique index if needed
                    target = self.quarantine_dir / action.path.name
                    counter = 1
                    while target.exists():
                        target = self.quarantine_dir / f"{action.path.stem}_{counter}{action.path.suffix}"
                        counter += 1
                    shutil.move(str(action.path), str(target))
                else:
                    action.path.unlink(missing_ok=True)

                deleted_count += 1
                bytes_reclaimed += action.size_bytes
            except Exception as e:
                errors.append(f"Failed to delete {action.path}: {e}")

        return deleted_count, bytes_reclaimed, errors

"""Deterministic folder tree hashing to detect duplicate directory clones."""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from dedup_engine.core import hash_stream, should_ignore, DEFAULT_IGNORE_PATTERNS
from dedup_engine.models import DuplicateFolderGroup, FolderEntry


class FolderDeduplicator:
    """Detects identical directory trees using bottom-up content signatures."""

    def __init__(
        self,
        algorithm: str = "sha256",
        min_files: int = 2,
        ignore_patterns: Optional[List[str]] = None,
    ) -> None:
        self.algorithm = algorithm
        self.min_files = min_files
        self.ignore_patterns = list(DEFAULT_IGNORE_PATTERNS)
        if ignore_patterns:
            self.ignore_patterns.extend(ignore_patterns)

    def scan_folders(
        self,
        root_dir: Path,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> List[DuplicateFolderGroup]:
        """
        Scans all directories under root_dir and computes a deterministic Merkle-style
        content hash for each folder tree based on relative child paths and file hashes.
        """
        if not root_dir.is_dir():
            raise NotADirectoryError(f"Root path is not a directory: {root_dir}")

        if progress_callback:
            progress_callback("Collecting directory hierarchy...", 0)

        # Map each directory to its list of (relative_path_from_dir, file_hash, file_size)
        folder_candidates: List[Path] = []
        file_hashes_cache: Dict[Path, Tuple[str, int]] = {}

        # 1. Discover all non-ignored directories
        for root, dirs, files in os.walk(root_dir):
            root_path = Path(root)
            dirs[:] = [
                d for d in dirs
                if not should_ignore(root_path / d, root_dir, self.ignore_patterns)
            ]
            if root_path != root_dir:
                folder_candidates.append(root_path)

        if progress_callback:
            progress_callback(
                f"Computing signatures for {len(folder_candidates)} folders...",
                len(folder_candidates),
            )

        tree_map: Dict[str, List[FolderEntry]] = defaultdict(list)

        for folder in folder_candidates:
            child_signatures: List[str] = []
            total_size = 0
            file_count = 0

            try:
                for sub_root, _, sub_files in os.walk(folder):
                    sub_root_path = Path(sub_root)
                    for f in sub_files:
                        f_path = sub_root_path / f
                        if should_ignore(f_path, root_dir, self.ignore_patterns):
                            continue

                        # Read or compute file hash
                        if f_path not in file_hashes_cache:
                            try:
                                f_stat = f_path.stat()
                                f_h = hash_stream(f_path, algorithm=self.algorithm)
                                file_hashes_cache[f_path] = (f_h, f_stat.st_size)
                            except (OSError, PermissionError):
                                continue

                        f_hash, f_size = file_hashes_cache[f_path]
                        rel_path = str(f_path.relative_to(folder)).replace("\\", "/")
                        child_signatures.append(f"{rel_path}:{f_hash}")
                        total_size += f_size
                        file_count += 1
            except (OSError, PermissionError):
                continue

            if file_count < self.min_files:
                continue

            # Deterministic sorting ensures same files in any order produce the exact same hash
            child_signatures.sort()
            combined_raw = "\n".join(child_signatures).encode("utf-8")
            folder_tree_hash = hashlib.new(self.algorithm, combined_raw).hexdigest()

            entry = FolderEntry(
                path=folder,
                file_count=file_count,
                total_size_bytes=total_size,
                tree_hash=folder_tree_hash,
            )
            tree_map[folder_tree_hash].append(entry)

        # Filter out unique folders and prune sub-directory redundancy
        duplicate_groups: List[DuplicateFolderGroup] = []
        for t_hash, folders in tree_map.items():
            if len(folders) > 1:
                duplicate_groups.append(
                    DuplicateFolderGroup(
                        tree_hash=t_hash,
                        total_size_bytes=folders[0].total_size_bytes,
                        file_count=folders[0].file_count,
                        folders=folders,
                    )
                )

        # Sort by reclaimable space descending
        duplicate_groups.sort(key=lambda g: g.reclaimable_bytes, reverse=True)
        return self._filter_nested_duplicates(duplicate_groups)

    def _filter_nested_duplicates(
        self,
        groups: List[DuplicateFolderGroup],
    ) -> List[DuplicateFolderGroup]:
        """
        If a parent directory is already marked as duplicate, prune its child subdirectories
        to avoid redundant reporting of every subfolder.
        """
        # Collect all duplicate folder paths
        matched_roots: Set[Path] = set()
        filtered_groups: List[DuplicateFolderGroup] = []

        for group in groups:
            # Check if folders in this group are subdirectories of higher-level duplicate roots
            is_nested = False
            for parent_root in matched_roots:
                if any(f.path.is_relative_to(parent_root) and f.path != parent_root for f in group.folders):
                    is_nested = True
                    break

            if not is_nested:
                filtered_groups.append(group)
                for f in group.folders:
                    matched_roots.add(f.path)

        return filtered_groups

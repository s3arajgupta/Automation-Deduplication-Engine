"""High-performance multi-stage file deduplication engine."""

from __future__ import annotations

import fnmatch
import hashlib
import os
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Set

from dedup_engine.models import DuplicateGroup, FileEntry

DEFAULT_IGNORE_PATTERNS = [
    ".git",
    ".git/*",
    "node_modules",
    "node_modules/*",
    "__pycache__",
    "__pycache__/*",
    ".venv",
    ".venv/*",
    "venv",
    "venv/*",
    "build",
    "build/*",
    "dist",
    "dist/*",
    ".idea",
    ".vscode",
    "*.pyc",
]


def should_ignore(path: Path, root: Path, ignore_patterns: List[str]) -> bool:
    """Check if a path matches any specified glob or filename ignore pattern."""
    rel_path_str = str(path.relative_to(root)).replace("\\", "/")
    name = path.name

    for pattern in ignore_patterns:
        pattern = pattern.strip().replace("\\", "/")
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_path_str, pattern):
            return True
        # Match directory prefixes
        if f"/{pattern}/" in f"/{rel_path_str}/":
            return True
    return False


def hash_stream(
    file_path: Path,
    algorithm: str = "sha256",
    max_bytes: Optional[int] = None,
    block_size: int = 65536,
) -> str:
    """Hash a file using a streaming chunk reader with optional byte limit."""
    hasher = hashlib.new(algorithm)
    bytes_read = 0

    with open(file_path, "rb") as f:
        while True:
            read_size = block_size
            if max_bytes is not None:
                remaining = max_bytes - bytes_read
                if remaining <= 0:
                    break
                read_size = min(block_size, remaining)

            chunk = f.read(read_size)
            if not chunk:
                break
            hasher.update(chunk)
            bytes_read += len(chunk)

    return hasher.hexdigest()


class DuplicateScanner:
    """Multi-stage pipeline for scanning and identifying duplicate files."""

    def __init__(
        self,
        algorithm: str = "sha256",
        prefix_bytes: int = 4096,
        min_size_bytes: int = 1,
        ignore_patterns: Optional[List[str]] = None,
    ) -> None:
        self.algorithm = algorithm
        self.prefix_bytes = prefix_bytes
        self.min_size_bytes = min_size_bytes
        self.ignore_patterns = list(DEFAULT_IGNORE_PATTERNS)
        if ignore_patterns:
            self.ignore_patterns.extend(ignore_patterns)

    def scan_directory(
        self,
        target_dir: Path,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> List[DuplicateGroup]:
        """
        Executes the 3-stage deduplication pipeline:
          Stage 1: Stat file sizes into buckets.
          Stage 2: 4KB Prefix hash to prune false positives.
          Stage 3: Full cryptographic content hash.
        """
        if not target_dir.is_dir():
            raise NotADirectoryError(f"Target is not a directory: {target_dir}")

        # ---------------------------------------------------------
        # Stage 1: File Discovery & Size Grouping
        # ---------------------------------------------------------
        if progress_callback:
            progress_callback("Stage 1/3: Discovering files and grouping by size...", 0)

        size_map: Dict[int, List[FileEntry]] = defaultdict(list)
        total_files_scanned = 0

        for root, dirs, files in os.walk(target_dir):
            root_path = Path(root)
            # Filter directories in-place to avoid descending into ignored folders
            dirs[:] = [
                d for d in dirs
                if not should_ignore(root_path / d, target_dir, self.ignore_patterns)
            ]

            for file_name in files:
                file_path = root_path / file_name
                if should_ignore(file_path, target_dir, self.ignore_patterns):
                    continue

                try:
                    stat = file_path.stat()
                    file_size = stat.st_size
                    if file_size < self.min_size_bytes:
                        continue

                    entry = FileEntry(
                        path=file_path,
                        size=file_size,
                        mtime=stat.st_mtime,
                    )
                    size_map[file_size].append(entry)
                    total_files_scanned += 1
                except (OSError, PermissionError):
                    continue

        # Prune unique sizes (files with unique sizes cannot have duplicates)
        candidate_groups: List[List[FileEntry]] = [
            group for group in size_map.values() if len(group) > 1
        ]

        if not candidate_groups:
            return []

        # ---------------------------------------------------------
        # Stage 2: Fast Prefix Hashing (e.g. 4KB header)
        # ---------------------------------------------------------
        if progress_callback:
            progress_callback("Stage 2/3: Calculating fast prefix hashes...", len(candidate_groups))

        prefix_map: Dict[str, List[FileEntry]] = defaultdict(list)
        for group in candidate_groups:
            for entry in group:
                try:
                    # If file is smaller than prefix size, full content is hashed here
                    p_hash = hash_stream(
                        entry.path,
                        algorithm=self.algorithm,
                        max_bytes=self.prefix_bytes,
                    )
                    entry.prefix_hash = p_hash
                    # Unique key combines size + prefix hash
                    key = f"{entry.size}_{p_hash}"
                    prefix_map[key].append(entry)
                except (OSError, PermissionError):
                    continue

        # Prune unique prefix groups
        prefix_candidates: List[List[FileEntry]] = [
            group for group in prefix_map.values() if len(group) > 1
        ]

        if not prefix_candidates:
            return []

        # ---------------------------------------------------------
        # Stage 3: Full Cryptographic Content Hashing
        # ---------------------------------------------------------
        if progress_callback:
            progress_callback("Stage 3/3: Verifying full content hashes...", len(prefix_candidates))

        full_hash_map: Dict[str, List[FileEntry]] = defaultdict(list)
        for group in prefix_candidates:
            # Optimization: If all files in group are <= prefix_bytes, prefix_hash IS full_hash!
            is_small = all(e.size <= self.prefix_bytes for e in group)

            for entry in group:
                try:
                    if is_small and entry.prefix_hash:
                        f_hash = entry.prefix_hash
                    else:
                        f_hash = hash_stream(entry.path, algorithm=self.algorithm)
                    entry.full_hash = f_hash
                    full_hash_map[f_hash].append(entry)
                except (OSError, PermissionError):
                    continue

        # Construct final duplicate groups (filter groups where count > 1)
        duplicate_groups: List[DuplicateGroup] = []
        for f_hash, entries in full_hash_map.items():
            if len(entries) > 1:
                duplicate_groups.append(
                    DuplicateGroup(
                        file_hash=f_hash,
                        size_per_file=entries[0].size,
                        files=entries,
                    )
                )

        # Sort duplicate groups by reclaimable size descending
        duplicate_groups.sort(key=lambda g: g.reclaimable_bytes, reverse=True)
        return duplicate_groups

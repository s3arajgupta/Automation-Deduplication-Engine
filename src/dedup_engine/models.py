"""Data structures and representations for Deduplication Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


class RetentionStrategy(str, Enum):
    """Rule determining which file/folder to keep when resolving duplicates."""
    NEWEST = "newest"
    OLDEST = "oldest"
    SHORTEST_PATH = "shortest-path"


@dataclass
class FileEntry:
    """Metadata representation of a scanned file."""
    path: Path
    size: int
    mtime: float
    prefix_hash: Optional[str] = None
    full_hash: Optional[str] = None


@dataclass
class DuplicateGroup:
    """A cluster of files sharing the identical full cryptographic hash."""
    file_hash: str
    size_per_file: int
    files: List[FileEntry] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.files)

    @property
    def reclaimable_bytes(self) -> int:
        """Space saved if all but one duplicate file are deleted."""
        if self.count > 1:
            return (self.count - 1) * self.size_per_file
        return 0


@dataclass
class FolderEntry:
    """Summary of a directory and its deterministic content signature."""
    path: Path
    file_count: int
    total_size_bytes: int
    tree_hash: str


@dataclass
class DuplicateFolderGroup:
    """A cluster of directories with identical internal content trees."""
    tree_hash: str
    total_size_bytes: int
    file_count: int
    folders: List[FolderEntry] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.folders)

    @property
    def reclaimable_bytes(self) -> int:
        """Space saved if redundant directory clones are removed."""
        if self.count > 1:
            return (self.count - 1) * self.total_size_bytes
        return 0


@dataclass
class CleanupAction:
    """Individual file resolution action."""
    path: Path
    action: str  # "KEEP" or "DELETE"
    reason: str
    size_bytes: int


@dataclass
class CleanupPlan:
    """Overall blueprint of files to keep vs delete."""
    actions: List[CleanupAction] = field(default_factory=list)
    reclaimable_bytes: int = 0
    total_files_to_delete: int = 0

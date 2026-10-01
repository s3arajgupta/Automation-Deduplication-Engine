import tempfile
from pathlib import Path
import pytest

from dedup_engine.folder_hasher import FolderDeduplicator


def test_folder_deduplicator():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Folder A: 2 files
        folder_a = root / "project_original"
        folder_a.mkdir()
        (folder_a / "README.md").write_text("# Project", encoding="utf-8")
        (folder_a / "main.py").write_text("print('hello')", encoding="utf-8")

        # Folder B: Exact clone of Folder A
        folder_b = root / "project_backup"
        folder_b.mkdir()
        (folder_b / "README.md").write_text("# Project", encoding="utf-8")
        (folder_b / "main.py").write_text("print('hello')", encoding="utf-8")

        # Folder C: Different files
        folder_c = root / "project_different"
        folder_c.mkdir()
        (folder_c / "README.md").write_text("# Other", encoding="utf-8")
        (folder_c / "main.py").write_text("print('other')", encoding="utf-8")

        deduplicator = FolderDeduplicator(min_files=2)
        folder_groups = deduplicator.scan_folders(root)

        assert len(folder_groups) == 1
        group = folder_groups[0]
        assert group.count == 2
        paths = {f.path for f in group.folders}
        assert folder_a in paths
        assert folder_b in paths
        assert folder_c not in paths
        assert group.file_count == 2

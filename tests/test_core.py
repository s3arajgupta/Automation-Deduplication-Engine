import tempfile
from pathlib import Path
import pytest

from dedup_engine.core import DuplicateScanner, hash_stream, should_ignore


def test_should_ignore():
    root = Path("/dummy/project")
    git_file = root / ".git" / "config"
    pyc_file = root / "module.pyc"
    valid_file = root / "src" / "main.py"

    patterns = [".git", "*.pyc"]
    assert should_ignore(git_file, root, patterns) is True
    assert should_ignore(pyc_file, root, patterns) is True
    assert should_ignore(valid_file, root, patterns) is False


def test_hash_stream():
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write("Hello DupFold World!")
        temp_path = Path(f.name)

    try:
        full_hash = hash_stream(temp_path, algorithm="sha256")
        assert isinstance(full_hash, str)
        assert len(full_hash) == 64

        # Prefix hash
        prefix_hash = hash_stream(temp_path, algorithm="sha256", max_bytes=5)
        assert isinstance(prefix_hash, str)
        assert prefix_hash != full_hash
    finally:
        if temp_path.exists():
            temp_path.unlink()


def test_duplicate_scanner_3stage():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Create identical files
        f1 = root / "file1.txt"
        f2 = root / "file2.txt"
        f1.write_text("Identical content in both files.", encoding="utf-8")
        f2.write_text("Identical content in both files.", encoding="utf-8")

        # Create file with SAME size but different content to test prefix/full hashing discrimination
        f3 = root / "file3.txt"
        f3.write_text("Differing content but exact size", encoding="utf-8")
        assert f1.stat().st_size == f3.stat().st_size

        # Create unique file with different size
        f4 = root / "unique.txt"
        f4.write_text("Short", encoding="utf-8")

        scanner = DuplicateScanner(algorithm="sha256")
        groups = scanner.scan_directory(root)

        assert len(groups) == 1
        group = groups[0]
        assert group.count == 2
        paths = {f.path for f in group.files}
        assert f1 in paths
        assert f2 in paths
        assert f3 not in paths
        assert f4 not in paths

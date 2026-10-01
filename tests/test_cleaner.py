import tempfile
import time
from pathlib import Path
import pytest

from dedup_engine.cleaner import CleanupEngine
from dedup_engine.models import DuplicateGroup, FileEntry, RetentionStrategy


def test_retention_strategies():
    f_old = FileEntry(path=Path("/a/old.txt"), size=100, mtime=1000.0)
    f_new = FileEntry(path=Path("/a/new.txt"), size=100, mtime=2000.0)
    f_short = FileEntry(path=Path("/a/s.txt"), size=100, mtime=1500.0)

    group = DuplicateGroup(file_hash="abc", size_per_file=100, files=[f_old, f_new, f_short])

    # Test NEWEST
    cleaner_newest = CleanupEngine(strategy=RetentionStrategy.NEWEST)
    plan = cleaner_newest.plan_cleanup([group])
    assert plan.total_files_to_delete == 2
    kept = [a for a in plan.actions if a.action == "KEEP"]
    assert kept[0].path == f_new.path

    # Test OLDEST
    cleaner_oldest = CleanupEngine(strategy=RetentionStrategy.OLDEST)
    plan_old = cleaner_oldest.plan_cleanup([group])
    kept_old = [a for a in plan_old.actions if a.action == "KEEP"]
    assert kept_old[0].path == f_old.path

    # Test SHORTEST PATH
    cleaner_short = CleanupEngine(strategy=RetentionStrategy.SHORTEST_PATH)
    plan_short = cleaner_short.plan_cleanup([group])
    kept_short = [a for a in plan_short.actions if a.action == "KEEP"]
    assert kept_short[0].path == f_short.path


def test_cleanup_execution_and_dry_run():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        f1 = root / "keep.txt"
        f2 = root / "delete.txt"
        f1.write_text("duplicate data", encoding="utf-8")
        time.sleep(0.01)
        f2.write_text("duplicate data", encoding="utf-8")

        entry1 = FileEntry(path=f1, size=f1.stat().st_size, mtime=f1.stat().st_mtime)
        entry2 = FileEntry(path=f2, size=f2.stat().st_size, mtime=f2.stat().st_mtime)
        group = DuplicateGroup(file_hash="xyz", size_per_file=entry1.size, files=[entry1, entry2])

        cleaner = CleanupEngine(strategy=RetentionStrategy.OLDEST)
        plan = cleaner.plan_cleanup([group])

        # Test Dry Run
        deleted, reclaimed, errors = cleaner.execute_plan(plan, dry_run=True)
        assert deleted == 1
        assert reclaimed == entry1.size
        assert f1.exists()
        assert f2.exists()  # Dry run should NOT touch f2

        # Test Live Execution
        deleted_live, reclaimed_live, errors_live = cleaner.execute_plan(plan, dry_run=False)
        assert deleted_live == 1
        assert f1.exists()
        assert not f2.exists()  # Live run should have removed f2

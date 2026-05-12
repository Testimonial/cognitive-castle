import os
import time
import tempfile
from cognitive_castle.palace import clean_stale_locks


def test_removes_stale_lock():
    with tempfile.TemporaryDirectory() as d:
        lock_path = os.path.join(d, "old.lock")
        open(lock_path, "w").close()
        old_time = time.time() - 90000  # 25 hours ago
        os.utime(lock_path, (old_time, old_time))
        removed, kept = clean_stale_locks(d)
        assert removed == 1
        assert kept == 0
        assert not os.path.exists(lock_path)


def test_keeps_fresh_lock():
    with tempfile.TemporaryDirectory() as d:
        lock_path = os.path.join(d, "new.lock")
        open(lock_path, "w").close()
        removed, kept = clean_stale_locks(d)
        assert removed == 0
        assert kept == 1
        assert os.path.exists(lock_path)


def test_ignores_non_lock_files():
    with tempfile.TemporaryDirectory() as d:
        other = os.path.join(d, "not-a-lock.txt")
        open(other, "w").close()
        removed, kept = clean_stale_locks(d)
        assert removed == 0
        assert kept == 0


def test_nonexistent_dir_returns_zeros():
    removed, kept = clean_stale_locks("/tmp/nonexistent_castle_locks_xyz")
    assert removed == 0
    assert kept == 0

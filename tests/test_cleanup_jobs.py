"""Tests for cleanup of expired conversion jobs and their temporary files."""

from __future__ import annotations

import threading
from pathlib import Path

from vid2gif.backend.services.file_manager import FileManager
from vid2gif.backend.services.job_store import InMemoryJobStore


def test_cleanup_jobs__removes_expired_job_and_tmp_dir(tmp_path: Path) -> None:
    """Remove expired jobs and their temporary directories."""
    job_store = InMemoryJobStore()
    file_manager = FileManager(tmp_path)

    job_id = "oldjob"
    job_dir = tmp_path / job_id
    job_dir.mkdir()
    (job_dir / "file.gif").write_text("x")

    job_store.jobs[job_id] = {"created_at": 0.0}

    file_manager.cleanup_expired_jobs(job_store, now=10.0, ttl_seconds=5.0)

    assert job_id not in job_store.jobs
    assert not job_dir.exists()


def test_cleanup_jobs__keeps_recent_job(tmp_path: Path) -> None:
    """Keep jobs that have not exceeded the TTL."""
    job_store = InMemoryJobStore()
    file_manager = FileManager(tmp_path)

    job_id = "recentjob"
    job_dir = tmp_path / job_id
    job_dir.mkdir()

    job_store.jobs[job_id] = {"created_at": 9.0}

    file_manager.cleanup_expired_jobs(job_store, now=10.0, ttl_seconds=5.0)

    assert job_id in job_store.jobs
    assert job_dir.exists()


def test_cleanup_jobs__keeps_job_with_active_lock(tmp_path: Path) -> None:
    """Keep jobs that still have an active lock."""
    job_store = InMemoryJobStore()
    file_manager = FileManager(tmp_path)

    job_id = "lockedjob"
    job_dir = tmp_path / job_id
    job_dir.mkdir()

    job_store.jobs[job_id] = {"created_at": 0.0}
    job_store.job_locks[job_id] = threading.Lock()

    file_manager.cleanup_expired_jobs(job_store, now=10.0, ttl_seconds=5.0)

    assert job_id in job_store.jobs
    assert job_dir.exists()

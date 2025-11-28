"""Tests for cleanup of expired conversion jobs and their temporary files."""

from __future__ import annotations

import threading
from pathlib import Path

from backend.app import cleanup_expired_jobs, job_locks, jobs


def test_cleanup_jobs__removes_expired_job_and_tmp_dir(tmp_path: Path) -> None:
    """Remove expired jobs and their temporary directories."""
    job_id = "oldjob"
    job_dir = tmp_path / job_id
    job_dir.mkdir()
    (job_dir / "file.gif").write_text("x")

    jobs[job_id] = {"created_at": 0.0}

    cleanup_expired_jobs(base_dir=tmp_path, now=10.0, ttl_seconds=5.0)

    assert job_id not in jobs
    assert not job_dir.exists()


def test_cleanup_jobs__keeps_recent_job(tmp_path: Path) -> None:
    """Keep jobs that have not exceeded the TTL."""
    job_id = "recentjob"
    job_dir = tmp_path / job_id
    job_dir.mkdir()

    jobs[job_id] = {"created_at": 9.0}

    cleanup_expired_jobs(base_dir=tmp_path, now=10.0, ttl_seconds=5.0)

    assert job_id in jobs
    assert job_dir.exists()


def test_cleanup_jobs__keeps_job_with_active_lock(tmp_path: Path) -> None:
    """Keep jobs that still have an active lock."""
    job_id = "lockedjob"
    job_dir = tmp_path / job_id
    job_dir.mkdir()

    jobs[job_id] = {"created_at": 0.0}
    job_locks[job_id] = threading.Lock()

    cleanup_expired_jobs(base_dir=tmp_path, now=10.0, ttl_seconds=5.0)

    assert job_id in jobs
    assert job_dir.exists()

    jobs.pop(job_id, None)
    job_locks.pop(job_id, None)

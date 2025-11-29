"""Job state management service.

Provides thread-safe storage and manipulation of conversion job state.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class JobState:
    """Immutable snapshot of a job's current state."""

    job_id: str
    total_files: int
    processed_files: int = 0
    successful_files: int = 0
    error_files: int = 0
    status: str = "initializing"
    downloads: list[dict[str, str]] = field(default_factory=list)
    current_file_index: int = 0
    current_file_percent: float = 0.0
    current_file_est_seconds: float | None = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of job state.
        """
        return {
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "successful_files": self.successful_files,
            "error_files": self.error_files,
            "status": self.status,
            "downloads": self.downloads,
            "current_file_index": self.current_file_index,
            "current_file_percent": self.current_file_percent,
            "current_file_est_seconds": self.current_file_est_seconds,
            "created_at": self.created_at,
        }


class JobStoreProtocol(Protocol):
    """Protocol for job storage implementations."""

    def create_job(self, job_id: str, total_files: int) -> threading.Lock:
        """Create a new job and return its lock."""
        ...

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Get job state as a dictionary."""
        ...

    def has_job(self, job_id: str) -> bool:
        """Check if job exists."""
        ...

    def has_lock(self, job_id: str) -> bool:
        """Check if job has an active lock."""
        ...

    def get_lock(self, job_id: str) -> threading.Lock | None:
        """Get the lock for a job."""
        ...

    def update_progress(
        self,
        job_id: str,
        file_index: int,
        percent: float,
        est_seconds: float | None,
        status: str,
    ) -> None:
        """Update file conversion progress."""
        ...

    def record_file_success(
        self,
        job_id: str,
        original_name: str,
        download_url: str,
    ) -> bool:
        """Record successful file conversion. Return True if this was the last file."""
        ...

    def record_file_error(self, job_id: str) -> bool:
        """Record file conversion error. Return True if this was the last file."""
        ...

    def finalize_job(self, job_id: str, status: str) -> None:
        """Mark job as complete and release lock."""
        ...

    def remove_job(self, job_id: str) -> None:
        """Remove job from store."""
        ...

    def list_expired_jobs(self, now: float, ttl_seconds: float) -> list[str]:
        """Return job IDs that are expired and have no active lock."""
        ...


class InMemoryJobStore:
    """Thread-safe in-memory job storage.

    This implementation stores jobs in dictionaries. For production use with
    multiple workers, consider a Redis-backed implementation.
    """

    def __init__(self) -> None:
        """Initialize empty job store."""
        self._jobs: dict[str, dict[str, Any]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._store_lock = threading.Lock()

    @property
    def jobs(self) -> dict[str, dict[str, Any]]:
        """Direct access to jobs dict for backward compatibility."""
        return self._jobs

    @property
    def job_locks(self) -> dict[str, threading.Lock]:
        """Direct access to locks dict for backward compatibility."""
        return self._locks

    def create_job(self, job_id: str, total_files: int) -> threading.Lock:
        """Create a new job and return its lock.

        Args:
            job_id: Unique identifier for the job.
            total_files: Number of files in the job.

        Returns:
            A lock for synchronizing updates to this job.
        """
        lock = threading.Lock()
        with self._store_lock:
            self._locks[job_id] = lock
            self._jobs[job_id] = {
                "total_files": total_files,
                "processed_files": 0,
                "successful_files": 0,
                "error_files": 0,
                "status": "initializing",
                "downloads": [],
                "current_file_index": 0,
                "current_file_percent": 0.0,
                "current_file_est_seconds": None,
                "created_at": time.time(),
            }
        return lock

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Get job state as a dictionary.

        Args:
            job_id: The job identifier.

        Returns:
            Job state dictionary or None if not found.
        """
        return self._jobs.get(job_id)

    def has_job(self, job_id: str) -> bool:
        """Check if job exists.

        Args:
            job_id: The job identifier.

        Returns:
            True if job exists.
        """
        return job_id in self._jobs

    def has_lock(self, job_id: str) -> bool:
        """Check if job has an active lock.

        Args:
            job_id: The job identifier.

        Returns:
            True if job has a lock (still processing).
        """
        return job_id in self._locks

    def get_lock(self, job_id: str) -> threading.Lock | None:
        """Get the lock for a job.

        Args:
            job_id: The job identifier.

        Returns:
            The job's lock or None if not found.
        """
        return self._locks.get(job_id)

    def update_progress(
        self,
        job_id: str,
        file_index: int,
        percent: float,
        est_seconds: float | None,
        status: str,
    ) -> None:
        """Update file conversion progress.

        Args:
            job_id: The job identifier.
            file_index: Current file being processed (1-based).
            percent: Completion percentage for current file.
            est_seconds: Estimated seconds remaining.
            status: Status message.
        """
        job = self._jobs.get(job_id)
        if job:
            job.update({
                "current_file_index": file_index,
                "current_file_percent": round(percent, 2),
                "current_file_est_seconds": (
                    round(est_seconds) if est_seconds is not None else None
                ),
                "status": status,
            })

    def record_file_success(
        self,
        job_id: str,
        original_name: str,
        download_url: str,
    ) -> bool:
        """Record successful file conversion.

        Args:
            job_id: The job identifier.
            original_name: Original filename.
            download_url: URL to download the converted file.

        Returns:
            True if this was the last file in the job.
        """
        job = self._jobs.get(job_id)
        if not job:
            return False

        job["processed_files"] += 1
        job["successful_files"] += 1
        job["downloads"].append({
            "original": original_name,
            "url": download_url,
        })
        return job["processed_files"] == job["total_files"]

    def record_file_error(self, job_id: str) -> bool:
        """Record file conversion error.

        Args:
            job_id: The job identifier.

        Returns:
            True if this was the last file in the job.
        """
        job = self._jobs.get(job_id)
        if not job:
            return False

        job["processed_files"] += 1
        job["error_files"] += 1
        return job["processed_files"] == job["total_files"]

    def finalize_job(self, job_id: str, status: str) -> None:
        """Mark job as complete and release lock.

        Args:
            job_id: The job identifier.
            status: Final status string.
        """
        job = self._jobs.get(job_id)
        if job:
            job.update({
                "status": status,
                "current_file_percent": 100.0,
                "current_file_est_seconds": 0,
                "current_file_index": job["total_files"],
            })
        with self._store_lock:
            self._locks.pop(job_id, None)

    def set_status(self, job_id: str, status: str) -> None:
        """Update job status.

        Args:
            job_id: The job identifier.
            status: New status string.
        """
        job = self._jobs.get(job_id)
        if job:
            job["status"] = status

    def remove_job(self, job_id: str) -> None:
        """Remove job from store.

        Args:
            job_id: The job identifier.
        """
        with self._store_lock:
            self._jobs.pop(job_id, None)
            self._locks.pop(job_id, None)

    def list_expired_jobs(self, now: float, ttl_seconds: float) -> list[str]:
        """Return job IDs that are expired and have no active lock.

        Args:
            now: Current timestamp.
            ttl_seconds: Time-to-live in seconds.

        Returns:
            List of expired job IDs.
        """
        expired: list[str] = []
        for job_id, job_data in list(self._jobs.items()):
            created_at = job_data.get("created_at")
            if created_at is None:
                continue
            if job_id in self._locks:
                continue
            if now - float(created_at) > ttl_seconds:
                expired.append(job_id)
        return expired

    def compute_final_status(self, job_id: str) -> str:
        """Compute the final status string for a completed job.

        Args:
            job_id: The job identifier.

        Returns:
            One of 'done', 'failed', or 'completed with errors (N/M successful)'.
        """
        job = self._jobs.get(job_id)
        if not job:
            return "unknown"

        total = job["total_files"]
        successful = job["successful_files"]

        if successful == total:
            return "done"
        if successful > 0:
            return f"completed with errors ({successful}/{total} successful)"
        return "failed"


# Default global instance for backward compatibility during migration
_default_store: InMemoryJobStore | None = None


def get_default_store() -> InMemoryJobStore:
    """Get or create the default global job store instance.

    Returns:
        Returns the singleton InMemoryJobStore instance, creating it on first call.
    """
    global _default_store
    if _default_store is None:
        _default_store = InMemoryJobStore()
    return _default_store

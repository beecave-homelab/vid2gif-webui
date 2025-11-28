"""Filesystem I/O for temporary files and cleanup.

Handles creation and cleanup of temporary directories and files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from vid2gif.backend.services.job_store import JobStoreProtocol


class FileManagerProtocol(Protocol):
    """Protocol for file management implementations."""

    def ensure_base_dir(self) -> None:
        """Ensure the base temporary directory exists."""
        ...

    def create_job_dir(self, job_id: str) -> Path:
        """Create a directory for a specific job.

        Args:
            job_id: The job identifier.

        Returns:
            Path to the created directory.
        """
        ...

    def write_input_file(self, job_id: str, filename: str, data: bytes) -> Path:
        """Write input file data to the job directory.

        Args:
            job_id: The job identifier.
            filename: Name of the file.
            data: File content as bytes.

        Returns:
            Path to the written file.
        """
        ...

    def get_output_path(self, job_id: str, original_name: str) -> Path:
        """Get the output path for a converted file.

        Args:
            job_id: The job identifier.
            original_name: Original input filename.

        Returns:
            Path where output should be written.
        """
        ...

    def cleanup_input_file(self, path: Path) -> None:
        """Remove an input file after processing.

        Args:
            path: Path to the file to remove.
        """
        ...

    def cleanup_expired_jobs(
        self,
        job_store: JobStoreProtocol,
        now: float,
        ttl_seconds: float,
    ) -> None:
        """Remove expired jobs and their directories.

        Args:
            job_store: Job store to query for expired jobs.
            now: Current timestamp.
            ttl_seconds: Time-to-live in seconds.
        """
        ...

    def file_exists(self, job_id: str, filename: str) -> bool:
        """Check if a file exists in a job directory.

        Args:
            job_id: The job identifier.
            filename: Name of the file.

        Returns:
            True if file exists.
        """
        ...

    def get_file_path(self, job_id: str, filename: str) -> Path:
        """Get the full path to a file in a job directory.

        Args:
            job_id: The job identifier.
            filename: Name of the file.

        Returns:
            Full path to the file.
        """
        ...


class FileManager:
    """Manage temporary files for video conversion jobs.

    Handles directory creation, file storage, and cleanup of temporary
    files used during the conversion process.
    """

    def __init__(self, base_dir: str | Path) -> None:
        """Initialize file manager.

        Args:
            base_dir: Base directory for temporary files.
        """
        self._base_dir = Path(base_dir)

    @property
    def base_dir(self) -> Path:
        """Get the base directory path.

        Returns:
            The base directory as a Path object.
        """
        return self._base_dir

    def ensure_base_dir(self) -> None:
        """Ensure the base temporary directory exists."""
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def create_job_dir(self, job_id: str) -> Path:
        """Create a directory for a specific job.

        Args:
            job_id: The job identifier.

        Returns:
            Path to the created directory.

        Note:
            May raise OSError if directory creation fails.
        """
        job_dir = self._base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        logging.info("Job %s: Created temporary directory %s", job_id, job_dir)
        return job_dir

    def write_input_file(self, job_id: str, filename: str, data: bytes) -> Path:
        """Write input file data to the job directory.

        Args:
            job_id: The job identifier.
            filename: Name of the file.
            data: File content as bytes.

        Returns:
            Path to the written file.
        """
        file_path = self._base_dir / job_id / filename
        file_path.write_bytes(data)
        logging.info("Job %s: Saved %s to %s", job_id, filename, file_path)
        return file_path

    def get_output_path(self, job_id: str, original_name: str) -> Path:
        """Get the output path for a converted file.

        Args:
            job_id: The job identifier.
            original_name: Original input filename.

        Returns:
            Path where output GIF should be written.
        """
        output_name = Path(original_name).stem + ".gif"
        return self._base_dir / job_id / output_name

    def cleanup_input_file(self, path: Path) -> None:
        """Remove an input file after processing.

        Args:
            path: Path to the file to remove.
        """
        try:
            if path.exists():
                path.unlink()
                logging.debug("Cleaned up temporary input file: %s", path)
        except OSError as e:
            logging.warning("Could not delete temporary input file %s: %s", path, e)

    def cleanup_expired_jobs(
        self,
        job_store: JobStoreProtocol,
        now: float,
        ttl_seconds: float,
    ) -> None:
        """Remove expired jobs and their directories.

        Args:
            job_store: Job store to query for expired jobs.
            now: Current timestamp.
            ttl_seconds: Time-to-live in seconds.
        """
        expired_ids = job_store.list_expired_jobs(now, ttl_seconds)

        for job_id in expired_ids:
            job_store.remove_job(job_id)
            self._remove_job_dir(job_id)

    def _remove_job_dir(self, job_id: str) -> None:
        """Remove a job's temporary directory and contents.

        Args:
            job_id: The job identifier.
        """
        job_dir = self._base_dir / job_id
        try:
            if job_dir.exists():
                for child in job_dir.iterdir():
                    try:
                        child.unlink()
                    except OSError as exc:
                        logging.warning(
                            "Job %s: Could not delete temporary file %s: %s",
                            job_id,
                            child,
                            exc,
                        )
                job_dir.rmdir()
        except OSError as exc:
            logging.warning(
                "Job %s: Could not delete temporary directory %s: %s",
                job_id,
                job_dir,
                exc,
            )

    def file_exists(self, job_id: str, filename: str) -> bool:
        """Check if a file exists in a job directory.

        Args:
            job_id: The job identifier.
            filename: Name of the file.

        Returns:
            True if file exists and is a regular file.
        """
        path = self._base_dir / job_id / filename
        return path.exists() and path.is_file()

    def get_file_path(self, job_id: str, filename: str) -> Path:
        """Get the full path to a file in a job directory.

        Args:
            job_id: The job identifier.
            filename: Name of the file.

        Returns:
            Full path to the file.
        """
        return self._base_dir / job_id / filename

"""Conversion orchestration service.

Coordinates job state, file management, and FFmpeg execution.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from vid2gif.backend.services.ffmpeg_runner import (
    ConversionParams,
    FFmpegRunner,
    ProgressInfo,
)
from vid2gif.backend.services.file_manager import FileManager
from vid2gif.backend.services.job_store import InMemoryJobStore

# Allowed scale values for validation
ALLOWED_SCALES = frozenset({
    "original",
    "320:-1",
    "360:-1",
    "480:-1",
    "720:-1",
    "1080:-1",
    "1920:-1",
    "2560:-1",
    "3840:-1",
})


def is_scale_allowed(scale: str) -> bool:
    """Return True if the provided scale value is allowed for conversions.

    Args:
        scale: Scale value to validate.

    Returns:
        True if scale is in the allowed set.
    """
    return scale in ALLOWED_SCALES


class ConversionService:
    """Orchestrates media conversion jobs.

    Coordinates between job state management, file operations, and FFmpeg
    execution. The specific conversion type (GIF, audio, etc.) is determined
    by the strategy configured in the FFmpegRunner.

    Single Responsibility: Job orchestration only. Does not know about
    conversion-specific details (those live in the strategy).
    """

    def __init__(
        self,
        job_store: InMemoryJobStore,
        file_manager: FileManager,
        ffmpeg_runner: FFmpegRunner,
        *,
        ttl_seconds: float = 3600.0,
    ) -> None:
        """Initialize conversion service.

        Args:
            job_store: Storage for job state.
            file_manager: Handler for file operations.
            ffmpeg_runner: Handler for FFmpeg execution.
            ttl_seconds: Time-to-live for jobs in seconds.
        """
        self._job_store = job_store
        self._file_manager = file_manager
        self._ffmpeg_runner = ffmpeg_runner
        self._ttl_seconds = ttl_seconds

    @property
    def job_store(self) -> InMemoryJobStore:
        """Get the job store.

        Returns:
            The job store instance.
        """
        return self._job_store

    @property
    def file_manager(self) -> FileManager:
        """Get the file manager.

        Returns:
            The file manager instance.
        """
        return self._file_manager

    def cleanup_expired_jobs(self, now: float | None = None) -> None:
        """Remove expired jobs and their temporary directories.

        Args:
            now: Current timestamp (defaults to time.time()).
        """
        current_time = now if now is not None else time.time()
        self._file_manager.cleanup_expired_jobs(
            self._job_store,
            current_time,
            self._ttl_seconds,
        )

    def create_job(self, job_id: str, total_files: int) -> threading.Lock:
        """Create a new conversion job.

        Args:
            job_id: Unique identifier for the job.
            total_files: Number of files in the job.

        Returns:
            Lock for synchronizing job updates.
        """
        self._file_manager.create_job_dir(job_id)
        return self._job_store.create_job(job_id, total_files)

    def get_job(self, job_id: str) -> dict | None:
        """Get job state.

        Args:
            job_id: The job identifier.

        Returns:
            Job state dictionary or None if not found.
        """
        return self._job_store.get_job(job_id)

    def set_job_status(self, job_id: str, status: str) -> None:
        """Update job status.

        Args:
            job_id: The job identifier.
            status: New status string.
        """
        self._job_store.set_status(job_id, status)

    def process_file(
        self,
        job_id: str,
        lock: threading.Lock,
        original_name: str,
        file_bytes: bytes | None,
        *,
        input_path: Path | None = None,
        scale: str,
        fps: int,
        start_time_sec: float,
        end_time_sec: float,
        file_index: int,
        total_files: int,
    ) -> None:
        """Process a single video file for conversion.

        Args:
            job_id: The job identifier.
            lock: Thread lock for synchronizing job state updates.
            original_name: Original filename of the video.
            file_bytes: Raw bytes of the video file. Optional when input_path is provided.
            input_path: Existing path on disk for the uploaded file. If provided, the
                file will not be rewritten from bytes.
            scale: Scale factor (e.g., "320:-1") or "original".
            fps: Frames per second for output.
            start_time_sec: Start time in seconds for trimming.
            end_time_sec: End time in seconds for trimming.
            file_index: Index of current file (1-based).
            total_files: Total number of files in the job.

        Raises:
            ValueError: If ``file_bytes`` is absent when no ``input_path`` is supplied.
        """
        logging.info(
            "Job %s: Starting file %d/%d: %s (Trim: %.2fs to %.2fs, Scale: %s, FPS: %d)",
            job_id,
            file_index,
            total_files,
            original_name,
            start_time_sec,
            end_time_sec,
            scale,
            fps,
        )

        input_filename = f"{file_index}_{original_name}"
        resolved_input_path: Path | None = None

        try:
            if input_path:
                resolved_input_path = input_path
            else:
                if file_bytes is None:
                    msg = "file_bytes must be provided when input_path is not set"
                    raise ValueError(msg)
                resolved_input_path = self._file_manager.write_input_file(
                    job_id, input_filename, file_bytes
                )
            output_ext = self._ffmpeg_runner.strategy.output_extension
            output_path = self._file_manager.get_output_path(job_id, original_name, output_ext)

            params = ConversionParams(
                input_path=resolved_input_path,
                output_path=output_path,
                scale=scale,
                fps=fps,
                start_time_sec=start_time_sec,
                end_time_sec=end_time_sec,
            )

            def on_progress(progress: ProgressInfo) -> None:
                with lock:
                    if not self._job_store.has_job(job_id):
                        return
                    self._job_store.update_progress(
                        job_id,
                        file_index,
                        progress.percent,
                        progress.est_seconds_remaining,
                        f"Converting file {file_index}/{total_files} ({original_name})...",
                    )

            success = self._ffmpeg_runner.run_conversion(params, on_progress)

            with lock:
                if not self._job_store.has_job(job_id):
                    return

                if success:
                    output_ext = self._ffmpeg_runner.strategy.output_extension
                    output_name = Path(original_name).stem + output_ext
                    download_url = f"/download/{job_id}/{output_name}"
                    is_last = self._job_store.record_file_success(
                        job_id, original_name, download_url
                    )
                else:
                    is_last = self._job_store.record_file_error(job_id)

                log_level = logging.INFO if success else logging.ERROR
                logging.log(
                    log_level,
                    "Job %s: File %d: ffmpeg finished for %s with %s. Output: %s",
                    job_id,
                    file_index,
                    original_name,
                    "success" if success else "error",
                    output_path,
                )

                if is_last:
                    final_status = self._job_store.compute_final_status(job_id)
                    self._job_store.finalize_job(job_id, final_status)
                    logging.info(
                        "Job %s: All files processed. Final status: %s",
                        job_id,
                        final_status,
                    )
                else:
                    job = self._job_store.get_job(job_id)
                    if job:
                        self._job_store.set_status(
                            job_id,
                            f"Processed {job['processed_files']}/{total_files} files...",
                        )

        except Exception as e:
            logging.error(
                "Job %s: File %d: Unhandled error processing %s: %s",
                job_id,
                file_index,
                original_name,
                e,
                exc_info=True,
            )
            with lock:
                if not self._job_store.has_job(job_id):
                    return

                is_last = self._job_store.record_file_error(job_id)
                if is_last:
                    final_status = self._job_store.compute_final_status(job_id)
                    self._job_store.finalize_job(job_id, final_status)
                    logging.info(
                        "Job %s: Finished (error on last file). Final status: %s",
                        job_id,
                        final_status,
                    )
                else:
                    job = self._job_store.get_job(job_id)
                    if job:
                        self._job_store.set_status(
                            job_id,
                            f"Error on file {file_index}. "
                            f"Processed {job['processed_files']}/{total_files}...",
                        )

        finally:
            if resolved_input_path:
                self._file_manager.cleanup_input_file(resolved_input_path)

    def record_skip_error(
        self,
        job_id: str,
        lock: threading.Lock,
        total_files: int,
    ) -> None:
        """Record an error for a file that was skipped due to validation.

        Args:
            job_id: The job identifier.
            lock: Thread lock for synchronizing job state updates.
            total_files: Total number of files in the job.
        """
        with lock:
            is_last = self._job_store.record_file_error(job_id)
            if is_last:
                final_status = self._job_store.compute_final_status(job_id)
                self._job_store.finalize_job(job_id, final_status)

    def file_exists(self, job_id: str, filename: str) -> bool:
        """Check if a file exists in a job directory.

        Args:
            job_id: The job identifier.
            filename: Name of the file.

        Returns:
            True if file exists.
        """
        return self._file_manager.file_exists(job_id, filename)

    def get_file_path(self, job_id: str, filename: str) -> Path:
        """Get the full path to a file in a job directory.

        Args:
            job_id: The job identifier.
            filename: Name of the file.

        Returns:
            Full path to the file.
        """
        return self._file_manager.get_file_path(job_id, filename)

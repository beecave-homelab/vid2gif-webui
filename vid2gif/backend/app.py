"""Backend FastAPI application for the Video to GIF conversion service.

This module provides a thin HTTP layer over the conversion service.
Business logic is delegated to the services layer.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from vid2gif.backend.services.conversion import ConversionService, is_scale_allowed
from vid2gif.backend.services.ffmpeg_runner import FFmpegRunner
from vid2gif.backend.services.file_manager import FileManager
from vid2gif.backend.services.job_store import InMemoryJobStore
from vid2gif.backend.utils.constant import (
    FFMPEG_MAX_CONCURRENT,
    JOB_TTL_SECONDS,
    TMP_BASE_DIR,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Service layer setup ---
# Create service instances with dependency injection
_job_store = InMemoryJobStore()
_file_manager = FileManager(TMP_BASE_DIR)
_ffmpeg_semaphore = threading.Semaphore(FFMPEG_MAX_CONCURRENT)
_ffmpeg_runner = FFmpegRunner(semaphore=_ffmpeg_semaphore)
_conversion_service = ConversionService(
    job_store=_job_store,
    file_manager=_file_manager,
    ffmpeg_runner=_ffmpeg_runner,
    ttl_seconds=float(JOB_TTL_SECONDS),
)

# Backward-compatible references for existing tests
jobs = _job_store.jobs
job_locks = _job_store.job_locks
FFMPEG_SEMAPHORE = _ffmpeg_semaphore

# Expose TMP_BASE_DIR dynamically via property for test compatibility
TMP_BASE_DIR = TMP_BASE_DIR  # noqa: PLW0127 - Re-export for backward compat

# Ensure tmp directory exists
_file_manager.ensure_base_dir()

app = FastAPI()


def run_with_ffmpeg_semaphore(task: Any) -> None:  # noqa: ANN401
    """Run a task while respecting the global ffmpeg concurrency semaphore.

    Deprecated: Use FFmpegRunner with semaphore instead.

    Args:
        task: Callable to execute.
    """
    FFMPEG_SEMAPHORE.acquire()
    try:
        task()
    finally:
        FFMPEG_SEMAPHORE.release()


def cleanup_expired_jobs(
    base_dir: str | None = None,  # noqa: ARG001 - kept for backward compatibility
    *,
    now: float | None = None,
    ttl_seconds: float | None = None,  # noqa: ARG001 - kept for backward compatibility
) -> None:
    """Remove expired jobs and their corresponding temporary directories.

    Deprecated: Use ConversionService.cleanup_expired_jobs instead.

    Args:
        base_dir: Ignored, kept for backward compatibility.
        now: Current timestamp.
        ttl_seconds: Ignored, kept for backward compatibility.
    """
    _conversion_service.cleanup_expired_jobs(now=now)


def process_job_file(
    job_id: str,
    lock: threading.Lock,
    original_name: str,
    file_bytes: bytes,
    scale: str,
    fps: int,
    start_time_sec: float,
    end_time_sec: float,
    file_index: int,
    total_files: int,
) -> None:
    """Process a single video file for conversion within a larger job.

    Deprecated: Use ConversionService.process_file instead.

    Args:
        job_id: The unique identifier for the job.
        lock: Thread lock for synchronizing job state updates.
        original_name: The original filename of the video.
        file_bytes: The raw bytes of the video file.
        scale: The scaling factor (e.g., "320:-1") or "original".
        fps: The frames per second for the output GIF.
        start_time_sec: The start time in seconds for trimming.
        end_time_sec: The end time in seconds for trimming.
        file_index: The index of the current file in the job (1-based).
        total_files: The total number of files in the job.
    """
    _conversion_service.process_file(
        job_id=job_id,
        lock=lock,
        original_name=original_name,
        file_bytes=file_bytes,
        scale=scale,
        fps=fps,
        start_time_sec=start_time_sec,
        end_time_sec=end_time_sec,
        file_index=file_index,
        total_files=total_files,
    )


@app.post("/convert")
async def convert(
    files: list[UploadFile] = File(...),
    scale: str = Form("original"),
    fps: int = Form(10, ge=1, le=20),
    start_times: list[str] = Form(...),
    end_times: list[str] = Form(...),
) -> dict[str, str]:
    """Accept video files, scale, fps, start/end times and start background conversion.

    Args:
        files: List of video files to convert.
        scale: Scaling factor or "original".
        fps: Frames per second.
        start_times: List of start times (seconds) corresponding to each file.
        end_times: List of end times (seconds) corresponding to each file.

    Returns:
        A dictionary containing the job ID.

    Raises:
        HTTPException: If no files are provided, if input lists have mismatched lengths,
            or if the requested scale is invalid.
        ValueError: If start/end times are invalid or cannot be parsed.
    """
    job_id = str(uuid.uuid4())
    num_files = len(files)
    logging.info(
        f"Received /convert request, scale='{scale}', fps={fps}, {num_files} file(s). "
        f"Assigned job_id: {job_id}"
    )

    # Validation
    if num_files == 0:
        raise HTTPException(status_code=400, detail="No files provided.")
    if len(start_times) != num_files or len(end_times) != num_files:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Mismatch between number of files ({num_files}), "
                f"start_times ({len(start_times)}), and end_times ({len(end_times)})."
            ),
        )

    if not is_scale_allowed(scale):
        raise HTTPException(status_code=400, detail=f"Invalid scale value: {scale}")

    # Opportunistic cleanup of expired jobs and temp files
    _conversion_service.cleanup_expired_jobs()

    # Create job and initialize state
    try:
        job_lock = _conversion_service.create_job(job_id, num_files)
    except OSError as e:
        logging.error("Job %s: Failed to create job: %s", job_id, e)
        raise HTTPException(status_code=500, detail="Failed to create temporary storage.")

    # Process each file
    for i, file in enumerate(files):
        try:
            start_time_sec = float(start_times[i])
            end_time_sec = float(end_times[i])
            if start_time_sec < 0 or end_time_sec < 0 or end_time_sec <= start_time_sec:
                raise ValueError(
                    f"Invalid start/end time for file {i + 1}: "
                    f"start={start_time_sec}, end={end_time_sec}"
                )

            contents = await file.read()
            logging.info(
                f"Job {job_id}: Read {len(contents)} bytes for file {i + 1}: {file.filename}"
            )

            # Launch background thread for this specific file, passing fps
            threading.Thread(
                target=process_job_file,
                args=(
                    job_id,
                    job_lock,
                    file.filename,
                    contents,
                    scale,
                    fps,
                    start_time_sec,
                    end_time_sec,
                    i + 1,  # file index (1-based)
                    num_files,
                ),
                daemon=True,
            ).start()

        except ValueError as e:
            logging.error(
                "Job %s: Invalid time value for file %d (%s): %s. Skipping file.",
                job_id,
                i + 1,
                file.filename,
                e,
            )
            _conversion_service.record_skip_error(job_id, job_lock, num_files)

        except Exception as e:
            logging.error(
                "Job %s: Failed to start processing for file %d (%s): %s",
                job_id,
                i + 1,
                file.filename,
                e,
                exc_info=True,
            )
            _conversion_service.record_skip_error(job_id, job_lock, num_files)

    # Update status after attempting to launch all threads
    job = _conversion_service.get_job(job_id)
    if job and job["processed_files"] < num_files:
        _conversion_service.set_job_status(job_id, "processing")

    logging.info(f"Job {job_id}: Launched processing threads for {num_files} files.")
    return {"job_id": job_id}


@app.get("/progress")
def get_progress(job_id: str) -> dict[str, Any]:
    """Return the current progress status of a conversion job.

    Args:
        job_id: The unique identifier for the job.

    Returns:
        A dictionary containing the job status, or a JSONResponse with an error if not found.
    """
    # No lock needed for read, but be mindful of potential race conditions if keys are added/removed
    # during read. Getting the whole dict is generally safe enough.
    job = _conversion_service.get_job(job_id)
    if not job:
        logging.warning("Progress request for invalid job_id: %s", job_id)
        return JSONResponse({"error": "Invalid job_id"}, status_code=404)
    return job


@app.get("/download/{job_id}/{gif_filename}")
def download(job_id: str, gif_filename: str) -> Response:
    """Serve the generated GIF file for download.

    Args:
        job_id: The unique identifier for the job.
        gif_filename: The name of the GIF file to download.

    Returns:
        A FileResponse containing the GIF file, or a JSONResponse with an error.
    """
    # Construct path using the job-specific sub-directory
    # Basic security checks: Prevent directory traversal via job_id or filename
    if not job_id or ".." in job_id or "/" in job_id or "\\" in job_id:
        logging.warning(f"Download request blocked for potentially unsafe job_id: {job_id}")
        return JSONResponse({"error": "Invalid job_id"}, status_code=400)

    if not gif_filename or ".." in gif_filename or "/" in gif_filename or "\\" in gif_filename:
        logging.warning(
            "Download request blocked for potentially unsafe filename: %s", gif_filename
        )
        return JSONResponse({"error": "Invalid filename"}, status_code=400)

    if not _conversion_service.file_exists(job_id, gif_filename):
        logging.warning(
            "Download request failed: File not found for job %s, file %s",
            job_id,
            gif_filename,
        )
        return JSONResponse({"error": "File not found or job invalid"}, status_code=404)

    path = _conversion_service.get_file_path(job_id, gif_filename)
    logging.info("Serving file %s for download", path)
    return FileResponse(path, media_type="image/gif", filename=gif_filename)


# Serve the frontend
app.mount("/", StaticFiles(directory="vid2gif/frontend", html=True), name="frontend")

"""Backend FastAPI application for the Video to GIF conversion service."""

from __future__ import annotations

import logging
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .utils.constant import FFMPEG_MAX_CONCURRENT, JOB_TTL_SECONDS, TMP_BASE_DIR

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI()
# In-memory job store and locks
jobs: dict[str, dict[str, Any]] = {}
job_locks: dict[str, threading.Lock] = {}
FFMPEG_SEMAPHORE = threading.Semaphore(FFMPEG_MAX_CONCURRENT)

# Ensure tmp directory exists
Path(TMP_BASE_DIR).mkdir(parents=True, exist_ok=True)


def is_scale_allowed(scale: str) -> bool:
    """Return True if the provided scale value is allowed for conversions."""
    allowed_scales = {
        "original",
        "320:-1",
        "360:-1",
        "480:-1",
        "720:-1",
        "1080:-1",
        "1920:-1",
        "2560:-1",
        "3840:-1",
    }
    return scale in allowed_scales


def run_with_ffmpeg_semaphore(task: Callable[[], None]) -> None:
    """Run a task while respecting the global ffmpeg concurrency semaphore."""
    FFMPEG_SEMAPHORE.acquire()
    try:
        task()
    finally:
        FFMPEG_SEMAPHORE.release()


def cleanup_expired_jobs(
    base_dir: str | Path = TMP_BASE_DIR,
    *,
    now: float | None = None,
    ttl_seconds: float | None = None,
) -> None:
    """Remove expired jobs and their corresponding temporary directories."""
    current_time = now if now is not None else time.time()
    ttl = ttl_seconds if ttl_seconds is not None else float(JOB_TTL_SECONDS)
    base_path = Path(base_dir)

    expired_ids: list[str] = []
    for job_id, job_data in list(jobs.items()):
        created_at = job_data.get("created_at")
        if created_at is None:
            continue

        if job_locks.get(job_id) is not None:
            continue

        if current_time - float(created_at) > ttl:
            expired_ids.append(job_id)

    for job_id in expired_ids:
        jobs.pop(job_id, None)
        job_locks.pop(job_id, None)
        job_dir = base_path / job_id
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
    logging.info(
        f"Job {job_id}: Starting processing file {file_index}/{total_files}: {original_name} "
        f"(Trim: {start_time_sec:.2f}s to {end_time_sec:.2f}s, Scale: {scale}, FPS: {fps})"
    )

    tmp_dir = Path(TMP_BASE_DIR) / job_id
    # Note: tmp_dir is created in the /convert endpoint now

    # Ensure unique input names if needed
    input_path = tmp_dir / f"{file_index}_{original_name}"
    output_name = Path(original_name).stem + ".gif"
    output_path = tmp_dir / output_name

    clip_duration = max(0.01, end_time_sec - start_time_sec)  # Ensure non-zero duration

    try:
        # Write the bytes
        input_path.write_bytes(file_bytes)
        logging.info(f"Job {job_id}: File {file_index}: Saved {original_name} to {input_path}")

        # Optional: Run ffprobe just to check validity if needed, but duration comes from user
        # ffprobe_cmd = ["ffprobe", "-v", "error", input_path]
        # probe_res = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=False)
        # if probe_res.returncode != 0:
        #     raise ValueError(f"ffprobe validation failed: {probe_res.stderr}")

        # --- Prepare ffmpeg filters ---
        filters = []
        filters.append(f"fps={fps}")  # Always apply FPS filter first

        if scale != "original":
            # Apply scaling only if a specific scale is chosen
            scale_filter_str = f"scale={scale}:flags=lanczos"
            filters.append(scale_filter_str)
        # Else (scale == "original"), no scaling filter is added

        # Add palette filters
        filters.append("split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse")

        # Join all filters with commas
        vf_filter = ",".join(filters)

        # Use -ss before -i for fast seek, -to after -i for accurate end time
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start_time_sec),  # Start time seek (fast)
            "-i",
            str(input_path),
            "-to",
            str(end_time_sec),  # End time (accurate)
            "-vf",
            vf_filter,
            "-loop",
            "0",
            str(output_path),
        ]
        logging.info(f"Job {job_id}: File {file_index}: Running ffmpeg: {' '.join(ffmpeg_cmd)}")

        conversion_start_time = time.time()

        def ffmpeg_task() -> None:
            proc = subprocess.Popen(
                ffmpeg_cmd,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            # --- Parse progress from stderr ---
            if proc.stderr:
                for line in proc.stderr:
                    if "time=" in line:
                        try:
                            t_str = line.split("time=")[1].split()[0]
                            h, m, s_part = t_str.split(":")
                            # elapsed_video is relative to the START of the *output* stream
                            # For percentage, we compare against the desired clip duration
                            elapsed_output_time = int(h) * 3600 + int(m) * 60 + float(s_part)
                            pct = (
                                min((elapsed_output_time / clip_duration) * 100.0, 100.0)
                                if clip_duration > 0
                                else 0.0
                            )
                            elapsed_wall = time.time() - conversion_start_time
                            est_remain = (
                                (elapsed_wall / pct) * (100.0 - pct)
                                if pct > 0 and pct < 100
                                else None
                            )

                            with lock:
                                if job_id in jobs:  # Check if job wasn't cancelled/deleted
                                    jobs[job_id].update({
                                        # Keep overall job file progress,
                                        # but update current file details
                                        "current_file_index": file_index,
                                        "current_file_percent": round(pct, 2),
                                        "current_file_est_seconds": (
                                            round(est_remain) if est_remain is not None else None
                                        ),
                                        "status": (
                                            f"Converting file {file_index}/"
                                            f"{total_files} ({original_name})..."
                                        ),
                                    })
                        except Exception as e:  # noqa: BLE001
                            logging.warning(
                                f"Job {job_id}: File {file_index}: "
                                f"Error parsing ffmpeg progress line: "
                                f"'{line.strip()}' - {e}"
                            )

            # --- Wait for ffmpeg and check result ---
            return_code = proc.wait()
            success = return_code == 0
            log_level = logging.INFO if success else logging.ERROR
            logging.log(
                log_level,
                f"Job {job_id}: File {file_index}: ffmpeg finished for {original_name} "
                f"with code {return_code}. Output: {output_path}",
            )

            # --- Update final job status (under lock) ---
            with lock:
                if job_id not in jobs:
                    return  # Job might have been deleted

                jobs[job_id]["processed_files"] += 1
                is_last_file = jobs[job_id]["processed_files"] == total_files

                if success:
                    jobs[job_id]["successful_files"] += 1
                    jobs[job_id]["downloads"].append({
                        "original": original_name,
                        "url": f"/download/{job_id}/{output_name}",
                    })
                else:
                    jobs[job_id]["error_files"] += 1

                # Update status only if this is the last file
                if is_last_file:
                    if jobs[job_id]["successful_files"] == total_files:
                        final_status = "done"
                    elif jobs[job_id]["successful_files"] > 0:
                        final_status = (
                            f"completed with errors "
                            f"({jobs[job_id]['successful_files']}/{total_files} successful)"
                        )
                    else:
                        final_status = "failed"

                    logging.info(f"Job {job_id}: All files processed. Final status: {final_status}")
                    jobs[job_id].update({
                        "status": final_status,
                        "current_file_percent": 100.0,  # Mark final percentage
                        "current_file_est_seconds": 0,
                        "current_file_index": total_files,  # Ensure index shows completion
                    })
                    # Clean up lock
                    if job_id in job_locks:
                        del job_locks[job_id]
                else:
                    # Update status to show progress if not last file
                    jobs[job_id]["status"] = (
                        f"Processed {jobs[job_id]['processed_files']}/{total_files} files..."
                    )

        run_with_ffmpeg_semaphore(ffmpeg_task)

    except Exception as e:
        logging.error(
            f"Job {job_id}: File {file_index}: Unhandled error processing file "
            f"{original_name}: {e}",
            exc_info=True,
        )
        # Ensure job state reflects the failure even on unexpected exceptions
        with lock:
            if job_id in jobs:
                jobs[job_id]["processed_files"] += 1
                jobs[job_id]["error_files"] += 1
                is_last_file = jobs[job_id]["processed_files"] == total_files
                if is_last_file:
                    # Determine final status as above
                    final_status = "unknown"
                    if (
                        jobs[job_id]["successful_files"] == total_files
                    ):  # Should be 0 if we got here
                        final_status = "done"  # Should not happen
                    elif jobs[job_id]["successful_files"] > 0:
                        final_status = (
                            f"completed with errors "
                            f"({jobs[job_id]['successful_files']}/{total_files} successful)"
                        )
                    else:
                        final_status = "failed"
                    jobs[job_id]["status"] = final_status
                    logging.info(
                        f"Job {job_id}: Finished processing (due to error on last file). "
                        f"Final status: {final_status}"
                    )
                    if job_id in job_locks:
                        del job_locks[job_id]  # Cleanup lock
                else:
                    jobs[job_id]["status"] = (
                        f"Error on file {file_index}. "
                        f"Processed {jobs[job_id]['processed_files']}/{total_files}..."
                    )

    finally:
        # Attempt to clean up the input file regardless of success/failure
        try:
            if input_path.exists():
                input_path.unlink()
                logging.debug(
                    f"Job {job_id}: File {file_index}: "
                    f"Cleaned up temporary input file: {input_path}"
                )
        except OSError as e:
            logging.warning(
                f"Job {job_id}: File {file_index}: Could not delete temporary input file "
                f"{input_path}: {e}"
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
    cleanup_expired_jobs()

    # Create job directory
    job_tmp_dir = Path(TMP_BASE_DIR) / job_id
    try:
        job_tmp_dir.mkdir(parents=True, exist_ok=True)
        logging.info(f"Job {job_id}: Created temporary directory {job_tmp_dir}")
    except OSError as e:
        logging.error(f"Job {job_id}: Failed to create temporary directory {job_tmp_dir}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create temporary storage.")

    # Initialize job state and lock
    job_lock = threading.Lock()
    job_locks[job_id] = job_lock
    created_at = time.time()
    jobs[job_id] = {
        "total_files": num_files,
        "processed_files": 0,
        "successful_files": 0,
        "error_files": 0,
        "status": "initializing",
        "downloads": [],
        "current_file_index": 0,
        "current_file_percent": 0.0,
        "current_file_est_seconds": None,
        "created_at": created_at,
    }

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
                f"Job {job_id}: Invalid time value for file {i + 1} ({file.filename}): {e}. "
                "Skipping file."
            )
            # How to handle this? We need to update job state correctly even for skipped files.
            with job_lock:
                jobs[job_id]["processed_files"] += 1
                jobs[job_id]["error_files"] += 1
                # Check if this was the last file and update final status if needed
                if jobs[job_id]["processed_files"] == num_files:
                    # Simplified final status check here
                    final_status = (
                        "failed"
                        if jobs[job_id]["successful_files"] == 0
                        else "completed with errors"
                    )
                    jobs[job_id]["status"] = final_status
                    if job_id in job_locks:
                        del job_locks[job_id]  # Cleanup lock

        except Exception as e:
            logging.error(
                f"Job {job_id}: Failed to start processing for file {i + 1} ({file.filename}): {e}",
                exc_info=True,
            )
            with job_lock:
                jobs[job_id]["processed_files"] += 1
                jobs[job_id]["error_files"] += 1
                # Check if this was the last file and update final status
                # if needed (similar to above)
                if jobs[job_id]["processed_files"] == num_files:
                    final_status = (
                        "failed"
                        if jobs[job_id]["successful_files"] == 0
                        else "completed with errors"
                    )
                    jobs[job_id]["status"] = final_status
                    if job_id in job_locks:
                        del job_locks[job_id]  # Cleanup lock

    # Update status after attempting to launch all threads
    with job_lock:
        # Only update to 'processing' if no errors occurred during launch
        # causing premature completion
        if jobs[job_id]["processed_files"] < num_files:
            jobs[job_id]["status"] = "processing"

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
    job = jobs.get(job_id)
    if not job:
        logging.warning(f"Progress request for invalid job_id: {job_id}")
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
        logging.warning(f"Download request blocked for potentially unsafe filename: {gif_filename}")
        return JSONResponse({"error": "Invalid filename"}, status_code=400)

    path = Path(TMP_BASE_DIR) / job_id / gif_filename
    logging.info(
        f"Received /download request for job {job_id}, file {gif_filename}. Checking path: {path}"
    )

    if not path.exists() or not path.is_file():
        logging.warning(f"Download request failed: File not found at {path}")
        return JSONResponse({"error": "File not found or job invalid"}, status_code=404)

    # Extract original base name for download filename suggestion
    download_filename = gif_filename
    logging.info(f"Serving file {path} for download as {download_filename}")
    return FileResponse(path, media_type="image/gif", filename=download_filename)


# Serve the frontend
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

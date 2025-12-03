"""Additional tests for backend.app endpoints and job processing."""

from __future__ import annotations

import asyncio
import io
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.responses import JSONResponse

from vid2gif.backend import app


def test_convert__rejects_empty_files_list() -> None:
    """Raise HTTPException 400 when no files are provided."""

    async def call_convert() -> None:
        with pytest.raises(HTTPException) as exc_info:
            await app.convert(
                files=[],
                scale="original",
                fps=10,
                start_times=[],
                end_times=[],
            )

        assert exc_info.value.status_code == 400
        assert "no files" in exc_info.value.detail.lower()

    asyncio.run(call_convert())


def test_convert__rejects_mismatched_times_lengths() -> None:
    """Raise HTTPException 400 when times list lengths do not match files."""
    upload = UploadFile(file=io.BytesIO(b"data"), filename="test.mp4")

    async def call_convert() -> None:
        with pytest.raises(HTTPException) as exc_info:
            await app.convert(
                files=[upload],
                scale="original",
                fps=10,
                start_times=["0.0"],
                end_times=[],
            )

        assert exc_info.value.status_code == 400
        assert "mismatch" in exc_info.value.detail.lower()

    asyncio.run(call_convert())


def test_get_progress__returns_404_for_unknown_job_id() -> None:
    """Return error JSONResponse when job_id does not exist."""
    response = app.get_progress(job_id="missing")

    assert isinstance(response, JSONResponse)
    assert response.status_code == 404
    assert b"invalid job_id" in response.body.lower()


def test_get_progress__returns_job_state_for_existing_job() -> None:
    """Return stored job state when job_id exists."""
    job_id = "some-job-id"
    app.jobs[job_id] = {"status": "processing", "total_files": 1}

    try:
        result = app.get_progress(job_id=job_id)
        assert isinstance(result, dict)
        assert result["status"] == "processing"
    finally:
        app.jobs.pop(job_id, None)


def test_download__rejects_unsafe_job_id() -> None:
    """Return 400 JSONResponse when job_id contains unsafe path segments."""
    response = app.download(job_id="../escape", gif_filename="file.gif")

    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
    assert b"invalid job_id" in response.body.lower()


def test_download__rejects_unsafe_filename() -> None:
    """Return 400 JSONResponse when filename contains unsafe path segments."""
    response = app.download(job_id="job1", gif_filename="../file.gif")

    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
    assert b"invalid filename" in response.body.lower()


def test_download__returns_404_when_file_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return 404 JSONResponse when target GIF file is missing."""
    monkeypatch.setattr(app._file_manager, "_base_dir", tmp_path)

    response = app.download(job_id="job1", gif_filename="missing.gif")

    assert isinstance(response, JSONResponse)
    assert response.status_code == 404
    assert b"file not found" in response.body.lower()


def test_download__returns_file_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Serve an existing GIF file from the expected tmp directory."""
    monkeypatch.setattr(app._file_manager, "_base_dir", tmp_path)

    job_id = "job-download"
    filename = "out.gif"
    job_dir = tmp_path / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / filename).write_bytes(b"gif-data")

    response = app.download(job_id=job_id, gif_filename=filename)

    assert response.status_code == 200
    assert response.media_type == "image/gif"


def test_process_job_file__records_success_and_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Record successful processing of a single file and add download entry."""
    monkeypatch.setattr(app._file_manager, "_base_dir", tmp_path)

    job_id = "jobproc"
    app.jobs[job_id] = {
        "processed_files": 0,
        "successful_files": 0,
        "error_files": 0,
        "downloads": [],
        "status": "initializing",
        "total_files": 1,
    }

    job_tmp_dir = tmp_path / job_id
    job_tmp_dir.mkdir(parents=True, exist_ok=True)

    lock = threading.Lock()
    app.job_locks[job_id] = lock

    # Mock FFmpegRunner to return success
    def fake_run_conversion(
        params: Any,
        on_progress: Any = None,  # noqa: ANN401
    ) -> bool:
        # Simulate progress callback
        if on_progress:
            from vid2gif.backend.services.ffmpeg_runner import ProgressInfo

            on_progress(ProgressInfo(percent=50.0, est_seconds_remaining=1.0))
            on_progress(ProgressInfo(percent=100.0, est_seconds_remaining=0.0))
        return True

    monkeypatch.setattr(app._ffmpeg_runner, "run_conversion", fake_run_conversion)

    try:
        app.process_job_file(
            job_id=job_id,
            lock=lock,
            original_name="video.mp4",
            file_bytes=b"dummy",
            scale="original",
            fps=10,
            start_time_sec=0.0,
            end_time_sec=1.0,
            file_index=1,
            total_files=1,
        )

        job_state = app.jobs[job_id]
        assert job_state["processed_files"] == 1
        assert job_state["successful_files"] == 1
        assert job_state["status"] == "done"
        assert job_state["downloads"]
        assert job_state["downloads"][0]["url"].endswith(".gif")
        assert job_id not in app.job_locks
    finally:
        app.jobs.pop(job_id, None)
        app.job_locks.pop(job_id, None)


def test_process_job_file__handles_scaled_variant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handle a job where a non-original scale is requested."""
    monkeypatch.setattr(app._file_manager, "_base_dir", tmp_path)

    job_id = "jobproc-scale"
    app.jobs[job_id] = {
        "processed_files": 0,
        "successful_files": 0,
        "error_files": 0,
        "downloads": [],
        "status": "initializing",
        "total_files": 1,
    }

    job_tmp_dir = tmp_path / job_id
    job_tmp_dir.mkdir(parents=True, exist_ok=True)

    lock = threading.Lock()
    app.job_locks[job_id] = lock

    def fake_run_conversion(
        params: Any,
        on_progress: Any = None,  # noqa: ANN401
    ) -> bool:
        return True

    monkeypatch.setattr(app._ffmpeg_runner, "run_conversion", fake_run_conversion)

    try:
        app.process_job_file(
            job_id=job_id,
            lock=lock,
            original_name="video.mp4",
            file_bytes=b"dummy",
            scale="320:-1",
            fps=10,
            start_time_sec=0.0,
            end_time_sec=1.0,
            file_index=1,
            total_files=1,
        )

        job_state = app.jobs[job_id]
        assert job_state["processed_files"] == 1
        assert job_state["successful_files"] == 1
    finally:
        app.jobs.pop(job_id, None)
        app.job_locks.pop(job_id, None)


def test_convert__creates_job_and_starts_processing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create a job and start background processing threads for valid input."""
    import time

    from starlette.testclient import TestClient

    monkeypatch.setattr(app._file_manager, "_base_dir", tmp_path)

    # Mock process_job_file to immediately mark job complete
    def fake_process_job_file(
        job_id: str,
        lock: threading.Lock,
        original_name: str,
        file_bytes: bytes | None,  # noqa: ARG001
        scale: str,  # noqa: ARG001
        fps: int,  # noqa: ARG001
        start_time_sec: float,  # noqa: ARG001
        end_time_sec: float,  # noqa: ARG001
        file_index: int,  # noqa: ARG001
        total_files: int,
        *,
        input_path: Path | None = None,  # noqa: ARG001
    ) -> None:
        with lock:
            job = app.jobs[job_id]
            job["processed_files"] += 1
            job["successful_files"] += 1
            job["downloads"].append({
                "original": original_name,
                "url": f"/download/{job_id}/out.gif",
            })
            if job["processed_files"] == total_files:
                job["status"] = "done"
                if job_id in app.job_locks:
                    del app.job_locks[job_id]

    monkeypatch.setattr(app, "process_job_file", fake_process_job_file)

    client = TestClient(app.app)
    response = client.post(
        "/convert",
        files={"files": ("video.mp4", b"data", "video/mp4")},
        data={"scale": "original", "fps": "10", "start_times": "0.0", "end_times": "1.0"},
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]

    # Wait briefly for background thread to complete
    time.sleep(0.1)

    try:
        job_state = app.jobs[job_id]
        assert job_state["total_files"] == 1
        assert job_state["processed_files"] == 1
        assert job_state["successful_files"] == 1
        assert job_state["status"] == "done"
        assert job_state["downloads"]
    finally:
        app.jobs.pop(job_id, None)
        app.job_locks.pop(job_id, None)

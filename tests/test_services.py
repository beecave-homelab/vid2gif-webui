"""Tests for the service layer modules."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from vid2gif.backend.services.command_runner import ProgressInfo, parse_ffmpeg_time
from vid2gif.backend.services.conversion import (
    ALLOWED_SCALES,
    ConversionService,
    is_scale_allowed,
)
from vid2gif.backend.services.conversion_strategy import (
    ConversionParams,
    GifConversionStrategy,
)
from vid2gif.backend.services.ffmpeg_runner import FFmpegRunner
from vid2gif.backend.services.file_manager import FileManager
from vid2gif.backend.services.job_store import InMemoryJobStore, JobState

# --- JobStore tests ---


def test_job_store__create_job_initializes_state() -> None:
    """Create job with correct initial state."""
    store = InMemoryJobStore()
    lock = store.create_job("job1", 3)

    assert isinstance(lock, threading.Lock)
    assert store.has_job("job1")
    assert store.has_lock("job1")

    job = store.get_job("job1")
    assert job is not None
    assert job["total_files"] == 3
    assert job["processed_files"] == 0
    assert job["status"] == "initializing"


def test_job_store__get_job_returns_none_for_missing() -> None:
    """Return None for non-existent job."""
    store = InMemoryJobStore()
    assert store.get_job("missing") is None
    assert not store.has_job("missing")


def test_job_store__update_progress() -> None:
    """Update progress fields correctly."""
    store = InMemoryJobStore()
    store.create_job("job1", 2)

    store.update_progress("job1", 1, 50.5, 10.5, "Converting...")

    job = store.get_job("job1")
    assert job is not None
    assert job["current_file_index"] == 1
    assert job["current_file_percent"] == 50.5
    assert job["current_file_est_seconds"] == 10  # rounded (banker's rounding)
    assert job["status"] == "Converting..."


def test_job_store__record_file_success() -> None:
    """Record successful file and return whether it was the last."""
    store = InMemoryJobStore()
    store.create_job("job1", 2)

    is_last = store.record_file_success("job1", "video.mp4", "/download/job1/video.gif")
    assert not is_last

    job = store.get_job("job1")
    assert job is not None
    assert job["processed_files"] == 1
    assert job["successful_files"] == 1
    assert len(job["downloads"]) == 1

    is_last = store.record_file_success("job1", "video2.mp4", "/download/job1/video2.gif")
    assert is_last


def test_job_store__record_file_error() -> None:
    """Record file error and return whether it was the last."""
    store = InMemoryJobStore()
    store.create_job("job1", 1)

    is_last = store.record_file_error("job1")
    assert is_last

    job = store.get_job("job1")
    assert job is not None
    assert job["processed_files"] == 1
    assert job["error_files"] == 1


def test_job_store__finalize_job() -> None:
    """Finalize job sets final status and removes lock."""
    store = InMemoryJobStore()
    store.create_job("job1", 1)

    store.finalize_job("job1", "done")

    assert not store.has_lock("job1")
    job = store.get_job("job1")
    assert job is not None
    assert job["status"] == "done"
    assert job["current_file_percent"] == 100.0


def test_job_store__compute_final_status() -> None:
    """Compute correct final status based on success/error counts."""
    store = InMemoryJobStore()

    # All successful
    store.create_job("job1", 2)
    store.jobs["job1"]["successful_files"] = 2
    assert store.compute_final_status("job1") == "done"

    # Partial success
    store.create_job("job2", 3)
    store.jobs["job2"]["successful_files"] = 2
    status = store.compute_final_status("job2")
    assert "completed with errors" in status
    assert "2/3" in status

    # All failed
    store.create_job("job3", 2)
    store.jobs["job3"]["successful_files"] = 0
    assert store.compute_final_status("job3") == "failed"

    # Non-existent job
    assert store.compute_final_status("missing") == "unknown"


def test_job_store__remove_job() -> None:
    """Remove job and its lock."""
    store = InMemoryJobStore()
    store.create_job("job1", 1)

    store.remove_job("job1")

    assert not store.has_job("job1")
    assert not store.has_lock("job1")


def test_job_store__list_expired_jobs() -> None:
    """List jobs that are expired and have no lock."""
    store = InMemoryJobStore()

    # Recent job - not expired
    store.create_job("recent", 1)
    store.finalize_job("recent", "done")
    store.jobs["recent"]["created_at"] = 9.0

    # Old job - expired
    store.create_job("old", 1)
    store.finalize_job("old", "done")
    store.jobs["old"]["created_at"] = 0.0

    # Old job with lock - not eligible
    store.create_job("locked", 1)
    store.jobs["locked"]["created_at"] = 0.0

    expired = store.list_expired_jobs(now=10.0, ttl_seconds=5.0)

    assert "old" in expired
    assert "recent" not in expired
    assert "locked" not in expired


def test_job_state_to_dict() -> None:
    """JobState.to_dict returns correct dictionary."""
    state = JobState(job_id="test", total_files=2, status="processing")
    d = state.to_dict()

    assert d["total_files"] == 2
    assert d["status"] == "processing"
    assert "job_id" not in d  # job_id not included in dict


# --- FFmpegRunner tests ---


def test_gif_strategy__build_command_original_scale() -> None:
    """Build command without scale filter for original."""
    params = ConversionParams(
        input_path=Path("/tmp/input.mp4"),
        output_path=Path("/tmp/output.gif"),
        scale="original",
        fps=10,
        start_time_sec=0.0,
        end_time_sec=5.0,
    )
    strategy = GifConversionStrategy()

    cmd = strategy.build_command(params)

    assert "ffmpeg" in cmd
    assert "-ss" in cmd
    assert "0.0" in cmd
    assert "-to" in cmd
    assert "5.0" in cmd
    assert "fps=10" in cmd[cmd.index("-vf") + 1]
    assert "scale=" not in cmd[cmd.index("-vf") + 1]


def test_gif_strategy__build_command_with_scale() -> None:
    """Build command with scale filter."""
    params = ConversionParams(
        input_path=Path("/tmp/input.mp4"),
        output_path=Path("/tmp/output.gif"),
        scale="320:-1",
        fps=15,
        start_time_sec=1.0,
        end_time_sec=3.0,
    )
    strategy = GifConversionStrategy()

    cmd = strategy.build_command(params)
    vf_filter = cmd[cmd.index("-vf") + 1]

    assert "scale=320:-1" in vf_filter
    assert "fps=15" in vf_filter


def test_parse_ffmpeg_time() -> None:
    """Parse FFmpeg time string to seconds."""
    assert parse_ffmpeg_time("00:00:01.50") == 1.5
    assert parse_ffmpeg_time("00:01:30.00") == 90.0
    assert parse_ffmpeg_time("01:00:00.00") == 3600.0


def test_conversion_params_clip_duration() -> None:
    """ConversionParams.clip_duration calculates correctly."""
    params = ConversionParams(
        input_path=Path("/tmp/in.mp4"),
        output_path=Path("/tmp/out.gif"),
        scale="original",
        fps=10,
        start_time_sec=2.0,
        end_time_sec=5.0,
    )
    assert params.clip_duration == 3.0

    # Minimum duration
    params2 = ConversionParams(
        input_path=Path("/tmp/in.mp4"),
        output_path=Path("/tmp/out.gif"),
        scale="original",
        fps=10,
        start_time_sec=0.0,
        end_time_sec=0.0,
    )
    assert params2.clip_duration == 0.01


def test_ffmpeg_runner__run_conversion_without_semaphore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run conversion without semaphore."""
    runner = FFmpegRunner(semaphore=None)

    # Mock the command runner's run_command method
    def fake_run_command(
        cmd: list[str],  # noqa: ARG001
        *,
        clip_duration: float | None = None,  # noqa: ARG001
        on_progress: Any = None,  # noqa: ANN401, ARG001
    ) -> bool:
        return True

    monkeypatch.setattr(runner._command_runner, "run_command", fake_run_command)

    params = ConversionParams(
        input_path=tmp_path / "in.mp4",
        output_path=tmp_path / "out.gif",
        scale="original",
        fps=10,
        start_time_sec=0.0,
        end_time_sec=1.0,
    )

    result = runner.run_conversion(params)
    assert result is True


def test_ffmpeg_runner__run_conversion_with_semaphore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run conversion with semaphore limits concurrency."""
    semaphore = threading.Semaphore(1)
    runner = FFmpegRunner(semaphore=semaphore)

    # Mock the command runner's run_command method
    def fake_run_command(
        cmd: list[str],  # noqa: ARG001
        *,
        clip_duration: float | None = None,  # noqa: ARG001
        on_progress: Any = None,  # noqa: ANN401, ARG001
    ) -> bool:
        return True

    monkeypatch.setattr(runner._command_runner, "run_command", fake_run_command)

    params = ConversionParams(
        input_path=tmp_path / "in.mp4",
        output_path=tmp_path / "out.gif",
        scale="original",
        fps=10,
        start_time_sec=0.0,
        end_time_sec=1.0,
    )

    result = runner.run_conversion(params)
    assert result is True


def test_progress_info() -> None:
    """ProgressInfo dataclass stores values correctly."""
    info = ProgressInfo(percent=75.5, est_seconds_remaining=30.0)
    assert info.percent == 75.5
    assert info.est_seconds_remaining == 30.0


# --- ConversionStrategy tests ---


def test_gif_strategy__output_extension() -> None:
    """GifConversionStrategy returns correct output extension."""
    strategy = GifConversionStrategy()
    assert strategy.output_extension == ".gif"


def test_gif_strategy__description() -> None:
    """GifConversionStrategy returns correct description."""
    strategy = GifConversionStrategy()
    assert strategy.description == "GIF conversion"


def test_gif_strategy__build_command_includes_palette() -> None:
    """GIF strategy includes palette generation for quality."""
    params = ConversionParams(
        input_path=Path("/tmp/input.mp4"),
        output_path=Path("/tmp/output.gif"),
        scale="original",
        fps=10,
        start_time_sec=0.0,
        end_time_sec=5.0,
    )
    strategy = GifConversionStrategy()

    cmd = strategy.build_command(params)
    vf_filter = cmd[cmd.index("-vf") + 1]

    assert "palettegen" in vf_filter
    assert "paletteuse" in vf_filter
    assert "-loop" in cmd
    assert "0" in cmd  # infinite loop


def test_ffmpeg_runner__uses_strategy() -> None:
    """FFmpegRunner exposes strategy property."""
    strategy = GifConversionStrategy()
    runner = FFmpegRunner(strategy=strategy)

    assert runner.strategy is strategy
    assert runner.strategy.output_extension == ".gif"


def test_ffmpeg_runner__defaults_to_gif_strategy() -> None:
    """FFmpegRunner defaults to GifConversionStrategy."""
    runner = FFmpegRunner()

    assert isinstance(runner.strategy, GifConversionStrategy)


# --- FileManager tests ---


def test_file_manager__ensure_base_dir(tmp_path: Path) -> None:
    """Create base directory if it doesn't exist."""
    base_dir = tmp_path / "new_base"
    manager = FileManager(base_dir)

    manager.ensure_base_dir()

    assert base_dir.exists()


def test_file_manager__create_job_dir(tmp_path: Path) -> None:
    """Create job directory."""
    manager = FileManager(tmp_path)

    job_dir = manager.create_job_dir("job123")

    assert job_dir == tmp_path / "job123"
    assert job_dir.exists()


def test_file_manager__write_input_file(tmp_path: Path) -> None:
    """Write input file to job directory."""
    manager = FileManager(tmp_path)
    (tmp_path / "job1").mkdir()

    path = manager.write_input_file("job1", "video.mp4", b"content")

    assert path == tmp_path / "job1" / "video.mp4"
    assert path.read_bytes() == b"content"


def test_file_manager__get_output_path(tmp_path: Path) -> None:
    """Get output path with specified extension."""
    manager = FileManager(tmp_path)

    path = manager.get_output_path("job1", "video.mp4", ".gif")
    assert path == tmp_path / "job1" / "video.gif"

    # Also works with other extensions
    path_mp3 = manager.get_output_path("job1", "audio.wav", ".mp3")
    assert path_mp3 == tmp_path / "job1" / "audio.mp3"


def test_file_manager__cleanup_input_file(tmp_path: Path) -> None:
    """Remove input file after processing."""
    manager = FileManager(tmp_path)
    file_path = tmp_path / "temp.mp4"
    file_path.write_bytes(b"data")

    manager.cleanup_input_file(file_path)

    assert not file_path.exists()


def test_file_manager__cleanup_input_file_missing(tmp_path: Path) -> None:
    """Handle missing file gracefully."""
    manager = FileManager(tmp_path)
    file_path = tmp_path / "nonexistent.mp4"

    # Should not raise
    manager.cleanup_input_file(file_path)


def test_file_manager__file_exists(tmp_path: Path) -> None:
    """Check file existence."""
    manager = FileManager(tmp_path)
    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    (job_dir / "out.gif").write_bytes(b"data")

    assert manager.file_exists("job1", "out.gif")
    assert not manager.file_exists("job1", "missing.gif")
    assert not manager.file_exists("job2", "out.gif")


def test_file_manager__get_file_path(tmp_path: Path) -> None:
    """Get full file path."""
    manager = FileManager(tmp_path)

    path = manager.get_file_path("job1", "out.gif")

    assert path == tmp_path / "job1" / "out.gif"


# --- Conversion service tests ---


def test_is_scale_allowed() -> None:
    """Validate allowed scales."""
    assert is_scale_allowed("original")
    assert is_scale_allowed("320:-1")
    assert is_scale_allowed("1080:-1")
    assert not is_scale_allowed("invalid")
    assert not is_scale_allowed("")


def test_allowed_scales_constant() -> None:
    """ALLOWED_SCALES contains expected values."""
    assert "original" in ALLOWED_SCALES
    assert "720:-1" in ALLOWED_SCALES
    assert len(ALLOWED_SCALES) == 9


def test_conversion_service__create_job(tmp_path: Path) -> None:
    """Create job through service."""
    store = InMemoryJobStore()
    file_manager = FileManager(tmp_path)
    runner = FFmpegRunner()
    service = ConversionService(store, file_manager, runner)

    lock = service.create_job("job1", 2)

    assert isinstance(lock, threading.Lock)
    assert store.has_job("job1")
    assert (tmp_path / "job1").exists()


def test_conversion_service__get_job(tmp_path: Path) -> None:
    """Get job state through service."""
    store = InMemoryJobStore()
    file_manager = FileManager(tmp_path)
    runner = FFmpegRunner()
    service = ConversionService(store, file_manager, runner)

    service.create_job("job1", 1)

    job = service.get_job("job1")
    assert job is not None
    assert job["total_files"] == 1

    assert service.get_job("missing") is None


def test_conversion_service__set_job_status(tmp_path: Path) -> None:
    """Set job status through service."""
    store = InMemoryJobStore()
    file_manager = FileManager(tmp_path)
    runner = FFmpegRunner()
    service = ConversionService(store, file_manager, runner)

    service.create_job("job1", 1)
    service.set_job_status("job1", "processing")

    job = service.get_job("job1")
    assert job is not None
    assert job["status"] == "processing"


def test_conversion_service__file_exists(tmp_path: Path) -> None:
    """Check file existence through service."""
    store = InMemoryJobStore()
    file_manager = FileManager(tmp_path)
    runner = FFmpegRunner()
    service = ConversionService(store, file_manager, runner)

    (tmp_path / "job1").mkdir()
    (tmp_path / "job1" / "out.gif").write_bytes(b"data")

    assert service.file_exists("job1", "out.gif")
    assert not service.file_exists("job1", "missing.gif")


def test_conversion_service__get_file_path(tmp_path: Path) -> None:
    """Get file path through service."""
    store = InMemoryJobStore()
    file_manager = FileManager(tmp_path)
    runner = FFmpegRunner()
    service = ConversionService(store, file_manager, runner)

    path = service.get_file_path("job1", "out.gif")

    assert path == tmp_path / "job1" / "out.gif"


def test_conversion_service__record_skip_error(tmp_path: Path) -> None:
    """Record skip error through service."""
    store = InMemoryJobStore()
    file_manager = FileManager(tmp_path)
    runner = FFmpegRunner()
    service = ConversionService(store, file_manager, runner)

    lock = service.create_job("job1", 1)
    service.record_skip_error("job1", lock, 1)

    job = service.get_job("job1")
    assert job is not None
    assert job["error_files"] == 1
    assert job["status"] == "failed"

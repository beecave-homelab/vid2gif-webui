"""FFmpeg subprocess execution and progress parsing.

Handles building FFmpeg commands, executing them, and parsing progress output.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class ConversionParams:
    """Parameters for a video-to-GIF conversion."""

    input_path: Path
    output_path: Path
    scale: str
    fps: int
    start_time_sec: float
    end_time_sec: float

    @property
    def clip_duration(self) -> float:
        """Calculate clip duration in seconds.

        Returns:
            Duration of the clip, minimum 0.01 seconds.
        """
        return max(0.01, self.end_time_sec - self.start_time_sec)


@dataclass
class ProgressInfo:
    """Progress information from FFmpeg conversion."""

    percent: float
    est_seconds_remaining: float | None


class ProgressCallback(Protocol):
    """Callback protocol for progress updates."""

    def __call__(self, progress: ProgressInfo) -> None:
        """Handle progress update.

        Args:
            progress: Current progress information.
        """
        ...


class FFmpegRunnerProtocol(Protocol):
    """Protocol for FFmpeg execution implementations."""

    def run_conversion(
        self,
        params: ConversionParams,
        on_progress: ProgressCallback | None = None,
    ) -> bool:
        """Run the FFmpeg conversion.

        Args:
            params: Conversion parameters.
            on_progress: Optional callback for progress updates.

        Returns:
            True if conversion succeeded, False otherwise.
        """
        ...


def build_ffmpeg_command(params: ConversionParams) -> list[str]:
    """Build the FFmpeg command for video-to-GIF conversion.

    Args:
        params: Conversion parameters.

    Returns:
        List of command-line arguments for FFmpeg.
    """
    filters = [f"fps={params.fps}"]

    if params.scale != "original":
        filters.append(f"scale={params.scale}:flags=lanczos")

    filters.append("split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse")
    vf_filter = ",".join(filters)

    return [
        "ffmpeg",
        "-y",
        "-ss",
        str(params.start_time_sec),
        "-i",
        str(params.input_path),
        "-to",
        str(params.end_time_sec),
        "-vf",
        vf_filter,
        "-loop",
        "0",
        str(params.output_path),
    ]


def parse_ffmpeg_time(time_str: str) -> float:
    """Parse FFmpeg time string (HH:MM:SS.ms) to seconds.

    Args:
        time_str: Time string in HH:MM:SS.ms format.

    Returns:
        Time in seconds.

    Note:
        May raise ValueError if time string format is invalid.
    """
    h, m, s_part = time_str.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s_part)


class FFmpegRunner:
    """Execute FFmpeg conversions with progress tracking.

    This implementation uses subprocess.Popen to run FFmpeg and parses
    stderr for progress information.
    """

    def __init__(
        self,
        *,
        semaphore: threading.Semaphore | None = None,
    ) -> None:
        """Initialize FFmpeg runner.

        Args:
            semaphore: Optional semaphore for concurrency limiting.
        """
        self._semaphore = semaphore

    def run_conversion(
        self,
        params: ConversionParams,
        on_progress: ProgressCallback | None = None,
    ) -> bool:
        """Run the FFmpeg conversion.

        Args:
            params: Conversion parameters.
            on_progress: Optional callback for progress updates.

        Returns:
            True if conversion succeeded (exit code 0), False otherwise.
        """

        def task() -> bool:
            return self._execute(params, on_progress)

        if self._semaphore:
            self._semaphore.acquire()
            try:
                return task()
            finally:
                self._semaphore.release()
        else:
            return task()

    def _execute(
        self,
        params: ConversionParams,
        on_progress: ProgressCallback | None,
    ) -> bool:
        """Execute the FFmpeg subprocess.

        Args:
            params: Conversion parameters.
            on_progress: Optional callback for progress updates.

        Returns:
            True if conversion succeeded, False otherwise.
        """
        cmd = build_ffmpeg_command(params)
        logging.info("Running ffmpeg: %s", " ".join(cmd))

        conversion_start_time = time.time()
        clip_duration = params.clip_duration

        proc = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if proc.stderr and on_progress:
            self._parse_progress(
                proc.stderr,
                clip_duration,
                conversion_start_time,
                on_progress,
            )

        return_code = proc.wait()
        return return_code == 0

    def _parse_progress(
        self,
        stderr: subprocess.Popen[str].stderr,  # type: ignore[type-arg]
        clip_duration: float,
        start_time: float,
        on_progress: ProgressCallback,
    ) -> None:
        """Parse FFmpeg stderr for progress information.

        Args:
            stderr: FFmpeg stderr stream.
            clip_duration: Expected clip duration in seconds.
            start_time: Wall-clock time when conversion started.
            on_progress: Callback for progress updates.
        """
        for line in stderr:
            if "time=" not in line:
                continue

            try:
                t_str = line.split("time=")[1].split()[0]
                elapsed_output_time = parse_ffmpeg_time(t_str)
                pct = (
                    min((elapsed_output_time / clip_duration) * 100.0, 100.0)
                    if clip_duration > 0
                    else 0.0
                )

                elapsed_wall = time.time() - start_time
                est_remain = (elapsed_wall / pct) * (100.0 - pct) if 0 < pct < 100 else None

                on_progress(ProgressInfo(percent=pct, est_seconds_remaining=est_remain))

            except Exception as e:  # noqa: BLE001
                logging.warning("Error parsing ffmpeg progress line '%s': %s", line.strip(), e)

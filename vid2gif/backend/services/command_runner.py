"""Generic command execution with progress parsing.

Infrastructure module for running subprocesses (like FFmpeg) and parsing
their progress output. This is decoupled from specific conversion types.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import IO, Protocol


@dataclass
class ProgressInfo:
    """Progress information from a running command.

    Attributes:
        percent: Completion percentage (0-100).
        est_seconds_remaining: Estimated seconds until completion, if known.
    """

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


class FFmpegProgressParser:
    """Parse FFmpeg stderr for progress information.

    This is a stateless helper that extracts progress from FFmpeg output.
    """

    @staticmethod
    def parse_progress_line(
        line: str,
        clip_duration: float,
        start_time: float,
    ) -> ProgressInfo | None:
        """Parse a single FFmpeg output line for progress.

        Args:
            line: A line from FFmpeg stderr.
            clip_duration: Expected clip duration in seconds.
            start_time: Wall-clock time when conversion started.

        Returns:
            ProgressInfo if progress was found, None otherwise.
        """
        if "time=" not in line:
            return None

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

            return ProgressInfo(percent=pct, est_seconds_remaining=est_remain)

        except Exception as e:  # noqa: BLE001
            logging.warning("Error parsing ffmpeg progress line '%s': %s", line.strip(), e)
            return None


class CommandRunner:
    """Execute shell commands with optional concurrency limiting.

    This is a generic infrastructure component for running subprocesses.
    It handles semaphore-based concurrency control and progress parsing.
    """

    def __init__(
        self,
        *,
        semaphore: threading.Semaphore | None = None,
    ) -> None:
        """Initialize command runner.

        Args:
            semaphore: Optional semaphore for concurrency limiting.
        """
        self._semaphore = semaphore
        self._progress_parser = FFmpegProgressParser()

    def run_command(
        self,
        cmd: list[str],
        *,
        clip_duration: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> bool:
        """Run a shell command with optional progress tracking.

        Args:
            cmd: Command-line arguments.
            clip_duration: Expected clip duration for progress calculation.
            on_progress: Optional callback for progress updates.

        Returns:
            True if command succeeded (exit code 0), False otherwise.
        """

        def task() -> bool:
            return self._execute(cmd, clip_duration, on_progress)

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
        cmd: list[str],
        clip_duration: float | None,
        on_progress: ProgressCallback | None,
    ) -> bool:
        """Execute the subprocess.

        Args:
            cmd: Command-line arguments.
            clip_duration: Expected clip duration for progress calculation.
            on_progress: Optional callback for progress updates.

        Returns:
            True if command succeeded, False otherwise.
        """
        logging.info("Running command: %s", " ".join(cmd))

        conversion_start_time = time.time()

        proc = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if proc.stderr and on_progress and clip_duration:
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
        stderr: IO[str],
        clip_duration: float,
        start_time: float,
        on_progress: ProgressCallback,
    ) -> None:
        """Parse stderr for progress information.

        Args:
            stderr: Subprocess stderr stream.
            clip_duration: Expected clip duration in seconds.
            start_time: Wall-clock time when command started.
            on_progress: Callback for progress updates.
        """
        for line in stderr:
            progress = self._progress_parser.parse_progress_line(
                line,
                clip_duration,
                start_time,
            )
            if progress:
                on_progress(progress)

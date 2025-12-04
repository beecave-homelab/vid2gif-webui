"""FFmpeg conversion runner with strategy pattern support.

This module provides a thin adapter that combines the generic CommandRunner
infrastructure with a ConversionStrategy to execute media conversions.
"""

from __future__ import annotations

import logging
import threading
from typing import Protocol

from vid2gif.backend.services.command_runner import (
    CommandRunner,
    ProgressCallback,
    ProgressInfo,
)
from vid2gif.backend.services.conversion_strategy import (
    ConversionParams,
    ConversionStrategy,
    GifConversionStrategy,
)
from vid2gif.backend.utils.constant import SEGMENT_MAX_DURATION_SECONDS

# Re-export for backward compatibility
__all__ = [
    "ConversionParams",
    "FFmpegRunner",
    "FFmpegRunnerProtocol",
    "GifConversionStrategy",
    "ProgressCallback",
    "ProgressInfo",
]


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


class FFmpegRunner:
    """Execute media conversions using a pluggable strategy.

    This is a thin adapter that:
    - Delegates command building to a ConversionStrategy
    - Delegates execution to a CommandRunner

    Single Responsibility: Coordinates conversion execution using injected
    strategy and runner, without knowing the specifics of either.
    """

    def __init__(
        self,
        *,
        semaphore: threading.Semaphore | None = None,
        strategy: ConversionStrategy | None = None,
        command_runner: CommandRunner | None = None,
    ) -> None:
        """Initialize FFmpeg runner.

        Args:
            semaphore: Optional semaphore for concurrency limiting.
            strategy: Conversion strategy (defaults to GifConversionStrategy).
            command_runner: Command runner (created with semaphore if not provided).
        """
        self._strategy = strategy or GifConversionStrategy()
        self._command_runner = command_runner or CommandRunner(semaphore=semaphore)

    @property
    def strategy(self) -> ConversionStrategy:
        """Get the conversion strategy.

        Returns:
            The current conversion strategy.
        """
        return self._strategy

    def run_conversion(
        self,
        params: ConversionParams,
        on_progress: ProgressCallback | None = None,
    ) -> bool:
        """Run the conversion using the configured strategy.

        For clips longer than ``SEGMENT_MAX_DURATION_SECONDS``, a two-pass strategy
        is used to avoid OOM errors during palette generation:
        1. Generate a global palette using subsampled frames (1 fps).
        2. Convert the full clip using the pre-generated palette.

        Shorter clips are processed in a single standard pass.

        Args:
            params: Conversion parameters.
            on_progress: Optional callback for progress updates.

        Returns:
            True if conversion succeeded (exit code 0), False otherwise.
        """
        clip_duration = params.clip_duration

        # Standard single-pass for short clips
        if clip_duration <= SEGMENT_MAX_DURATION_SECONDS:
            cmd = self._strategy.build_command(params)
            return self._command_runner.run_command(
                cmd,
                clip_duration=clip_duration,
                on_progress=on_progress,
            )

        # Two-pass subsampled palette strategy for long clips
        logging.info(
            "Clip duration %.2fs > %.2fs. Using subsampled palette strategy.",
            clip_duration,
            SEGMENT_MAX_DURATION_SECONDS,
        )

        palette_path = params.output_path.with_suffix(".palette.png")

        # Step 1: Generate palette from subsampled frames (1 fps)
        # This drastically reduces memory usage compared to full-frame analysis
        palette_cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(params.start_time_sec),
            "-i",
            str(params.input_path),
            "-to",
            str(params.end_time_sec),
            "-vf",
            "fps=1,palettegen",
            str(palette_path),
        ]

        logging.info("Step 1/2: Generating subsampled palette...")
        if not self._command_runner.run_command(palette_cmd, clip_duration=None):
            return False

        # Step 2: Convert using the pre-generated palette
        filters = [f"fps={params.fps}"]
        if params.scale != "original":
            filters.append(f"scale={params.scale}:flags=lanczos")

        # Use the external palette file
        filters.append("paletteuse")
        vf_filter = ",".join(filters)

        convert_cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(params.start_time_sec),
            "-i",
            str(params.input_path),
            "-i",
            str(palette_path),
            "-to",
            str(params.end_time_sec),
            "-lavfi",
            vf_filter,
            "-loop",
            "0",
            str(params.output_path),
        ]

        logging.info("Step 2/2: Converting with pre-generated palette...")
        success = self._command_runner.run_command(
            convert_cmd,
            clip_duration=clip_duration,
            on_progress=on_progress,
        )

        # Cleanup palette
        try:
            palette_path.unlink(missing_ok=True)
        except OSError as e:
            logging.warning("Failed to cleanup palette file: %s", e)

        return success

"""FFmpeg conversion runner with strategy pattern support.

This module provides a thin adapter that combines the generic CommandRunner
infrastructure with a ConversionStrategy to execute media conversions.
"""

from __future__ import annotations

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

        Args:
            params: Conversion parameters.
            on_progress: Optional callback for progress updates.

        Returns:
            True if conversion succeeded (exit code 0), False otherwise.
        """
        cmd = self._strategy.build_command(params)
        return self._command_runner.run_command(
            cmd,
            clip_duration=params.clip_duration,
            on_progress=on_progress,
        )

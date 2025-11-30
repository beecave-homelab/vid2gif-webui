"""Conversion strategy definitions.

Separates use-case-specific conversion logic from generic infrastructure.
Each strategy defines what command to run and what output format to produce.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class ConversionParams:
    """Generic parameters for media conversion.

    Attributes:
        input_path: Path to the input file.
        output_path: Path for the output file.
        scale: Scale specification (e.g., "320:-1" or "original").
        fps: Frames per second for output.
        start_time_sec: Start time in seconds for trimming.
        end_time_sec: End time in seconds for trimming.
    """

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


class ConversionStrategy(Protocol):
    """Protocol for media conversion strategies.

    Each strategy defines:
    - The output file extension
    - How to build the conversion command
    - Human-readable description for status messages
    """

    @property
    @abstractmethod
    def output_extension(self) -> str:
        """Return the output file extension (e.g., '.gif', '.mp3').

        Returns:
            File extension including the leading dot.
        """
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a human-readable description of the conversion type.

        Returns:
            Description string for status messages (e.g., 'GIF conversion').
        """
        ...

    @abstractmethod
    def build_command(self, params: ConversionParams) -> list[str]:
        """Build the command-line arguments for the conversion.

        Args:
            params: Conversion parameters.

        Returns:
            List of command-line arguments.
        """
        ...


class GifConversionStrategy:
    """Strategy for video-to-GIF conversion using FFmpeg.

    Uses palettegen/paletteuse filter chain for high-quality GIF output.
    """

    @property
    def output_extension(self) -> str:
        """Return the GIF file extension.

        Returns:
            The string '.gif'.
        """
        return ".gif"

    @property
    def description(self) -> str:
        """Return description for GIF conversion.

        Returns:
            Human-readable description for status messages.
        """
        return "GIF conversion"

    def build_command(self, params: ConversionParams) -> list[str]:
        """Build the FFmpeg command for video-to-GIF conversion.

        Uses palette generation for optimal color quality.

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

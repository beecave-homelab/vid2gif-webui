"""Tests for validating allowed scale values for conversions."""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import HTTPException, UploadFile

from vid2gif.backend.app import convert, is_scale_allowed


def test_is_scale_allowed__accepts_frontend_scale_options() -> None:
    """Accept all scale values that are exposed in the frontend select options."""
    allowed_values = {
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

    for value in allowed_values:
        assert is_scale_allowed(value) is True


def test_is_scale_allowed__rejects_obviously_invalid_values() -> None:
    """Reject scale values that are not in the allowlist."""
    invalid_values = [
        "",
        "auto",
        "320x240",
        "320:-2",
        "320:abc",
        "320;-1",
        "320:-1;rm -rf /",
    ]

    for value in invalid_values:
        assert is_scale_allowed(value) is False


def test_convert__rejects_invalid_scale_before_processing() -> None:
    """Raise HTTPException 400 when scale is not in the allowlist."""
    upload = UploadFile(file=io.BytesIO(b"data"), filename="test.mp4")

    async def call_convert() -> None:
        with pytest.raises(HTTPException) as exc_info:
            await convert(
                files=[upload],
                scale="invalid-scale",
                fps=10,
                start_times=["0.0"],
                end_times=["1.0"],
            )

        assert exc_info.value.status_code == 400
        assert "scale" in exc_info.value.detail.lower()

    asyncio.run(call_convert())

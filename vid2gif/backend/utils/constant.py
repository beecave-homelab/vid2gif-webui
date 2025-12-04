"""Project-wide constants and configuration."""

from __future__ import annotations

from .env_loader import load_project_env

# Load once (single source of truth)
_ENV = load_project_env()

# Exposed constants (typed, with sensible defaults)
# Using os.getcwd() for default tmp base to ensure absolute path correctness if needed,
# but keeping it simple as "tmp" to match original behavior, just centralized.
TMP_BASE_DIR: str = _ENV.get("TMP_BASE_DIR", "tmp")
JOB_TTL_SECONDS: int = int(_ENV.get("JOB_TTL_SECONDS", "3600"))
FFMPEG_MAX_CONCURRENT: int = int(_ENV.get("FFMPEG_MAX_CONCURRENT", "4"))
SEGMENT_MAX_DURATION_SECONDS: float = float(_ENV.get("SEGMENT_MAX_DURATION_SECONDS", "30"))

"""Environment variable loading utilities."""

from __future__ import annotations

import os


def load_project_env() -> dict[str, str]:
    """Load environment variables from the system.

    Returns:
        A dictionary containing the current environment variables.
    """
    # Parse once: could expand to load .env, validate, coerce types, etc.
    return dict(os.environ)

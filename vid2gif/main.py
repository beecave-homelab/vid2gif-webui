"""Entry point for the vid2gif application."""

from __future__ import annotations

from vid2gif.backend.app import app

if __name__ == "__main__":
    app.run()

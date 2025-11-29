"""Tests for limiting concurrent ffmpeg conversions via a semaphore."""

from __future__ import annotations

import threading
import time

from vid2gif.backend import app


def test_run_with_ffmpeg_semaphore__limits_concurrent_tasks() -> None:
    """Ensure no more than the configured number of tasks run concurrently."""
    max_concurrent = 2
    app.FFMPEG_SEMAPHORE = threading.Semaphore(max_concurrent)

    current = 0
    max_seen = 0
    lock = threading.Lock()
    release_event = threading.Event()

    def make_worker() -> threading.Thread:
        def run() -> None:
            nonlocal current, max_seen

            def task() -> None:
                nonlocal current, max_seen
                with lock:
                    current += 1
                    max_seen = max(max_seen, current)
                release_event.wait(timeout=1.0)
                with lock:
                    current -= 1

            app.run_with_ffmpeg_semaphore(task)

        return threading.Thread(target=run)

    threads = [make_worker() for _ in range(5)]
    for t in threads:
        t.start()

    time.sleep(0.1)
    release_event.set()

    for t in threads:
        t.join(timeout=1.0)

    assert max_seen <= max_concurrent

---
repo: https://github.com/beecave-homelab/vid2gif-webui
commit: 9cde92fe085f47d9255ddcc116b21577d4338a10
generated: 2025-11-26T22:01:00+01:00
---
<!-- SECTIONS:API,WEBUI,DOCKER,TESTS -->

# Project Overview | vid2gif-webui

A self-hosted web application for converting video files to animated GIFs using ffmpeg. Designed for homelab users who want a simple, browser-based interface for batch video-to-GIF conversion with trimming, scaling, and FPS control.

[![Python](https://img.shields.io/badge/Python-3.13+-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.122+-green)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-brightgreen)](LICENSE)
[![Version](https://img.shields.io/badge/Version-0.1.0-blue)](#version-summary)

---

## Table of Contents

- [Quickstart for Developers](#quickstart-for-developers)
- [Version Summary](#version-summary)
- [Project Features](#project-features)
- [Project Structure](#project-structure)
- [Architecture Highlights](#architecture-highlights)
- [API Reference](#api-reference)
- [WebUI Overview](#webui-overview)
- [Docker Deployment](#docker-deployment)
- [Configuration & Environment Variables](#configuration--environment-variables)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Development Workflow](#development-workflow)

---

## Quickstart for Developers

```bash
# Clone the repository
git clone https://github.com/beecave-homelab/vid2gif-webui.git
cd vid2gif-webui

# Install dependencies (requires PDM)
pdm install

# Run development server (requires ffmpeg installed locally)
pdm run start-dev

# Or use Docker for development
docker compose -f docker-compose.dev.yaml up --build
```

Access the WebUI at `http://localhost:8080` (PDM) or `http://localhost:8000` (Docker).

---

## Version Summary

| Version | Date       | Type | Key Changes                                      |
|---------|------------|------|--------------------------------------------------|
| 0.1.0   | 2025-11-26 | ✨   | Initial release: video-to-GIF conversion via web |

---

## Project Features

- **Drag-and-drop video upload** — supports multiple files in a single batch
- **Video trimming** — set start/end times per video with sliders and numeric inputs
- **Configurable output** — scale (320px–4K) and FPS (1–20)
- **Real-time progress** — per-file percentage and ETA via polling
- **Concurrent conversion limiting** — semaphore-controlled ffmpeg processes
- **Automatic job cleanup** — expired jobs and temp files removed after TTL
- **Docker-ready** — production and development compose files included

---

## Project Structure

<details><summary>Show tree</summary>

```text
vid2gif-webui/
├── backend/                    # Python FastAPI backend
│   ├── app.py                  # Main application: endpoints, job processing
│   └── utils/
│       ├── constant.py         # Centralized configuration constants
│       └── env_loader.py       # Environment variable loader (single source)
├── frontend/                   # Static HTML/CSS/JS frontend
│   ├── index.html              # Main UI page
│   ├── script.js               # Client-side logic: upload, polling, editor
│   └── style.css               # Dark-themed responsive styles
├── tests/                      # Pytest test suite
│   ├── test_cleanup_jobs.py    # Job expiration and temp file cleanup
│   ├── test_concurrency_limit.py # Semaphore-based ffmpeg limiting
│   └── test_scale_validation.py  # Scale allowlist validation
├── Dockerfile                  # Production container image
├── Dockerfile.dev              # Development container image
├── docker-compose.yaml         # Production compose (with reload)
├── docker-compose.dev.yaml     # Development compose (with reload)
├── pyproject.toml              # PDM project config, dependencies, scripts
├── pdm.lock                    # Locked dependency versions
├── AGENTS.md                   # Coding rules and standards (Ruff + Pytest + SOLID)
└── README.md                   # Brief project description
```

</details>

---

## Architecture Highlights

### Backend (`backend/app.py`)

- **Framework**: FastAPI with Uvicorn (dev) / Gunicorn (prod)
- **Job Model**: In-memory `dict` keyed by UUID; stores status, progress, download links
- **Concurrency Control**: `threading.Semaphore` limits simultaneous ffmpeg processes (default: 4)
- **Background Processing**: Each file spawns a daemon thread calling ffmpeg via `subprocess.Popen`
- **Progress Parsing**: Reads ffmpeg stderr for `time=` lines to compute percentage
- **Cleanup**: `cleanup_expired_jobs()` runs opportunistically on each `/convert` request

### Frontend (`frontend/`)

- **Vanilla JS** — no build step required
- **Video Editor**: Per-file start/end sliders synced with `<video>` element
- **Polling**: `pollProgress()` fetches `/progress?job_id=...` every second until done
- **Dark Theme**: Minimal CSS with responsive layout

### Data Flow

```text
┌─────────────┐   POST /convert    ┌─────────────────┐
│   Browser   │ ─────────────────► │  FastAPI App    │
│  (script.js)│                    │  (backend/app)  │
└─────────────┘                    └────────┬────────┘
       │                                    │
       │ GET /progress?job_id=...           │ spawn threads
       │◄───────────────────────────────────┤
       │                                    ▼
       │                           ┌────────────────┐
       │                           │  ffmpeg (CLI)  │
       │                           └────────┬───────┘
       │                                    │
       │ GET /download/{job_id}/{file}.gif  │ writes .gif
       │◄───────────────────────────────────┘
       ▼
   Download GIF
```

---

## API Reference

### `POST /convert`

Start a batch conversion job.

| Parameter     | Type           | Description                                      |
|---------------|----------------|--------------------------------------------------|
| `files`       | `UploadFile[]` | Video files to convert                           |
| `scale`       | `str`          | Output width (`original`, `320:-1`, ..., `3840:-1`) |
| `fps`         | `int`          | Frames per second (1–20, default 10)             |
| `start_times` | `str[]`        | Start time in seconds per file                   |
| `end_times`   | `str[]`        | End time in seconds per file                     |

**Response**: `{ "job_id": "<uuid>" }`

### `GET /progress`

Poll job status.

| Parameter | Type  | Description         |
|-----------|-------|---------------------|
| `job_id`  | `str` | UUID from `/convert`|

**Response** (example):

```json
{
  "total_files": 2,
  "processed_files": 1,
  "successful_files": 1,
  "error_files": 0,
  "status": "Converting file 2/2 (video.mp4)...",
  "current_file_percent": 45.2,
  "current_file_est_seconds": 12,
  "downloads": [
    { "original": "clip.mp4", "url": "/download/<job_id>/clip.gif" }
  ]
}
```

### `GET /download/{job_id}/{gif_filename}`

Download a generated GIF. Returns `image/gif` with `Content-Disposition` header.

---

## WebUI Overview

| Element            | Description                                                  |
|--------------------|--------------------------------------------------------------|
| **Drop Zone**      | Drag-and-drop or click to select video files                 |
| **Video Previews** | Inline `<video>` with playback controls                      |
| **Trim Controls**  | Start/End sliders + numeric inputs per video                 |
| **Scale Dropdown** | Preset widths from Original to 4K                            |
| **FPS Input**      | Number input (1–20)                                          |
| **Progress Bar**   | Shows overall job status and ETA                             |
| **Download Links** | Appear after conversion completes                            |

---

## Docker Deployment

### Production

```bash
docker compose up -d --build
```

- Exposes port **8000**
- Runs Uvicorn with `--reload` and `--log-level debug` (adjust for true prod)
- Mounts `./backend` and `./frontend` as volumes for live editing

### Development

```bash
docker compose -f docker-compose.dev.yaml up --build
```

Same as production compose (currently identical files).

### Image Details

- **Base**: `python:3.10-slim`
- **System deps**: `ffmpeg`, `gcc`
- **Python deps**: Installed from `backend/requirements.txt` (generated from `pyproject.toml`)

---

## Configuration & Environment Variables

All configuration is centralized in `backend/utils/constant.py`. **Do not** read `os.environ` elsewhere.

| Variable              | Default | Description                                |
|-----------------------|---------|--------------------------------------------|
| `TMP_BASE_DIR`        | `tmp`   | Directory for temporary job files          |
| `JOB_TTL_SECONDS`     | `3600`  | Seconds before expired jobs are cleaned up |
| `FFMPEG_MAX_CONCURRENT` | `4`   | Max simultaneous ffmpeg processes          |

To override, set environment variables before starting the server:

```bash
export JOB_TTL_SECONDS=7200
pdm run start-dev
```

---

## Coding Standards

This project follows strict coding rules defined in [`AGENTS.md`](AGENTS.md). Key points:

### Linting & Formatting

- **Ruff** is the single source of truth
- Rules enabled: `F`, `E`, `W`, `N`, `I`, `D`, `DOC`, `TID`, `UP`, `FA`
- Line length: 100 characters
- Docstring style: Google

```bash
pdm run lint      # Check
pdm run fix       # Auto-fix
pdm run format    # Format
```

### Naming Conventions

- **Functions/variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_CASE`

### Imports

1. Standard library
2. Third-party
3. First-party/local

Always use `from __future__ import annotations` at the top of Python files.

### SOLID Principles

- **SRP**: One responsibility per module/function
- **OCP**: Extend via protocols, not modification
- **LSP**: Subtypes must be substitutable
- **ISP**: Small, role-specific interfaces
- **DIP**: Depend on abstractions, inject dependencies

### Configuration Management

- Environment variables loaded **once** in `env_loader.py`
- Constants exposed **only** from `constant.py`
- No direct `os.environ` access outside `constant.py`

---

## Testing

### Running Tests

```bash
# Quick run
pdm run test

# With coverage
pdm run test-cov
```

### Test Files

| File                          | Coverage Area                              |
|-------------------------------|--------------------------------------------|
| `test_scale_validation.py`    | `is_scale_allowed()` allowlist validation  |
| `test_cleanup_jobs.py`        | Job expiration and temp directory cleanup  |
| `test_concurrency_limit.py`   | Semaphore-based ffmpeg concurrency control |

### Test Naming Convention

```text
test_<unit_under_test>__<expected_behavior>()
```

### Coverage Target

Guideline: **≥ 85%** line coverage. CI should fail below threshold.

---

## Development Workflow

### 1. Setup

```bash
pdm install
```

### 2. Run Dev Server

```bash
pdm run start-dev
# or
docker compose -f docker-compose.dev.yaml up --build
```

### 3. Make Changes

- Backend: Edit `backend/app.py` (hot-reload enabled)
- Frontend: Edit `frontend/*.{html,js,css}` (refresh browser)

### 4. Lint & Format

```bash
pdm run fix
pdm run format
```

### 5. Test

```bash
pdm run test
pdm run test-cov
```

### 6. Commit

Run lint + tests before committing. Use conventional commit format.

---

## Key Files Reference

| File                          | Purpose                                         |
|-------------------------------|-------------------------------------------------|
| `backend/app.py`              | FastAPI app, endpoints, job processing logic    |
| `backend/utils/constant.py`   | Centralized configuration constants             |
| `backend/utils/env_loader.py` | Environment variable loading                    |
| `frontend/index.html`         | Main HTML structure                             |
| `frontend/script.js`          | Client-side upload, polling, video editor       |
| `frontend/style.css`          | Dark-themed responsive styles                   |
| `pyproject.toml`              | Project metadata, dependencies, PDM scripts     |
| `AGENTS.md`                   | Coding rules (Ruff, Pytest, SOLID)              |
| `Dockerfile`                  | Production container build                      |
| `docker-compose.yaml`         | Production deployment                           |

---

## Dependencies

### Runtime (Python)

| Package            | Version   | Purpose                          |
|--------------------|-----------|----------------------------------|
| `fastapi`          | ≥0.122.0  | Web framework                    |
| `uvicorn[standard]`| ≥0.38.0   | ASGI server (dev)                |
| `gunicorn`         | ≥23.0.0   | WSGI server (prod)               |
| `python-multipart` | ≥0.0.20   | File upload handling             |
| `python-env`       | ≥1.0.0    | Environment utilities            |

### Development (Python)

| Package      | Version  | Purpose                |
|--------------|----------|------------------------|
| `ruff`       | ≥0.6.9   | Linting & formatting   |
| `pytest`     | ≥8.0.0   | Testing framework      |
| `pytest-cov` | ≥5.0.0   | Coverage reporting     |

### System

| Tool     | Purpose                        |
|----------|--------------------------------|
| `ffmpeg` | Video-to-GIF conversion engine |

---

## Troubleshooting

### ffmpeg not found

Ensure ffmpeg is installed and in PATH:

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
apt-get install ffmpeg

# Docker handles this automatically
```

### Port already in use

```bash
# Find process using port 8080
lsof -i :8080

# Kill it or use a different port
pdm run uvicorn backend.app:app --port 8081
```

### Job files not cleaning up

Check `JOB_TTL_SECONDS` value. Cleanup runs opportunistically on `/convert` requests.

---

**Always update this file when code or configuration changes.**

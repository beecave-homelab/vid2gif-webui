# VERSIONS.md

## ToC

- [v0.3.2 (Current)](#v032-current---29-11-2025)
- [v0.3.1](#v031---29-11-2025)
- [v0.3.0](#v030---28-11-2025)
- [v0.2.0](#v020---27-11-2025)
- [v0.1.0](#v010---26-11-2025)

## **v0.3.2** (Current) - *29-11-2025*

### 🐛 Brief Description (v0.3.2)

Patch release to fix container image metadata and Compose configuration so GitHub Actions can correctly build and push images to GitHub Container Registry (GHCR).

### **Bug Fixes in v0.3.2**

- **Fixed**: Missing OCI image metadata for source repository in Docker images.
  - **Issue**: Built images lacked a canonical `org.opencontainers.image.source` label.
  - **Solution**: Added `LABEL org.opencontainers.image.source=https://github.com/beecave-homelab/vid2gif-webui` to both `Dockerfile` and `Dockerfile.dev`.
- **Fixed**: Docker Compose images not aligned with GHCR publishing workflow.
  - **Issue**: `docker-compose.yaml` and `docker-compose.dev.yaml` did not reference the GHCR image names used by the CI workflows.
  - **Solution**: Updated production compose to use `ghcr.io/beecave-homelab/vid2gif-webui:main` and development compose to use `ghcr.io/beecave-homelab/vid2gif-webui:dev`, with explicit container names.

### **Key Commits in v0.3.2**

`eac6a56`, `66770cb`

---

## **v0.3.1** - *29-11-2025*

### 🐛 Brief Description (v0.3.1)

Patch release fixing inconsistencies introduced during the v0.3.0 refactor. Corrects the legacy backend static files mount path, updates Python version to 3.13 in CI and Docker, adds missing HTTPx dependency, and removes the duplicate legacy `backend/` directory.

### **Bug Fixes in v0.3.1**

- **Fixed**: Legacy entrypoint (`uvicorn backend.app:app`) failed to start.
  - **Issue**: `StaticFiles(directory="frontend")` raised `RuntimeError` because `frontend/` was removed in v0.3.0.
  - **Root Cause**: Static mount path not updated when frontend moved to `vid2gif/frontend/`.
  - **Solution**: Updated mount to `vid2gif/frontend`.
- **Fixed**: Python version mismatch in CI workflow and Dockerfiles.
  - **Issue**: CI used Python 3.12 while `pyproject.toml` requires `>=3.13`.
  - **Solution**: Updated `pr-ci.yaml` and Dockerfiles to Python 3.13.
- **Fixed**: Missing `httpx` dependency for test client.
  - **Issue**: `pytest` with FastAPI `TestClient` requires `httpx`.
  - **Solution**: Added `httpx>=0.28.1` to project dependencies.

### 🧹 **Cleanup in v0.3.1**

- **Removed**: Legacy `backend/` directory containing duplicate `app.py`.
  - **Issue**: `backend/app.py` was a full duplicate of `vid2gif/backend/app.py`, not a re-export shim.
  - **Solution**: Removed the legacy directory; all code now uses `vid2gif.backend` exclusively.

### **Key Commits in v0.3.1**

`e07dad2`, `ef3d20a`, `a401e6b`, `cbbb870`

---

## **v0.3.0** - *28-11-2025*

### ♻️ Brief Description (v0.3.0)

Major architectural refactor introducing a modular service layer following SOLID principles (SRP/OCP). Backend restructured into `vid2gif/` package with dependency injection for improved testability. Added GitHub Actions CI/CD workflows.

### **New Features in v0.3.0**

- **Added**: GitHub Actions workflow for PR validation (lint, format, tests).
- **Added**: GitHub Actions workflow for Docker image builds on main branch.
- **Added**: Service layer architecture with dedicated modules:
  - `job_store.py` — Thread-safe job state management
  - `ffmpeg_runner.py` — FFmpeg subprocess execution & progress parsing
  - `file_manager.py` — Filesystem I/O & cleanup
  - `conversion.py` — Orchestration coordinator

### **Bug Fixes in v0.3.0**

- N/A (refactor release).

### **Improvements in v0.3.0**

- **Refactored**: Moved `backend/` and `frontend/` into `vid2gif/` package structure.
- **Improved**: Backend `app.py` is now a thin HTTP layer delegating to services.
- **Enhanced**: Dependency injection enables easy mocking and unit testing.
- **Updated**: All tests updated for new package structure.
- **Added**: Comprehensive service layer tests (`test_services.py`, `test_backend_app_flow.py`).
- **Updated**: Docker configurations for new package paths.
- **Updated**: Documentation reflecting new architecture.

### **Key Commits in v0.3.0**

`1fa2a32`, `48ea90a`, `47409ab`, `c18340b`, `0c9315d`

---

## **v0.2.0** - *27-11-2025*

### Brief Description (v0.2.0)

Feature and UX-focused minor release adding configuration via `.env.example`, improving the WebUI conversion controls, and hardening progress/error handling.

### **New Features in v0.2.0**

- **Added**: `.env.example` configuration template for `TMP_BASE_DIR`, `JOB_TTL_SECONDS`, and `FFMPEG_MAX_CONCURRENT`.
- **Enhanced**: Developer onboarding via clearer configuration and documentation.

### **Bug Fixes in v0.2.0**

- **Fixed**: Progress polling edge cases that could leave the progress bar stuck.
  - **Issue**: Intermittent network or backend glitches could cause polling to fail without retries.
  - **Root Cause**: Missing retry logic and limited error handling around `/progress` requests.
  - **Solution**: Added retry logic and more robust handling of polling failures.
- **Fixed**: Fragile video conversion error handling.
  - **Issue**: Some ffmpeg failures were not surfaced clearly to the client.
  - **Root Cause**: Limited parsing and propagation of ffmpeg errors.
  - **Solution**: Improved error tracking and reporting during conversion.

### **Improvements in v0.2.0**

- **Improved**: Conversion controls with better animations, focus visibility, and responsive design.
- **Updated**: Documentation and project overview to explain the end-to-end workflow and data flow.
- **Updated**: `.gitignore` to better exclude temporary and generated files.
- **Improved**: Test coverage for job cleanup, concurrency limiting, and scale validation.

### **Key Commits in v0.2.0**

`9c0498e`, `8429e82`, `2933906`, `b091f11`, `0c0e8a3`

---

## **v0.1.0** - *26-11-2025*

### Brief Description (v0.1.0)

Initial public release of `vid2gif-webui`, providing a self-hosted web interface for video-to-GIF conversion.

### **New Features in v0.1.0**

- **Added**: FastAPI backend with `/convert`, `/progress`, and `/download` endpoints.
- **Added**: WebUI for uploading videos, trimming clips, and configuring scale/FPS.
- **Added**: Basic concurrent conversion handling and temporary job storage.

### **Bug Fixes in v0.1.0**

- N/A (initial release).

### **Improvements in v0.1.0**

- N/A (baseline implementation).

### **Key Commits in v0.1.0**

Initial import and setup of the repository.

---

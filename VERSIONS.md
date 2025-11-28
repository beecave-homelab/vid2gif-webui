# VERSIONS.md

## ToC

- [v0.3.0 (Current)](#v030-current---28-11-2025)
- [v0.2.0](#v020---27-11-2025)
- [v0.1.0](#v010---26-11-2025)

## **v0.3.0** (Current) - *28-11-2025*

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

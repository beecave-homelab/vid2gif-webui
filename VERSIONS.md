# VERSIONS.md

## ToC

- [v0.2.0 (Current)](#v020-current---27-11-2025)
- [v0.1.0](#v010---26-11-2025)

## **v0.2.0** (Current) - *27-11-2025*

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

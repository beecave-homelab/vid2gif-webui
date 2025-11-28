# vid2gif-webui

Self-hosted web app for converting video files into animated GIFs using ffmpeg.

This project gives you a simple, browser-based interface for turning short video clips into GIFs. You can upload multiple videos at once, trim each clip, choose the output size and frame rate, and then download the generated GIFs directly from your browser. Everything runs on your own machine or server.

## Quick Start

If you just want to run the app and use the web interface, the easiest way is Docker.

### Option 1: Run with Docker (recommended)

1. Make sure Docker and Docker Compose are installed.
2. Clone the repository:

   ```bash
   git clone https://github.com/beecave-homelab/vid2gif-webui.git
   cd vid2gif-webui
   ```

3. Start the service:

   ```bash
   # Production-style setup (Gunicorn on port 8080)
   docker compose up --build
   ```

4. Open your browser at:

   - `http://localhost:8080`

### Option 2: Run locally with Python

Use this if you prefer running the backend directly on your machine.

1. Install [PDM](https://pdm.fming.dev/latest/) and make sure `ffmpeg` is installed and in your `PATH`.
2. Clone the repository and install dependencies:

   ```bash
   git clone https://github.com/beecave-homelab/vid2gif-webui.git
   cd vid2gif-webui
   pdm install
   ```

3. Start the production/development server:

   ```bash
   pdm run start

   # Development server (Uvicorn with reload)
   pdm run start-dev
   ```

4. Open your browser at:

   - `http://localhost:8080` (production)
   - `http://localhost:8081` (development)

## Using the Web Interface

Once the app is running (via Docker or locally):

1. Open the URL in your browser (usually `http://localhost:8080` or `http://localhost:8081` in dev Docker).
2. **Add videos**:
   - Drag & drop one or more video files into the large drop zone, **or**
   - Click the drop zone and pick files from your computer.
3. **Adjust start and end times per video**:
   - Each video shows its own preview.
   - Use the *Start* and *End* sliders or numeric inputs to trim your clip.
   - The time display shows: start, end, selected duration, and total duration.
4. **Choose output options**:
   - **Scale**: pick `Original` or a target width (e.g. 320px, 720px, up to 4K).
   - **FPS**: choose frames per second between 1 and 20 (10 is a good default).
5. **Start conversion**:
   - Click **Create GIF**.
   - The app will upload your videos and start converting them in the background.
6. **Watch progress**:
   - A progress bar shows the current file’s percentage and an estimated time.
   - Status text will tell you whether files are still converting, completed with errors, or finished.
7. **Download your GIFs**:
   - When a job finishes, download links appear below the progress bar.
   - Click a link to download each generated GIF.

## Configuration (Optional)

Most users can just run the app as-is. If you want to tune behavior (for example, where temporary files are stored or how many conversions run at once), you can change a few environment variables.

The recommended way is to start from the provided `.env.example` file in the project root:

1. Copy it to `.env`:

   ```bash
   cp .env.example .env
   ```

2. Open `.env` in a text editor and adjust the values as needed.

These variables are read once at startup by the backend (via the process environment):

| Variable                | Default | What it controls                               |
|-------------------------|---------|-----------------------------------------------|
| `TMP_BASE_DIR`          | `tmp`   | Where temporary job folders and GIFs are kept |
| `JOB_TTL_SECONDS`       | `3600`  | How long to keep finished jobs (in seconds)   |
| `FFMPEG_MAX_CONCURRENT` | `4`     | Max number of videos converted at the same time |

How you load the values from `.env` depends on how you run the app:

- **Local/PDM**: ensure the variables from `.env` are present in your shell environment before running `pdm run start` or `pdm run start-dev` (for example by exporting them in your shell profile or using a tool like `direnv`).
- **Docker/Compose**: you can wire these variables into the container using your own `docker-compose` override (for example with `env_file: .env` or explicit `environment:` entries).

## Troubleshooting

No GIFs are produced / conversions fail immediately:

- Make sure `ffmpeg` is installed if you are running locally.
- In Docker, ffmpeg is installed inside the image by default.

Progress bar never moves:

- Check that the backend is reachable (open browser dev tools → Network → `/progress` requests).
- If the job ID is invalid or expired, you may see a message that the job was not found.

Disk fills up with temporary GIFs:

- Jobs and their temporary directories are cleaned up after `JOB_TTL_SECONDS`.
- Lower the TTL if you run many conversions and do not need to keep results for long.

Port already in use:

- Change the exposed port in `docker-compose.yaml` or run the dev server on another port:

  ```bash
  uvicorn backend.app:app --host 0.0.0.0 --port 8081 --reload
  ```

## For Developers

If you are interested in the internal architecture, API details, testing, or coding standards:

- See **`project-overview.md`** for a full technical overview:
  - Backend and frontend architecture
  - API endpoints and example payloads
  - Testing strategy and coverage
  - Docker images and development workflows
- See **`AGENTS.md`** for coding rules (Ruff, Pytest, SOLID, configuration guidelines).

These documents are the single source of truth for development and contribution details.

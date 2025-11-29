# ─── Runtime Stage ─────────────────────────────────────────────────────────────
FROM python:3.13-slim
# Install ffmpeg & build tools (gcc is needed for some optional uvicorn deps)
RUN apt-get update && apt-get install -y ffmpeg gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Backend Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (will be overlaid by volumes in docker-compose)
COPY ./vid2gif /app/vid2gif

EXPOSE 8080
# Default command reflecting the structure used in compose
CMD ["gunicorn", "vid2gif.backend.app:app", "--bind", "0.0.0.0:8080"] 
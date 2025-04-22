# ─── Runtime Stage ─────────────────────────────────────────────────────────────
FROM python:3.10-slim
# Install ffmpeg & build tools (gcc is needed for some optional uvicorn deps)
RUN apt-get update && apt-get install -y ffmpeg gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Backend Dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (will be overlaid by volumes in docker-compose)
COPY ./backend /app/backend
COPY ./frontend /app/frontend

EXPOSE 8000
# Default command reflecting the structure used in compose
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"] 
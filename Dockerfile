# Slim Python base. Works on both amd64 and arm64 (Raspberry Pi 64-bit OS).
FROM python:3.11-slim-bookworm

# Which Moonshine model to use: "tiny" (bundled, offline) or "base" (downloaded).
ARG MOONSHINE_MODEL=tiny

ENV MOONSHINE_MODEL=${MOONSHINE_MODEL} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Keep thread count modest for a 4-core Pi.
    OMP_NUM_THREADS=4

# libsndfile1: audio decoding for soundfile.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so this layer is cached across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# Default: run the HTTP service. Override the command to use the CLI, e.g.
#   docker run --rm -v "$PWD/samples:/data" computah-moonshine \
#       python -m app.transcribe /data/recording.wav
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8000"]

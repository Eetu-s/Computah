# Slim Python base. Works on both amd64 and arm64 (Raspberry Pi 64-bit OS).
FROM python:3.11-slim-bookworm

# Which Moonshine model to use: "tiny" (bundled, offline) or "base" (downloaded).
ARG MOONSHINE_MODEL=tiny

ENV MOONSHINE_MODEL=${MOONSHINE_MODEL} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Keep thread count modest for a 4-core Pi.
    OMP_NUM_THREADS=4

# libportaudio2: microphone capture for the mic listener (sounddevice).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so this layer is cached across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core.py listen.py ./

# Listen to the microphone and POST completed sentences to POST_URL.
CMD ["python", "listen.py"]

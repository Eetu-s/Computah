# Slim Python base. Works on both amd64 and arm64 (Raspberry Pi 64-bit OS).
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# libportaudio2: microphone capture (sounddevice).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so this layer is cached across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Listen to the mic; send each utterance to Gemma 4; run the tool it picks.
CMD ["python", "agent.py"]

# Raspberry Pi 5 runs 64-bit; python:*-slim is multi-arch and resolves to
# linux/arm64 on the Pi. All deps are pure-Python wheels, so no build tools
# are needed and the image stays small.
FROM python:3.12-slim

LABEL org.opencontainers.image.title="computah-cast" \
      org.opencontainers.image.description="Host an image on a Raspberry Pi and display it on a Hisense VIDAA TV"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    IMAGE_PATH=/data/current.jpg \
    HTTP_PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

CMD ["python", "app.py"]

# Tiny, dependency-free receiver. Pure Python stdlib — no pip install needed.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PORT=9000

WORKDIR /app
COPY app.py .
COPY commands ./commands

EXPOSE 9000

CMD ["python", "app.py"]

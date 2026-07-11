# Convenience targets. On the Raspberry Pi, `make build && make up` is enough.

IMAGE ?= computah-moonshine
MODEL ?= tiny
FILE  ?= samples/beckett.wav

.PHONY: build up down logs transcribe health cross-build

# Build the image natively (run this on the Pi, or on any 64-bit machine).
build:
	docker build --build-arg MOONSHINE_MODEL=$(MODEL) -t $(IMAGE) .

# Build for the Pi (arm64) from an x86 machine using buildx.
cross-build:
	docker buildx build --platform linux/arm64 \
		--build-arg MOONSHINE_MODEL=$(MODEL) -t $(IMAGE) --load .

# Start the HTTP service (http://localhost:8000).
up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

health:
	curl -s http://localhost:8000/health

# Transcribe a file via the running HTTP service: make transcribe FILE=samples/x.wav
transcribe:
	curl -s -F "file=@$(FILE)" http://localhost:8000/transcribe

# Transcribe a file with the one-shot CLI (no server needed).
cli:
	docker run --rm -v "$(PWD)/samples:/data" $(IMAGE) \
		python -m app.transcribe /data/$(notdir $(FILE))

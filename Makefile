# Convenience targets. On the Raspberry Pi, `make build && make up` is enough.

IMAGE ?= computah-moonshine
MODEL ?= tiny

.PHONY: build cross-build up up-stt up-agent down logs

# Build the STT (mic) image natively (run this on the Pi, or any 64-bit machine).
build:
	docker build --build-arg MOONSHINE_MODEL=$(MODEL) -t $(IMAGE) STT

# Build the STT image for the Pi (arm64) from an x86 machine using buildx.
cross-build:
	docker buildx build --platform linux/arm64 \
		--build-arg MOONSHINE_MODEL=$(MODEL) -t $(IMAGE) --load STT

# Start the speech path selected in .env (COMPOSE_PROFILES). Default: stt.
up:
	docker compose up -d --build

# Explicitly start one path (overrides .env for this command).
up-stt:
	COMPOSE_PROFILES=stt docker compose up -d --build

up-agent:
	COMPOSE_PROFILES=agent docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

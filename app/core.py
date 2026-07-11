"""Core transcription logic shared by the CLI and the HTTP server.

Uses the ``moonshine-voice`` package, which ships a prebuilt native inference
library plus the ``tiny-en`` model bundled inside the wheel — so the default
setup runs fully offline with no model download. Audio is decoded with
soundfile and downmixed to mono; the native library resamples to the rate it
needs internally, so we just hand it the samples and their sample rate.

The transcriber is loaded once and cached: the first call pays the load cost,
every call afterwards is fast.
"""

from __future__ import annotations

import functools
import os
from typing import IO, List, Tuple, Union

import numpy as np
import soundfile as sf

# Which model to use: "tiny" (bundled, fast, small — good for a Pi) or "base"
# (more accurate; downloaded on first use, so needs network once). Override
# with the MOONSHINE_MODEL env var.
DEFAULT_MODEL = os.environ.get("MOONSHINE_MODEL", "tiny")

# Language of the model. "en" tiny is bundled in the package.
LANGUAGE = os.environ.get("MOONSHINE_LANGUAGE", "en")

AudioSource = Union[str, os.PathLike, IO[bytes]]


@functools.lru_cache(maxsize=1)
def load_transcriber():
    """Load and cache the Moonshine transcriber for the configured model."""
    # Imported lazily so importing this module (e.g. for --help) stays cheap.
    from moonshine_voice import ModelArch, Transcriber
    from moonshine_voice.utils import get_model_path

    if DEFAULT_MODEL == "tiny" and LANGUAGE == "en":
        # Bundled with the wheel — no download, works offline.
        model_path = str(get_model_path("tiny-en"))
        model_arch = ModelArch.TINY
    else:
        # Any other language/size is fetched (and then cached) on first use.
        from moonshine_voice import get_model_for_language

        wanted = ModelArch.BASE if DEFAULT_MODEL == "base" else ModelArch.TINY
        model_path, model_arch = get_model_for_language(LANGUAGE, wanted)

    return Transcriber(str(model_path), model_arch=model_arch)


def load_audio(source: AudioSource) -> Tuple[List[float], int]:
    """Decode ``source`` (path or file-like) to (mono float samples, sample_rate)."""
    audio, sample_rate = sf.read(source, dtype="float32", always_2d=True)

    # Downmix to mono.
    audio = audio.mean(axis=1)

    return audio.astype(np.float32).tolist(), int(sample_rate)


def transcribe_samples(samples: List[float], sample_rate: int) -> str:
    """Transcribe mono float samples into text."""
    transcriber = load_transcriber()
    transcript = transcriber.transcribe_without_streaming(samples, sample_rate)
    return " ".join(line.text for line in transcript.lines).strip()


def transcribe(source: AudioSource) -> str:
    """Decode an audio file/stream and transcribe it into text."""
    samples, sample_rate = load_audio(source)
    return transcribe_samples(samples, sample_rate)

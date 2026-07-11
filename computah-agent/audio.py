"""Microphone capture and utterance segmentation.

Moonshine brings its own VAD, but this agent deliberately does not go through
Moonshine — Gemma 4 ingests the raw audio — so it has to cut utterances out of
the mic stream itself.

The detector is a plain energy gate against a rolling noise floor. That is
enough for a close-talk mic and keeps the dependency list to sounddevice+numpy
(no native VAD extension to cross-compile for the Pi). It over-triggers in a
noisy room, which is by design: a false trigger costs one Gemma call, and the
wake-word gate in the prompt is what actually decides whether to act.
"""
from __future__ import annotations

import io
import logging
import queue
import wave

import numpy as np
import sounddevice as sd

log = logging.getLogger("computah.audio")

FRAME_MS = 30  # analysis frame; 30 ms @ 16 kHz = 480 samples


def to_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """Pack float32 [-1, 1] mono samples into a 16-bit PCM WAV container.

    Gemma 4's audio encoder wants 16 kHz mono; llama-server wants a real WAV
    file (base64'd), not bare PCM.
    """
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def load_wav(path: str, sample_rate: int) -> bytes:
    """Read a WAV file and re-encode it to the mono 16 kHz WAV Gemma expects."""
    with wave.open(path, "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    if width != 2:
        raise ValueError(f"{path}: need 16-bit PCM WAV, got {width * 8}-bit")

    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32767.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)

    if rate != sample_rate:
        # Linear resample. Fine for speech; avoids pulling in scipy/librosa.
        duration = samples.shape[0] / float(rate)
        target_n = int(duration * sample_rate)
        samples = np.interp(
            np.linspace(0.0, duration, target_n, endpoint=False),
            np.arange(samples.shape[0]) / float(rate),
            samples,
        ).astype(np.float32)
        log.debug("resampled %s from %d Hz to %d Hz", path, rate, sample_rate)

    return to_wav(samples, sample_rate)


class Utterances:
    """Yields one WAV blob per detected utterance, forever.

    Usage:
        for wav in Utterances(cfg):
            ...
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.frame_len = int(cfg.sample_rate * FRAME_MS / 1000)
        self._q: queue.Queue = queue.Queue()

        frames_per_sec = 1000 / FRAME_MS
        self._silence_frames = max(1, int(cfg.silence_sec * frames_per_sec))
        self._preroll_frames = max(1, int(cfg.preroll_sec * frames_per_sec))
        self._max_frames = int(cfg.max_utterance_sec * frames_per_sec)
        self._min_frames = max(1, int(cfg.min_utterance_sec * frames_per_sec))

        # Rolling estimate of room noise, seeded on the first frames.
        self._noise_rms = None

    def _callback(self, indata, _frames, _time, status):
        if status:
            log.debug("mic status: %s", status)
        self._q.put(indata[:, 0].copy())

    def _is_speech(self, rms: float) -> bool:
        if self._noise_rms is None:
            self._noise_rms = rms
            return False

        speech = rms > max(self._noise_rms * self.cfg.vad_threshold, self.cfg.vad_min_rms)
        if not speech:
            # Track the floor only while quiet, so a long sentence can't drag it up.
            self._noise_rms = 0.95 * self._noise_rms + 0.05 * rms
        return speech

    def __iter__(self):
        cfg = self.cfg
        stream = sd.InputStream(
            samplerate=cfg.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.frame_len,
            device=cfg.mic_device,
            callback=self._callback,
        )

        preroll: list[np.ndarray] = []
        captured: list[np.ndarray] = []
        silence_run = 0
        voiced_frames = 0
        capturing = False

        with stream:
            log.info(
                "listening (device=%s, %d Hz)",
                cfg.mic_device if cfg.mic_device is not None else "default",
                cfg.sample_rate,
            )
            while True:
                frame = self._q.get()
                rms = float(np.sqrt(np.mean(np.square(frame))))
                speech = self._is_speech(rms)

                if not capturing:
                    preroll.append(frame)
                    if len(preroll) > self._preroll_frames:
                        preroll.pop(0)
                    if speech:
                        capturing = True
                        captured = list(preroll)  # keep the clipped first word
                        preroll = []
                        silence_run = 0
                        voiced_frames = 1
                        log.debug("utterance start (rms=%.4f)", rms)
                    continue

                captured.append(frame)
                silence_run = 0 if speech else silence_run + 1
                voiced_frames += 1 if speech else 0

                done = silence_run >= self._silence_frames
                truncated = len(captured) >= self._max_frames
                if not (done or truncated):
                    continue

                if truncated:
                    log.warning(
                        "utterance hit the %.0fs cap — sending it truncated",
                        cfg.max_utterance_sec,
                    )

                # Drop the trailing silence we used to detect the end.
                clip = captured if truncated else captured[: -self._silence_frames]
                capturing = False
                captured = []

                # Measure the speech, not the clip: the clip always opens with
                # the pre-roll, which would otherwise push every cough past the
                # minimum on its own.
                if voiced_frames < self._min_frames:
                    log.debug("ignoring blip (%d voiced frames)", voiced_frames)
                    continue

                samples = np.concatenate(clip)
                log.info("utterance: %.1fs", samples.shape[0] / cfg.sample_rate)
                yield to_wav(samples, cfg.sample_rate)

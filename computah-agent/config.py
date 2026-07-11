"""Environment-driven configuration for computah-agent.

Same convention as computah-cast: every setting is an environment variable so
the whole service is configured from the Docker `environment:` block.
"""
import os


def _bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class Config:
    def __init__(self, env=None):
        env = env or os.environ

        # --- Gemma 4 (llama.cpp server) --------------------------------------
        # OpenAI-compatible endpoint. Point this at a beefier LAN box if the Pi
        # is too slow; the agent itself is tiny and can stay on the Pi.
        self.llama_url = env.get("LLAMA_URL", "http://llama:8080").rstrip("/")
        # llama-server ignores the model name, but it must be present.
        self.llama_model = env.get("LLAMA_MODEL", "gemma-4")
        self.llama_timeout = int(env.get("LLAMA_TIMEOUT", "120"))
        self.temperature = float(env.get("LLAMA_TEMPERATURE", "0"))

        # --- Microphone ------------------------------------------------------
        # Gemma 4's audio encoder expects 16 kHz mono; do not change.
        self.sample_rate = 16000
        _dev = env.get("MIC_DEVICE")
        self.mic_device = int(_dev) if _dev not in (None, "") else None

        # --- Utterance segmentation (energy VAD) -----------------------------
        # Speech is detected when a frame's RMS rises this far above the
        # rolling noise floor. Raise it if a noisy room self-triggers.
        self.vad_threshold = float(env.get("VAD_THRESHOLD", "3.0"))
        # Absolute floor, so a silent room can't make the ratio trigger on hiss.
        self.vad_min_rms = float(env.get("VAD_MIN_RMS", "0.012"))
        # Silence needed to consider the utterance finished.
        self.silence_sec = float(env.get("SILENCE_SEC", "0.8"))
        # Audio kept from *before* the trigger, so the first word isn't clipped.
        self.preroll_sec = float(env.get("PREROLL_SEC", "0.4"))
        # Shorter than this is a click/cough, not speech.
        self.min_utterance_sec = float(env.get("MIN_UTTERANCE_SEC", "0.4"))
        # Gemma 4 accepts at most 30 s of audio — hard cap, don't raise.
        self.max_utterance_sec = min(float(env.get("MAX_UTTERANCE_SEC", "15")), 30.0)

        # --- Behaviour -------------------------------------------------------
        # The model only acts when it hears this word; "" disables the gate and
        # every utterance is treated as a command.
        self.wake_word = env.get("WAKE_WORD", "computah").strip()
        # Log the chosen tool but don't run it. Useful for tuning the mic.
        self.dry_run = _bool(env.get("DRY_RUN"), False)
        self.log_level = env.get("LOG_LEVEL", "INFO").upper()

        # --- Tool targets ----------------------------------------------------
        # Base URL of the computah-cast REST API (see ../computah-cast).
        self.cast_url = env.get("CAST_URL", "http://localhost:8000").rstrip("/")
        self.cast_timeout = int(env.get("CAST_TIMEOUT", "30"))

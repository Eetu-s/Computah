"""Model resolution for the Moonshine microphone listener.

Picks which Moonshine model to use. The default ``tiny-en`` model is bundled
inside the ``moonshine-voice`` wheel, so it works offline with no download.
"""

from __future__ import annotations

import os

# Which model to use: "tiny" (bundled, fast, small — good for a Pi) or "base"
# (more accurate; downloaded on first use, so needs network once).
DEFAULT_MODEL = os.environ.get("MOONSHINE_MODEL", "tiny")

# Language of the model. "en" tiny is bundled in the package.
LANGUAGE = os.environ.get("MOONSHINE_LANGUAGE", "en")


def resolve_model():
    """Return (model_path, model_arch) for the configured model."""
    # Imported lazily so importing this module (e.g. for --help) stays cheap.
    from moonshine_voice import ModelArch
    from moonshine_voice.utils import get_model_path

    if DEFAULT_MODEL == "tiny" and LANGUAGE == "en":
        # Bundled with the wheel — no download, works offline.
        return str(get_model_path("tiny-en")), ModelArch.TINY

    # Any other language/size is fetched (and then cached) on first use.
    from moonshine_voice import get_model_for_language

    wanted = ModelArch.BASE if DEFAULT_MODEL == "base" else ModelArch.TINY
    model_path, model_arch = get_model_for_language(LANGUAGE, wanted)
    return str(model_path), model_arch

#!/usr/bin/env python3
"""Single source of truth for the PLANNER BRAIN — the LLM that plans the storyboard.

Operator-selectable, EXACTLY three options, all routed through OpenRouter
(OpenAI-compatible). This is NOT scene["model"] (the seedance/gpt_image media
generators); it is the LLM that decomposes a brief into a scene plan.

Default = super-free ($0) so a build never accidentally bills planner tokens.

All three slugs verified live against GET https://openrouter.ai/api/v1/models
(2026-06-21). OpenRouter is OpenAI-compatible: same chat-completions body + response
shape as the legacy build.nvidia.com endpoint, so only the base URL, the model slug,
and the auth key (OPENROUTER_API_KEY) change.
"""
import os

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# key -> {label, slug, paid, price per 1M tokens (prompt, completion)}
BRAINS = {
    "ultra-paid": {
        "label": "Nemotron 3 Ultra (paid)",
        "slug": "nvidia/nemotron-3-ultra-550b-a55b",
        "paid": True,
        "price_per_1m": {"prompt": 0.50, "completion": 2.20},
    },
    "super-free": {
        "label": "Nemotron 3 Super (free)",
        "slug": "nvidia/nemotron-3-super-120b-a12b:free",
        "paid": False,
        "price_per_1m": {"prompt": 0.0, "completion": 0.0},
    },
    "super-paid": {
        "label": "Nemotron 3 Super (paid)",
        "slug": "nvidia/nemotron-3-super-120b-a12b",
        "paid": True,
        "price_per_1m": {"prompt": 0.09, "completion": 0.45},
    },
}

DEFAULT_BRAIN = "super-free"
VALID_BRAINS = tuple(BRAINS.keys())


def normalize_brain(brain):
    """Coerce any input to a valid brain key; unknown/empty -> DEFAULT_BRAIN ($0)."""
    b = str(brain or "").strip().lower()
    return b if b in BRAINS else DEFAULT_BRAIN


def brain_def(brain):
    """Return the {label, slug, paid, price_per_1m} record for a (normalized) brain."""
    return BRAINS[normalize_brain(brain)]


def brain_endpoint():
    """OpenRouter chat-completions endpoint (OpenAI-compatible)."""
    return OPENROUTER_URL


def brain_key():
    """OpenRouter API key. `zsh -lc` / `source ~/.zshrc` both provide it."""
    return os.environ.get("OPENROUTER_API_KEY")

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
    # --- Non-Nemotron brains (bake-off / post-hackathon economical alternatives) ---
    # All OpenAI-compatible via OpenRouter; slugs verified live 2026-07-17. Added so
    # the same call_model path can A/B copy quality vs the Nemotron baseline. Default
    # brain is unchanged (super-free); these are opt-in only.
    "sonnet5": {
        "label": "Claude Sonnet 5 (paid)",
        "slug": "anthropic/claude-sonnet-5",
        "paid": True,
        "price_per_1m": {"prompt": 2.00, "completion": 10.00},
    },
    "kimi-k2": {
        "label": "Kimi K2 (paid)",
        "slug": "moonshotai/kimi-k2",
        "paid": True,
        "price_per_1m": {"prompt": 0.57, "completion": 2.30},
    },
    "deepseek-v3": {
        "label": "DeepSeek V3.2 (paid)",
        "slug": "deepseek/deepseek-v3.2",
        "paid": True,
        "price_per_1m": {"prompt": 0.27, "completion": 0.40},
    },
    "kimi-k26": {
        "label": "Kimi K2.6 (paid)",
        "slug": "moonshotai/kimi-k2.6",
        "paid": True,
        "price_per_1m": {"prompt": 0.95, "completion": 4.00},
    },
    "deepseek-v4": {
        "label": "DeepSeek V4 Pro (paid)",
        "slug": "deepseek/deepseek-v4-pro",
        "paid": True,
        "price_per_1m": {"prompt": 0.43, "completion": 0.87},
    },
    "qwen3-max": {
        "label": "Qwen3 Max (paid)",
        "slug": "qwen/qwen3-max",
        "paid": True,
        "price_per_1m": {"prompt": 0.78, "completion": 3.90},
    },
    "gpt52": {
        "label": "GPT-5.2 (paid)",
        "slug": "openai/gpt-5.2",
        "paid": True,
        "price_per_1m": {"prompt": 1.75, "completion": 14.00},
    },
    # Nous Hermes — the Conversion Read (page diagnosis) runs on Hermes; planning
    # stays on Nemotron. hermes (3 405B) is the $0 default analyze brain.
    "hermes": {
        "label": "Nous Hermes 3 405B (free)",
        "slug": "nousresearch/hermes-3-llama-3.1-405b:free",
        "paid": False,
        "price_per_1m": {"prompt": 0.0, "completion": 0.0},
    },
    "hermes-405b": {
        "label": "Nous Hermes 4 405B (paid)",
        "slug": "nousresearch/hermes-4-405b",
        "paid": True,
        "price_per_1m": {"prompt": 1.00, "completion": 3.00},
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

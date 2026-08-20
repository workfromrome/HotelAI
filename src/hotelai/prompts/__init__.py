"""Loads LLM prompt templates from src/hotelai/prompts/*.md, so prompt text lives in
files instead of being embedded in code (AGENTS.md: prompts must be editable without
touching Python). Callers `.format(...)` the result themselves when a template has
placeholders (e.g. `{fallback_message}`)."""
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Reads `<name>.md` from this directory and returns its stripped contents."""
    return (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()

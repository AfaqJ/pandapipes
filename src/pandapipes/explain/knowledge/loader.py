"""
Knowledge loader — reads curated Markdown files and returns relevant sections.

Matching strategy (MVP): keyword overlap between the error text and
file/section content. No ML, no embeddings, instant.
"""

from __future__ import annotations

import re
from pathlib import Path

# Directory containing the curated .md files.
_PACK_DIR = Path(__file__).parent / "pack"

# Cache: filename → file content (loaded once on first use).
_cache: dict[str, str] = {}


def load_relevant(error_type: str, error_msg: str, max_chars: int = 800) -> str:
    """
    Return a curated knowledge excerpt relevant to the given error.

    Parameters
    ----------
    error_type : str
        Exception class name, e.g. ``"PipeflowNotConverged"``.
    error_msg : str
        Exception message string.
    max_chars : int
        Truncate the returned excerpt to this many characters.

    Returns
    -------
    str
        Relevant knowledge text, or empty string if nothing matched.
    """
    _ensure_cache()

    # Build a set of keywords from the error — lowercase, split on non-alpha.
    raw_terms = f"{error_type} {error_msg}".lower()
    keywords = set(re.split(r"[^a-z0-9]+", raw_terms)) - _STOP_WORDS

    best_file: str | None = None
    best_score: int = 0

    for filename, content in _cache.items():
        score = _score(content.lower(), keywords)
        if score > best_score:
            best_score = score
            best_file = filename

    if best_file is None or best_score == 0:
        return ""

    text = _cache[best_file]
    # Truncate cleanly on a line boundary.
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0] + "\n..."

    return text


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "", "a", "an", "the", "is", "in", "at", "of", "to", "and",
    "or", "not", "no", "for", "with", "this", "that", "from",
    "by", "be", "are", "was", "were", "has", "have",
}


def _ensure_cache() -> None:
    """Load all .md files from the pack directory into memory (once)."""
    if _cache:
        return
    if not _PACK_DIR.exists():
        return
    for md_file in sorted(_PACK_DIR.glob("*.md")):
        try:
            _cache[md_file.name] = md_file.read_text(encoding="utf-8")
        except Exception:
            pass


def _score(content: str, keywords: set[str]) -> int:
    """Count how many keywords appear in `content`."""
    return sum(1 for kw in keywords if kw and len(kw) > 2 and kw in content)

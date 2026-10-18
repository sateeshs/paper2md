"""Reject degenerate LLM explanations before they reach the database.

Weak or overloaded models fail in ways that still look like success: they echo
the prompt's field template back ("{what_it_computes text}"), return an empty
field, or fall into a repetition loop that runs to the token ceiling. All of
these parse as valid JSON, so without an explicit check they are written as
real explanations and surface on the site.
"""

from __future__ import annotations

import json
import re

# The model echoing a field template instead of answering: "{what_it_computes}"
# or "{what_it_computes text}".
_PLACEHOLDER_RE = re.compile(r"^\s*\{[a-z_]+(?:\s+text)?\}\s*$", re.IGNORECASE)

# Fields that carry no meaning if blank — an explanation without these is not
# an explanation.
REQUIRED_FIELDS = ("what_it_computes",)

# A repetition loop is the failure mode behind max_tokens truncation.
_MIN_LEN_FOR_REPETITION_CHECK = 400
# Tuned to catch true loops ("for for for…" is ~0.3% unique) without flagging
# legitimately repetitive prose, which lands around 8% on short vocabularies.
_MAX_REPEAT_RATIO = 0.05   # unique words / total words below this is degenerate
_MAX_CONSECUTIVE_REPEATS = 20


def _repetition_defect(text: str) -> str | None:
    """Detect a model stuck repeating itself."""
    if len(text) < _MIN_LEN_FOR_REPETITION_CHECK:
        return None

    words = text.split()
    if not words:
        return None

    unique_ratio = len(set(words)) / len(words)
    if unique_ratio < _MAX_REPEAT_RATIO:
        return f"repetition loop (only {unique_ratio:.0%} unique words)"

    run, previous = 1, None
    for word in words:
        run = run + 1 if word == previous else 1
        if run > _MAX_CONSECUTIVE_REPEATS:
            return f"repetition loop ({word!r} repeated {run}x)"
        previous = word

    return None


def find_defect(explanation: str | None) -> str | None:
    """Return a reason the explanation is unusable, or None when it is fine."""
    if not explanation or not explanation.strip():
        return "empty explanation"

    try:
        parsed = json.loads(explanation)
    except (json.JSONDecodeError, TypeError):
        return "unparseable JSON"

    if not isinstance(parsed, dict):
        return f"expected a JSON object, got {type(parsed).__name__}"

    for field in REQUIRED_FIELDS:
        value = parsed.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"missing or empty {field}"

    for field, value in parsed.items():
        if not isinstance(value, str):
            continue
        if _PLACEHOLDER_RE.match(value):
            return f"placeholder text in {field}"
        defect = _repetition_defect(value)
        if defect:
            return f"{defect} in {field}"

    return None


def is_usable(explanation: str | None) -> bool:
    """True when the explanation is worth storing."""
    return find_defect(explanation) is None

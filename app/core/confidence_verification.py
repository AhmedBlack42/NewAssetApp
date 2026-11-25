"""Central confidence verification rules."""
from __future__ import annotations

DEFAULT_VERIFICATION_THRESHOLD = 0.77


def model_verified(confidence: float | None, threshold: float = DEFAULT_VERIFICATION_THRESHOLD) -> bool:
    """Return True only for a finite raw/model score strictly above the threshold."""
    if confidence is None:
        return False
    try:
        score = float(confidence)
    except (TypeError, ValueError):
        return False
    return 0.0 <= score <= 1.0 and score > float(threshold)

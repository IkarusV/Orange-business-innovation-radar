"""Zero-token pre-filter: keep only articles containing at least one tech-signal
keyword. More aggressive than the blocklist (rejects by default, not by exception).
"""
from .prefilter_blocklist import TECH_KEYWORDS


def passes_whitelist(title: str, summary: str = None) -> bool:
    """True = send onward (keep, a tech keyword was found). False = reject."""
    text = f"{title or ''} {summary or ''}".lower()
    return any(kw in text for kw in TECH_KEYWORDS)

"""Zero-token pre-filter: reject articles matching known no-tech-signal patterns,
unless a tech keyword is present (escape hatch always wins). Grounded in real
no_match examples from the article_classifications table, not guessed.
"""
import re

# Tech-signal terms (escape hatch): if any of these appear, never blocklist,
# regardless of category/pattern match below. English-only — see caveat in
# opportunity_classifier/README.md about non-English TED notices.
TECH_KEYWORDS = [
    "ai ", "artificial intelligence", "machine learning", " ml ", "generative ai", "llm",
    "chatbot", "agentic", "ai agent", "iot", "internet of things", "sensor", "telematics",
    "cloud", "data platform", "data lake", "digital twin", "robot", "robotic", "automat",
    "cybersecurity", "cyber security", "zero trust", "biometric", "blockchain",
    "distributed ledger", "computer vision", "image recognition", "nlp",
    "natural language processing", "speech recognition", "voice assistant",
    "predictive", "anomaly detection", "5g", "edge computing", "rfid",
    "asset tracking", "autonomous vehicle", "drone", "ar/vr", "augmented reality",
    "virtual reality", "e-invoicing", "peppol", "warehouse automation", "smart",
    "connect", "digital", "platform", "software", "algorithm", "analytics",
    "scada", "reinforcement learning", "deep learning", "neural network",
]

# (country prefix ignored) category phrases seen repeatedly producing no_match,
# with no tech content, in a large random sample. Conservative: category alone
# never triggers rejection if TECH_KEYWORDS matched above.
BLOCKLIST_CATEGORY_PATTERNS = [
    r"insurance (services|brokerage)",
    r"hotel[- ]?(guesthouse )?accommodation",
    r"unrestricted-clientele restaurant",
    r"school catering services",
    r"road salt\b",
    r"(fuel oils|unleaded petrol|wood fuels)",
    r"non-residential property renting or leasing",
    r"road-sweeping vehicles",
    r"facade work",
    r"installation of doors\b",
    r"financial consultancy services",
    r"expert witness services",
    r"relocation services",
    r"park(s)? maintenance services",
    r"planting and maintenance services",
    r"^motor vehicles$",
    r"military vehicles and associated parts",
    r"pharmaceutical products$",
    r"blood-testing reagents",
    r"^ambulances$",
    r"port and forwarding agency services",
    r"retail trade services$",
    r"^construction work$",
]

# RSS/gnews headline patterns: personnel moves, macro-economics, legislation,
# generic PR fluff — none of these describe a technology deployment.
BLOCKLIST_TEXT_PATTERNS = [
    r"\binsurance moves\b",
    r"\bretires\b",
    r"\bhonou?red for\b",
    r"\bjoins as\b",
    r"\bnames new\b",
    r"\bappoints\b",
    r"\bpmi\b",
    r"\binflation\b",
    r"\btariffs?\b",
    r"\bgdp\b",
    r"\bcelebrates\b",
    r"\brecognizes\b",
    r"\b\w+ month\b",
    r"\bbill (streamlines|passes|advances)\b",
    r"\blegislation\b",
    r"\bcongressional\b",
    r"\bpolicy memorandum\b",
]

_CATEGORY_RE = re.compile("|".join(BLOCKLIST_CATEGORY_PATTERNS), re.IGNORECASE)
_TEXT_RE = re.compile("|".join(BLOCKLIST_TEXT_PATTERNS), re.IGNORECASE)


def passes_blocklist(title: str, summary: str = None) -> bool:
    """True = send onward (keep). False = reject as presumed no_match, zero-cost."""
    text = f"{title or ''} {summary or ''}".lower()

    if any(kw in text for kw in TECH_KEYWORDS):
        return True  # escape hatch always wins

    if _CATEGORY_RE.search(title or ""):
        return False
    if _TEXT_RE.search(title or ""):
        return False
    return True

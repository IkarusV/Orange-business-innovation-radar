import os
from dotenv import load_dotenv

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
if not TAVILY_API_KEY:
    raise ValueError("TAVILY_API_KEY manquante dans le fichier .env")

# =========================
# ORANGE BUSINESS CONTEXT
# =========================

ORANGE_DOMAINS = [
    "Smart Industries",
    "Connectivity Solutions",
    "Cybersecurity",
    "Cloud",
    "Customer Experience",
    "Employee Experience",
]

VERTICALS = [
    "Manufacturing",
    "Retail",
    "Finance",
    "Insurance",
    "Public Sector",
    "Defense",
    "Automotive",
    "Transportation & Logistics",
    "Construction",
    "Lifesciences",
    "Energy",
    "Wholesale",
    "Media & Entertainment",
    "Healthcare",
    "Natural Resources",
    "Aerospace & Defense",
]

PERSONAS = [
    "CIO",
    "IT Executive",
    "Network Executive",
    "Security Executive",
    "CISO",
    "COO",
    "Production Executive",
    "CMO",
    "CX Executive",
    "CDO",
    "Industrial Safety Manager",
    "Quality Manager",
]

USE_CASES = [
    "Energy optimization",
    "Predictive maintenance",
    "Quality inspection",
    "Worker safety",
    "Demand forecasting",
    "Supply chain optimization",
    "Customer service automation",
    "Fraud detection",
    "Cyber threat detection",
    "Network optimization",
    "IT operations automation",
    "Digital workplace",
    "Process automation",
    "Asset tracking",
    "Remote monitoring",
    "Traceability",
    "Compliance monitoring",
    "Predictive analytics",
    "Field service optimization",
    "Production optimization",
]

TECHNOLOGIES = [
    "Artificial Intelligence",
    "Generative AI",
    "Machine Learning",
    "Computer Vision",
    "IoT",
    "Edge Computing",
    "Private 5G",
    "Cloud",
    "Data Platforms",
    "Digital Twins",
    "Robotics",
    "Cybersecurity",
    "Network & SD-WAN",
    "Automation",
]

SIGNAL_TYPES = {
    "trend": "emerging trend future outlook analyst report",
    "buying_signal": "enterprise demand procurement RFP spending adoption",
    "regulation": "regulation legislation policy compliance standards EU",
    "market_move": "market size revenue growth investment funding acquisition partnership",
    "technology_maturity": "technology maturity production deployment enterprise adoption",
    "proof_signal": "pilot deployment customer case study ROI results business outcome",
}

TIME_HORIZONS = {
    "historical": ("2020-01-01", "2023-12-31"),
    "recent": ("2024-01-01", "2026-08-21"),
}

# Keep the prototype affordable.
DISCOVERY_MAX_RESULTS = 3
DEEP_MAX_RESULTS = 5
DISCOVERY_SEARCH_DEPTH = "basic"
DEEP_SEARCH_DEPTH = "advanced"

# Number of candidate combinations to screen.
MAX_CANDIDATES = 120

# Number of opportunities to deep-research.
MAX_DEEP_RESEARCH = 15

# Final radar size.
FINAL_RADAR_SIZE = 10

# Maximum final topics per Orange domain.
MAX_TOPICS_PER_DOMAIN = 3

# Approximate Tavily credit budget for this prototype.
MAX_TAVILY_CREDITS = 300

# Estimated credits according to Tavily's current search model.
SEARCH_CREDIT_COST = {
    "basic": 1,
    "advanced": 2,
}

OUTPUT_JSON = "innovation_radar.json"
OUTPUT_CSV = "innovation_radar.csv"
OUTPUT_HTML = "innovation_radar.html"

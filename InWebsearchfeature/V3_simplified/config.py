import os
from dotenv import load_dotenv

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not TAVILY_API_KEY:
    raise ValueError("TAVILY_API_KEY manquante dans le fichier .env")


# ============================================================
# PARAMETRES DE RECHERCHE
# ============================================================

# Budget maximum pour CE prototype.
# Tu peux mettre 100, 200, 300...
MAX_TAVILY_CREDITS = 100


# Recherche "basic" = moins chère.
# On utilise advanced uniquement si nécessaire.
SEARCH_DEPTH = "basic"

# Nombre maximum de résultats par recherche.
MAX_RESULTS = 5


# ============================================================
# PERIODES
# ============================================================

# On veut volontairement mélanger ancien + récent.
PERIODS = {
    "historical": {
        "start_date": "2020-01-01",
        "end_date": "2023-12-31",
    },

    "recent": {
        "start_date": "2024-01-01",
        "end_date": "2026-08-21",
    },
}


# ============================================================
# RECHERCHES AUTONOMES
# ============================================================

# Ces recherches permettent à Tavily de compléter
# automatiquement une opportunité.
#
# IMPORTANT :
# On reste volontairement sur quelques recherches seulement
# pour économiser les crédits.

AUTONOMOUS_SEARCHES = [
    "market growth",
    "adoption trend",
    "investment funding",
    "historical evolution",
]


# ============================================================
# DIVERSITE
# ============================================================

# Requête permettant de chercher des opportunités
# en dehors de la cybersécurité.

NON_CYBER_QUERY = (
    "emerging business technology opportunities "
    "industry growth adoption investment "
    "-cybersecurity -cyber"
)
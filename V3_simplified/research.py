from datetime import datetime
from tavily import TavilyClient

from V3_simplified.config import (
    TAVILY_API_KEY,
    MAX_TAVILY_CREDITS,
    SEARCH_DEPTH,
    MAX_RESULTS,
    PERIODS,
    AUTONOMOUS_SEARCHES,
    NON_CYBER_QUERY,
)


# ============================================================
# CLIENT TAVILY
# ============================================================

client = TavilyClient(api_key=TAVILY_API_KEY)


# ============================================================
# GESTION DU BUDGET
# ============================================================

class ResearchBudget:

    def __init__(self, max_credits=MAX_TAVILY_CREDITS):

        self.max_credits = max_credits
        self.used = 0

    def can_search(self):

        return self.used + 1 <= self.max_credits

    def spend(self):

        if not self.can_search():
            return False

        self.used += 1
        return True

    def remaining(self):

        return self.max_credits - self.used


# ============================================================
# RECHERCHE TAVILY
# ============================================================

def tavily_search(
    query,
    budget,
    period="recent",
    max_results=MAX_RESULTS,
):
    """
    Effectue une recherche Tavily.

    Chaque résultat conserve :
    - titre
    - URL
    - date
    - contenu
    - score Tavily
    - requête utilisée

    Cela permet ensuite de savoir :
    "D'où vient cette information ?"
    """

    if not budget.spend():

        print("Budget Tavily atteint.")

        return []


    dates = PERIODS[period]


    print()
    print("Recherche Tavily :")
    print(query)
    print("Période :", period)


    try:

        response = client.search(

            query=query,

            search_depth=SEARCH_DEPTH,

            max_results=max_results,

            start_date=dates["start_date"],

            end_date=dates["end_date"],
        )

    except Exception as error:

        print("Erreur Tavily :", error)

        return []


    results = []


    for result in response.get("results", []):

        results.append({

            "query": query,

            "period": period,

            "title": result.get("title"),

            "url": result.get("url"),

            "published_date": result.get(
                "published_date"
            ),

            "score": result.get("score"),

            "content": result.get("content"),

            "retrieved_at": datetime.now().isoformat(),
        })


    return results


# ============================================================
# RECHERCHE SUR MOT-CLE
# ============================================================

def keyword_search(keyword, budget):

    """
    Recherche simple à partir d'un mot-clé.

    Exemple :

    keyword_search(
        "agriculture artificial intelligence",
        budget
    )
    """

    return tavily_search(

        query=keyword,

        budget=budget,

        period="recent",
    )


# ============================================================
# RECHERCHE DE CHIFFRES
# ============================================================

def numeric_search(topic, budget):

    """
    Recherche volontairement orientée vers
    les données quantitatives.

    Exemple :
    "AI agriculture market size CAGR"
    """

    query = (
        f"{topic} "
        "market size "
        "revenue "
        "CAGR "
        "growth rate "
        "adoption rate "
        "forecast"
    )

    return tavily_search(

        query=query,

        budget=budget,

        period="recent",
    )


# ============================================================
# RECHERCHE HISTORIQUE
# ============================================================

def historical_search(topic, budget):

    """
    Recherche volontairement des informations
    plus anciennes.

    Cela permet de compléter les données
    récentes provenant du scraping.
    """

    query = (
        f"{topic} "
        "market evolution "
        "historical trend "
        "adoption "
        "technology development"
    )

    return tavily_search(

        query=query,

        budget=budget,

        period="historical",
    )


# ============================================================
# RECHERCHE AUTONOME
# ============================================================

def autonomous_research(topic, budget):

    """
    Tavily effectue plusieurs recherches
    complémentaires automatiquement.

    Exemple :

    topic = "AI in agriculture"

    Le programme cherchera automatiquement :
    - croissance
    - adoption
    - investissement
    - historique
    """

    all_results = []


    for search_type in AUTONOMOUS_SEARCHES:

        if not budget.can_search():

            break


        query = (
            f"{topic} "
            f"{search_type} "
            "enterprise business"
        )


        results = tavily_search(

            query=query,

            budget=budget,

            period="recent",
        )


        all_results.extend(results)


    # Ajouter une recherche historique.

    if budget.can_search():

        all_results.extend(

            historical_search(
                topic,
                budget
            )
        )


    return all_results


# ============================================================
# RECHERCHE D'OPPORTUNITES HORS CYBERSECURITE
# ============================================================

def search_non_cyber_opportunities(budget):

    """
    Cherche des opportunités technologiques
    sans partir d'un domaine déjà défini.

    L'objectif est d'aider à éviter que le radar
    soit dominé par la cybersécurité.
    """

    return tavily_search(

        query=NON_CYBER_QUERY,

        budget=budget,

        period="recent",
    )
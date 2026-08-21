import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from tavily import TavilyClient


# ============================================================
# 1. CONFIGURATION
# ============================================================

load_dotenv()

API_KEY = os.getenv("TAVILY_API_KEY")

if not API_KEY:
    raise ValueError(
        "Clé Tavily introuvable.\n"
        "Vérifie que ton fichier .env contient :\n"
        "TAVILY_API_KEY=tvly-..."
    )

tavily_client = TavilyClient(api_key=API_KEY)


# ============================================================
# 2. OPPORTUNITY À ANALYSER
# ============================================================

# ============================================================
# MODIFICATION 1 :
# C'est ici que tu peux changer l'Opportunity.
# ============================================================

vertical = "Manufacturing"
use_case = "Energy optimization"
technology = "Computer Vision"

opportunity = f"{vertical} × {use_case} × {technology}"


# ============================================================
# 3. CONFIGURATION GENERALE
# ============================================================

MAX_RESULTS = 5

# "basic" consomme généralement moins que "advanced".
# Pour ton prototype, tu peux utiliser "advanced" pour avoir
# de meilleurs résultats.
SEARCH_DEPTH = "advanced"

# False = moins de données récupérées et plus simple.
INCLUDE_RAW_CONTENT = False

# Petite pause entre les recherches pour éviter d'envoyer
# trop rapidement les requêtes.
DELAY_BETWEEN_SEARCHES = 1


# ============================================================
# 4. PERIODES DE RECHERCHE
# ============================================================

# ============================================================
# MODIFICATION 2 :
# On sépare volontairement :
#
# HISTORIQUE = comprendre l'évolution
# RECENT     = détecter les signaux actuels
# ============================================================

periods = {

    "historical": {
        "start_date": "2020-01-01",
        "end_date": "2024-12-31"
    },

    "recent": {
        "start_date": "2025-01-01",
        "end_date": "2026-08-21"
    }
}


# ============================================================
# 5. TYPES DE SIGNAUX
# ============================================================

# ============================================================
# MODIFICATION 3 :
# Chaque signal possède maintenant une vraie recherche
# spécialisée.
#
# Le but est de ne pas simplement demander :
#
# "computer vision manufacturing"
#
# mais de chercher plusieurs types de preuves.
# ============================================================

signal_queries = {

    "market": (
        f"{vertical} {use_case} {technology} "
        "market size revenue growth CAGR forecast"
    ),

    "technology": (
        f"{vertical} {use_case} {technology} "
        "technology adoption deployment maturity trend"
    ),

    "business": (
        f"{vertical} {use_case} {technology} "
        "investment funding acquisition partnership companies"
    ),

    "proof": (
        f"{vertical} {use_case} {technology} "
        "case study pilot deployment production results ROI"
    ),

    "regulation": (
        f"{vertical} {use_case} {technology} "
        "regulation standards legislation compliance EU"
    )
}


# ============================================================
# 6. RECHERCHES SPECIFIQUES POUR LES CHIFFRES
# ============================================================

# ============================================================
# MODIFICATION 4 :
# On ajoute une recherche dédiée aux données quantitatives.
#
# Cela répond directement à ton besoin :
#
# "rechercher des chiffres"
#
# Exemple :
# - market size
# - CAGR
# - investment
# - adoption rate
# - revenue
# ============================================================

numeric_queries = {

    "market_size": (
        f"{vertical} {use_case} {technology} "
        "market size USD billion revenue"
    ),

    "growth": (
        f"{vertical} {use_case} {technology} "
        "CAGR growth rate forecast 2030"
    ),

    "investment": (
        f"{vertical} {use_case} {technology} "
        "investment funding million billion"
    ),

    "adoption": (
        f"{vertical} {use_case} {technology} "
        "adoption rate percentage companies"
    )
}


# ============================================================
# 7. RECHERCHES POUR LA DIVERSIFICATION
# ============================================================

# ============================================================
# MODIFICATION 5 :
# Le problème que vous avez identifié est important :
#
# votre radar risque de produire énormément de Cybersecurity.
#
# Ici on prépare donc une capacité à chercher volontairement
# des domaines différents.
#
# Pour l'instant, on ne fait pas encore de "IA autonome".
# On fournit simplement des recherches de diversification.
# ============================================================

diversification_queries = [

    f"{vertical} emerging technologies opportunities 2026",

    f"{vertical} emerging technology trends outside cybersecurity",

    f"{vertical} AI automation sustainability opportunities",

    f"{vertical} energy efficiency digital transformation opportunities",

    f"{vertical} robotics computer vision industrial innovation",

    f"{vertical} emerging technology market growth new opportunities"
]


# ============================================================
# 8. FONCTION DE RECHERCHE TAVILY
# ============================================================

def search_tavily(
    query,
    signal_type,
    period_name,
    start_date=None,
    end_date=None
):
    """
    Effectue une recherche Tavily et transforme les résultats
    dans une structure exploitable par le futur agent IA.
    """

    print("\n" + "=" * 80)
    print("SIGNAL :", signal_type.upper())
    print("PERIODE :", period_name.upper())
    print("QUERY :", query)
    print("=" * 80)

    search_parameters = {

        "query": query,

        "max_results": MAX_RESULTS,

        "search_depth": SEARCH_DEPTH
    }

    # Dates de publication.
    if start_date:
        search_parameters["start_date"] = start_date

    if end_date:
        search_parameters["end_date"] = end_date

    # Contenu brut optionnel.
    if INCLUDE_RAW_CONTENT:
        search_parameters["include_raw_content"] = True

    try:

        response = tavily_client.search(
            **search_parameters
        )

    except Exception as e:

        print("\nERREUR TAVILY :", e)

        return []


    results = response.get("results", [])

    print(
        "NOMBRE DE RESULTATS :",
        len(results)
    )


    structured_results = []


    for i, result in enumerate(
        results,
        start=1
    ):

        structured_result = {

            "signal_type": signal_type,

            "period": period_name,

            "query": query,

            "title": result.get("title"),

            "url": result.get("url"),

            "date": result.get("published_date"),

            "score": result.get("score"),

            "content": result.get("content")
        }


        structured_results.append(
            structured_result
        )


        # ----------------------------------------------------
        # AFFICHAGE
        # ----------------------------------------------------

        print("\n" + "-" * 80)

        print(
            "RESULTAT",
            i
        )

        print(
            "TITRE :",
            structured_result["title"]
        )

        print(
            "URL :",
            structured_result["url"]
        )

        print(
            "DATE :",
            structured_result["date"]
        )

        print(
            "SCORE :",
            structured_result["score"]
        )


        content = structured_result["content"]


        if content:

            print(
                "CONTENU :",
                content[:700].replace(
                    "\n",
                    " "
                )
            )


    return structured_results


# ============================================================
# 9. DEBUT DU RADAR
# ============================================================

print("\n")

print("#" * 80)
print("INNOVATION RADAR")
print("EXTERNAL RESEARCH PROTOTYPE")
print("#" * 80)


print("\nOPPORTUNITY :")
print(opportunity)


print("\nVERTICAL :", vertical)
print("USE CASE :", use_case)
print("TECHNOLOGY :", technology)


print("\nRecherche externe en cours...")


# Toutes les données seront stockées ici.

all_results = []


# ============================================================
# 10. RECHERCHE PRINCIPALE
# ============================================================

# ============================================================
# MODIFICATION 6 :
#
# On effectue maintenant réellement les recherches pour
# CHAQUE signal et pour CHAQUE période.
#
# Donc :
#
# market     → historique
# market     → récent
# technology → historique
# technology → récent
# etc.
#
# Cela produit une vraie comparaison temporelle.
# ============================================================

for period_name, period in periods.items():

    print("\n")
    print("#" * 80)

    print(
        "PERIODE DE RECHERCHE :",
        period_name.upper()
    )

    print("#" * 80)


    for signal_type, query in signal_queries.items():

        results = search_tavily(

            query=query,

            signal_type=signal_type,

            period_name=period_name,

            start_date=period["start_date"],

            end_date=period["end_date"]
        )


        all_results.extend(
            results
        )


        time.sleep(
            DELAY_BETWEEN_SEARCHES
        )


# ============================================================
# 11. RECHERCHE SPECIFIQUE DES CHIFFRES
# ============================================================

print("\n")
print("#" * 80)
print("QUANTITATIVE RESEARCH")
print("#" * 80)


# ============================================================
# MODIFICATION 7 :
#
# Les recherches de chiffres sont séparées des recherches
# générales.
#
# Cela permettra plus tard à l'IA d'extraire automatiquement :
#
# "Market size = $20B"
# "CAGR = 7.8%"
# etc.
# ============================================================

for numeric_type, query in numeric_queries.items():

    results = search_tavily(

        query=query,

        signal_type=f"numeric_{numeric_type}",

        period_name="recent",

        start_date=periods["recent"]["start_date"],

        end_date=periods["recent"]["end_date"]
    )


    all_results.extend(
        results
    )


    time.sleep(
        DELAY_BETWEEN_SEARCHES
    )


# ============================================================
# 12. ANALYSE DE LA QUALITE DES SOURCES
# ============================================================

print("\n")
print("#" * 80)
print("DATA QUALITY")
print("#" * 80)


total_sources = len(
    all_results
)


sources_with_date = [

    result

    for result in all_results

    if result.get("date")
]


sources_without_date = [

    result

    for result in all_results

    if not result.get("date")
]


sources_with_url = [

    result

    for result in all_results

    if result.get("url")
]


print(
    "\nTOTAL SOURCES :",
    total_sources
)


print(
    "SOURCES AVEC DATE :",
    len(sources_with_date)
)


print(
    "SOURCES SANS DATE :",
    len(sources_without_date)
)


print(
    "SOURCES AVEC URL :",
    len(sources_with_url)
)


# ============================================================
# 13. COUVERTURE DES SIGNAUX
# ============================================================

print("\n")
print("#" * 80)
print("SIGNAL COVERAGE")
print("#" * 80)


signal_coverage = {}


all_signal_types = list(
    signal_queries.keys()
) + [

    f"numeric_{x}"

    for x in numeric_queries.keys()
]


for signal_type in all_signal_types:

    count = sum(

        1

        for result in all_results

        if result["signal_type"] == signal_type

    )


    signal_coverage[
        signal_type
    ] = count


    print(
        f"{signal_type.upper():25} : "
        f"{count} sources"
    )


# ============================================================
# 14. COMPARAISON HISTORIQUE / RECENT
# ============================================================

historical_results = [

    result

    for result in all_results

    if result["period"] == "historical"
]


recent_results = [

    result

    for result in all_results

    if result["period"] == "recent"
]


print("\n")
print("#" * 80)
print("TIME COVERAGE")
print("#" * 80)


print(
    "SOURCES HISTORIQUES :",
    len(historical_results)
)


print(
    "SOURCES RECENTES :",
    len(recent_results)
)


# ============================================================
# 15. DETECTION DES GAPS
# ============================================================

gaps = []


# ------------------------------------------------------------
# Signaux absents
# ------------------------------------------------------------

for signal_type, count in signal_coverage.items():

    if count == 0:

        gaps.append(

            f"Aucun résultat trouvé pour "
            f"le signal '{signal_type}'."

        )


# ------------------------------------------------------------
# Sources sans date
# ------------------------------------------------------------

if len(sources_without_date) > 0:

    gaps.append(

        f"{len(sources_without_date)} "
        "sources n'ont pas de date publiée."

    )


# ------------------------------------------------------------
# Historique
# ------------------------------------------------------------

if len(historical_results) == 0:

    gaps.append(
        "Aucune donnée historique trouvée."
    )


# ------------------------------------------------------------
# Recent
# ------------------------------------------------------------

if len(recent_results) == 0:

    gaps.append(
        "Aucune donnée récente trouvée."
    )


# ============================================================
# 16. GENERATION DE RECHERCHES SUPPLEMENTAIRES
# ============================================================

suggested_searches = []


# ============================================================
# MODIFICATION 8 :
#
# Le système ne se contente plus de chercher.
#
# Il regarde ce qui manque et propose les prochaines
# recherches à effectuer.
#
# C'est la première étape vers ton futur agent intelligent.
# ============================================================


# Régulation insuffisante

if signal_coverage.get(
    "regulation",
    0
) < 3:

    suggested_searches.append(

        f"{vertical} {technology} {use_case} "
        "EU regulation legislation standards"

    )


# Historique insuffisant

if len(historical_results) < 5:

    suggested_searches.append(

        f"{vertical} {use_case} {technology} "
        "historical market adoption 2020 2021 2022 2023 2024"

    )


# Sources sans dates

if len(sources_without_date) > 0:

    suggested_searches.append(

        f"{vertical} {use_case} {technology} "
        "historical report market study"

    )


# Business cases

if signal_coverage.get(
    "business",
    0
) < 3:

    suggested_searches.append(

        f"{vertical} {use_case} {technology} "
        "investment funding acquisition partnership"

    )


# Proof

if signal_coverage.get(
    "proof",
    0
) < 3:

    suggested_searches.append(

        f"{vertical} {use_case} {technology} "
        "real world deployment customer case study ROI"

    )


# ============================================================
# 17. RECHERCHES DE DIVERSIFICATION
# ============================================================

print("\n")
print("#" * 80)
print("DIVERSIFICATION SEARCH IDEAS")
print("#" * 80)


for i, query in enumerate(
    diversification_queries,
    start=1
):

    print(
        f"{i}. {query}"
    )


# On ne lance PAS automatiquement ces recherches.
#
# Pourquoi ?
#
# Parce que demain ton collègue pourra connecter cette partie
# à un agent qui décidera lui-même quand utiliser ces recherches.
#
# Pour l'instant elles constituent les "portes d'entrée"
# vers d'autres opportunités.


# ============================================================
# 18. DETECTION SIMPLE DES THEMES
# ============================================================

# ============================================================
# MODIFICATION 9 :
#
# Première version très simple de la diversification.
#
# On compte quelques mots-clés dans les résultats.
#
# Ce n'est PAS encore une IA.
#
# Mais cela donne déjà une indication permettant de montrer :
#
# "Nous pouvons détecter les thèmes dominants."
# ============================================================

theme_keywords = {

    "cybersecurity": [
        "cybersecurity",
        "cyber security",
        "security",
        "threat",
        "ransomware"
    ],

    "AI": [
        "artificial intelligence",
        "machine learning",
        "AI"
    ],

    "robotics": [
        "robotics",
        "robot",
        "automation"
    ],

    "energy": [
        "energy",
        "electricity",
        "efficiency",
        "sustainability"
    ],

    "computer_vision": [
        "computer vision",
        "machine vision",
        "visual inspection"
    ]
}


theme_counts = {}


for theme, keywords in theme_keywords.items():

    count = 0


    for result in all_results:

        content = (
            result.get("content")
            or ""
        ).lower()


        if any(
            keyword.lower() in content
            for keyword in keywords
        ):

            count += 1


    theme_counts[
        theme
    ] = count


print("\n")
print("#" * 80)
print("THEME DISTRIBUTION")
print("#" * 80)


for theme, count in theme_counts.items():

    print(
        f"{theme:20} : {count} sources"
    )


# ============================================================
# 19. CONSTRUCTION DU RESULTAT FINAL
# ============================================================

radar_output = {

    "opportunity": {

        "vertical": vertical,

        "use_case": use_case,

        "technology": technology,

        "label": opportunity
    },


    "research_date":
        datetime.now().isoformat(),


    "configuration": {

        "max_results_per_query":
            MAX_RESULTS,

        "search_depth":
            SEARCH_DEPTH,

        "historical_period":
            periods["historical"],

        "recent_period":
            periods["recent"]
    },


    "signal_coverage":
        signal_coverage,


    "theme_distribution":
        theme_counts,


    "data_quality": {

        "total_sources":
            total_sources,

        "sources_with_date":
            len(sources_with_date),

        "sources_without_date":
            len(sources_without_date),

        "sources_with_url":
            len(sources_with_url),

        "historical_sources":
            len(historical_results),

        "recent_sources":
            len(recent_results)
    },


    "gaps":
        gaps,


    "suggested_next_searches":
        suggested_searches,


    "diversification_searches":
        diversification_queries,


    # --------------------------------------------------------
    # IMPORTANT :
    # Toutes les sources restent conservées.
    #
    # Cela permettra au futur agent IA de répondre :
    #
    # "D'où vient cette information ?"
    #
    # --------------------------------------------------------

    "sources":
        all_results
}


# ============================================================
# 20. SAUVEGARDE JSON
# ============================================================

output_file = (
    "innovation_radar_research.json"
)


with open(

    output_file,

    "w",

    encoding="utf-8"

) as f:

    json.dump(

        radar_output,

        f,

        ensure_ascii=False,

        indent=2
    )


# ============================================================
# 21. CREATION D'UN RESUME LISIBILE
# ============================================================

# ============================================================
# MODIFICATION 10 :
#
# En plus du JSON technique, on crée un fichier texte facile
# à montrer à ton collègue.
# ============================================================

summary_file = (
    "innovation_radar_summary.txt"
)


with open(

    summary_file,

    "w",

    encoding="utf-8"

) as f:

    f.write(
        "INNOVATION RADAR\n"
    )

    f.write(
        "================\n\n"
    )

    f.write(
        f"Opportunity : {opportunity}\n"
    )

    f.write(
        f"Date : {datetime.now().isoformat()}\n\n"
    )


    f.write(
        "DATA QUALITY\n"
    )

    f.write(
        "------------\n"
    )

    f.write(
        f"Total sources : {total_sources}\n"
    )

    f.write(
        f"Sources avec date : "
        f"{len(sources_with_date)}\n"
    )

    f.write(
        f"Sources sans date : "
        f"{len(sources_without_date)}\n"
    )

    f.write(
        f"Sources historiques : "
        f"{len(historical_results)}\n"
    )

    f.write(
        f"Sources récentes : "
        f"{len(recent_results)}\n\n"
    )


    f.write(
        "SIGNAL COVERAGE\n"
    )

    f.write(
        "---------------\n"
    )


    for signal, count in signal_coverage.items():

        f.write(
            f"{signal} : {count}\n"
        )


    f.write(
        "\nTHEME DISTRIBUTION\n"
    )

    f.write(
        "------------------\n"
    )


    for theme, count in theme_counts.items():

        f.write(
            f"{theme} : {count}\n"
        )


    f.write(
        "\nDATA GAPS\n"
    )

    f.write(
        "---------\n"
    )


    if gaps:

        for gap in gaps:

            f.write(
                f"- {gap}\n"
            )

    else:

        f.write(
            "Aucun gap majeur détecté.\n"
        )


    f.write(
        "\nSUGGESTED NEXT SEARCHES\n"
    )

    f.write(
        "------------------------\n"
    )


    for search in suggested_searches:

        f.write(
            f"- {search}\n"
        )


    f.write(
        "\nSOURCES\n"
    )

    f.write(
        "-------\n"
    )


    for i, result in enumerate(
        all_results,
        start=1
    ):

        f.write(
            f"\n[{i}] "
            f"{result.get('title')}\n"
        )

        f.write(
            f"URL: "
            f"{result.get('url')}\n"
        )

        f.write(
            f"Date: "
            f"{result.get('date')}\n"
        )

        f.write(
            f"Signal: "
            f"{result.get('signal_type')}\n"
        )

        f.write(
            f"Period: "
            f"{result.get('period')}\n"
        )


# ============================================================
# 22. RESUME FINAL
# ============================================================

print("\n")
print("#" * 80)
print("RESEARCH COMPLETE")
print("#" * 80)


print(
    "\nOpportunity :",
    opportunity
)


print(
    "Sources trouvées :",
    total_sources
)


print(
    "Sources avec date :",
    len(sources_with_date)
)


print(
    "Sources sans date :",
    len(sources_without_date)
)


print(
    "Sources historiques :",
    len(historical_results)
)


print(
    "Sources récentes :",
    len(recent_results)
)


print(
    "\nFichier JSON :",
    output_file
)


print(
    "Résumé lisible :",
    summary_file
)


print(
    "\nPrototype terminé."
)


# ============================================================
# 23. RAPPEL POUR LE FUTUR AGENT IA
# ============================================================

print("\n")
print("#" * 80)
print("NEXT STEP — AI AGENT")
print("#" * 80)

print(
    """
Le moteur de recherche est maintenant prêt à être connecté
à un agent IA.

L'agent pourra ensuite :

1. Lire l'Opportunity
2. Lire les résultats Tavily
3. Identifier les chiffres importants
4. Conserver les URLs des sources
5. Identifier les informations manquantes
6. Demander de nouvelles recherches
7. Comparer historique et récent
8. Identifier les thèmes surreprésentés
9. Chercher volontairement d'autres domaines
10. Proposer de nouvelles opportunities
"""
)
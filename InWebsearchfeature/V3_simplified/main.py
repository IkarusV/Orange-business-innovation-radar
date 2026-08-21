import json

from V3_simplified.research import (
    ResearchBudget,
    keyword_search,
    numeric_search,
    historical_search,
    autonomous_research,
    search_non_cyber_opportunities,
)


# ============================================================
# AFFICHAGE DES RESULTATS
# ============================================================

def display_results(results):

    print()
    print("=" * 70)
    print("RESULTATS")
    print("=" * 70)


    if not results:

        print("Aucun résultat.")

        return


    for i, result in enumerate(results, start=1):

        print()
        print(f"[{i}] {result.get('title')}")

        print(
            "Date :",
            result.get("published_date")
            or "date inconnue"
        )

        print(
            "URL :",
            result.get("url")
        )

        print(
            "Score Tavily :",
            result.get("score")
        )

        print()

        content = result.get("content") or ""

        print(content[:500])

        print("-" * 70)


# ============================================================
# SAUVEGARDE
# ============================================================

def save_results(results, filename="tavily_results.json"):

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            results,
            file,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("Résultats sauvegardés dans :", filename)


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():

    print("=" * 70)
    print("TAVILY - ORANGE BUSINESS INNOVATION RADAR")
    print("=" * 70)


    budget = ResearchBudget()


    while True:

        print()
        print("Crédits utilisés :", budget.used)
        print("Crédits restants :", budget.remaining())

        print()
        print("Que veux-tu faire ?")
        print()
        print("1 - Recherche par mot-clé")
        print("2 - Recherche de chiffres")
        print("3 - Recherche historique")
        print("4 - Recherche autonome")
        print("5 - Chercher de nouvelles opportunités hors cybersécurité")
        print("0 - Quitter")


        choice = input(
            "\nTon choix : "
        ).strip()


        # ----------------------------------------------------
        # QUITTER
        # ----------------------------------------------------

        if choice == "0":

            print("Fin du programme.")

            break


        # ----------------------------------------------------
        # MOT-CLE
        # ----------------------------------------------------

        elif choice == "1":

            keyword = input(
                "\nMot-clé ou question : "
            )

            results = keyword_search(
                keyword,
                budget
            )


            display_results(results)

            save_results(results)


        # ----------------------------------------------------
        # CHIFFRES
        # ----------------------------------------------------

        elif choice == "2":

            topic = input(
                "\nSujet pour lequel tu cherches des chiffres : "
            )

            results = numeric_search(
                topic,
                budget
            )


            display_results(results)

            save_results(results)


        # ----------------------------------------------------
        # HISTORIQUE
        # ----------------------------------------------------

        elif choice == "3":

            topic = input(
                "\nSujet à rechercher historiquement : "
            )

            results = historical_search(
                topic,
                budget
            )


            display_results(results)

            save_results(results)


        # ----------------------------------------------------
        # AUTONOME
        # ----------------------------------------------------

        elif choice == "4":

            topic = input(
                "\nSujet / opportunité à approfondir : "
            )

            results = autonomous_research(
                topic,
                budget
            )


            display_results(results)

            save_results(results)


        # ----------------------------------------------------
        # NOUVELLES OPPORTUNITES
        # ----------------------------------------------------

        elif choice == "5":

            results = search_non_cyber_opportunities(
                budget
            )


            display_results(results)

            save_results(
                results,
                "non_cyber_opportunities.json"
            )


        else:

            print(
                "\nChoix incorrect. "
                "Choisis 0, 1, 2, 3, 4 ou 5."
            )


        # ----------------------------------------------------
        # BUDGET
        # ----------------------------------------------------

        if budget.remaining() <= 0:

            print()
            print(
                "Le budget Tavily de ce prototype "
                "est épuisé."
            )

            break


if __name__ == "__main__":

    main()
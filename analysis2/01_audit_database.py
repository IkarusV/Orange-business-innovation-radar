from pathlib import Path
import sqlite3


# ============================================================
# 1. PATH CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PIPELINE_ROOT = (
    PROJECT_ROOT
    / "BeCode_dataOrange-radar-research-pipeline"
)

DB_PATH = (
    PIPELINE_ROOT
    / "data"
    / "articles_analysis.db"
)


# ============================================================
# 2. DATABASE CONNECTION
# ============================================================

def connect_read_only() -> sqlite3.Connection:
    """Open the analysis database without allowing modifications."""

    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found:\n{DB_PATH}"
        )

    connection = sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro",
        uri=True,
    )

    connection.row_factory = sqlite3.Row
    return connection


# ============================================================
# 3. DISPLAY HELPERS
# ============================================================

def print_section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def print_query(
    connection: sqlite3.Connection,
    title: str,
    query: str,
    parameters: tuple = (),
) -> None:
    """Execute and print a small audit query."""

    print_section(title)

    cursor = connection.execute(query, parameters)
    rows = cursor.fetchall()

    if not rows:
        print("No results")
        return

    column_names = [description[0] for description in cursor.description]

    print(" | ".join(column_names))
    print("-" * 70)

    for row in rows:
        values = [
            "NULL" if row[column] is None else str(row[column])
            for column in column_names
        ]
        print(" | ".join(values))


# ============================================================
# 4. DATABASE STRUCTURE
# ============================================================

def audit_database_structure(
    connection: sqlite3.Connection,
) -> None:

    print_query(
        connection,
        "DATABASE TABLES",
        """
        SELECT name AS table_name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name
        """,
    )


# ============================================================
# 5. DATASET SIZE AND COVERAGE
# ============================================================

def audit_dataset_size(
    connection: sqlite3.Connection,
) -> None:

    print_query(
        connection,
        "MAIN TABLE COUNTS",
        """
        SELECT 'articles' AS table_name, COUNT(*) AS rows
        FROM articles

        UNION ALL

        SELECT 'article_classifications', COUNT(*)
        FROM article_classifications

        UNION ALL

        SELECT 'classification_pool', COUNT(*)
        FROM classification_pool

        UNION ALL

        SELECT 'ml_noise_scores', COUNT(*)
        FROM ml_noise_scores

        UNION ALL

        SELECT 'opportunity_spaces', COUNT(*)
        FROM opportunity_spaces
        """,
    )

    print_query(
        connection,
        "ARTICLES BY VERTICAL",
        """
        SELECT
            vertical,
            COUNT(*) AS article_count
        FROM articles
        GROUP BY vertical
        ORDER BY article_count DESC
        """,
    )

    print_query(
        connection,
        "ARTICLES BY SOURCE TYPE",
        """
        SELECT
            source_type,
            COUNT(*) AS article_count
        FROM articles
        GROUP BY source_type
        ORDER BY article_count DESC
        """,
    )


# ============================================================
# 6. CLASSIFICATION AUDIT
# ============================================================

def audit_classifications(
    connection: sqlite3.Connection,
) -> None:

    print_query(
        connection,
        "CLASSIFICATION STATUS",
        """
        SELECT
            status,
            COUNT(*) AS records,
            ROUND(AVG(confidence), 3) AS average_confidence
        FROM article_classifications
        GROUP BY status
        ORDER BY records DESC
        """,
    )

    print_query(
        connection,
        "CLASSIFICATION COMPLETENESS",
        """
        SELECT
            COUNT(*) AS total_classifications,

            SUM(
                status = 'classified'
                AND NULLIF(TRIM(use_case_id), '') IS NOT NULL
                AND NULLIF(TRIM(technology_id), '') IS NOT NULL
            ) AS complete_opportunity_matches,

            SUM(
                status = 'classified'
                AND (
                    NULLIF(TRIM(use_case_id), '') IS NULL
                    OR NULLIF(TRIM(technology_id), '') IS NULL
                )
            ) AS partial_matches,

            SUM(status = 'needs_review') AS needs_review,

            SUM(status = 'no_match') AS no_match
        FROM article_classifications
        """,
    )

    print_query(
        connection,
        "CLIENT RELEVANCE COVERAGE",
        """
        SELECT
            COUNT(*) AS classifications,
            COUNT(client_relevance) AS with_client_relevance,
            ROUND(AVG(client_relevance), 3)
                AS average_client_relevance
        FROM article_classifications
        """,
    )


# ============================================================
# 7. MANUFACTURING AUDIT
# ============================================================

def audit_manufacturing(
    connection: sqlite3.Connection,
) -> None:

    print_query(
        connection,
        "MANUFACTURING ARTICLES BY SOURCE",
        """
        SELECT
            source_type,
            COUNT(*) AS article_count
        FROM articles
        WHERE vertical = 'Manufacturing'
        GROUP BY source_type
        ORDER BY article_count DESC
        """,
    )

    print_query(
        connection,
        "MANUFACTURING CLASSIFICATION STATUS",
        """
        SELECT
            classifications.status,
            COUNT(*) AS records
        FROM article_classifications AS classifications
        JOIN articles
          ON articles.id = classifications.article_id
        WHERE articles.vertical = 'Manufacturing'
        GROUP BY classifications.status
        ORDER BY records DESC
        """,
    )

    print_query(
        connection,
        "MANUFACTURING COMPLETE AND PARTIAL MATCHES",
        """
        SELECT
            SUM(
                classifications.status = 'classified'
                AND classifications.use_case_id IS NOT NULL
                AND classifications.technology_id IS NOT NULL
            ) AS complete_matches,

            SUM(
                classifications.status = 'classified'
                AND (
                    classifications.use_case_id IS NULL
                    OR classifications.technology_id IS NULL
                )
            ) AS partial_matches,

            SUM(
                classifications.status = 'needs_review'
            ) AS review_candidates
        FROM article_classifications AS classifications
        JOIN articles
          ON articles.id = classifications.article_id
        WHERE articles.vertical = 'Manufacturing'
        """,
    )

    print_query(
        connection,
        "MANUFACTURING OPPORTUNITY SPACES",
        """
        SELECT
            use_case_id,
            technology_id,
            article_count
        FROM opportunity_spaces
        WHERE vertical = 'Manufacturing'
        ORDER BY article_count DESC,
                 use_case_id,
                 technology_id
        """,
    )


# ============================================================
# 8. ML FILTER AUDIT
# ============================================================

def audit_ml_filter(
    connection: sqlite3.Connection,
) -> None:

    print_query(
        connection,
        "ML FILTER RESULTS",
        """
        SELECT
            keep_recommended,
            COUNT(*) AS records,
            ROUND(AVG(usefulness_prob), 3)
                AS average_probability,
            ROUND(MIN(usefulness_prob), 3)
                AS minimum_probability,
            ROUND(MAX(usefulness_prob), 3)
                AS maximum_probability
        FROM ml_noise_scores
        GROUP BY keep_recommended
        ORDER BY keep_recommended DESC
        """,
    )

    print_query(
        connection,
        "MANUFACTURING ML FILTER RESULTS",
        """
        SELECT
            scores.keep_recommended,
            COUNT(*) AS records,
            ROUND(AVG(scores.usefulness_prob), 3)
                AS average_probability
        FROM ml_noise_scores AS scores
        JOIN articles
          ON articles.id = scores.article_id
        WHERE articles.vertical = 'Manufacturing'
        GROUP BY scores.keep_recommended
        """,
    )


# ============================================================
# 9. DATE QUALITY
# ============================================================

def audit_dates(
    connection: sqlite3.Connection,
) -> None:

    print_query(
        connection,
        "PUBLICATION DATE COVERAGE",
        """
        SELECT
            MIN(published_date) AS earliest_date,
            MAX(published_date) AS latest_date,
            SUM(published_date IS NULL) AS missing_dates,
            SUM(
                DATE(published_date) > DATE('now')
            ) AS future_dates
        FROM articles
        """,
    )

    print_query(
        connection,
        "FUTURE DATES BY SOURCE",
        """
        SELECT
            source_type,
            COUNT(*) AS future_records,
            MIN(published_date) AS earliest_future_date,
            MAX(published_date) AS latest_future_date
        FROM articles
        WHERE DATE(published_date) > DATE('now')
        GROUP BY source_type
        ORDER BY future_records DESC
        """,
    )


# ============================================================
# 10. DUPLICATES AND INTEGRITY
# ============================================================

def audit_data_quality(
    connection: sqlite3.Connection,
) -> None:

    print_query(
        connection,
        "DUPLICATE URL SUMMARY",
        """
        SELECT COUNT(*) AS duplicated_urls
        FROM (
            SELECT url
            FROM articles
            WHERE url IS NOT NULL
              AND TRIM(url) <> ''
            GROUP BY url
            HAVING COUNT(*) > 1
        )
        """,
    )

    print_query(
        connection,
        "DUPLICATE GUID SUMMARY",
        """
        SELECT COUNT(*) AS duplicated_guids
        FROM (
            SELECT guid
            FROM articles
            WHERE guid IS NOT NULL
              AND TRIM(guid) <> ''
            GROUP BY guid
            HAVING COUNT(*) > 1
        )
        """,
    )

    print_query(
        connection,
        "ORPHAN CLASSIFICATIONS",
        """
        SELECT COUNT(*) AS orphan_classifications
        FROM article_classifications AS classifications
        LEFT JOIN articles
          ON articles.id = classifications.article_id
        WHERE articles.id IS NULL
        """,
    )

    print_query(
        connection,
        "CLASSIFICATION POOL RUNS",
        """
        SELECT
            DATE(selected_at) AS selection_date,
            COUNT(*) AS records
        FROM classification_pool
        GROUP BY DATE(selected_at)
        ORDER BY selection_date
        """,
    )


# ============================================================
# 11. MAIN PROGRAM
# ============================================================

def main() -> None:
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Database: {DB_PATH}")

    with connect_read_only() as connection:
        audit_database_structure(connection)
        audit_dataset_size(connection)
        audit_classifications(connection)
        audit_manufacturing(connection)
        audit_ml_filter(connection)
        audit_dates(connection)
        audit_data_quality(connection)

    print_section("AUDIT COMPLETE")
    print("The database was opened in read-only mode.")
    print("No records were modified.")


if __name__ == "__main__":
    main()
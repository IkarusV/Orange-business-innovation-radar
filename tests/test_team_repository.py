import sqlite3

from radar_v2.services import team_repository


def test_demo_opportunities_are_complete_when_team_db_is_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(team_repository, "TEAM_DB", tmp_path / "missing.db")
    opportunities = team_repository.list_opportunities()
    assert opportunities
    assert all(item["vertical"] and item["use_case"] and item["technology"] for item in opportunities)


def test_team_opportunity_space_replaces_demo(monkeypatch, tmp_path):
    """A team space with no linked evidence still replaces the demo list. Its
    attractiveness comes from the five weighted components (only market signal
    strength is available here, and it normalizes to the neutral 50 when no
    space in the run has dated evidence), not from avg_client_relevance."""
    database = tmp_path / "articles.db"
    connection = sqlite3.connect(database)
    connection.executescript("""
        CREATE TABLE articles(id INTEGER PRIMARY KEY, vertical TEXT, source_name TEXT, source_type TEXT,
                              extra TEXT, published_date TEXT, collected_at TEXT);
        CREATE TABLE opportunity_spaces(id INTEGER PRIMARY KEY, vertical TEXT,use_case_id TEXT,technology_id TEXT,article_count INTEGER,avg_client_relevance REAL,last_updated_at TEXT,linked_article_ids TEXT);
        INSERT INTO opportunity_spaces VALUES(7,'Manufacturing','predictive-maintenance','digital-twin',3,0.91,'2026-08-24','[]');
    """)
    connection.commit()
    connection.close()
    monkeypatch.setattr(team_repository, "TEAM_DB", database)
    opportunities = team_repository.list_opportunities()
    assert len(opportunities) == 1
    assert opportunities[0]["id"] == 7
    assert opportunities[0]["relevance"] == 50


def test_space_with_no_typed_evidence_is_later_not_now(monkeypatch, tmp_path):
    """A database predating the signal-type columns must still render: the
    horizon falls back to Later, never to an unearned Now."""
    database = tmp_path / "articles.db"
    connection = sqlite3.connect(database)
    connection.executescript("""
        CREATE TABLE articles(id INTEGER PRIMARY KEY, vertical TEXT, source_name TEXT, source_type TEXT,
                              extra TEXT, published_date TEXT, collected_at TEXT);
        CREATE TABLE article_classifications(article_id INTEGER PRIMARY KEY, confidence REAL);
        CREATE TABLE opportunity_spaces(id INTEGER PRIMARY KEY, vertical TEXT,use_case_id TEXT,technology_id TEXT,article_count INTEGER,avg_client_relevance REAL,last_updated_at TEXT,linked_article_ids TEXT);
        INSERT INTO articles VALUES(1,'Manufacturing','TED','ted','{}','2026-08-20','2026-08-20');
        INSERT INTO article_classifications VALUES(1,0.9);
        INSERT INTO opportunity_spaces VALUES(7,'Manufacturing','predictive-maintenance','digital-twin',1,NULL,'2026-08-24','[1]');
    """)
    connection.commit()
    connection.close()
    monkeypatch.setattr(team_repository, "TEAM_DB", database)
    opportunity = team_repository.list_opportunities()[0]
    assert opportunity["horizon"] == "Later"
    assert opportunity["signal_mix"] == []


def test_discovery_uses_all_team_verticals():
    verticals = team_repository.all_verticals()
    assert len(verticals) == 14
    assert "Manufacturing" in verticals
    assert "Media & Entertainment" in verticals

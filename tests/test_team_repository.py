import sqlite3

from radar_v2.services import team_repository


def test_demo_opportunities_are_complete_when_team_db_is_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(team_repository, "TEAM_DB", tmp_path / "missing.db")
    opportunities = team_repository.list_opportunities()
    assert opportunities
    assert all(item["vertical"] and item["use_case"] and item["technology"] for item in opportunities)


def test_team_opportunity_space_replaces_demo(monkeypatch, tmp_path):
    database = tmp_path / "articles.db"
    connection = sqlite3.connect(database)
    connection.executescript("""
        CREATE TABLE articles(id INTEGER PRIMARY KEY, vertical TEXT, source_type TEXT);
        CREATE TABLE opportunity_spaces(id INTEGER PRIMARY KEY, vertical TEXT,use_case_id TEXT,technology_id TEXT,article_count INTEGER,avg_client_relevance REAL,last_updated_at TEXT,linked_article_ids TEXT);
        INSERT INTO opportunity_spaces VALUES(7,'Manufacturing','predictive-maintenance','digital-twin',3,0.91,'2026-08-24','[]');
    """)
    connection.commit()
    connection.close()
    monkeypatch.setattr(team_repository, "TEAM_DB", database)
    opportunities = team_repository.list_opportunities()
    assert len(opportunities) == 1
    assert opportunities[0]["id"] == 7
    assert opportunities[0]["relevance"] == 91


def test_discovery_uses_all_team_verticals():
    verticals = team_repository.all_verticals()
    assert len(verticals) == 14
    assert "Manufacturing" in verticals
    assert "Media & Entertainment" in verticals

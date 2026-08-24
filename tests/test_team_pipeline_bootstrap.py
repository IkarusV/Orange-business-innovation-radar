import sqlite3

import sys
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1] / "Pipelineteamfile"
sys.path.insert(0, str(PIPELINE))

import run_radar
from opportunity_classifier.collector import storage as classifier_storage


def test_ml_training_requires_both_classes():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE articles(id INTEGER PRIMARY KEY)")
    classifier_storage.ensure_schema(connection)
    assert run_radar.ml_training_ready(connection) is False
    for index in range(1, 6):
        connection.execute("INSERT INTO articles VALUES(?)", (index,))
        connection.execute("INSERT INTO article_classifications(article_id,status,classified_at) VALUES(?, 'classified','now')", (index,))
    assert run_radar.ml_training_ready(connection) is False
    for index in range(6, 11):
        connection.execute("INSERT INTO articles VALUES(?)", (index,))
        connection.execute("INSERT INTO article_classifications(article_id,status,classified_at) VALUES(?, 'no_match','now')", (index,))
    assert run_radar.ml_training_ready(connection) is True


def test_opportunity_recompute_removes_stale_space():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE articles(id INTEGER PRIMARY KEY,vertical TEXT)")
    classifier_storage.ensure_schema(connection)
    connection.execute("INSERT INTO opportunity_spaces(vertical,use_case_id,technology_id,article_count,linked_article_ids,first_seen_at,last_updated_at) VALUES('Old','x','y',1,'[]','now','now')")
    classifier_storage.recompute_opportunity_spaces(connection)
    assert connection.execute("SELECT COUNT(*) FROM opportunity_spaces").fetchone()[0] == 0


def test_pipeline_lock_prevents_overlapping_run(monkeypatch, tmp_path):
    lock = tmp_path / "pipeline.lock"
    lock.write_text("existing", encoding="utf-8")
    monkeypatch.setattr(run_radar, "LOCK_PATH", lock)
    try:
        run_radar.run(limit=1)
        assert False, "expected overlapping run to be rejected"
    except RuntimeError as error:
        assert "already running" in str(error)

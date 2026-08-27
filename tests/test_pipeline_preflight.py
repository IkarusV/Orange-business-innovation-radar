from radar_v2.services import team_repository


def test_pipeline_preflight_handles_empty_database(monkeypatch, tmp_path):
    monkeypatch.setattr(team_repository, "TEAM_DB", tmp_path / "missing.db")
    assert team_repository.pipeline_preflight() == {"articles": 0, "classification_calls": 0, "pool": 0, "ml_scored": 0, "spaces": 0}

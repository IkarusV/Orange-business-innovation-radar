from pathlib import Path

from radar import db
from radar import library


class FakeClient:
    def __init__(self):
        self.calls = 0

    def generate_json(self, system_prompt, user_prompt):
        self.calls += 1
        return {
            "summary": "Partner-led cloud strategy",
            "key_facts": ["Cloud"],
            "company_language": ["trusted"],
            "strategic_signals": [],
            "opportunities_or_capabilities": [],
            "risks_or_unknowns": [],
            "document_type": "strategy",
        }


def setup_library(monkeypatch, tmp_path):
    database = tmp_path / "radar.db"
    monkeypatch.setattr(db, "db_path", lambda: database)
    monkeypatch.setattr(library, "LIBRARY_ROOT", tmp_path / "Documents")
    db.initialize(database)


def test_document_processing_is_one_call_and_context_is_selected(monkeypatch, tmp_path):
    setup_library(monkeypatch, tmp_path)
    document = library.add_document("Acme", "strategy.txt", b"Cloud and partner strategy", "text/plain")
    client = FakeClient()
    library.process_document(document["id"], client, ["scoring"])

    assert client.calls == 1
    assert "Partner-led cloud strategy" in library.library_context("Acme", "scoring", 5, 1000)
    assert library.library_context("Acme", "collection", 5, 1000) == ""
    processed = Path(db.rows("SELECT processed_path FROM library_documents WHERE id=?", (document["id"],))[0]["processed_path"])
    assert processed.exists()


def test_duplicate_uploads_do_not_overwrite(monkeypatch, tmp_path):
    setup_library(monkeypatch, tmp_path)
    first = library.add_document("Acme", "strategy.txt", b"First", "text/plain")
    second = library.add_document("Acme", "strategy.txt", b"Second", "text/plain")
    assert first["name"] == "strategy.txt"
    assert second["name"] == "strategy_2.txt"


def test_combined_report_uses_one_call(monkeypatch, tmp_path):
    setup_library(monkeypatch, tmp_path)
    first = library.add_document("Acme", "one.txt", b"Cloud", "text/plain")
    second = library.add_document("Acme", "two.txt", b"Partners", "text/plain")
    client = FakeClient()
    library.process_document(first["id"], client, ["all"])
    library.process_document(second["id"], client, ["all"])
    before_report = client.calls
    report = library.create_report("Acme", [first["id"], second["id"]], client)
    assert client.calls - before_report == 1
    assert report["name"] == "report_Acme_1.txt"

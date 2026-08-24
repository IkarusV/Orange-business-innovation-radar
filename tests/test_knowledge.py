import json
from pathlib import Path

from radar_v2.services import extension_store, knowledge


class FakeClient:
    calls = 0

    class Responses:
        def create(self, **kwargs):
            FakeClient.calls += 1
            return type("Response", (), {"output_text": json.dumps({"executive_summary": "Focused summary", "key_facts": []})})()

    responses = Responses()


def setup_store(monkeypatch, tmp_path):
    monkeypatch.setattr(extension_store, "EXTENSION_DB", tmp_path / "product.db")
    monkeypatch.setattr(extension_store, "DOCUMENTS", tmp_path / "Documents")
    monkeypatch.setattr(knowledge, "DOCUMENTS", tmp_path / "Documents")
    extension_store.save_company("Acme", "Europe", "https://acme.example", "Growth")


def test_each_document_is_processed_in_an_isolated_call(monkeypatch, tmp_path):
    setup_store(monkeypatch, tmp_path)
    first = extension_store.save_document("one.txt", b"Revenue 10 million EUR")
    second = extension_store.save_document("two.txt", b"Cloud strategy")
    monkeypatch.setattr(knowledge, "_client", lambda *args: FakeClient())
    FakeClient.calls = 0
    documents = extension_store._rows("SELECT * FROM documents ORDER BY id")
    knowledge.process_document(documents[0], "Focus on finance", "https://example", "key", "model", "responses")
    knowledge.process_document(documents[1], "Focus on strategy", "https://example", "key", "model", "responses")
    assert FakeClient.calls == 2
    assert Path(extension_store._rows("SELECT processed_path FROM documents WHERE id=?", (first["id"],))[0]["processed_path"]).exists()
    assert Path(extension_store._rows("SELECT processed_path FROM documents WHERE id=?", (second["id"],))[0]["processed_path"]).exists()


def test_combined_report_uses_one_additional_call(monkeypatch, tmp_path):
    setup_store(monkeypatch, tmp_path)
    extension_store.save_document("one.txt", b"Revenue")
    extension_store.save_document("two.txt", b"Strategy")
    monkeypatch.setattr(knowledge, "_client", lambda *args: FakeClient())
    FakeClient.calls = 0
    documents = extension_store._rows("SELECT * FROM documents ORDER BY id")
    report = knowledge.create_combined_report(documents, "Focus on 2026", "https://example", "key", "model", "responses")
    assert FakeClient.calls == 1
    assert report.exists()

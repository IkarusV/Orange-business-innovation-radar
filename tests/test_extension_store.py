from radar_v2.services import extension_store


def test_company_documents_use_portable_sanitized_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(extension_store, "EXTENSION_DB", tmp_path / "product.db")
    monkeypatch.setattr(extension_store, "DOCUMENTS", tmp_path / "Documents")
    extension_store.save_company("Acme Europe", "Europe", "https://acme.example", "Secure services")
    saved = extension_store.save_document("Board Plan.md", b"Strategy")
    assert saved["name"] == "Board_Plan.md"
    assert (tmp_path / "Documents" / "Acme_Europe" / "Board_Plan.md").exists()
    assert extension_store.documents()[0]["company"] == "Acme Europe"


def test_processing_selection_is_separate_from_context_selection(monkeypatch, tmp_path):
    monkeypatch.setattr(extension_store, "EXTENSION_DB", tmp_path / "product.db")
    monkeypatch.setattr(extension_store, "DOCUMENTS", tmp_path / "Documents")
    extension_store.save_company("Acme", "Europe", "https://acme.example", "Growth")
    saved = extension_store.save_document("strategy.txt", b"Strategy")
    extension_store.toggle_document(saved["id"])
    assert len(extension_store.selected_documents()) == 1
    assert extension_store.selected_document_texts(5, 1000) == []

    summary = tmp_path / "Documents" / "Acme" / "processed" / "strategy.summary.json"
    summary.parent.mkdir(parents=True)
    summary.write_text('{"summary":"Growth"}', encoding="utf-8")
    extension_store.update_document_processing(saved["id"], "Processed", str(summary), "")
    context = extension_store.selected_document_texts(5, 1000)
    assert len(context) == 1
    assert context[0]["scope"] == "Everywhere"
    extension_store.toggle_document_context(saved["id"])
    assert extension_store.selected_document_texts(5, 1000) == []

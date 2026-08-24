from radar_v2.services import extension_store


def test_latest_search_restores_saved_results(monkeypatch, tmp_path):
    monkeypatch.setattr(extension_store, "EXTENSION_DB", tmp_path / "product.db")
    result_id = extension_store.save_search("bank cloud", "SearXNG", [{"title": "Evidence", "url": "https://example.com", "source": "bing", "date": "Recent", "excerpt": "Signal"}])
    saved = extension_store.latest_search()
    assert saved["id"] == result_id
    assert saved["query"] == "bank cloud"
    assert saved["results"][0]["url"] == "https://example.com"

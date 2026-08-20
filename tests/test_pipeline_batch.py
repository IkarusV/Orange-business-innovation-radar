from radar.pipeline import analyze_batch


class FakeClient:
    def __init__(self):
        self.calls = 0

    def generate_json(self, system_prompt, user_prompt):
        self.calls += 1
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return {"results": [
            {"article_id": 1, "is_relevant": False, "triage_confidence": "HIGH"},
            {"article_id": 2, "is_relevant": False, "triage_confidence": "HIGH"},
            {"article_id": 3, "is_relevant": False, "triage_confidence": "HIGH"},
            {"article_id": 4, "is_relevant": False, "triage_confidence": "HIGH"},
            {"article_id": 5, "is_relevant": False, "triage_confidence": "HIGH"},
        ]}


def test_five_articles_use_one_model_request(monkeypatch):
    monkeypatch.setattr("radar.pipeline.company_context", lambda *args, **kwargs: "Test company")
    monkeypatch.setattr("radar.pipeline.source_metadata", lambda source: {"source_category": "media", "quality_default": 3, "independence_group": "example"})
    articles = [
        {"id": index, "source_name": "Source", "published_at": "2026-01-01", "url": f"https://example.com/{index}", "title": f"Article {index}", "content": "Content"}
        for index in range(1, 6)
    ]
    client = FakeClient()
    results = analyze_batch(articles, client)
    assert client.calls == 1
    assert len(results) == 5
    assert "RESEARCH-GROUNDED DECISION RULES" in client.user_prompt
    assert "Never use them as independent proof" in client.user_prompt
    assert "independence_group=example" in client.user_prompt

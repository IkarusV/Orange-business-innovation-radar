from radar.pipeline import analyze_batch


class FakeClient:
    def __init__(self):
        self.calls = 0

    def generate_json(self, system_prompt, user_prompt):
        self.calls += 1
        return {"results": [
            {"article_id": 1, "is_relevant": False},
            {"article_id": 2, "is_relevant": False},
            {"article_id": 3, "is_relevant": False},
            {"article_id": 4, "is_relevant": False},
            {"article_id": 5, "is_relevant": False},
        ]}


def test_five_articles_use_one_model_request(monkeypatch):
    monkeypatch.setattr("radar.pipeline.company_context", lambda *args, **kwargs: "Test company")
    articles = [
        {"id": index, "source_name": "Source", "published_at": "2026-01-01", "url": f"https://example.com/{index}", "title": f"Article {index}", "content": "Content"}
        for index in range(1, 6)
    ]
    client = FakeClient()
    results = analyze_batch(articles, client)
    assert client.calls == 1
    assert len(results) == 5

from radar.ingestion import canonical_url, clean_text


def test_canonical_url_removes_tracking_and_fragment():
    assert canonical_url("HTTPS://Example.COM/story/?utm_source=x#part") == "https://example.com/story"


def test_clean_text_strips_html_and_space():
    assert clean_text("<p>Hello   <b>radar</b></p>") == "Hello radar"

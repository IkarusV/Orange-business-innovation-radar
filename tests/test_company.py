import pytest

from radar.company import DocumentError, extract_document


def test_extract_text_document():
    assert extract_document("strategy.md", b"# Strategy\nPartner-led cloud", "text/markdown") == "# Strategy\nPartner-led cloud"


def test_reject_unsupported_document():
    with pytest.raises(DocumentError):
        extract_document("logo.png", b"not-an-image-parser", "image/png")

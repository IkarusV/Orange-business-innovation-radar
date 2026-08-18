import pytest

from radar.ai import AIError, _json_object, _responses_text


def test_json_object_accepts_fenced_json():
    assert _json_object('```json\n{"ok": true}\n```') == {"ok": True}


def test_json_object_rejects_non_json():
    with pytest.raises(AIError):
        _json_object("not structured")


def test_responses_text_extracts_nested_content():
    payload = {"output": [{"content": [{"type": "output_text", "text": "{\"ok\":true}"}]}]}
    assert _responses_text(payload) == '{"ok":true}'

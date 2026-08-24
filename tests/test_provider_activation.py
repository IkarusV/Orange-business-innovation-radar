from radar_v2.state import RadarState


def test_activation_requires_a_key(monkeypatch):
    monkeypatch.delenv("NAVY_API_KEY", raising=False)
    state = RadarState()
    result = state.activate_provider()
    assert state.provider_session_active is False
    assert result is not None


def test_activation_uses_session_key(monkeypatch):
    monkeypatch.delenv("NAVY_API_KEY", raising=False)
    state = RadarState()
    state.ai_api_key = "session-key"
    state.activate_provider()
    assert state.provider_session_active is True


def test_disconnect_clears_session_key():
    state = RadarState()
    state.ai_api_key = "session-key"
    state.provider_session_active = True
    state.deactivate_provider()
    assert state.ai_api_key == ""
    assert state.provider_session_active is False


def test_pipeline_requires_activation_even_when_key_exists(monkeypatch):
    monkeypatch.setenv("NAVY_API_KEY", "environment-key")
    state = RadarState()
    state.provider_session_active = False
    assert state.provider_session_active is False

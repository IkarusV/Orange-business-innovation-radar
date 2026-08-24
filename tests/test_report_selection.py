from radar_v2.state import RadarState


def test_report_selector_parses_user_facing_label():
    state = RadarState()
    state.set_report_opportunity("1 · Warehouse automation")
    assert state.report_opportunity_id == 1


def test_report_selector_ignores_invalid_label():
    state = RadarState()
    state.set_report_opportunity("Choose an opportunity")
    assert state.report_opportunity_id == 0

from radar_v2.constants import INK, LINE, MUTED, ORANGE, PANEL, PANEL_SOFT, TEXT


PAGE = {
    "background": INK,
    "color": TEXT,
    "min_height": "100vh",
    "font_family": "Inter, ui-sans-serif, system-ui, sans-serif",
}

CARD = {
    "background": PANEL,
    "border": f"1px solid {LINE}",
    "border_radius": "20px",
    "padding": "22px",
    "box_shadow": "0 18px 50px rgba(0,0,0,.18)",
}

SOFT_CARD = {
    "background": PANEL_SOFT,
    "border": f"1px solid {LINE}",
    "border_radius": "16px",
    "padding": "18px",
}

BUTTON = {
    "background": ORANGE,
    "color": "#080808",
    "border_radius": "12px",
    "font_weight": "700",
    "cursor": "pointer",
    "transition": "transform .18s ease, filter .18s ease",
    "_hover": {"transform": "translateY(-2px)", "filter": "brightness(1.08)"},
}

GHOST_BUTTON = {
    "background": "transparent",
    "color": TEXT,
    "border": f"1px solid {LINE}",
    "border_radius": "12px",
    "cursor": "pointer",
    "_hover": {"border_color": ORANGE, "color": ORANGE},
}

INPUT = {
    "background": "#101010",
    "border": f"1px solid {LINE}",
    "border_radius": "12px",
    "color": TEXT,
    "min_height": "44px",
}

MUTED_TEXT = {"color": MUTED, "line_height": "1.6"}

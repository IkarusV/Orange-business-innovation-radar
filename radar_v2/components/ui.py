import reflex as rx

from radar_v2.constants import LINE, MUTED, ORANGE, PANEL, PANEL_SOFT, TEXT
from radar_v2.services import role_modes
from radar_v2.state import RadarState
from radar_v2.styles import BUTTON, CARD, MUTED_TEXT, SOFT_CARD


def page_header(eyebrow: str, title: str, subtitle: str, action: rx.Component | None = None) -> rx.Component:
    return rx.flex(
        rx.vstack(
            rx.text(eyebrow, color=ORANGE, font_size="11px", letter_spacing=".2em", text_transform="uppercase", weight="bold"),
            rx.heading(title, font_size=rx.breakpoints(initial="32px", sm="42px", lg="52px"), line_height="1.05", max_width="900px"),
            rx.text(subtitle, font_size=rx.breakpoints(initial="15px", sm="17px"), max_width="760px", **MUTED_TEXT),
            spacing="3", align="start",
        ),
        rx.spacer(),
        action or rx.box(),
        direction=rx.breakpoints(initial="column", lg="row"),
        gap="5", align=rx.breakpoints(initial="start", lg="center"), width="100%",
    )


def metric_card(label: str, value, detail: str, icon: str) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.center(rx.icon(icon, size=20, color=ORANGE), width="42px", height="42px", background="#2a1b0d", border_radius="12px"),
            rx.spacer(),
            rx.icon("arrow-up-right", size=16, color=MUTED),
            width="100%", align="center",
        ),
        rx.heading(value, font_size="34px", margin_top="18px"),
        rx.text(label, color=TEXT, weight="medium"),
        rx.text(detail, color=MUTED, font_size="12px", margin_top="5px"),
        **CARD,
    )


def status_badge(horizon) -> rx.Component:
    return rx.badge(
        horizon,
        variant="soft",
        color_scheme=rx.match(horizon, ("Now", "orange"), ("Next", "blue"), "gray"),
        radius="full",
        padding="5px 9px",
    )


def publication_badge(publication_status) -> rx.Component:
    """Radar/Watchlist gate badge. A separate signal from the horizon badge -
    this is about evidence independence, not timing - shown next to it rather
    than merged into it."""
    return rx.badge(
        publication_status,
        variant="surface",
        color_scheme=rx.match(publication_status, ("RADAR", "orange"), "gray"),
        radius="full",
        padding="5px 9px",
    )


def opportunity_card(item) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.badge(item["vertical"], color_scheme="gray", variant="soft", radius="full"),
            rx.spacer(),
            publication_badge(item["publication_status"]),
            status_badge(item["horizon"]),
            width="100%",
        ),
        rx.cond(
            item["primary_domain_label"] != "",
            rx.badge(item["primary_domain_label"], color_scheme="orange", variant="surface", radius="full", margin_top="14px"),
            rx.box(),
        ),
        rx.heading(item["use_case"], size="5", margin_top="10px"),
        rx.text(item["technology"], color=ORANGE, weight="medium", margin_top="3px"),
        rx.text(item["summary"], color=MUTED, line_height="1.55", margin_top="13px", min_height="72px"),
        rx.grid(
            rx.vstack(rx.text("Attractiveness", color=MUTED, size="1"), rx.text(item["relevance"].to_string() + " / 100", weight="bold", color=ORANGE), spacing="1", align="start"),
            rx.vstack(rx.text("Orange fit", color=MUTED, size="1"), rx.text(item["orange_fit_score"].to_string() + " / 100", weight="bold"), spacing="1", align="start"),
            rx.vstack(rx.text("Momentum", color=MUTED, size="1"), rx.text(item["momentum"], weight="bold"), spacing="1", align="start"),
            rx.vstack(rx.text("Signals", color=MUTED, size="1"), rx.text(item["article_count"], weight="bold"), spacing="1", align="start"),
            columns="4", gap="3", margin_top="18px",
        ),
        rx.button(
            "Open opportunity", rx.icon("arrow-right", size=16),
            on_click=RadarState.select_opportunity(item["id"]),
            width="100%", margin_top="20px", **BUTTON,
        ),
        **CARD,
        transition="transform .2s ease, border-color .2s ease",
        _hover={"transform": "translateY(-5px)", "border_color": ORANGE},
    )


def sales_opportunity_card(item) -> rx.Component:
    """Single-column, larger card for sales mode: the recommended move and the
    persona hook are readable without opening the detail page, because this view
    is used live in front of a customer."""
    return rx.box(
        rx.flex(
            rx.hstack(
                rx.badge(item["vertical"], color_scheme="gray", variant="soft", radius="full"),
                rx.cond(
                    item["primary_domain_label"] != "",
                    rx.badge(item["primary_domain_label"], color_scheme="orange", variant="surface", radius="full"),
                    rx.box(),
                ),
                spacing="2", align="center", wrap="wrap",
            ),
            rx.spacer(),
            publication_badge(item["publication_status"]),
            status_badge(item["horizon"]),
            width="100%", align="center", gap="3", wrap="wrap",
        ),
        rx.heading(item["use_case"], size="6", margin_top="14px"),
        rx.text(item["technology"], color=ORANGE, weight="medium", margin_top="4px"),
        rx.grid(
            rx.box(
                rx.text("Recommended move", color=MUTED, size="1"),
                # Per space and already resolved for the active mode by
                # visible_opportunities, so this card shows the sales-mode move.
                rx.text(item["recommended_move"], line_height="1.55", margin_top="5px"),
                **SOFT_CARD,
            ),
            rx.box(
                rx.text("Persona hook", color=MUTED, size="1"),
                rx.cond(
                    RadarState.persona_weighting_available,
                    rx.cond(
                        item["persona_weights"].length() > 0,
                        rx.fragment(
                            rx.hstack(
                                rx.badge(item["persona_weights"][0]["label"], color_scheme="orange", variant="soft", radius="full"),
                                rx.text("strongest match", color=MUTED, size="1"),
                                spacing="2", align="center", margin_top="5px",
                            ),
                            rx.text(item["summary"], line_height="1.55", margin_top="7px"),
                        ),
                        rx.text(
                            "No persona clears the relevance threshold for this space.",
                            color=MUTED, line_height="1.55", margin_top="5px",
                        ),
                    ),
                    rx.text(
                        "Persona targeting is not available yet - this space is shown unweighted.",
                        color=MUTED, line_height="1.55", margin_top="5px",
                    ),
                ),
                **SOFT_CARD,
            ),
            columns=rx.breakpoints(initial="1", md="2"), gap="4", width="100%", margin_top="18px",
        ),
        rx.flex(
            rx.hstack(
                rx.text("Attractiveness", color=MUTED, size="1"),
                rx.text(item["relevance"].to_string() + " / 100", weight="bold", color=ORANGE),
                spacing="2", align="center",
            ),
            rx.hstack(
                rx.text("Orange fit", color=MUTED, size="1"),
                rx.text(item["orange_fit_score"].to_string() + " / 100", weight="bold"),
                spacing="2", align="center",
            ),
            rx.hstack(rx.text("Signals", color=MUTED, size="1"), rx.text(item["article_count"], weight="bold"), spacing="2", align="center"),
            rx.hstack(rx.text("Momentum", color=MUTED, size="1"), rx.text(item["momentum"], weight="bold"), spacing="2", align="center"),
            rx.spacer(),
            rx.button(
                "Open opportunity", rx.icon("arrow-right", size=16),
                on_click=RadarState.select_opportunity(item["id"]), **BUTTON,
            ),
            gap="5", align="center", wrap="wrap", width="100%", margin_top="20px",
        ),
        **CARD, width="100%",
    )


def role_mode_chip(item) -> rx.Component:
    """Same toggle language as the domain priority chips - one selected mode."""
    return rx.button(
        rx.cond(item["selected"], rx.icon("check", size=14), rx.icon("circle", size=14)),
        rx.text(item["label"], size="2"),
        on_click=RadarState.set_role_mode(item["id"]),
        variant="surface",
        cursor="pointer",
        border_radius="999px",
        padding="7px 13px",
        height="auto",
        background=rx.cond(item["selected"], "#2a1b0d", "#101010"),
        color=rx.cond(item["selected"], ORANGE, TEXT),
        border=rx.cond(item["selected"], f"1px solid {ORANGE}", f"1px solid {LINE}"),
        _hover={"border_color": ORANGE},
    )


def role_mode_switcher(compact: bool = False) -> rx.Component:
    """The active mode stays on screen everywhere it changes what is shown, so a
    returning tab never leaves the user guessing which view they are in."""
    return rx.box(
        rx.flex(
            rx.hstack(
                rx.icon("user-round-cog", size=16, color=ORANGE),
                rx.text("View mode", weight="medium", size="2"),
                rx.badge(RadarState.role_mode_label, color_scheme="orange", variant="soft", radius="full"),
                spacing="2", align="center",
            ),
            rx.spacer(),
            rx.text("Sorted by " + RadarState.role_mode_sort_label, color=MUTED, size="1"),
            gap="3", align="center", wrap="wrap", width="100%",
        ),
        rx.flex(
            rx.foreach(RadarState.role_mode_options, role_mode_chip),
            wrap="wrap", gap="2", width="100%", margin_top="12px",
        ),
        rx.cond(
            compact,
            rx.box(),
            rx.text(RadarState.role_mode_description, color=MUTED, size="1", margin_top="10px"),
        ),
        rx.cond(
            RadarState.role_mode_sort_note != "",
            rx.callout(RadarState.role_mode_sort_note, icon="info", color_scheme="gray", size="1", width="100%", margin_top="12px"),
            rx.box(),
        ),
        **SOFT_CARD, width="100%",
    )


def persona_prompt() -> rx.Component:
    """Sales mode asks for a persona first. While the persona feature does not
    exist this is a notice, never a gate - a mode with no escape would be empty
    on a still-sparse dataset."""
    return rx.box(
        rx.hstack(
            rx.center(rx.icon("user-round-search", size=22, color=ORANGE), width="46px", height="46px", background="#2a1b0d", border_radius="12px"),
            rx.vstack(
                rx.heading("Pick the persona you are meeting", size="4"),
                rx.text(
                    "Sales mode narrows the radar to the topics that land with one persona in one vertical.",
                    color=MUTED, size="2",
                ),
                spacing="1", align="start",
            ),
            spacing="3", align="center", width="100%",
        ),
        rx.cond(
            RadarState.persona_options.length() > 0,
            rx.select(
                RadarState.persona_options,
                value=RadarState.persona_filter,
                on_change=RadarState.set_persona_filter,
                placeholder="Choose a persona",
                width="280px",
            ),
            rx.callout(
                "Persona targeting is not implemented yet, so no persona list exists. "
                "Sales mode still applies its own sort and layout, and the full topic list stays below.",
                icon="triangle-alert", color_scheme="gray", size="1", width="100%",
            ),
        ),
        **SOFT_CARD, width="100%", margin_top="14px",
    )


def detail_region(region_key: str, *content: rx.Component) -> rx.Component:
    """One region of the opportunity detail page, positioned and expanded by the
    active mode's presentation profile.

    Every region is always rendered: `collapsed` closes the disclosure, it never
    removes the content from the page, so signals and sources stay reachable in
    every mode.
    """
    emphasis = RadarState.region_emphasis[region_key]
    is_lead = emphasis == role_modes.LEAD
    is_collapsed = emphasis == role_modes.COLLAPSED
    return rx.el.details(
        rx.el.summary(
            rx.flex(
                rx.vstack(
                    rx.hstack(
                        rx.heading(role_modes.region_label(region_key), size="6"),
                        rx.cond(is_lead, rx.badge("Focus", color_scheme="orange", variant="soft", radius="full"), rx.box()),
                        spacing="2", align="center", wrap="wrap",
                    ),
                    rx.text(role_modes.region_hint(region_key), color=MUTED, size="2"),
                    spacing="1", align="start",
                ),
                rx.spacer(),
                rx.icon("chevron-down", size=18, color=MUTED),
                width="100%", align="center", gap="3",
            ),
            style={
                "cursor": "pointer",
                "list_style": "none",
                "&::-webkit-details-marker": {"display": "none"},
            },
        ),
        rx.box(*content, margin_top="16px", width="100%"),
        open=rx.cond(is_collapsed, False, True),
        data_emphasis=emphasis,
        style={
            "order": rx.cond(is_lead, 1, rx.cond(is_collapsed, 3, 2)),
            "flex": rx.cond(is_lead, "1 1 100%", "1 1 420px"),
            "background": PANEL,
            "border": rx.cond(is_lead, f"1px solid {ORANGE}", f"1px solid {LINE}"),
            "border_radius": "20px",
            "padding": "22px",
            "box_shadow": "0 18px 50px rgba(0,0,0,.18)",
            "min_width": "0",
        },
    )


def placeholder_region(title: str, detail: str) -> rx.Component:
    """Content for a region whose underlying feature is not built yet. It states
    the gap instead of inventing a value from unrelated data."""
    return rx.box(
        rx.hstack(rx.icon("construction", size=16, color=MUTED), rx.text(title, weight="medium"), spacing="2", align="center"),
        rx.text(detail, color=MUTED, size="2", line_height="1.55", margin_top="8px"),
        **SOFT_CARD, width="100%",
    )


def attractiveness_row(item) -> rx.Component:
    """One component of the attractiveness score, shown with the weight it carries
    and what it measures. A component with no data is labelled as such - it is
    excluded from the weighted score rather than counted as a zero."""
    return rx.box(
        rx.flex(
            rx.hstack(
                rx.text(item["label"], weight="medium"),
                rx.badge(item["weight"].to_string() + "%", color_scheme="gray", variant="soft", radius="full"),
                spacing="2", align="center",
            ),
            rx.spacer(),
            rx.cond(
                item["available"],
                rx.text(item["value"].to_string() + " / 100", weight="bold", color=ORANGE),
                rx.badge("No data yet", color_scheme="gray", variant="surface", radius="full"),
            ),
            width="100%", align="center", gap="3",
        ),
        rx.cond(
            item["available"],
            rx.progress(value=item["value"], color_scheme="orange", margin_top="11px"),
            rx.box(height="8px", width="100%", margin_top="11px", border_radius="999px", border=f"1px dashed {LINE}"),
        ),
        rx.text(
            rx.cond(
                item["available"],
                rx.match(
                    item["key"],
                    ("market_signal_strength", "Recency-weighted volume of linked institutional evidence, relative to the strongest space on the radar."),
                    ("source_credibility", "Average publisher trust of the sources behind this evidence."),
                    ("evidence_quality", "Classifier confidence where it exists, blended with evidence count, source independence and trust where it doesn't."),
                    ("novelty_momentum", "Growth over the last 90 days vs. the 90 before, ranked against every other space on the radar this run."),
                    "Contributes to the attractiveness score.",
                ),
                rx.match(
                    item["key"],
                    ("novelty_momentum", "Not enough dated evidence to compare two periods."),
                    "Not enough data yet - excluded from the score rather than counted as zero."
                ),
            ),
            color=MUTED, size="1", line_height="1.5", margin_top="9px",
        ),
        **SOFT_CARD, width="100%",
    )


def horizon_check_row(item) -> rx.Component:
    """One line of the timing explanation: the count the rules acted on, and
    whether it cleared the threshold. Same principle as attractiveness_row -
    a badge nobody can question is a badge nobody can trust."""
    return rx.box(
        rx.flex(
            rx.hstack(
                rx.cond(
                    item["met"],
                    rx.icon("circle-check", size=15, color=ORANGE),
                    rx.icon("circle-dashed", size=15, color=MUTED),
                ),
                rx.text(item["label"], weight="medium"),
                spacing="2", align="center",
            ),
            rx.spacer(),
            rx.text(item["value"].to_string(), weight="bold", color=rx.cond(item["met"], ORANGE, MUTED)),
            width="100%", align="center", gap="3",
        ),
        rx.text(item["detail"], color=MUTED, size="1", line_height="1.5", margin_top="7px"),
        **SOFT_CARD, width="100%",
    )


def signal_type_row(item) -> rx.Component:
    """How many of this space's signals carry one type, next to the question
    that assigned it - so a wrong badge can be traced to a wrong answer."""
    return rx.box(
        rx.flex(
            rx.text(item["label"], weight="medium"),
            rx.spacer(),
            rx.badge(item["value"].to_string(), color_scheme="orange", variant="soft", radius="full"),
            width="100%", align="center", gap="3",
        ),
        rx.text(item["question"], color=MUTED, size="1", line_height="1.5", margin_top="7px"),
        **SOFT_CARD, width="100%",
    )


def persona_relevance_row(item) -> rx.Component:
    """One persona's derived relevance to this space: the tier, and which
    table produced it - use case, domain, or both agreeing - same
    explainability principle as the horizon and signal-type rows above."""
    return rx.box(
        rx.flex(
            rx.text(item["label"], weight="medium"),
            rx.spacer(),
            rx.badge(
                rx.match(item["weight"], (1.0, "Primary"), (0.6, "Secondary"), (0.3, "Peripheral"), "Not relevant"),
                color_scheme=rx.match(item["weight"], (1.0, "orange"), (0.6, "orange"), "gray"),
                variant=rx.match(item["weight"], (1.0, "solid"), "soft"),
                radius="full",
            ),
            width="100%", align="center", gap="3",
        ),
        rx.text(
            rx.match(
                item["source"],
                ("use_case", "From this space's use case."),
                ("domain", "From this space's business domain."),
                ("both", "From both the use case and the business domain."),
                "No table produced this weight.",
            ),
            color=MUTED, size="1", line_height="1.5", margin_top="7px",
        ),
        **SOFT_CARD, width="100%",
    )


def priority_chip(item, on_toggle) -> rx.Component:
    """Toggle for one closed-taxonomy entry in Orange's own priority list."""
    return rx.button(
        rx.cond(item["selected"], rx.icon("check", size=14), rx.icon("plus", size=14)),
        rx.text(item["label"], size="2"),
        on_click=on_toggle(item["id"]),
        variant="surface",
        cursor="pointer",
        border_radius="999px",
        padding="7px 13px",
        height="auto",
        background=rx.cond(item["selected"], "#2a1b0d", "#101010"),
        color=rx.cond(item["selected"], ORANGE, TEXT),
        border=rx.cond(item["selected"], f"1px solid {ORANGE}", f"1px solid {LINE}"),
        _hover={"border_color": ORANGE},
    )


def section_title(title: str, subtitle: str = "") -> rx.Component:
    return rx.vstack(
        rx.heading(title, size="6"),
        rx.cond(subtitle != "", rx.text(subtitle, color=MUTED), rx.box()),
        spacing="1", align="start", width="100%",
    )


def evidence_card(item) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.badge(item["source_type"], color_scheme="orange", variant="surface"),
            rx.text(item["date"], color=MUTED, size="1"),
            rx.spacer(),
            rx.text(item["confidence"].to_string() + "% match", color=MUTED, size="1"),
            width="100%", align="center",
        ),
        rx.heading(item["title"], size="4", margin_top="12px"),
        rx.text(item["excerpt"], color=MUTED, line_height="1.55", margin_top="8px"),
        rx.link("View source", rx.icon("external-link", size=14), href=item["url"], is_external=True, color=ORANGE, margin_top="13px", display="flex", gap="6px", align_items="center"),
        **SOFT_CARD,
    )


def empty_state(icon: str, title: str, text: str) -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.center(rx.icon(icon, size=28, color=ORANGE), width="62px", height="62px", background="#2a1b0d", border_radius="18px"),
            rx.heading(title, size="5"),
            rx.text(text, color=MUTED, text_align="center", max_width="450px"),
            align="center", spacing="3",
        ),
        width="100%", min_height="280px", border=f"1px dashed {LINE}", border_radius="20px", background=PANEL_SOFT,
    )

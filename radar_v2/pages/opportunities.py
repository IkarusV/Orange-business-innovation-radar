import reflex as rx

from radar_v2.components.shell import page_shell
from radar_v2.components.ui import (
    empty_state,
    opportunity_card,
    page_header,
    persona_prompt,
    priority_chip,
    role_mode_switcher,
    sales_opportunity_card,
)
from radar_v2.constants import LINE, MUTED
from radar_v2.state import RadarState
from radar_v2.styles import INPUT


def opportunities() -> rx.Component:
    return page_shell(
        rx.vstack(
            page_header(
                "Opportunity portfolio", "Find the spaces that deserve a closer look.",
                "Filter the radar by business domain, sector and timing, then open any opportunity to review its supporting signals and business direction.",
            ),
            rx.vstack(
                role_mode_switcher(),
                rx.cond(RadarState.persona_prompt_visible, persona_prompt(), rx.box()),
                rx.flex(
                    rx.input(
                        placeholder="Search by sector, use case or technology",
                        value=RadarState.search_filter,
                        on_change=RadarState.set_search_filter,
                        width=rx.breakpoints(initial="100%", lg="360px"),
                        **INPUT,
                    ),
                    rx.select(
                        RadarState.vertical_options,
                        value=RadarState.vertical_filter,
                        on_change=RadarState.set_vertical_filter,
                        width="220px",
                    ),
                    rx.select(
                        ["All horizons", "Now", "Next", "Later"],
                        value=RadarState.horizon_filter,
                        on_change=RadarState.set_horizon_filter,
                        width="180px",
                    ),
                    gap="3", direction=rx.breakpoints(initial="column", sm="row"), width="100%",
                ),
                rx.flex(
                    rx.text("Business domains", weight="medium", size="2"),
                    rx.cond(
                        RadarState.domain_filter_count > 0,
                        rx.badge(RadarState.domain_filter_count.to_string() + " selected", color_scheme="orange", variant="soft", radius="full"),
                        rx.text("All domains", color=MUTED, size="1"),
                    ),
                    rx.spacer(),
                    rx.cond(
                        RadarState.domain_filter_count > 0,
                        rx.button("Clear", rx.icon("eraser", size=14), on_click=RadarState.clear_domain_filter, variant="ghost", color_scheme="gray", size="1", cursor="pointer"),
                        rx.box(),
                    ),
                    gap="2", align="center", width="100%", margin_top="4px",
                ),
                rx.flex(
                    rx.foreach(RadarState.domain_filter_options, lambda option: priority_chip(option, RadarState.toggle_domain_filter)),
                    wrap="wrap", gap="2", width="100%",
                ),
                rx.text(
                    "Selecting several domains widens the result - a space matches if any of its domains is selected. "
                    "A view mode only seeds these filters; changing one is a normal action, not an override.",
                    color=MUTED, size="1",
                ),
                rx.flex(
                    rx.text("Geography", weight="medium", size="2"),
                    rx.cond(
                        RadarState.region_filter_count > 0,
                        rx.badge(RadarState.region_filter_count.to_string() + " selected", color_scheme="orange", variant="soft", radius="full"),
                        rx.text("All regions", color=MUTED, size="1"),
                    ),
                    rx.spacer(),
                    rx.cond(
                        RadarState.region_filter_count > 0,
                        rx.button("Clear", rx.icon("eraser", size=14), on_click=RadarState.clear_region_filter, variant="ghost", color_scheme="gray", size="1", cursor="pointer"),
                        rx.box(),
                    ),
                    gap="2", align="center", width="100%", margin_top="4px",
                ),
                rx.flex(
                    rx.foreach(RadarState.region_filter_options, lambda option: priority_chip(option, RadarState.toggle_region_filter)),
                    wrap="wrap", gap="2", width="100%",
                ),
                rx.text(
                    "A space matches if any of its regions is selected. Global / Cross-region returns only topics "
                    "explicitly resolved there - EU-wide regulation and worldwide statements - not topics that simply "
                    "carry no geography, which stay a separate state.",
                    color=MUTED, size="1",
                ),
                spacing="3", width="100%",
                padding="16px", border=f"1px solid {LINE}", border_radius="16px", background="#121212",
            ),
            rx.cond(
                RadarState.visible_opportunities.length() > 0,
                rx.cond(
                    # Sales mode is read live in a meeting, so it uses one wide
                    # card per topic instead of the scanning grid.
                    RadarState.role_mode_is_single_column,
                    rx.vstack(rx.foreach(RadarState.visible_opportunities, sales_opportunity_card), spacing="5", width="100%"),
                    rx.grid(rx.foreach(RadarState.visible_opportunities, opportunity_card), columns=rx.breakpoints(initial="1", md="2", xl="3"), gap="5", width="100%"),
                ),
                empty_state("search-x", "No matching opportunities", "Try a broader domain, sector, horizon or search phrase."),
            ),
            spacing="6", width="100%", align="start",
        )
    )

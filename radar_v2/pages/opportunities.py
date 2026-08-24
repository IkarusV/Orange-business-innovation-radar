import reflex as rx

from radar_v2.components.shell import page_shell
from radar_v2.components.ui import empty_state, opportunity_card, page_header
from radar_v2.constants import LINE
from radar_v2.state import RadarState
from radar_v2.styles import INPUT


def opportunities() -> rx.Component:
    return page_shell(
        rx.vstack(
            page_header(
                "Opportunity portfolio", "Find the spaces that deserve a closer look.",
                "Filter the radar by sector and timing, then open any opportunity to review its supporting signals and business direction.",
            ),
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
                padding="16px", border=f"1px solid {LINE}", border_radius="16px", background="#121212",
            ),
            rx.cond(
                RadarState.visible_opportunities.length() > 0,
                rx.grid(rx.foreach(RadarState.visible_opportunities, opportunity_card), columns=rx.breakpoints(initial="1", md="2", xl="3"), gap="5", width="100%"),
                empty_state("search-x", "No matching opportunities", "Try a broader sector, horizon or search phrase."),
            ),
            spacing="6", width="100%", align="start",
        )
    )

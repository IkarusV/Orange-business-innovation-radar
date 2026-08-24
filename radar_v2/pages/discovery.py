import reflex as rx

from radar_v2.components.shell import page_shell
from radar_v2.components.ui import empty_state, page_header
from radar_v2.constants import LINE, MUTED, ORANGE
from radar_v2.state import RadarState
from radar_v2.styles import BUTTON, CARD, INPUT


def result_card(item) -> rx.Component:
    return rx.box(
        rx.hstack(rx.badge(item["source"], variant="soft", color_scheme="orange"), rx.text(item["date"], color=MUTED, size="1"), width="100%"),
        rx.heading(item["title"], size="4", margin_top="12px"),
        rx.text(item["excerpt"], color=MUTED, line_height="1.55", margin_top="8px"),
        rx.link("Open source", rx.icon("external-link", size=14), href=item["url"], is_external=True, color=ORANGE, display="flex", gap="6px", margin_top="12px"),
        **CARD,
    )


def discovery() -> rx.Component:
    return page_shell(
        rx.vstack(
            page_header("Market discovery", "Ask a focused question. Expand the evidence landscape.", "Search beyond the institutional backbone when a market, customer, competitor or regulation deserves a closer look."),
            rx.badge("Search provider: " + RadarState.search_provider, color_scheme="orange", variant="soft", radius="full"),
            rx.box(
                rx.flex(
                    rx.input(placeholder="What would you like to explore?", value=RadarState.discovery_query, on_change=RadarState.set_discovery_query, flex="1", **INPUT),
                    rx.button(
                        rx.cond(RadarState.discovery_running, rx.spinner(size="2"), rx.icon("search", size=17)),
                        rx.cond(RadarState.discovery_running, "Searching...", "Discover sources"),
                        on_click=RadarState.run_discovery,
                        disabled=RadarState.discovery_running,
                        **BUTTON,
                    ),
                    direction=rx.breakpoints(initial="column", sm="row"), gap="3", width="100%",
                ),
                rx.text(RadarState.search_message, color=MUTED, margin_top="12px"),
                rx.cond(RadarState.discovery_error != "", rx.text(RadarState.discovery_error, color="#ff8b8b", margin_top="6px"), rx.box()),
                rx.hstack(
                    rx.select(RadarState.discovery_vertical_options, value=RadarState.discovery_vertical, on_change=RadarState.set_discovery_vertical, width="260px"),
                    rx.button("Add to next radar update", rx.icon("plus", size=16), on_click=RadarState.add_discovery_to_radar, variant="outline", color_scheme="orange"),
                    margin_top="14px", spacing="3", align="center",
                ),
                **CARD,
            ),
            rx.cond(
                RadarState.discovery_results.length() > 0,
                rx.grid(rx.foreach(RadarState.discovery_results, result_card), columns=rx.breakpoints(initial="1", md="2"), gap="4", width="100%"),
                empty_state("compass", "Your discovery canvas", "Search a market question to reveal additional sources and perspectives."),
            ),
            spacing="6", width="100%", align="start",
        )
    )

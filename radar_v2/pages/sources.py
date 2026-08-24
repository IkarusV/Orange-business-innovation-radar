import reflex as rx

from radar_v2.components.shell import page_shell
from radar_v2.components.ui import page_header, section_title
from radar_v2.constants import LINE, MUTED, ORANGE
from radar_v2.state import RadarState
from radar_v2.styles import BUTTON, CARD, INPUT


def source_card(item) -> rx.Component:
    return rx.box(
        rx.hstack(rx.box(width="10px", height="10px", border_radius="50%", background=item["accent"]), rx.text(item["label"], weight="medium"), rx.spacer(), rx.badge(item["count"].to_string() + " signals", variant="soft"), width="100%"),
        rx.progress(value=item["count"], max=60, color_scheme="orange", margin_top="16px"),
        **CARD,
    )


def custom_source_row(item) -> rx.Component:
    return rx.hstack(
        rx.icon("globe", color=ORANGE, size=18),
        rx.vstack(rx.text(item["name"], weight="medium"), rx.link(item["url"], href=item["url"], is_external=True, color=MUTED, size="1"), spacing="1", align="start"),
        rx.spacer(), rx.badge(item["category"], variant="soft"),
        padding="14px 0", border_bottom=f"1px solid {LINE}", width="100%",
    )


def sources() -> rx.Component:
    return page_shell(
        rx.vstack(
            page_header("Source landscape", "A broader view starts with the right evidence.", "The radar combines institutional procurement and research signals with the priority sources your team chooses to follow."),
            rx.hstack(
                rx.text("Sector for collected source updates", color=MUTED),
                rx.select(RadarState.discovery_vertical_options, value=RadarState.discovery_vertical, on_change=RadarState.set_discovery_vertical, width="270px"),
                rx.button("Collect priority sources", rx.icon("refresh-cw", size=16), on_click=RadarState.collect_priority_sources, **BUTTON),
                width="100%", justify="end", align="center", spacing="3", wrap="wrap",
            ),
            rx.grid(rx.foreach(RadarState.source_mix, source_card), columns=rx.breakpoints(initial="1", sm="2", lg="4"), gap="4", width="100%"),
            rx.grid(
                rx.box(
                    section_title("Add a priority source", "Bring a market, partner or customer source into focus"),
                    rx.vstack(
                        rx.input(placeholder="Source name", value=RadarState.source_name, on_change=RadarState.set_source_name, **INPUT),
                        rx.input(placeholder="https://...", value=RadarState.source_url, on_change=RadarState.set_source_url, **INPUT),
                        rx.select(["Industry source", "Partner", "Customer", "Regulator", "Competitor"], value=RadarState.source_category, on_change=RadarState.set_source_category, width="100%"),
                        rx.button("Add source", on_click=RadarState.add_source, width="100%", **BUTTON),
                        spacing="3", width="100%",
                    ), **CARD,
                ),
                rx.box(
                    section_title("Priority watchlist", "Sources selected by your team"),
                    rx.cond(RadarState.custom_sources.length() > 0, rx.foreach(RadarState.custom_sources, custom_source_row), rx.text("Add a source to start your focused watchlist.", color=MUTED, padding="30px 0")),
                    **CARD,
                ),
                columns=rx.breakpoints(initial="1", lg="2"), gap="5", width="100%",
            ),
            spacing="6", width="100%", align="start",
        )
    )

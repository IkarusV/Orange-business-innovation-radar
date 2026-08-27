import reflex as rx

from radar_v2.components.shell import page_shell
from radar_v2.components.ui import metric_card, opportunity_card, page_header, section_title
from radar_v2.constants import LINE, MUTED, ORANGE, PANEL_SOFT
from radar_v2.state import RadarState
from radar_v2.styles import BUTTON, CARD


def overview() -> rx.Component:
    return page_shell(
        rx.vstack(
            page_header(
                "Strategic foresight",
                "Turn market signals into focused business moves.",
                "Explore institutional evidence across sectors, understand where momentum is building, and choose the opportunities worth advancing.",
                rx.link(rx.button("Explore opportunities", rx.icon("arrow-right", size=17), **BUTTON), href="/opportunities"),
            ),
            rx.grid(
                metric_card("Opportunity spaces", RadarState.metrics["opportunities"], "Prioritised business themes", "radar"),
                metric_card("Market signals", RadarState.metrics["signals"], "Procurement and research evidence", "radio-tower"),
                metric_card("Sectors covered", RadarState.metrics["verticals"], "Across the active portfolio", "layers-3"),
                columns=rx.breakpoints(initial="1", sm="2", lg="3"), gap="4", width="100%",
            ),
            rx.grid(
                rx.box(
                    section_title("Portfolio pulse", "Attractiveness across the current opportunity set"),
                    rx.recharts.bar_chart(
                        rx.recharts.cartesian_grid(stroke="#292929", vertical=False),
                        rx.recharts.x_axis(data_key="name", stroke=MUTED, font_size=10),
                        rx.recharts.y_axis(stroke=MUTED, domain=[0, 100]),
                        rx.recharts.tooltip(content_style={"background": "#111", "border": f"1px solid {LINE}", "border_radius": "10px"}),
                        rx.recharts.bar(data_key="relevance", fill=ORANGE, radius=[7, 7, 0, 0]),
                        data=RadarState.radar_chart_data,
                        height=320,
                        width="100%",
                        margin={"top": 30, "right": 10, "left": -20, "bottom": 20},
                    ),
                    **CARD,
                ),
                rx.box(
                    section_title("Source coverage", "A balanced institutional evidence base"),
                    rx.vstack(
                        rx.foreach(
                            RadarState.source_mix,
                            lambda item: rx.box(
                                rx.hstack(
                                    rx.box(width="10px", height="10px", border_radius="50%", background=item["accent"]),
                                    rx.text(item["label"], weight="medium"),
                                    rx.spacer(),
                                    rx.text(item["count"], color=ORANGE, weight="bold"),
                                    width="100%", align="center",
                                ),
                                rx.progress(value=item["count"], max=60, color_scheme="orange", margin_top="10px"),
                                width="100%", padding="13px 0", border_bottom=f"1px solid {LINE}",
                            ),
                        ),
                        spacing="0", width="100%",
                    ),
                    **CARD,
                ),
                columns=rx.breakpoints(initial="1", lg="2"), gap="5", width="100%",
            ),
            rx.hstack(
                section_title("Opportunities gaining momentum", "A focused selection from the current radar"),
                # This selection follows the active view mode's filters and sort,
                # so the mode has to be named here too.
                rx.badge(RadarState.role_mode_label + " view", color_scheme="orange", variant="soft", radius="full"),
                rx.spacer(),
                rx.link("View all", href="/opportunities", color=ORANGE, weight="medium"),
                width="100%", align="end",
            ),
            rx.grid(
                rx.foreach(RadarState.visible_opportunities[:3], opportunity_card),
                columns=rx.breakpoints(initial="1", md="2", xl="3"), gap="5", width="100%",
            ),
            spacing="7", width="100%", align="start",
        )
    )

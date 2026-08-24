import reflex as rx

from radar_v2.components.shell import page_shell
from radar_v2.components.ui import evidence_card, page_header, section_title, status_badge
from radar_v2.constants import LINE, MUTED, ORANGE
from radar_v2.state import RadarState
from radar_v2.styles import BUTTON, CARD, SOFT_CARD


def opportunity_detail() -> rx.Component:
    item = RadarState.selected_opportunity
    return page_shell(
        rx.vstack(
            rx.link(rx.hstack(rx.icon("arrow-left", size=15), rx.text("Back to opportunities"), spacing="2"), href="/opportunities", color=MUTED),
            page_header(
                item["vertical"], item["use_case"], item["summary"],
                rx.button("Build business report", rx.icon("file-chart-column", size=17), on_click=RadarState.choose_report_opportunity(item["id"]), **BUTTON),
            ),
            rx.hstack(status_badge(item["horizon"]), rx.badge(item["technology"], variant="surface", color_scheme="gray"), spacing="3"),
            rx.grid(
                rx.box(rx.text("Strategic fit", color=MUTED), rx.heading(item["relevance"].to_string() + "%", size="8", color=ORANGE), rx.progress(value=item["relevance"], color_scheme="orange", margin_top="12px"), **CARD),
                rx.box(rx.text("Evidence confidence", color=MUTED), rx.heading(item["confidence"].to_string() + "%", size="8"), rx.progress(value=item["confidence"], color_scheme="blue", margin_top="12px"), **CARD),
                rx.box(rx.text("Supporting signals", color=MUTED), rx.heading(item["article_count"], size="8"), rx.text("Institutional records", color=MUTED, margin_top="12px"), **CARD),
                rx.box(rx.text("Momentum", color=MUTED), rx.heading(item["momentum"], size="8", color="#4bd08b"), rx.text("Current evidence cycle", color=MUTED, margin_top="12px"), **CARD),
                columns=rx.breakpoints(initial="2", lg="4"), gap="4", width="100%",
            ),
            rx.grid(
                rx.box(
                    section_title("Business direction"),
                    rx.vstack(
                        rx.box(rx.text("Opportunity", color=MUTED, size="1"), rx.text(item["use_case"], weight="medium", margin_top="4px"), **SOFT_CARD),
                        rx.box(rx.text("Enabling capability", color=MUTED, size="1"), rx.text(item["technology"], weight="medium", margin_top="4px"), **SOFT_CARD),
                        rx.box(rx.text("Recommended move", color=MUTED, size="1"), rx.text("Validate with a focused customer conversation and shape a measurable proof of value.", line_height="1.55", margin_top="4px"), **SOFT_CARD),
                        spacing="3", width="100%",
                    ),
                    **CARD,
                ),
                rx.box(
                    section_title("Signal profile"),
                    rx.recharts.radial_bar_chart(
                        rx.recharts.radial_bar(data_key="value", background=True, fill=ORANGE),
                        data=[{"name": "Strategic fit", "value": item["relevance"]}, {"name": "Confidence", "value": item["confidence"]}],
                        inner_radius="35%", outer_radius="95%", start_angle=90, end_angle=-270, height=290, width="100%",
                    ),
                    **CARD,
                ),
                columns=rx.breakpoints(initial="1", lg="2"), gap="5", width="100%",
            ),
            section_title("Supporting evidence", "Open the original institutional records behind this opportunity"),
            rx.grid(rx.foreach(RadarState.evidence, evidence_card), columns=rx.breakpoints(initial="1", md="2"), gap="4", width="100%"),
            spacing="6", width="100%", align="start",
        )
    )

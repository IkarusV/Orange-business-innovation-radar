import reflex as rx

from radar_v2.components.shell import page_shell
from radar_v2.components.ui import empty_state, page_header, section_title
from radar_v2.constants import LINE, MUTED, ORANGE, TEXT
from radar_v2.state import RadarState
from radar_v2.styles import BUTTON, CARD, GHOST_BUTTON


def report_row(item) -> rx.Component:
    return rx.hstack(
        rx.center(rx.icon("file-chart-column", color=ORANGE, size=20), width="46px", height="46px", background="#2a1b0d", border_radius="12px"),
        rx.vstack(rx.text(item["title"], weight="medium"), rx.text(item["company"] + " · " + item["created"], color=MUTED, size="1"), spacing="1", align="start"),
        rx.spacer(),
        rx.badge(item["sources"].to_string() + " sources", variant="soft"),
        rx.badge(item["status"], color_scheme="green", variant="soft"),
        rx.button(rx.icon("arrow-right", size=16), on_click=RadarState.open_saved_report(item["id"]), aria_label="Open saved report", **GHOST_BUTTON),
        width="100%", padding="14px 0", border_bottom=f"1px solid {LINE}", align="center",
    )


def report_metric(item) -> rx.Component:
    return rx.box(
        rx.text(item["label"], color=MUTED, size="2"),
        rx.heading(item["value"], size="7", color=ORANGE, margin_top="8px"),
        rx.text(item["detail"], color=MUTED, size="1", margin_top="5px"),
        **CARD,
    )


def report_bullet(item) -> rx.Component:
    return rx.box(
        rx.text(item["title"], weight="bold"),
        rx.text(item["detail"], color=MUTED, line_height="1.55", margin_top="5px"),
        padding="14px 16px", background="#191919", border=f"1px solid {LINE}", border_radius="12px", width="100%",
    )


def report_risk(item) -> rx.Component:
    return rx.box(
        rx.hstack(rx.icon("triangle-alert", size=17, color="#ffb347"), rx.text(item["title"], weight="bold"), rx.spacer(), rx.badge(item["level"], variant="soft", color_scheme="orange"), width="100%", align="center"),
        rx.text(item["detail"], color=MUTED, line_height="1.55", margin_top="8px"),
        padding="15px 16px", background="#211b14", border="1px solid #4e3c21", border_radius="12px", width="100%",
    )


def reports() -> rx.Component:
    return page_shell(
        rx.vstack(
            page_header(
                "Decision reports", "Move from opportunity to an actionable business case.",
                "Create presentation-ready portfolio and evidence reports from the current radar, or develop a focused report around one priority opportunity.",
                rx.button("Generate portfolio reports", rx.icon("file-down", size=17), on_click=RadarState.generate_team_reports, **BUTTON),
            ),
            rx.grid(
                rx.box(rx.icon("chart-no-axes-combined", color=ORANGE, size=26), rx.heading("Portfolio overview", size="5", margin_top="18px"), rx.text("Coverage, source mix, sectors and evidence maturity in one concise report.", color=MUTED, margin_top="8px", line_height="1.5"), rx.button("Create overview", margin_top="20px", on_click=RadarState.generate_team_reports, **BUTTON), **CARD),
                rx.box(rx.icon("radar", color=ORANGE, size=26), rx.heading("Opportunity portfolio", size="5", margin_top="18px"), rx.text("Every complete opportunity space with its supporting institutional evidence and source links.", color=MUTED, margin_top="8px", line_height="1.5"), rx.button("Create portfolio", margin_top="20px", on_click=RadarState.generate_team_reports, **BUTTON), **CARD),
                rx.box(
                    rx.icon("briefcase-business", color=ORANGE, size=26),
                    rx.heading("Focused business case", size="5", margin_top="18px"),
                    rx.text("A deeper market, fit, risk and action plan for one opportunity selected below.", color=MUTED, margin_top="8px", line_height="1.5"),
                    rx.select(
                        RadarState.report_opportunity_options,
                        value=RadarState.selected_report_opportunity,
                        on_change=RadarState.set_report_opportunity,
                        placeholder="Select an opportunity",
                        margin_top="16px", width="100%",
                    ),
                    rx.button(
                        rx.cond(RadarState.report_running, rx.spinner(size="2"), rx.icon("sparkles", size=17)),
                        rx.cond(RadarState.report_running, "Building business case", "Generate focused report"),
                        on_click=RadarState.generate_focused_report,
                        disabled=RadarState.report_running,
                        margin_top="12px", width="100%", **BUTTON,
                    ),
                    **CARD,
                ),
                columns=rx.breakpoints(initial="1", lg="3"), gap="5", width="100%",
            ),
            section_title("Recent reports", "Your team's decision library"),
            rx.cond(
                RadarState.report_message != "",
                rx.box(rx.progress(value=RadarState.report_progress, color_scheme="orange"), rx.text(RadarState.report_message, color=MUTED, margin_top="8px"), **CARD, width="100%"),
                rx.box(),
            ),
            rx.cond(
                RadarState.report_id > 0,
                rx.box(
                    rx.hstack(rx.icon("file-chart-column", color=ORANGE, size=22), rx.vstack(rx.text("Open report", color=ORANGE, size="1", text_transform="uppercase", letter_spacing=".15em"), rx.heading(RadarState.report_title, size="5"), spacing="1", align="start"), spacing="3"),
                    rx.grid(rx.foreach(RadarState.report_metrics, report_metric), columns=rx.breakpoints(initial="2", md="4"), gap="4", margin_top="22px"),
                    rx.heading("Executive summary", size="4", margin_top="20px"),
                    rx.text(RadarState.report_summary, color=MUTED, line_height="1.65", margin_top="8px"),
                    rx.heading("Recommendation", size="4", margin_top="20px"),
                    rx.box(rx.text(RadarState.report_recommendation, color=TEXT, line_height="1.65"), padding="16px 18px", background="#241707", border="1px solid #704711", border_radius="12px", margin_top="8px"),
                    rx.grid(
                        rx.box(rx.heading("Market pulse", size="4"), rx.vstack(rx.foreach(RadarState.report_market_items, report_bullet), spacing="3", margin_top="12px"), **CARD),
                        rx.box(rx.heading("Financial picture", size="4"), rx.vstack(rx.foreach(RadarState.report_finance_items, report_bullet), spacing="3", margin_top="12px"), **CARD),
                        columns=rx.breakpoints(initial="1", lg="2"), gap="5", margin_top="20px",
                    ),
                    rx.cond(
                        RadarState.report_ranges.length() > 0,
                        rx.box(
                            rx.heading("Market range", size="4"),
                            rx.recharts.bar_chart(
                                rx.recharts.cartesian_grid(stroke="#292929", vertical=False),
                                rx.recharts.x_axis(data_key="label", stroke=MUTED, font_size=9),
                                rx.recharts.y_axis(stroke=MUTED),
                                rx.recharts.tooltip(content_style={"background": "#111", "border": "1px solid #333"}),
                                rx.recharts.bar(data_key="low", fill="#a86114", radius=[6, 6, 0, 0]),
                                rx.recharts.bar(data_key="high", fill=ORANGE, radius=[6, 6, 0, 0]),
                                data=RadarState.report_ranges, height=300, width="100%",
                            ),
                            rx.text("Low/high values are shown only when the report provides comparable numeric ranges.", color=MUTED, size="1"),
                            **CARD, width="100%", margin_top="20px",
                        ),
                        rx.box(),
                    ),
                    rx.grid(
                        rx.box(rx.heading("Company fit", size="4"), rx.vstack(rx.foreach(RadarState.report_fit_items, report_bullet), spacing="3", margin_top="12px"), **CARD),
                        rx.box(rx.heading("Risks to manage", size="4"), rx.vstack(rx.foreach(RadarState.report_risk_items, report_risk), spacing="3", margin_top="12px"), **CARD),
                        columns=rx.breakpoints(initial="1", lg="2"), gap="5", margin_top="20px",
                    ),
                    rx.box(rx.heading("Roadmap", size="4"), rx.vstack(rx.foreach(RadarState.report_roadmap_items, report_bullet), spacing="3", margin_top="12px"), **CARD, margin_top="20px"),
                    rx.accordion.root(
                        rx.accordion.item(
                            header="Research trail and sources",
                            content=rx.vstack(
                            rx.heading("Research queries", size="4", margin_top="18px"),
                            rx.vstack(rx.foreach(RadarState.report_queries, lambda query: rx.text(query, color=MUTED, size="2")), spacing="2", align="start", margin_top="8px"),
                            rx.heading("Sources", size="4", margin_top="20px"),
                            rx.vstack(
                                rx.foreach(
                                    RadarState.report_sources,
                                    lambda source: rx.link(
                                        rx.hstack(rx.text(source["title"], color=ORANGE, size="2"), rx.text(" · "), rx.text(source["url"], color=MUTED, size="2"), spacing="1"),
                                        href=source["url"], is_external=True,
                                    ),
                                ),
                                spacing="2", align="start", margin_top="8px",
                            ),
                            spacing="3", width="100%",
                            ),
                            value="research-trail",
                            color_scheme="orange",
                        ),
                        type="single", collapsible=True, variant="surface", width="100%", margin_top="28px",
                    ),
                    **CARD, width="100%",
                ),
                rx.box(),
            ),
            rx.cond(
                RadarState.reports.length() > 0,
                rx.box(rx.foreach(RadarState.reports, report_row), **CARD, width="100%"),
                empty_state("files", "No saved reports yet", "Generate a portfolio report or open an opportunity to build a focused business case."),
            ),
            spacing="6", width="100%", align="start",
        )
    )

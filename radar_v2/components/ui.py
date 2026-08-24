import reflex as rx

from radar_v2.constants import LINE, MUTED, ORANGE, PANEL_SOFT, TEXT
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


def opportunity_card(item) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.badge(item["vertical"], color_scheme="gray", variant="soft", radius="full"),
            rx.spacer(),
            status_badge(item["horizon"]),
            width="100%",
        ),
        rx.heading(item["use_case"], size="5", margin_top="18px"),
        rx.text(item["technology"], color=ORANGE, weight="medium", margin_top="3px"),
        rx.text(item["summary"], color=MUTED, line_height="1.55", margin_top="13px", min_height="72px"),
        rx.grid(
            rx.vstack(rx.text("Fit", color=MUTED, size="1"), rx.text(item["relevance"].to_string() + "%", weight="bold"), spacing="1", align="start"),
            rx.vstack(rx.text("Confidence", color=MUTED, size="1"), rx.text(item["confidence"].to_string() + "%", weight="bold"), spacing="1", align="start"),
            rx.vstack(rx.text("Signals", color=MUTED, size="1"), rx.text(item["article_count"], weight="bold"), spacing="1", align="start"),
            columns="3", gap="3", margin_top="18px",
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

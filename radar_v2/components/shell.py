import reflex as rx

from radar_v2.constants import LINE, MUTED, ORANGE, PANEL, TEXT
from radar_v2.state import RadarState
from radar_v2.styles import GHOST_BUTTON, PAGE


NAV_ITEMS = [
    ("grid-2x2", "Overview", "/"),
    ("radar", "Opportunities", "/opportunities"),
    ("building-2", "Company", "/company"),
    ("database", "Sources", "/sources"),
    ("search", "Discovery", "/discovery"),
    ("file-chart-column", "Reports", "/reports"),
    ("refresh-cw", "Radar update", "/refresh"),
    ("settings-2", "Settings", "/settings"),
]


def nav_link(icon: str, label: str, href: str) -> rx.Component:
    return rx.link(
        rx.hstack(
            rx.icon(icon, size=18),
            rx.text(label, weight="medium"),
            spacing="3",
            align="center",
        ),
        href=href,
        color=TEXT,
        text_decoration="none",
        padding="11px 13px",
        border_radius="11px",
        width="100%",
        _hover={"background": "#232323", "color": ORANGE},
    )


def sidebar() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.box(width="12px", height="34px", background=ORANGE, border_radius="3px"),
                rx.vstack(
                    rx.text("COBALT DATA SOCIETY", font_size="10px", letter_spacing=".18em", color=ORANGE, weight="bold"),
                    rx.heading("Innovation Radar", size="5", color=TEXT),
                    spacing="0",
                    align="start",
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            rx.separator(color=LINE),
            rx.vstack(*[nav_link(*item) for item in NAV_ITEMS], spacing="1", width="100%"),
            rx.spacer(),
            rx.link(
                rx.hstack(rx.icon("circle-help", size=18), rx.text("Help"), spacing="3"),
                href="/help", color=MUTED, text_decoration="none", padding="11px 13px",
                _hover={"color": ORANGE},
            ),
            rx.hstack(
                rx.avatar(fallback="OB", radius="full", size="2", color_scheme="orange"),
                rx.vstack(
                    rx.text(RadarState.company_name, color=TEXT, size="2", weight="medium"),
                    rx.text(RadarState.company_geography, color=MUTED, size="1"),
                    spacing="0", align="start",
                ),
                spacing="3", align="center", width="100%",
            ),
            width="100%",
            height="100%",
            align="start",
            spacing="5",
        ),
        position="fixed",
        left="0",
        top="0",
        bottom="0",
        width="255px",
        background=PANEL,
        border_right=f"1px solid {LINE}",
        padding="28px 18px",
        display=rx.breakpoints(initial="none", lg="block"),
        z_index="20",
    )


def mobile_nav() -> rx.Component:
    return rx.hstack(
        rx.heading("Innovation Radar", size="4"),
        rx.spacer(),
        rx.menu.root(
            rx.menu.trigger(rx.button(rx.icon("menu"), **GHOST_BUTTON)),
            rx.menu.content(*[
                rx.menu.item(rx.link(label, href=href, color=TEXT, text_decoration="none"))
                for _, label, href in NAV_ITEMS
            ]),
        ),
        display=rx.breakpoints(initial="flex", lg="none"),
        position="sticky", top="0", z_index="30", width="100%",
        padding="15px 20px", background=PANEL, border_bottom=f"1px solid {LINE}",
    )


def page_shell(content: rx.Component) -> rx.Component:
    return rx.box(
        sidebar(),
        mobile_nav(),
        rx.box(
            content,
            margin_left=rx.breakpoints(initial="0", lg="255px"),
            padding=rx.breakpoints(initial="22px", sm="32px", lg="40px 46px"),
            max_width="1700px",
        ),
        **PAGE,
    )

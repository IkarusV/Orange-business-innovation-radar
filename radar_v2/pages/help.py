import reflex as rx

from radar_v2.components.shell import page_shell
from radar_v2.components.ui import page_header
from radar_v2.constants import MUTED, ORANGE
from radar_v2.styles import CARD


ITEMS = [
    ("Opportunity space", "A focused combination of sector, business use case and enabling technology."),
    ("Signal", "A procurement, research, investment or market record that points to activity around an opportunity."),
    ("Strategic fit", "How closely an opportunity aligns with the active company's priorities and capabilities."),
    ("Confidence", "How consistently the available evidence supports the opportunity classification."),
    ("Now · Next · Later", "A simple planning horizon: act now, prepare next, or continue watching."),
]


def help_page() -> rx.Component:
    return page_shell(
        rx.vstack(
            page_header("Help", "A clear view of the radar in two minutes.", "The radar gathers market activity, finds recurring patterns and organises them into focused opportunity spaces for business discussion."),
            rx.grid(*[
                rx.box(rx.text(str(index + 1).zfill(2), color=ORANGE, font_size="12px", letter_spacing=".15em", weight="bold"), rx.heading(title, size="5", margin_top="12px"), rx.text(text, color=MUTED, line_height="1.6", margin_top="8px"), **CARD)
                for index, (title, text) in enumerate(ITEMS)
            ], columns=rx.breakpoints(initial="1", md="2", lg="3"), gap="4", width="100%"),
            rx.box(
                rx.heading("How to use it", size="6"),
                rx.text("Start with the overview, filter the opportunity portfolio, open the evidence behind promising spaces, and use the company workspace to keep recommendations aligned with your business. Refresh the radar when you want a new evidence cycle.", color=MUTED, line_height="1.7", margin_top="12px", max_width="900px"),
                **CARD, width="100%",
            ),
            spacing="6", width="100%", align="start",
        )
    )

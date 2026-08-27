import reflex as rx

from radar_v2.components.shell import page_shell
from radar_v2.components.ui import page_header, section_title
from radar_v2.constants import LINE, MUTED, ORANGE, TEXT
from radar_v2.state import RadarState
from radar_v2.styles import BUTTON, CARD, SOFT_CARD


STAGES = [
    ("database", "Collect", "Institutional procurement and research signals"),
    ("list-filter", "Focus", "A balanced evidence corpus across sectors and time"),
    ("sparkles", "Prioritise", "The learning model focuses attention on useful signals"),
    ("radar", "Map", "Signals become sector × use case × technology spaces"),
]


def refresh() -> rx.Component:
    return page_shell(
        rx.vstack(
            page_header("Radar update", "Run the full radar update.", "One controlled action collects institutional evidence, builds the corpus, applies the team learning model, classifies selected articles and refreshes opportunity spaces."),
            rx.box(
                    rx.hstack(
                        rx.icon("circle-play", color=ORANGE, size=22),
                    rx.vstack(
                        rx.heading("Quick start", size="5"),
                        rx.text("Start the complete team pipeline - it classifies the entire pending evidence pool, no cap.", color=MUTED, size="2"),
                        spacing="1", align="start",
                    ),
                    rx.spacer(),
                    rx.badge("Team pipeline", color_scheme="orange", variant="soft"),
                    width="100%", align="center",
                ),
                    rx.text("The team classifier sends one article per AI request, uncapped - every pending article is classified each run. Collection and corpus selection use the team pipeline's configured source rules.", color=MUTED, line_height="1.55", margin_top="16px"),
                    rx.hstack(
                        rx.cond(RadarState.provider_session_active, rx.badge("Provider ready", color_scheme="green", variant="soft"), rx.badge("Provider not active", color_scheme="gray", variant="soft")),
                        rx.cond(RadarState.provider_session_active, rx.text("The configured intelligence provider can run this update.", color=MUTED, size="2"), rx.text("Activate the provider in Settings before starting.", color="#ffb0b0", size="2")),
                        spacing="3", align="center", margin_top="14px",
                    ),
                    **CARD, width="100%",
            ),
            rx.grid(
                rx.box(
                    section_title("Update scope"),
                    rx.text("No cap - every pending article is sent to the classifier each run.", color=MUTED, margin_top="20px"),
                    rx.vstack(
                        rx.hstack(rx.text("Articles to classify this run", color=MUTED, size="2"), rx.spacer(), rx.text(RadarState.pipeline_preflight["classification_calls"], color=ORANGE, weight="bold"), width="100%"),
                        rx.hstack(rx.text("Current corpus", color=MUTED, size="2"), rx.spacer(), rx.text(RadarState.pipeline_preflight["pool"], color=TEXT, weight="bold"), width="100%"),
                        rx.hstack(rx.text("ML-scored records", color=MUTED, size="2"), rx.spacer(), rx.text(RadarState.pipeline_preflight["ml_scored"], color=TEXT, weight="bold"), width="100%"),
                        spacing="2", width="100%", margin_top="18px",
                    ),
                    rx.button(
                        rx.cond(RadarState.pipeline_running, rx.spinner(size="2"), rx.icon("refresh-cw", size=18)),
                        rx.cond(RadarState.pipeline_running, "Running radar update", "Run full radar update"),
                        on_click=RadarState.run_pipeline,
                        disabled=RadarState.pipeline_running,
                        width="100%", margin_top="24px", **BUTTON,
                    ),
                    **CARD,
                ),
                rx.box(
                    section_title("Live progress", "The current stage and message update while the team pipeline runs"),
                    rx.hstack(rx.heading(RadarState.pipeline_stage, size="5"), rx.spacer(), rx.text(RadarState.pipeline_progress.to_string() + "%", color=ORANGE, weight="bold"), width="100%", margin_top="20px"),
                    rx.progress(value=RadarState.pipeline_progress, color_scheme="orange", size="3", margin_top="15px"),
                    rx.text(RadarState.pipeline_message, color=MUTED, line_height="1.6", margin_top="18px"),
                    rx.grid(*[
                        rx.box(rx.icon(icon, size=18, color=ORANGE), rx.text(title, weight="medium", margin_top="10px"), rx.text(text, color=MUTED, size="1", line_height="1.45", margin_top="4px"), **SOFT_CARD)
                        for icon, title, text in STAGES
                    ], columns=rx.breakpoints(initial="2", lg="4"), gap="3", margin_top="24px"),
                    **CARD,
                ),
                columns=rx.breakpoints(initial="1", lg="2"), gap="5", width="100%",
            ),
            rx.box(
                section_title("Latest update"),
                rx.grid(
                    rx.vstack(rx.text("Run", color=MUTED, size="1"), rx.text(RadarState.last_run["run_id"], weight="medium"), spacing="1", align="start"),
                    rx.vstack(rx.text("Evidence pool", color=MUTED, size="1"), rx.text(RadarState.last_run["pool_size"], weight="medium"), spacing="1", align="start"),
                    rx.vstack(rx.text("Processing time", color=MUTED, size="1"), rx.text(RadarState.last_run["elapsed_seconds"].to_string() + " sec"), spacing="1", align="start"),
                    rx.vstack(rx.text("Evidence processed", color=MUTED, size="1"), rx.text(RadarState.last_run["tokens_this_run"], weight="medium"), spacing="1", align="start"),
                    columns=rx.breakpoints(initial="2", lg="4"), gap="4", margin_top="20px",
                ),
                **CARD, width="100%",
            ),
            spacing="6", width="100%", align="start",
        )
    )

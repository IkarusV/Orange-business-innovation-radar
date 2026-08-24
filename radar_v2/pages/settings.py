import reflex as rx

from radar_v2.components.shell import page_shell
from radar_v2.components.ui import page_header, section_title
from radar_v2.constants import MUTED
from radar_v2.state import RadarState
from radar_v2.styles import BUTTON, CARD, INPUT


def settings_page() -> rx.Component:
    return page_shell(
        rx.vstack(
            page_header(
                "Settings", "Connect the services behind your radar.",
                "Choose the intelligence model and search provider used for discovery, company knowledge and radar updates.",
            ),
            rx.grid(
                rx.box(
                    section_title("Intelligence provider", "Used for company knowledge and opportunity mapping"),
                    rx.vstack(
                        rx.text("Provider endpoint", color=MUTED, size="1"),
                        rx.input(value=RadarState.ai_base_url, on_change=RadarState.set_ai_base_url, placeholder="https://api.example.com/v1", **INPUT),
                        rx.text("Model", color=MUTED, size="1", margin_top="6px"),
                        rx.input(value=RadarState.ai_model, on_change=RadarState.set_ai_model, placeholder="Model name", **INPUT),
                        rx.text("API style", color=MUTED, size="1", margin_top="6px"),
                        rx.select(["responses", "chat"], value=RadarState.ai_mode, on_change=RadarState.set_ai_mode, width="100%"),
                        rx.text("Provider key", color=MUTED, size="1", margin_top="6px"),
                        rx.input(value=RadarState.ai_api_key, on_change=RadarState.set_ai_api_key, on_blur=RadarState.set_ai_api_key, type="password", placeholder="Activate this session after entering the key", **INPUT),
                        rx.hstack(
                            rx.cond(RadarState.provider_session_active, rx.badge("Provider ready", color_scheme="green", variant="soft"), rx.badge("Provider not active", color_scheme="gray", variant="soft")),
                            rx.spacer(),
                            rx.cond(RadarState.provider_session_active, rx.button("Disconnect", on_click=RadarState.deactivate_provider, variant="outline", color_scheme="gray"), rx.button("Activate session", on_click=RadarState.activate_provider, color_scheme="orange")),
                            width="100%", align="center", margin_top="8px",
                        ),
                        spacing="2", width="100%", align="start",
                    ),
                    **CARD,
                ),
                rx.box(
                    section_title("Search provider", "Used by focused market discovery"),
                    rx.vstack(
                        rx.text("Search service", color=MUTED, size="1"),
                        rx.select(["searxng", "tavily"], value=RadarState.search_provider, on_change=RadarState.set_search_provider, width="100%"),
                        rx.cond(
                            RadarState.search_provider == "searxng",
                            rx.vstack(
                                rx.text("SearXNG URL", color=MUTED, size="1", margin_top="6px"),
                                rx.input(value=RadarState.searxng_url, on_change=RadarState.set_searxng_url, placeholder="http://localhost:8888", **INPUT),
                                width="100%", align="start", spacing="2",
                            ),
                            rx.vstack(
                                rx.text("Tavily key", color=MUTED, size="1", margin_top="6px"),
                                rx.input(value=RadarState.tavily_api_key, on_change=RadarState.set_tavily_api_key, type="password", placeholder="Kept for this browser session", **INPUT),
                                rx.text("Search depth", color=MUTED, size="1", margin_top="6px"),
                                rx.select(["basic", "advanced"], value=RadarState.tavily_depth, on_change=RadarState.set_tavily_depth, width="100%"),
                                width="100%", align="start", spacing="2",
                            ),
                        ),
                        rx.text("Results per search", color=MUTED, size="1", margin_top="6px"),
                        rx.select(["5", "8", "10", "15", "20"], value=RadarState.max_search_results.to_string(), on_change=RadarState.set_max_search_results, width="100%"),
                        rx.text("Research queries per business report", color=MUTED, size="1", margin_top="6px"),
                        rx.select([str(value) for value in range(1, 21)], value=RadarState.max_research_queries.to_string(), on_change=RadarState.set_max_research_queries, width="100%"),
                        spacing="2", width="100%", align="start",
                    ),
                    **CARD,
                ),
                columns=rx.breakpoints(initial="1", lg="2"), gap="5", width="100%",
            ),
            rx.hstack(
                rx.button("Save settings", on_click=RadarState.save_settings, flex="1", **BUTTON),
                rx.cond(RadarState.provider_session_active, rx.badge("Ready to run", color_scheme="green", variant="surface", padding="12px"), rx.badge("Activate provider to run", color_scheme="gray", variant="surface", padding="12px")),
                width="100%", align="center", spacing="3",
            ),
            spacing="6", width="100%", align="start",
        )
    )

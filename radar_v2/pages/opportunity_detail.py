import reflex as rx

from radar_v2.components.shell import page_shell
from radar_v2.components.ui import (
    attractiveness_row,
    detail_region,
    evidence_card,
    horizon_check_row,
    page_header,
    persona_relevance_row,
    placeholder_region,
    publication_badge,
    role_mode_switcher,
    section_title,
    signal_type_row,
    status_badge,
)
from radar_v2.constants import LINE, MUTED, ORANGE
from radar_v2.state import RadarState
from radar_v2.styles import BUTTON, CARD, SOFT_CARD


def _identity_card(item) -> rx.Component:
    """Always visible, in every mode: what this space actually is. Not part of
    the mode-switched region set."""
    return rx.box(
        section_title("Business direction"),
        rx.grid(
            rx.box(rx.text("Opportunity", color=MUTED, size="1"), rx.text(item["use_case"], weight="medium", margin_top="4px"), **SOFT_CARD),
            rx.box(rx.text("Enabling capability", color=MUTED, size="1"), rx.text(item["technology"], weight="medium", margin_top="4px"), **SOFT_CARD),
            rx.box(
                rx.text("Business domain", color=MUTED, size="1"),
                rx.text(item["primary_domain_label"], weight="medium", margin_top="4px"),
                rx.text(
                    "Derived from the technology and use case assignment - the primary always comes from the technology.",
                    color=MUTED, size="1", line_height="1.5", margin_top="6px",
                ),
                **SOFT_CARD,
            ),
            columns=rx.breakpoints(initial="1", md="3"), gap="3", width="100%", margin_top="16px",
        ),
        **CARD, width="100%",
    )


def _market_size_card(item) -> rx.Component:
    """Opportunity-level annual addressable potential. Missing validation is
    rendered as evidence status, never as zero or a fabricated euro value."""
    market = item["market_size"]
    return rx.box(
        section_title(
            "Estimated annual addressable potential",
            "Opportunity-level scenario for Europe; separate from Attractiveness and Orange Fit",
        ),
        rx.flex(
            rx.box(
                rx.text("Market-size range", color=MUTED, size="1"),
                rx.heading(market["range_label"], size="7", color=rx.cond(market["estimated"], ORANGE, MUTED), margin_top="6px"),
                rx.text(market["availability_label"], color=MUTED, size="2", margin_top="8px"),
                flex="1", min_width="260px",
            ),
            rx.box(
                rx.text("Scope and coverage", color=MUTED, size="1"),
                rx.text(market["scope_label"], weight="medium", margin_top="6px"),
                rx.text(market["coverage_label"], color=MUTED, size="2", margin_top="6px"),
                flex="1", min_width="220px",
            ),
            rx.box(
                rx.text("Method", color=MUTED, size="1"),
                rx.text(market["method_label"], size="2", line_height="1.5", margin_top="6px"),
                flex="1", min_width="260px",
            ),
            gap="5", wrap="wrap", width="100%", margin_top="16px",
        ),
        rx.cond(
            market["context_note"] != "",
            rx.callout(
                market["context_note"], icon="info", color_scheme="gray", size="1",
                width="100%", margin_top="16px",
            ),
        ),
        rx.text(market["source_note"], color=MUTED, size="1", line_height="1.5", margin_top="12px"),
        **CARD, width="100%",
    )


def opportunity_detail() -> rx.Component:
    item = RadarState.selected_opportunity
    return page_shell(
        rx.vstack(
            rx.link(rx.hstack(rx.icon("arrow-left", size=15), rx.text("Back to opportunities"), spacing="2"), href="/opportunities", color=MUTED),
            page_header(
                item["vertical"], item["use_case"], item["summary"],
                rx.button("Build business report", rx.icon("file-chart-column", size=17), on_click=RadarState.choose_report_opportunity(item["id"]), **BUTTON),
            ),
            role_mode_switcher(compact=True),
            rx.flex(
                status_badge(item["horizon"]),
                publication_badge(item["publication_status"]),
                rx.badge(item["technology"], variant="surface", color_scheme="gray"),
                rx.foreach(
                    item["domain_labels"],
                    lambda label: rx.badge(label, variant="surface", color_scheme="orange", radius="full"),
                ),
                rx.cond(item["horizon_reason"], rx.text(item["horizon_reason"], color=MUTED, size="2")),
                gap="3", align="center", wrap="wrap",
            ),
            rx.grid(
                rx.box(rx.text("Attractiveness", color=MUTED), rx.heading(item["relevance"].to_string() + " / 100", size="8", color=ORANGE), rx.progress(value=item["relevance"], color_scheme="orange", margin_top="12px"), **CARD),
                rx.box(
                    rx.text("Orange fit", color=MUTED),
                    rx.heading(item["orange_fit_score"].to_string() + " / 100", size="8"),
                    rx.progress(value=item["orange_fit_score"], color_scheme="gray", margin_top="12px"),
                    **CARD,
                ),
                rx.box(rx.text("Evidence confidence", color=MUTED), rx.heading(item["confidence"].to_string() + "%", size="8"), rx.progress(value=item["confidence"], color_scheme="blue", margin_top="12px"), **CARD),
                rx.box(rx.text("Supporting signals", color=MUTED), rx.heading(item["article_count"], size="8"), rx.text("Institutional records", color=MUTED, margin_top="12px"), **CARD),
                rx.box(
                    rx.text("Momentum", color=MUTED),
                    rx.heading(item["momentum"], size="8", color=rx.match(item["momentum"], ("New", ORANGE), ("—", MUTED), "#4bd08b")),
                    rx.text(rx.match(item["momentum"], ("New", "No earlier evidence to compare"), ("—", "Not enough dated evidence"), "Against the previous 90 days"), color=MUTED, margin_top="12px"),
                    **CARD,
                ),
                columns=rx.breakpoints(initial="2", lg="5"), gap="4", width="100%",
            ),
            _market_size_card(item),
            _identity_card(item),
            # Region order and expansion come from the active mode's presentation
            # profile. CSS ordering is used rather than conditional rendering so
            # every region is in the page in every mode.
            rx.flex(
                detail_region(
                    "why_hot_now",
                    rx.box(rx.text(item["why_hot_now"], line_height="1.6"), **SOFT_CARD, width="100%"),
                    rx.callout(
                        "One clause per recent signal, strongest evidence type first. A space with a single "
                        "qualifying signal gets a single clause rather than a padded sentence.",
                        icon="info", color_scheme="gray", size="1", width="100%", margin_top="12px",
                    ),
                ),
                detail_region(
                    "why_this_matters",
                    rx.box(rx.text(item["why_this_matters"], line_height="1.6"), **SOFT_CARD, width="100%"),
                    rx.callout(
                        "The second clause lists every right-to-win element on the record. No account, deal, "
                        "reference case, offering or partner data exists in the radar yet, so it currently states "
                        "that absence rather than filling it in.",
                        icon="info", color_scheme="gray", size="1", width="100%", margin_top="12px",
                    ),
                ),
                detail_region(
                    "recommended_move",
                    rx.box(rx.text(RadarState.recommended_move_text, line_height="1.6"), **SOFT_CARD, width="100%"),
                    rx.callout(
                        "Composed for the active view mode from this space's timing, its strongest persona and its "
                        "leading signal type - a strategist, a salesperson and a presales engineer get different "
                        "moves on the same space.",
                        icon="info", color_scheme="gray", size="1", width="100%", margin_top="12px",
                    ),
                ),
                detail_region(
                    "score_breakdown",
                    rx.vstack(
                        rx.foreach(item["breakdown"], attractiveness_row),
                        spacing="3", width="100%",
                    ),
                    rx.callout(
                        "Components with no data yet are left out of the weighted score and the remaining weights are rescaled - a missing signal is never counted as a zero.",
                        icon="info", color_scheme="gray", size="1", width="100%", margin_top="16px",
                    ),
                    rx.box(
                        section_title("Why this timing", "Derived from what kind of signals this space has and when they landed - not from its score"),
                        rx.hstack(
                            status_badge(item["horizon"]),
                            rx.text(item["horizon_rule"], color=MUTED, size="2"),
                            spacing="3", align="center", margin_top="14px",
                        ),
                        rx.vstack(
                            rx.foreach(item["horizon_breakdown"], horizon_check_row),
                            spacing="3", width="100%", margin_top="16px",
                        ),
                        rx.callout(
                            "Now needs converging evidence: several concrete signals, from different sources, at least one of them recent. "
                            "A single tender, or two records from the same feed, lands in Next.",
                            icon="info", color_scheme="gray", size="1", width="100%", margin_top="16px",
                        ),
                        margin_top="20px", padding_top="20px", border_top=f"1px solid {LINE}", width="100%",
                    ),
                    rx.box(
                        section_title("Why Radar or Watchlist", "Evidence independence, not timing or attractiveness - see the badge next to the horizon badge above"),
                        rx.hstack(
                            publication_badge(item["publication_status"]),
                            rx.text(
                                rx.cond(
                                    item["publication_status"] == "RADAR",
                                    "Clears the independent-evidence bar for a curated Radar pick.",
                                    "Does not yet clear the independent-evidence bar - still worth tracking as a Watchlist item.",
                                ),
                                color=MUTED, size="2",
                            ),
                            spacing="3", align="center", margin_top="14px",
                        ),
                        rx.vstack(
                            rx.foreach(item["gate_breakdown"], horizon_check_row),
                            spacing="3", width="100%", margin_top="16px",
                        ),
                        margin_top="20px", padding_top="20px", border_top=f"1px solid {LINE}", width="100%",
                    ),
                    rx.box(
                        section_title("Orange Fit", "Orange Business fit / right-to-win - standalone from attractiveness, never one of its weighted components"),
                        rx.hstack(
                            rx.heading(item["orange_fit_score"].to_string() + " / 100", size="6"),
                            spacing="3", align="center", margin_top="14px",
                        ),
                        rx.text(
                            "Matched against the priority use cases and technologies set in Company when configured; "
                            "otherwise a fallback based on how many Orange Business domains this space touches.",
                            color=MUTED, size="2", line_height="1.5", margin_top="8px",
                        ),
                        margin_top="20px", padding_top="20px", border_top=f"1px solid {LINE}", width="100%",
                    ),
                ),
                detail_region(
                    "signals_evidence",
                    rx.box(
                        section_title("Signal types behind it", "Each answered against the article text alone"),
                        rx.cond(
                            item["signal_mix"],
                            rx.vstack(
                                rx.foreach(item["signal_mix"], signal_type_row),
                                spacing="3", width="100%", margin_top="16px",
                            ),
                            rx.callout(
                                "No signal types assigned to this evidence yet - run the classifier to populate them.",
                                icon="info", color_scheme="gray", size="1", width="100%", margin_top="16px",
                            ),
                        ),
                        width="100%",
                    ),
                    rx.box(
                        section_title("Supporting evidence", "Open the original institutional records behind this opportunity"),
                        rx.grid(rx.foreach(RadarState.evidence, evidence_card), columns=rx.breakpoints(initial="1", md="2"), gap="4", width="100%", margin_top="16px"),
                        margin_top="20px", padding_top="20px", border_top=f"1px solid {LINE}", width="100%",
                    ),
                ),
                detail_region(
                    "offering_matches",
                    placeholder_region(
                        "Offering & partner matches",
                        "Offering and partner matching is not part of the radar yet. The space's business domain and enabling "
                        "capability above are the closest available connection to the catalogue.",
                    ),
                ),
                detail_region(
                    "persona_relevance",
                    rx.cond(
                        RadarState.persona_weighting_available,
                        rx.cond(
                            item["persona_weights"].length() > 0,
                            rx.vstack(
                                rx.foreach(item["persona_weights"], persona_relevance_row),
                                spacing="3", width="100%",
                            ),
                            placeholder_region(
                                "Persona relevance",
                                "No persona clears even the peripheral tier for this space's use case, "
                                "business domain and vertical combination.",
                            ),
                        ),
                        placeholder_region(
                            "Persona relevance",
                            "Persona relevance weighting is not implemented yet, so no persona score is shown. "
                            "Every persona threshold in the view modes is currently a no-op.",
                        ),
                    ),
                ),
                direction="row", wrap="wrap", gap="5", width="100%", align="start",
            ),
            spacing="6", width="100%", align="start",
        )
    )

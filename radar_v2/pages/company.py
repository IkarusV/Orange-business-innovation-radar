import reflex as rx

from radar_v2.components.shell import page_shell
from radar_v2.components.ui import empty_state, page_header, priority_chip, section_title
from radar_v2.constants import LINE, MUTED, ORANGE
from radar_v2.state import RadarState
from radar_v2.styles import BUTTON, CARD, INPUT, SOFT_CARD


def document_row(item) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.button(
                rx.cond(item["selected"], rx.icon("circle-check-big", size=19), rx.icon("circle", size=19)),
                on_click=RadarState.toggle_document(item["id"]),
                variant="ghost", color_scheme="orange", padding="6px",
            ),
            rx.center(rx.icon("file-text", color=ORANGE, size=19), width="42px", height="42px", background="#2a1b0d", border_radius="11px"),
            rx.vstack(
                rx.text(item["name"], weight="medium"),
                rx.text(item["company"] + " · " + item["kind"] + " · " + item["size"], color=MUTED, size="1"),
                rx.cond(item["processed_name"] != "", rx.text("Summary: " + item["processed_name"], color=ORANGE, size="1"), rx.box()),
                spacing="1", align="start",
            ),
            rx.spacer(),
            rx.badge(item["status"], color_scheme=rx.cond(item["status"] == "Processed", "green", "gray"), variant="soft"),
            width="100%", align="center",
        ),
        rx.cond(
            item["status"] == "Processed",
            rx.vstack(
                rx.flex(
                    rx.hstack(
                        rx.switch(checked=item["context_enabled"], on_change=lambda _: RadarState.toggle_document_context(item["id"]), color_scheme="orange"),
                        rx.text("Use this summary as company guidance", size="2"),
                        align="center", spacing="2",
                    ),
                    rx.cond(
                        item["context_enabled"],
                        rx.select(
                            ["Opportunity mapping", "Scoring & fit", "Business reports", "Everywhere"],
                            value=item["context_scope"],
                            on_change=lambda value: RadarState.set_document_scope(item["id"], value),
                            width="240px",
                        ),
                        rx.box(),
                    ),
                    direction=rx.breakpoints(initial="column", sm="row"), gap="3", width="100%", justify="between", align=rx.breakpoints(initial="start", sm="center"),
                ),
                rx.cond(
                    item["context_enabled"],
                    rx.text(
                        rx.match(
                            item["context_scope"],
                            ("Opportunity mapping", "Guides how market signals are named and grouped."),
                            ("Scoring & fit", "Guides strategic relevance and company fit."),
                            ("Business reports", "Used when building company and decision reports."),
                            "Guides opportunity mapping, fit and reports.",
                        ),
                        color=MUTED, size="1",
                    ),
                    rx.text("Stored safely, but not added to any prompt.", color=MUTED, size="1"),
                ),
                width="100%", padding="12px 14px", background="#101010", border_radius="12px", spacing="2", align="start",
            ),
            rx.box(),
        ),
        width="100%", padding="13px 0", border_bottom=f"1px solid {LINE}", align="start", spacing="3",
    )


def orange_priorities_section() -> rx.Component:
    """Orange's OWN priority use cases and technologies - a separate concept from the
    customer/prospect business profile above. This selection drives the Orange Fit /
    right-to-win score (radar_v2/services/attractiveness.py's orange_fit()), which is
    standalone from the weighted Attractiveness score - it never enters that sum."""
    return rx.box(
        rx.flex(
            section_title("Orange priorities", "What Orange itself is pursuing - not the customer profile above"),
            rx.spacer(),
            rx.badge(RadarState.orange_priority_count.to_string() + " selected", color_scheme="orange", variant="soft", radius="full"),
            width="100%", align=rx.breakpoints(initial="start", sm="center"),
            direction=rx.breakpoints(initial="column", sm="row"), gap="3",
        ),
        rx.callout(
            "These choices drive each opportunity's Orange Fit score (shown on its detail page, and used to sort "
            "the Presales view) - not the Attractiveness score above, which never includes them. Leave them empty "
            "and Orange Fit falls back to a business-domain coverage estimate instead of a priority match.",
            icon="target", color_scheme="orange", size="1", width="100%", margin_top="16px",
        ),
        rx.text("Priority use cases", weight="medium", margin_top="22px"),
        rx.text("The business problems Orange wants to win", color=MUTED, size="1", margin_top="2px"),
        rx.flex(
            rx.foreach(RadarState.orange_use_case_options, lambda option: priority_chip(option, RadarState.toggle_orange_use_case)),
            wrap="wrap", gap="2", margin_top="12px", width="100%",
        ),
        rx.text("Priority technologies", weight="medium", margin_top="24px"),
        rx.text("The capabilities Orange wants to lead with", color=MUTED, size="1", margin_top="2px"),
        rx.flex(
            rx.foreach(RadarState.orange_technology_options, lambda option: priority_chip(option, RadarState.toggle_orange_technology)),
            wrap="wrap", gap="2", margin_top="12px", width="100%",
        ),
        rx.flex(
            rx.button("Save priorities", rx.icon("check", size=17), on_click=RadarState.save_orange_priorities, **BUTTON),
            rx.button("Clear all", rx.icon("eraser", size=16), on_click=RadarState.clear_orange_priorities, variant="outline", color_scheme="gray"),
            rx.spacer(),
            rx.cond(
                RadarState.orange_priorities_updated != "",
                rx.text("Last saved " + RadarState.orange_priorities_updated, color=MUTED, size="1"),
                rx.box(),
            ),
            direction=rx.breakpoints(initial="column", sm="row"),
            gap="3", margin_top="24px", width="100%", align=rx.breakpoints(initial="start", sm="center"),
        ),
        **CARD, width="100%",
    )


def company() -> rx.Component:
    return page_shell(
        rx.vstack(
            page_header("Company workspace", "Make every opportunity feel relevant to your business.", "Set the strategic lens and maintain a focused reference library that guides portfolio fit, language and recommendations."),
            rx.grid(
                rx.box(
                    section_title("Business profile", "This profile shapes portfolio relevance"),
                    rx.vstack(
                        rx.text("Company name", color=MUTED, size="1"),
                        rx.input(value=RadarState.company_name, on_change=RadarState.set_company_name, **INPUT),
                        rx.text("Priority market", color=MUTED, size="1", margin_top="6px"),
                        rx.input(value=RadarState.company_geography, on_change=RadarState.set_company_geography, **INPUT),
                        rx.text("Website", color=MUTED, size="1", margin_top="6px"),
                        rx.input(value=RadarState.company_website, on_change=RadarState.set_company_website, **INPUT),
                        rx.text("Strategic focus", color=MUTED, size="1", margin_top="6px"),
                        rx.text_area(value=RadarState.company_focus, on_change=RadarState.set_company_focus, **{**INPUT, "min_height": "130px"}),
                        rx.button("Save workspace", on_click=RadarState.save_company, width="100%", margin_top="10px", **BUTTON),
                        spacing="2", width="100%", align="start",
                    ),
                    **CARD,
                ),
                rx.box(
                    section_title("Reference library", "Add strategy, portfolio and market documents"),
                    rx.upload(
                        rx.vstack(
                            rx.center(rx.icon("cloud-upload", size=28, color=ORANGE), width="58px", height="58px", background="#2a1b0d", border_radius="16px"),
                            rx.heading("Drop company documents here", size="4"),
                            rx.text("PDF, presentation, document or text", color=MUTED),
                            rx.button("Choose files", **BUTTON),
                            align="center", spacing="3",
                        ),
                        id="company_documents",
                        multiple=True,
                        border=f"1px dashed {LINE}", border_radius="18px", padding="34px 20px", width="100%",
                        background="#101010", cursor="pointer",
                    ),
                    rx.cond(
                        rx.selected_files("company_documents").length() > 0,
                        rx.box(
                            rx.text("Selected files", weight="medium"),
                            rx.vstack(
                                rx.foreach(rx.selected_files("company_documents"), lambda filename: rx.hstack(rx.icon("file", size=15, color=ORANGE), rx.text(filename, size="2"), spacing="2", width="100%")),
                                spacing="2", align="start", margin_top="10px", width="100%",
                            ),
                            padding="14px", background="#101010", border_radius="13px", margin_top="14px",
                        ),
                        rx.box(),
                    ),
                    rx.button(
                        rx.cond(RadarState.upload_in_progress, rx.spinner(size="2"), rx.icon("folder-plus", size=17)),
                        rx.cond(RadarState.upload_in_progress, "Adding documents", "Add selected documents"),
                        on_click=RadarState.upload_documents(rx.upload_files(upload_id="company_documents", on_upload_progress=RadarState.upload_progress_update)),
                        disabled=RadarState.upload_in_progress,
                        width="100%", margin_top="14px", **BUTTON,
                    ),
                    rx.cond(
                        RadarState.upload_message != "",
                        rx.vstack(rx.progress(value=RadarState.upload_progress, color_scheme="orange", width="100%"), rx.text(RadarState.upload_message, color=MUTED, size="1"), spacing="2", width="100%", margin_top="12px"),
                        rx.box(),
                    ),
                    **CARD,
                ),
                columns=rx.breakpoints(initial="1", lg="2"), gap="5", width="100%",
            ),
            orange_priorities_section(),
            section_title("Company knowledge", "A concise view of the reference material available to the radar"),
            rx.callout(
                "Each selected document is summarised separately. Select two or more when you want an additional combined company report.",
                icon="info", color_scheme="orange", width="100%",
            ),
            rx.box(
                rx.hstack(
                    rx.vstack(
                        rx.text("Processing focus", weight="medium"),
                        rx.text("Optional guidance for this summary or company report", color=MUTED, size="1"),
                        spacing="1", align="start",
                    ),
                    rx.spacer(),
                    rx.badge(RadarState.selected_document_count.to_string() + " selected", color_scheme="orange", variant="soft"),
                    width="100%", align="center",
                ),
                rx.text_area(
                    placeholder="For example: focus on 2026 revenue, financial priorities and margin pressure",
                    value=RadarState.document_instruction,
                    on_change=RadarState.set_document_instruction,
                    margin_top="16px",
                    **{**INPUT, "min_height": "95px"},
                ),
                rx.flex(
                    rx.button(
                        rx.cond(RadarState.document_processing, rx.spinner(size="2"), rx.icon("sparkles", size=17)),
                        "Process selected separately",
                        on_click=RadarState.process_selected_documents,
                        disabled=RadarState.document_processing,
                        **BUTTON,
                    ),
                    rx.cond(
                        RadarState.selected_document_count >= 2,
                        rx.button("Create combined company report", rx.icon("files", size=17), on_click=RadarState.create_company_report, variant="outline", color_scheme="orange"),
                        rx.box(),
                    ),
                    direction=rx.breakpoints(initial="column", sm="row"), gap="3", margin_top="16px",
                ),
                rx.cond(
                    RadarState.processing_message != "",
                    rx.vstack(
                        rx.progress(value=RadarState.processing_progress, color_scheme="orange", width="100%"),
                        rx.text(RadarState.processing_message, color=MUTED, size="2"),
                        rx.cond(RadarState.processing_active_file != "", rx.text("Current file: " + RadarState.processing_active_file, color=ORANGE, size="1"), rx.box()),
                        spacing="2", width="100%", margin_top="14px", align="start",
                    ),
                    rx.box(),
                ),
                **CARD, width="100%",
            ),
            rx.cond(
                RadarState.documents.length() > 0,
                rx.box(rx.foreach(RadarState.documents, document_row), **CARD, width="100%"),
                empty_state("library", "Your reference library is ready", "Add company documents to personalise the radar's language and recommendations."),
            ),
            spacing="6", width="100%", align="start",
        )
    )

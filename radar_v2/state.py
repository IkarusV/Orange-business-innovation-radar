from __future__ import annotations

import json
import os
import re
from typing import Any

import reflex as rx
import requests

from radar_v2.constants import TEAM_PIPELINE
from radar_v2.models import DocumentItem, Evidence, Opportunity, ReportBullet, ReportItem, ReportMetric, ReportRange, ReportRisk, RoleModeOption, SearchResult, SourceSummary, TaxonomyOption
from radar_v2.services import domains, extension_store, geography, role_modes, team_repository
from radar_v2.services import knowledge
from radar_v2.services.reporting import create_focused_report
from radar_v2.services.pipeline_runner import company_context_file, stream_run


class RadarState(rx.State):
    opportunities: list[Opportunity] = []
    evidence: list[Evidence] = []
    selected_opportunity: Opportunity = {
        "id": 0, "vertical": "", "use_case_id": "", "use_case": "", "technology_id": "",
        "technology": "", "primary_domain": "", "primary_domain_label": "", "domains": [],
        "domain_labels": [], "article_count": 0, "relevance": 0, "confidence": 0,
        "horizon": "Next", "horizon_reason": None, "horizon_rule": "", "horizon_breakdown": [],
        "signal_mix": [], "momentum": "", "summary": "", "updated": "", "breakdown": [],
        "persona_weights": [], "persona_ids": [],
        "primary_region": "", "primary_region_label": geography.UNSPECIFIED_LABEL,
        "regions": [], "region_labels": [], "countries": [],
        "why_hot_now": "", "why_this_matters": "",
        "recommended_moves": {}, "recommended_move": "",
    }
    metrics: dict[str, int] = {}
    source_mix: list[SourceSummary] = []
    companies: list[dict[str, Any]] = []
    active_company: dict[str, Any] = {}
    documents: list[DocumentItem] = []
    custom_sources: list[dict[str, Any]] = []
    reports: list[ReportItem] = []

    vertical_filter: str = "All sectors"
    horizon_filter: str = "All horizons"
    # Business domains are multi-select: an empty list is no constraint, and
    # several selected domains widen the result rather than narrowing it.
    domain_filter: list[str] = []
    # Geography is multi-select on the same terms. Selecting `global` matches
    # only spaces explicitly resolved there - it never also returns the spaces
    # that simply have no geography, which stay a distinct state.
    region_filter: list[str] = []
    search_filter: str = ""
    # Role mode is view configuration only - filter seeds, a sort key and a
    # presentation profile. It is never written to an opportunity space, and it
    # is not a stored user preference (this app has no preferences mechanism):
    # it lives in view state and can be seeded from a ?mode= query parameter.
    role_mode: str = role_modes.DEFAULT_MODE
    # Selected persona's label - empty means no persona constraint. Same
    # value-is-the-label convention as every other filter select in this app.
    persona_filter: str = ""
    company_name: str = "Orange Business"
    company_geography: str = "Belgium & Europe"
    company_website: str = "https://www.orange-business.com"
    company_focus: str = "Trusted digital services, secure connectivity, cloud, data and AI"
    # Orange's OWN priority taxonomy selection - the strategic relevance input for the
    # attractiveness score. Distinct from the company profile above, which describes the
    # customer/prospect being pitched to.
    orange_use_case_ids: list[str] = []
    orange_technology_ids: list[str] = []
    orange_priorities_updated: str = ""
    source_name: str = ""
    source_url: str = ""
    source_category: str = "Industry source"
    discovery_query: str = ""
    discovery_provider: str = "SearXNG"
    discovery_vertical: str = "Manufacturing"
    discovery_results: list[SearchResult] = []
    search_message: str = ""
    discovery_running: bool = False
    discovery_error: str = ""

    pipeline_limit: int = 20
    pipeline_running: bool = False
    pipeline_progress: int = 0
    pipeline_stage: str = "Ready"
    pipeline_message: str = "Ready for the next radar update"
    last_run: dict[str, Any] = {}
    pipeline_preflight: dict[str, int] = {}

    ai_base_url: str = "https://api.navy/v1"
    ai_model: str = "gpt-5.6-luna"
    ai_mode: str = "responses"
    ai_api_key: str = ""
    provider_session_active: bool = False
    search_provider: str = "searxng"
    searxng_url: str = "http://localhost:8888"
    tavily_api_key: str = ""
    tavily_depth: str = "basic"
    max_search_results: int = 8
    max_research_queries: int = 5
    document_instruction: str = ""
    document_processing: bool = False
    upload_in_progress: bool = False
    upload_progress: int = 0
    upload_message: str = ""
    processing_progress: int = 0
    processing_active_file: str = ""
    processing_message: str = ""
    report_opportunity_id: int = 0
    report_running: bool = False
    report_progress: int = 0
    report_message: str = ""
    report_payload: dict[str, Any] = {}
    report_id: int = 0
    report_title: str = ""
    report_summary: str = ""
    report_recommendation: str = ""
    report_market_signal: str = ""
    report_financial_indicators: str = ""
    report_company_fit: str = ""
    report_queries: list[str] = []
    report_sources: list[dict[str, Any]] = []
    report_risks: list[dict[str, Any]] = []
    report_roadmap: list[dict[str, Any]] = []
    report_metrics: list[ReportMetric] = []
    report_market_items: list[ReportBullet] = []
    report_finance_items: list[ReportBullet] = []
    report_fit_items: list[ReportBullet] = []
    report_risk_items: list[ReportRisk] = []
    report_roadmap_items: list[ReportBullet] = []
    report_ranges: list[ReportRange] = []

    def load(self):
        self.opportunities = team_repository.list_opportunities()
        self.metrics = team_repository.dashboard_metrics()
        self.source_mix = team_repository.source_summary()
        self.companies = extension_store.companies()
        self.active_company = extension_store.active_company()
        self.company_name = self.active_company["name"]
        self.company_geography = self.active_company["geography"]
        self.company_website = self.active_company["website"]
        self.company_focus = self.active_company["focus"]
        priorities = extension_store.orange_priorities()
        self.orange_use_case_ids = priorities["use_case_ids"]
        self.orange_technology_ids = priorities["technology_ids"]
        self.orange_priorities_updated = (priorities["updated_at"] or "")[:10]
        self.documents = extension_store.documents()
        self.custom_sources = extension_store.custom_sources()
        self.reports = extension_store.reports()
        self.last_run = team_repository.latest_run()
        self.pipeline_preflight = team_repository.pipeline_preflight(self.pipeline_limit)
        saved_search = extension_store.latest_search()
        if saved_search:
            self.discovery_results = saved_search["results"]
            self.discovery_query = saved_search["query"]
            self.search_message = f"{len(self.discovery_results)} sources found in the latest saved search"
        settings = extension_store.settings()
        self.ai_base_url = settings["ai_base_url"]
        self.ai_model = settings["ai_model"]
        self.ai_mode = settings["ai_mode"]
        self.provider_session_active = bool(self.ai_api_key or os.getenv("NAVY_API_KEY"))
        self.search_provider = settings["search_provider"]
        self.searxng_url = settings["searxng_url"]
        self.tavily_depth = settings["tavily_depth"]
        self.max_search_results = settings["max_search_results"]
        self.max_research_queries = settings["max_research_queries"]

    @rx.var
    def visible_opportunities(self) -> list[Opportunity]:
        """OR within each of the domain and geography filters, AND across
        dimensions. A space matches a selected domain or region if it appears
        anywhere in its set, not only as primary.

        Filtering stays in memory rather than being pushed into the SQL query
        because two attractiveness components (market signal strength, novelty
        & momentum) are normalized against the whole run - re-querying a subset
        would silently rescore every remaining space.
        """
        query = self.search_filter.strip().lower()
        selected_domains = set(self.domain_filter)
        selected_regions = set(self.region_filter)
        matched = [
            item for item in self.opportunities
            if (self.vertical_filter == "All sectors" or item["vertical"] == self.vertical_filter)
            and (self.horizon_filter == "All horizons" or item["horizon"] == self.horizon_filter)
            and (not selected_domains or selected_domains.intersection(item["domains"]))
            and (not selected_regions or selected_regions.intersection(item.get("regions") or []))
            and (not query or query in " ".join(str(value) for value in item.values()).lower())
            and role_modes.persona_threshold_passes(item, self.role_mode, self.persona_filter)
        ]
        ordered = role_modes.sort_opportunities(matched, self.role_mode, self.persona_filter)
        # Every space carries a move for all three modes; the list cards render
        # one, so the active mode's is resolved here rather than in the card.
        return [
            {**item, "recommended_move": (item.get("recommended_moves") or {}).get(
                self.role_mode, item.get("recommended_move", ""),
            )}
            for item in ordered
        ]

    def set_search_filter(self, value: str):
        self.search_filter = value

    def _filters_match_defaults(self, mode_id: str) -> bool:
        """Whether the filter panel is still exactly as a mode seeded it."""
        defaults = role_modes.filter_defaults(mode_id)
        return (
            self.vertical_filter == defaults["vertical"]
            and self.horizon_filter == defaults["horizon"]
            and sorted(self.domain_filter) == sorted(defaults["domains"])
            and self.persona_filter == defaults["persona"]
        )

    def _seed_filter_defaults(self, mode_id: str):
        defaults = role_modes.filter_defaults(mode_id)
        self.vertical_filter = defaults["vertical"]
        self.horizon_filter = defaults["horizon"]
        self.domain_filter = list(defaults["domains"])
        self.persona_filter = defaults["persona"]

    def set_role_mode(self, mode_id: str):
        """Switching mode always changes sort and presentation. Filters are only
        re-seeded when the user has not touched them since the current mode
        seeded them - customised filters are the user's, not the mode's."""
        if mode_id not in role_modes.MODE_IDS or mode_id == self.role_mode:
            return
        if self._filters_match_defaults(self.role_mode):
            self._seed_filter_defaults(mode_id)
        self.role_mode = mode_id

    def load_role_mode(self):
        """Seed the mode from ?mode= so a shared link opens in the same view.
        A missing or unknown value leaves the current selection untouched."""
        try:
            requested = dict(self.router.url.query_parameters).get("mode", "")
        except Exception:
            requested = ""
        if requested in role_modes.MODE_IDS:
            self.set_role_mode(requested)

    def set_persona_filter(self, value: str):
        self.persona_filter = value

    def toggle_domain_filter(self, domain_id: str):
        if domain_id in self.domain_filter:
            self.domain_filter = [item for item in self.domain_filter if item != domain_id]
        else:
            self.domain_filter = self.domain_filter + [domain_id]

    def clear_domain_filter(self):
        self.domain_filter = []

    def toggle_region_filter(self, region_id: str):
        if region_id in self.region_filter:
            self.region_filter = [item for item in self.region_filter if item != region_id]
        else:
            self.region_filter = self.region_filter + [region_id]

    def clear_region_filter(self):
        self.region_filter = []

    def set_vertical_filter(self, value: str):
        self.vertical_filter = value

    def set_horizon_filter(self, value: str):
        self.horizon_filter = value

    def set_company_name(self, value: str):
        self.company_name = value

    def set_company_geography(self, value: str):
        self.company_geography = value

    def set_company_website(self, value: str):
        self.company_website = value

    def set_company_focus(self, value: str):
        self.company_focus = value

    def set_source_name(self, value: str):
        self.source_name = value

    def set_source_url(self, value: str):
        self.source_url = value

    def set_source_category(self, value: str):
        self.source_category = value

    def set_discovery_query(self, value: str):
        self.discovery_query = value

    def set_discovery_vertical(self, value: str):
        self.discovery_vertical = value

    def set_ai_base_url(self, value: str):
        self.ai_base_url = value

    def set_ai_model(self, value: str):
        self.ai_model = value

    def set_ai_mode(self, value: str):
        self.ai_mode = value

    def set_ai_api_key(self, value: str):
        self.ai_api_key = value

    def set_search_provider(self, value: str):
        self.search_provider = value

    def set_searxng_url(self, value: str):
        self.searxng_url = value

    def set_tavily_api_key(self, value: str):
        self.tavily_api_key = value

    def set_tavily_depth(self, value: str):
        self.tavily_depth = value

    def set_max_search_results(self, value: str):
        self.max_search_results = int(value)

    def set_max_research_queries(self, value: str):
        self.max_research_queries = int(value)

    def set_document_instruction(self, value: str):
        self.document_instruction = value

    def save_settings(self):
        extension_store.save_settings(self.ai_base_url, self.ai_model, self.ai_mode, self.search_provider, self.searxng_url, self.tavily_depth, self.max_search_results, self.max_research_queries)
        return rx.toast.success("Settings saved")

    def activate_provider(self):
        if not self.ai_api_key.strip() and not os.getenv("NAVY_API_KEY"):
            self.provider_session_active = False
            return rx.toast.error("Enter the provider key, then activate this session")
        self.provider_session_active = True
        return rx.toast.success("Provider ready for this session")

    def deactivate_provider(self):
        self.ai_api_key = ""
        self.provider_session_active = False
        return rx.toast.success("Provider disconnected from this session")

    def toggle_document(self, document_id: int):
        extension_store.toggle_document(document_id)
        self.documents = extension_store.documents()

    def toggle_document_context(self, document_id: int):
        extension_store.toggle_document_context(document_id)
        self.documents = extension_store.documents()

    def set_document_scope(self, document_id: int, scope: str):
        extension_store.set_document_scope(document_id, scope)
        self.documents = extension_store.documents()

    def process_selected_documents(self):
        selected = extension_store.selected_documents()
        if not selected:
            yield rx.toast.error("Select at least one document")
            return
        if not self.ai_api_key and not os.getenv("NAVY_API_KEY"):
            yield rx.toast.error("Add the AI provider key in Settings")
            return
        self.document_processing = True
        self.processing_progress = 0
        self.processing_message = f"Preparing {len(selected)} separate summary request(s)"
        yield
        key = self.ai_api_key or os.getenv("NAVY_API_KEY", "")
        completed = 0
        for index, document in enumerate(selected, 1):
            self.processing_active_file = document["name"]
            self.processing_message = f"Summarising {document['name']} · {index} of {len(selected)}"
            self.processing_progress = int((index - 1) / len(selected) * 100)
            yield
            try:
                knowledge.process_document(document, self.document_instruction, self.ai_base_url, key, self.ai_model, self.ai_mode)
                completed += 1
            except Exception as error:
                extension_store.update_document_processing(document["id"], "Needs attention", note=str(error)[:300])
            self.documents = extension_store.documents()
            self.processing_progress = int(index / len(selected) * 100)
            yield
        self.document_processing = False
        self.processing_active_file = ""
        self.processing_message = f"{completed} document summary(s) ready"
        yield rx.toast.success(f"{completed} document summary(s) ready")

    def create_company_report(self):
        selected = extension_store.selected_documents()
        if len(selected) < 2:
            yield rx.toast.error("Select at least two documents")
            return
        key = self.ai_api_key or os.getenv("NAVY_API_KEY", "")
        if not key:
            yield rx.toast.error("Add the AI provider key in Settings")
            return
        self.document_processing = True
        self.processing_progress = 20
        self.processing_message = f"Building one company report from {len(selected)} documents"
        yield
        try:
            knowledge.create_combined_report(selected, self.document_instruction, self.ai_base_url, key, self.ai_model, self.ai_mode)
            self.documents = extension_store.documents()
            self.reports = extension_store.reports()
            self.document_processing = False
            self.processing_progress = 100
            self.processing_message = "Combined company report ready"
            yield rx.toast.success("Company knowledge report ready")
        except Exception:
            self.document_processing = False
            self.processing_message = "The combined report could not be created"
            yield rx.toast.error("The company report could not be created")

    def select_opportunity(self, opportunity_id: int):
        self.selected_opportunity, self.evidence = team_repository.opportunity_detail(opportunity_id)
        return rx.redirect(f"/opportunities/{opportunity_id}")

    def choose_report_opportunity(self, opportunity_id: int):
        self.report_opportunity_id = opportunity_id
        self.report_payload = {}
        return rx.redirect("/reports")

    def generate_focused_report(self):
        if not self.report_opportunity_id:
            yield rx.toast.error("Choose an opportunity first")
            return
        key = self.ai_api_key or os.getenv("NAVY_API_KEY", "")
        if not key:
            yield rx.toast.error("Add the intelligence provider key in Settings")
            return
        self.report_running = True
        self.report_progress = 5
        self.report_message = "Preparing the selected opportunity"
        yield
        try:
            def progress(message: str):
                self.report_message = message
                if "search" in message.lower():
                    self.report_progress = 45
                elif "synthes" in message.lower():
                    self.report_progress = 75

            report_id, payload = create_focused_report(self.report_opportunity_id, key, progress)
            self.report_id = report_id
            self._set_report_payload(report_id, payload)
            self.reports = extension_store.reports()
            self.report_progress = 100
            self.report_message = "Business report ready"
            self.report_running = False
            yield rx.toast.success("Business report ready")
        except Exception as error:
            self.report_running = False
            self.report_message = "Report could not be completed"
            yield rx.toast.error(str(error)[:180])

    def set_report_opportunity(self, value: str):
        # Select values are user-facing labels such as "1 · Warehouse automation".
        raw_id = value.split(" · ", 1)[0].strip()
        try:
            self.report_opportunity_id = int(raw_id)
        except ValueError:
            self.report_opportunity_id = 0

    def _set_report_payload(self, report_id: int, payload: dict[str, Any], title: str = ""):
        self.report_id = report_id
        self.report_payload = payload
        self.report_title = title or str(payload.get("title", "Focused business report"))
        self.report_summary = self._text_value(payload.get("executive_summary", payload.get("report_summary", payload.get("summary", ""))))
        recommendation = payload.get("recommendation", payload.get("radar_guidance", ""))
        if isinstance(recommendation, dict):
            self.report_recommendation = self._text_value(recommendation.get("decision", ""))
            if recommendation.get("rationale"):
                self.report_recommendation += "\n\n" + self._text_value(recommendation["rationale"])
        else:
            self.report_recommendation = self._text_value(recommendation)
        self.report_market_signal = self._text_value(payload.get("market_signal", payload.get("market_estimates", "")))
        self.report_financial_indicators = self._text_value(payload.get("financial_indicators", payload.get("financial_profile", payload.get("financial_scenarios", ""))))
        self.report_company_fit = self._text_value(payload.get("company_fit", payload.get("company_role", "")))
        self.report_queries = [str(query) for query in payload.get("queries", [])]
        self.report_sources = self._dict_list(payload.get("sources", []))
        self.report_risks = self._dict_list(payload.get("risks", payload.get("risks_and_unknowns", [])))
        self.report_roadmap = self._dict_list(payload.get("roadmap", []))
        self.report_metrics = self._report_metrics(payload)
        self.report_market_items = self._report_bullets(payload.get("market_signal", payload.get("demand_evidence", "")), "Market signal")
        self.report_finance_items = self._report_bullets(payload.get("financial_indicators", payload.get("financial_profile", "")), "Financial signal")
        self.report_fit_items = self._report_bullets(payload.get("company_fit", payload.get("company_role", "")), "Company fit")
        self.report_risk_items = self._report_risks(payload.get("risks", payload.get("risks_and_unknowns", [])))
        self.report_roadmap_items = self._report_bullets(payload.get("roadmap", []), "Phase")
        self.report_ranges = self._report_ranges(payload)

    @staticmethod
    def _text_value(value: Any) -> str:
        if isinstance(value, str):
            return value
        if value is None:
            return ""
        return json.dumps(value, ensure_ascii=False, indent=2)

    @staticmethod
    def _dict_list(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item if isinstance(item, dict) else {"detail": str(item)} for item in value]

    @classmethod
    def _report_bullets(cls, value: Any, default_title: str) -> list[ReportBullet]:
        if isinstance(value, str):
            return [{"title": default_title, "detail": value}] if value else []
        if isinstance(value, list):
            output = []
            for index, item in enumerate(value, 1):
                if isinstance(item, dict):
                    title = str(item.get("title") or item.get("metric") or item.get("country") or f"{default_title} {index}")
                    preferred = item.get("detail") or item.get("assumption") or item.get("reported_value") or item.get("action") or item.get("summary")
                    if preferred is None:
                        readable = [f"{str(key).replace('_', ' ').title()}: {cls._text_value(item_value)}" for key, item_value in item.items() if key not in {"source_ids", "title", "metric", "country"}]
                        detail = " · ".join(readable)
                    else:
                        detail = cls._text_value(preferred)
                else:
                    title, detail = f"{default_title} {index}", str(item)
                output.append({"title": title, "detail": detail})
            return output
        if isinstance(value, dict):
            output = []
            for key, item in value.items():
                if key in {"source_ids", "horizon", "relevance", "confidence", "momentum"}:
                    continue
                label = str(key).replace("_", " ").title()
                if isinstance(item, list):
                    output.extend(cls._report_bullets(item, label))
                else:
                    output.append({"title": label, "detail": cls._text_value(item)})
            return output
        return []

    @classmethod
    def _report_risks(cls, value: Any) -> list[ReportRisk]:
        items = value if isinstance(value, list) else ([value] if value else [])
        output = []
        for index, item in enumerate(items, 1):
            if isinstance(item, dict):
                title = str(item.get("risk") or item.get("title") or f"Risk {index}")
                mitigation = cls._text_value(item.get("mitigation") or item.get("detail") or item)
                likelihood, impact = item.get("likelihood"), item.get("impact")
                level = f"Likelihood {likelihood}/5 · Impact {impact}/5" if likelihood and impact else "Review"
            else:
                title, mitigation, level = f"Risk {index}", str(item), "Review"
            output.append({"title": title, "detail": mitigation, "level": level})
        return output

    @classmethod
    def _report_metrics(cls, payload: dict[str, Any]) -> list[ReportMetric]:
        market = payload.get("market_signal", {})
        if not isinstance(market, dict):
            market = {}
        metrics = []
        for key, label in (("horizon", "Timing"), ("relevance", "Strategic fit"), ("confidence", "Confidence"), ("momentum", "Momentum")):
            if market.get(key) is not None:
                value = str(market[key])
                if key in {"relevance", "confidence"} and value.isdigit():
                    value += "%"
                metrics.append({"label": label, "value": value, "detail": "From the current report evidence"})
        financial = payload.get("financial_indicators", {})
        if isinstance(financial, dict) and financial.get("procurement_signals"):
            metrics.append({"label": "Demand signals", "value": str(len(financial["procurement_signals"])), "detail": "Named procurement records"})
        return metrics

    @classmethod
    def _report_ranges(cls, payload: dict[str, Any]) -> list[ReportRange]:
        estimates = payload.get("market_estimates", [])
        if not isinstance(estimates, list):
            return []
        output = []
        for item in estimates:
            if not isinstance(item, dict):
                continue
            raw = str(item.get("range", "")).replace(",", "")
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMB%]?)\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)\s*([KMB%]?)", raw, re.IGNORECASE)
            if not match or "%" in raw:
                continue
            first, first_unit, second, second_unit = match.groups()
            unit = first_unit.upper() or second_unit.upper()
            multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(unit, 1)
            output.append({"label": str(item.get("period", "Market estimate")), "low": float(first) * multiplier, "high": float(second) * multiplier, "unit": unit or "value", "detail": str(item.get("assumption", "Range from cited market sources"))})
        return output

    def open_saved_report(self, report_id: int):
        saved = extension_store.focused_report(report_id)
        if not saved:
            return rx.toast.error("This report could not be opened")
        self._set_report_payload(report_id, saved["payload"], saved["title"])
        return rx.toast.success("Report opened")

    def load_detail(self):
        raw = self.router.url.path.rstrip("/").rsplit("/", 1)[-1]
        try:
            opportunity_id = int(raw)
        except (TypeError, ValueError):
            opportunity_id = 1
        self.selected_opportunity, self.evidence = team_repository.opportunity_detail(opportunity_id)

    def save_company(self):
        extension_store.save_company(self.company_name, self.company_geography, self.company_website, self.company_focus)
        self.load()
        return rx.toast.success("Company workspace updated")

    def toggle_orange_use_case(self, use_case_id: str):
        if use_case_id in self.orange_use_case_ids:
            self.orange_use_case_ids = [item for item in self.orange_use_case_ids if item != use_case_id]
        else:
            self.orange_use_case_ids = self.orange_use_case_ids + [use_case_id]

    def toggle_orange_technology(self, technology_id: str):
        if technology_id in self.orange_technology_ids:
            self.orange_technology_ids = [item for item in self.orange_technology_ids if item != technology_id]
        else:
            self.orange_technology_ids = self.orange_technology_ids + [technology_id]

    def clear_orange_priorities(self):
        self.orange_use_case_ids = []
        self.orange_technology_ids = []

    def save_orange_priorities(self):
        extension_store.save_orange_priorities(self.orange_use_case_ids, self.orange_technology_ids)
        # Strategic relevance is 15% of every opportunity's score, so the portfolio
        # is rescored immediately. Only the derived data is refreshed (not a full
        # load()), so unsaved edits in the company profile form above are kept.
        self.opportunities = team_repository.list_opportunities()
        self.metrics = team_repository.dashboard_metrics()
        self.orange_priorities_updated = extension_store.orange_priorities()["updated_at"][:10]
        if not self.orange_use_case_ids and not self.orange_technology_ids:
            return rx.toast.success("Orange priorities cleared - strategic relevance is now unscored")
        return rx.toast.success("Orange priorities saved - opportunities rescored")

    async def upload_documents(self, files: list[rx.UploadFile]):
        if not files:
            yield rx.toast.error("Choose at least one document")
            return
        self.upload_in_progress = True
        self.upload_progress = 5
        self.upload_message = "Preparing selected files"
        yield
        for index, file in enumerate(files, 1):
            extension_store.save_document(file.filename or "company-document", await file.read())
            self.upload_progress = int(index / len(files) * 100)
            self.upload_message = f"Added {file.filename or 'document'} · {index} of {len(files)}"
            yield
        self.documents = extension_store.documents()
        self.upload_in_progress = False
        self.upload_message = f"{len(files)} document(s) added to the company library"
        yield rx.clear_selected_files("company_documents")
        yield rx.toast.success(f"{len(files)} document(s) added to the company library")

    def upload_progress_update(self, progress: dict[str, int | float | bool]):
        self.upload_in_progress = True
        self.upload_progress = int(progress.get("progress", 0))
        self.upload_message = "Uploading selected documents"

    def add_source(self):
        if not self.source_name.strip() or not self.source_url.startswith(("http://", "https://")):
            return rx.toast.error("Enter a source name and valid URL")
        extension_store.add_source(self.source_name, self.source_url, self.source_category)
        self.custom_sources = extension_store.custom_sources()
        self.source_name = ""
        self.source_url = ""
        return rx.toast.success("Source added")

    def collect_priority_sources(self):
        results = extension_store.fetch_custom_source_articles()
        if not results:
            return rx.toast.error("No readable source updates were available")
        inserted = team_repository.import_external_signals(results, self.discovery_vertical, "Priority source watchlist")
        return rx.toast.success(f"{inserted} source update(s) added to the next radar cycle")

    def run_discovery(self):
        query = self.discovery_query.strip()
        if not query:
            return rx.toast.error("Enter a discovery question")
        self.discovery_running = True
        self.discovery_error = ""
        self.search_message = "Searching the selected provider..."
        yield
        endpoint = self.searxng_url.rstrip("/")
        try:
            if self.search_provider == "tavily":
                key = self.tavily_api_key or os.getenv("TAVILY_API_KEY", "")
                response = requests.post("https://api.tavily.com/search", json={"api_key": key, "query": query, "search_depth": self.tavily_depth, "max_results": self.max_search_results}, timeout=30)
            else:
                response = requests.get(f"{endpoint}/search", params={"q": query, "format": "json", "language": "all"}, headers={"Accept": "application/json", "User-Agent": "Innovation-Radar-V2/1.0"}, timeout=30)
            response.raise_for_status()
            results = response.json().get("results", [])[:self.max_search_results]
            self.discovery_results = [{
                "title": item.get("title", "Untitled source"), "url": item.get("url", ""),
                "source": item.get("engine", "Web"), "date": item.get("publishedDate", "") or "Recent",
                "excerpt": item.get("content", "") or "Open the source to review the signal.",
            } for item in results if item.get("url")]
            extension_store.save_search(query, self.search_provider.title(), self.discovery_results)
            self.search_message = f"{len(self.discovery_results)} relevant sources found"
            self.discovery_running = False
        except Exception:
            self.search_message = "The selected search service is not available right now"
            self.discovery_error = "No results were saved. Check Settings and the provider URL."
            self.discovery_results = []
            self.discovery_running = False

    def add_discovery_to_radar(self):
        if not self.discovery_results:
            return rx.toast.error("Run a discovery search first")
        inserted = team_repository.import_external_signals(self.discovery_results, self.discovery_vertical)
        return rx.toast.success(f"{inserted} source(s) added to the next radar update")

    def set_pipeline_limit(self, value: list[float]):
        self.pipeline_limit = int(value[0])
        self.pipeline_preflight = team_repository.pipeline_preflight(self.pipeline_limit)

    def run_pipeline(self):
        if self.pipeline_running:
            return
        key = self.ai_api_key or os.getenv("NAVY_API_KEY", "")
        if not self.provider_session_active or not key:
            yield rx.toast.error("Activate the intelligence provider in Settings before running the radar")
            return
        self.pipeline_running = True
        self.pipeline_progress = 2
        self.pipeline_stage = "Starting"
        self.pipeline_message = "Preparing the evidence workspace"
        self.pipeline_preflight = team_repository.pipeline_preflight(self.pipeline_limit)
        yield
        try:
            context_path = company_context_file()
            for event in stream_run(self.pipeline_limit, context_path, key, self.ai_base_url, self.ai_model):
                self.pipeline_progress = event["progress"]
                self.pipeline_stage = event["stage"].replace("_", " ").title()
                self.pipeline_message = event["message"]
                yield
            self.pipeline_running = False
            self.load()
            yield rx.toast.success("Innovation radar updated")
        except Exception:
            self.pipeline_running = False
            self.pipeline_stage = "Update paused"
            self.pipeline_message = "The radar could not complete this update"
            yield rx.toast.error("The radar update could not be completed")

    def generate_team_reports(self):
        import subprocess
        import sys

        try:
            for script in ("generate_stats_report.py", "generate_opportunity_report.py"):
                subprocess.run([sys.executable, str(TEAM_PIPELINE / "reports" / script)], cwd=TEAM_PIPELINE, check=True)
            return rx.toast.success("Business reports are ready")
        except Exception:
            return rx.toast.error("Reports require a completed radar update")

    @rx.var
    def vertical_options(self) -> list[str]:
        return ["All sectors"] + sorted({item["vertical"] for item in self.opportunities})

    @rx.var
    def domain_filter_options(self) -> list[TaxonomyOption]:
        """Read from taxonomy.json, never hardcoded here - the domain
        vocabulary is closed and owned by configuration."""
        return [
            {"id": option["id"], "label": option["label"], "selected": option["id"] in self.domain_filter}
            for option in domains.options()
        ]

    @rx.var
    def domain_filter_count(self) -> int:
        return len(self.domain_filter)

    @rx.var
    def region_filter_options(self) -> list[TaxonomyOption]:
        """Read from taxonomy.json, never hardcoded here - the region grouping
        is a business decision owned by configuration, including the deliberate
        standalone Germany and France and the Switzerland+Austria-only DACH."""
        return [
            {"id": option["id"], "label": option["label"], "selected": option["id"] in self.region_filter}
            for option in geography.options()
        ]

    @rx.var
    def region_filter_count(self) -> int:
        return len(self.region_filter)

    @rx.var
    def role_mode_options(self) -> list[RoleModeOption]:
        return [
            {
                "id": item["id"], "label": item["label"],
                "description": item.get("description", ""), "icon": item.get("icon", "circle"),
                "selected": item["id"] == self.role_mode,
            }
            for item in role_modes.MODES
        ]

    @rx.var
    def role_mode_label(self) -> str:
        return role_modes.label(self.role_mode)

    @rx.var
    def role_mode_description(self) -> str:
        return role_modes.description(self.role_mode)

    @rx.var
    def role_mode_sort_label(self) -> str:
        return role_modes.sort_plan(self.role_mode)["effective_label"]

    @rx.var
    def role_mode_sort_note(self) -> str:
        """Empty unless the configured sort fell back to attractiveness because
        its underlying feature does not exist yet."""
        return role_modes.sort_plan(self.role_mode)["note"]

    @rx.var
    def role_mode_is_single_column(self) -> bool:
        return role_modes.list_density(self.role_mode) == "single_column"

    @rx.var
    def region_emphasis(self) -> dict[str, str]:
        """lead / standard / collapsed per detail page region. No value is ever
        'hidden' - collapsed regions stay in the page behind one click."""
        return role_modes.presentation(self.role_mode)

    @rx.var
    def persona_prompt_visible(self) -> bool:
        """Sales mode asks for a persona before the topic list. It is a prompt,
        not a gate - clearing it is a normal user action, not overriding a
        constraint, so the list stays reachable either way."""
        return role_modes.persona_required(self.role_mode) and not self.persona_filter

    @rx.var
    def persona_options(self) -> list[str]:
        return role_modes.persona_options()

    @rx.var
    def persona_weighting_available(self) -> bool:
        return role_modes.PERSONA_WEIGHTING_AVAILABLE

    @rx.var
    def recommended_move_text(self) -> str:
        """The selected space's move for the mode currently in view. The space
        carries all three; picking one is a view decision, so it happens here
        rather than being baked into the record."""
        moves = self.selected_opportunity.get("recommended_moves") or {}
        return moves.get(self.role_mode, moves.get(role_modes.DEFAULT_MODE, ""))

    @rx.var
    def discovery_vertical_options(self) -> list[str]:
        return team_repository.all_verticals()

    @rx.var
    def orange_use_case_options(self) -> list[TaxonomyOption]:
        """The closed classifier taxonomy - same source the pipeline classifies against."""
        return [
            {"id": key, "label": label, "selected": key in self.orange_use_case_ids}
            for key, label in sorted(team_repository.USE_CASES.items(), key=lambda pair: pair[1])
        ]

    @rx.var
    def orange_technology_options(self) -> list[TaxonomyOption]:
        return [
            {"id": key, "label": label, "selected": key in self.orange_technology_ids}
            for key, label in sorted(team_repository.TECHNOLOGIES.items(), key=lambda pair: pair[1])
        ]

    @rx.var
    def orange_priority_count(self) -> int:
        return len(self.orange_use_case_ids) + len(self.orange_technology_ids)

    @rx.var
    def report_opportunity_options(self) -> list[str]:
        return [str(item["id"]) + " · " + item["use_case"] for item in self.opportunities]

    @rx.var
    def selected_report_opportunity(self) -> str:
        prefix = str(self.report_opportunity_id) + " · "
        return next((option for option in self.report_opportunity_options if option.startswith(prefix)), "")

    @rx.var
    def radar_chart_data(self) -> list[dict[str, Any]]:
        return [{
            "name": item["use_case"], "relevance": item["relevance"], "confidence": item["confidence"],
            "signals": item["article_count"] * 5 + 20,
        } for item in self.visible_opportunities]

    @rx.var
    def selected_document_count(self) -> int:
        return sum(1 for item in self.documents if item["selected"])

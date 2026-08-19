from __future__ import annotations

import json

import plotly.express as px
import streamlit as st

from radar.ai import AIClient, AIError
from radar.company import DocumentError, fetch_document_url
from radar.config import ROOT, ai_settings, load_json
from radar.db import active_company, connect, initialize, knowledge_settings, rows, save_company, save_knowledge_settings, sync_sources, utcnow
from radar.library import STAGES, add_document, company_directory, create_report, process_document, refresh_library_index, rename_document, set_stages
from radar.intelligence import evidence_strength, opportunity_evidence_strength, sync_alec_research, taxonomy_prompt_context
from radar.pipeline import pipeline_preflight, refresh
from radar.scoring import publication_checks
from radar.seed import seed_demo

st.set_page_config(page_title="Orange Business Innovation Radar", page_icon="◉", layout="wide")

CSS = """
<style>
:root { --orange:#ff7900; --orange-light:#ffb46b; --black:#090909; --panel:#151515; --panel-2:#1e1e1e; --line:#353535; --text:#f7f7f7; --muted:#b8b8b8; --green:#72d69a; --red:#ff7272; }
.stApp { background:var(--black); color:var(--text); }
.stApp, .stApp p, .stApp li, .stApp label, .stApp span, .stApp h1, .stApp h2, .stApp h3 { color:var(--text); }
[data-testid="stSidebar"] { background:#111; border-right:1px solid var(--line); }
[data-testid="stSidebar"] * { color:var(--text); }
[data-testid="stHeader"] { background:var(--black); }
h1,h2,h3 { letter-spacing:-.035em; }
.hero { background:var(--panel); color:var(--text); padding:2rem 2.2rem; border-left:8px solid var(--orange); margin-bottom:1.2rem; }
.hero b { color:var(--orange); text-transform:uppercase; letter-spacing:.16em; font-size:.75rem; }
.hero h1 { margin:.35rem 0 .2rem; font-size:2.6rem; }
.hero p { margin:0; color:var(--muted); }
.opportunity { background:var(--panel); border:1px solid var(--line); border-top:4px solid var(--orange); padding:1.2rem; margin:.7rem 0; }
.tag { display:inline-block; padding:.25rem .55rem; margin-right:.3rem; background:#333; color:var(--text)!important; font-size:.74rem; font-weight:700; text-transform:uppercase; }
.watch { background:#5a330d; color:#ffd4a8!important; }
.score { font-size:1.8rem; font-weight:800; }
div[data-testid="stMetric"] { background:var(--panel); border:1px solid var(--line); padding:.8rem; }
.evidence { border-left:3px solid var(--orange); padding:.65rem .85rem; margin:.5rem 0; background:var(--panel-2); }
.rule-box { background:var(--panel-2); border:1px solid var(--line); padding:1rem; margin:.6rem 0; }
.pass { color:var(--green)!important; font-weight:700; }
.fail { color:var(--red)!important; font-weight:700; }
a { color:var(--orange-light)!important; }
[data-testid="stExpander"], [data-testid="stForm"], [data-testid="stAlert"] { background:var(--panel); border-color:var(--line); }
[data-baseweb="input"] > div, [data-baseweb="select"] > div, [data-baseweb="base-input"], textarea { background:var(--panel-2)!important; color:var(--text)!important; }
input, textarea { color:var(--text)!important; -webkit-text-fill-color:var(--text)!important; }
button[kind="primary"] { background:var(--orange)!important; color:#090909!important; border:none!important; font-weight:800!important; }
button[kind="secondary"], button[kind="formSubmit"] { background:var(--panel-2)!important; color:var(--text)!important; border:1px solid #666!important; }
[data-testid="stDataFrame"] { border:1px solid var(--line); }
[data-testid="stCaptionContainer"] p, .stApp small { color:var(--muted)!important; }
code { color:#ffb46b!important; background:#202020!important; }
hr { border-color:var(--line); }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def bootstrap() -> None:
    initialize()
    sync_sources(load_json("config/sources.json"))
    sync_alec_research()
    seed_demo()


def options(items: list[dict], key: str) -> list[str]:
    return sorted({str(item[key]) for item in items if item.get(key)})


def select_many(label: str, values: list[str], key: str) -> list[str]:
    return st.sidebar.multiselect(label, values, key=key, placeholder="All")


def opportunity_filters(opportunities: list[dict]) -> list[dict]:
    st.sidebar.markdown("### Focus")
    verticals = select_many("Vertical", options(opportunities, "vertical"), "vertical_filter")
    geographies = select_many("Geography", options(opportunities, "geography"), "geography_filter")
    domains = select_many("Capability domain", options(opportunities, "orange_domain"), "domain_filter")
    personas = select_many("Persona", options(opportunities, "persona"), "persona_filter")
    horizons = select_many("Time horizon", ["Now", "Next", "Later"], "horizon_filter")
    statuses = select_many("Publication state", ["Radar", "Watchlist"], "status_filter")
    query = st.sidebar.text_input("Ask/filter the radar", placeholder="e.g. public transport")
    result = opportunities
    for key, selected in (("vertical",verticals),("geography",geographies),("orange_domain",domains),("persona",personas),("horizon",horizons),("status",statuses)):
        if selected:
            result = [item for item in result if item.get(key) in selected]
    if query:
        words = query.lower().split()
        result = [item for item in result if all(word in " ".join(str(v) for v in item.values()).lower() for word in words)]
    return result


def radar_page() -> None:
    company = active_company()
    opportunities = rows("SELECT * FROM opportunities ORDER BY attractiveness DESC, confidence DESC")
    filtered = opportunity_filters(opportunities)
    st.markdown(f'<div class="hero"><b>Evidence to action · {company.get("name", "Company")}</b><h1>Innovation Radar</h1><p>Specific direct, partner-led, and ecosystem opportunities for {company.get("geography", "the selected market")}, ranked transparently and linked to next actions.</p></div>', unsafe_allow_html=True)
    launch_col, note_col = st.columns([1, 3])
    if launch_col.button("Run full pipeline", type="primary", use_container_width=True, key="radar_run"):
        run_full_pipeline()
    note_col.caption("Collect enabled feeds → deduplicate → run AI extraction → group opportunities → calculate scores → save results.")
    a,b,c,d = st.columns(4)
    a.metric("Visible opportunities", len(filtered))
    b.metric("On radar", sum(item["status"] == "Radar" for item in filtered))
    c.metric("Watchlist", sum(item["status"] == "Watchlist" for item in filtered))
    d.metric("Evidence items", rows("SELECT COUNT(*) count FROM evidence")[0]["count"])
    if not filtered:
        st.info("No opportunities match this focus. Remove filters or refresh sources.")
        return
    figure = px.scatter(
        filtered, x="attractiveness", y="right_to_win", size="confidence", color="horizon",
        hover_name="title", symbol="status", size_max=38,
        color_discrete_map={"Now":"#ff7900","Next":"#202020","Later":"#9f9f9f"},
        labels={"attractiveness":"Opportunity attractiveness","right_to_win":f"{company.get('name', 'Company')} right to win"},
    )
    figure.update_layout(
        height=510, plot_bgcolor="#151515", paper_bgcolor="#090909", font_color="#f7f7f7",
        legend_title_text="Horizon / state", xaxis_gridcolor="#333", yaxis_gridcolor="#333",
    )
    figure.add_vline(x=60, line_dash="dot", line_color="#777")
    figure.add_hline(y=60, line_dash="dot", line_color="#777")
    st.plotly_chart(figure, use_container_width=True)
    st.caption(f"Bubble size represents confidence. The right-to-win model is proposed, not a {company.get('name', 'company')}-confirmed formula.")
    st.subheader("Focused opportunities")
    display_limit = st.slider("Topics shown", 1, max(1, min(20, len(filtered))), min(6, len(filtered)))
    for item in filtered[:display_limit]:
        state_class = "watch" if item["status"] == "Watchlist" else ""
        st.markdown(f'''<div class="opportunity"><span class="tag {state_class}">{item['status']}</span><span class="tag">{item['horizon']}</span><span class="tag">{item['vertical']}</span><h3>{item['title']}</h3><span class="score">{item['attractiveness']:.0f}</span>/100 attractiveness &nbsp; <b>{item['right_to_win']:.0f}</b>/100 right to win &nbsp; <b>{item['confidence']}</b>/100 confidence</div>''', unsafe_allow_html=True)
        with st.expander("Evidence, explanation and next action"):
            evidence = rows("SELECT * FROM evidence WHERE opportunity_id=? ORDER BY published_at DESC", (item["id"],))
            independent_domains = len({proof["source_domain"] for proof in evidence if proof["source_domain"]})
            checks = publication_checks(len(evidence), independent_domains, item["confidence"])
            factors = json.loads(item["factors_json"] or "{}")
            classification = factors.get("classification", {})
            st.markdown("**Why this is Radar or Watchlist**")
            st.write(
                "Watchlist means the opportunity is worth monitoring but has not passed every evidence gate. "
                "Radar means every configured gate passed. It is not automatic approval for investment."
            )
            check_lines = "".join(
                f'<div class="{"pass" if passed else "fail"}">{"PASS" if passed else "FAIL"}: {label}</div>'
                for label, passed in checks.items()
            )
            st.markdown(f'<div class="rule-box">{check_lines}</div>', unsafe_allow_html=True)
            st.markdown("**Why this time horizon**")
            st.write(classification.get("horizon_rule", "This seeded/older record has no stored deterministic horizon trace."))
            st.caption(f"Assigned by: {classification.get('horizon_assigned_by', 'unknown')} · signal: {classification.get('signal_type', item['signal_type'])} · urgency: {classification.get('urgency', 'not stored')}/10")
            st.markdown("**Why hot now**")
            st.write(item["why_hot_now"])
            st.markdown(f"**Why it matters to {company.get('name', 'the active company')}**")
            st.write(item["why_it_matters"])
            st.markdown("**Recommended next action**")
            st.info(item["next_action"])
            st.caption(item["score_rationale"])
            evidence_indicator = opportunity_evidence_strength(item["id"])
            st.metric("Evidence strength (prototype)", f"{evidence_indicator['score']:.0f}/100")
            st.caption(f"Log-volume {evidence_indicator['volume']:.0f} · independence {evidence_indicator['independence']:.0f} · high-value signal mix {evidence_indicator['signal_quality']:.0f}. This is evidence support, not market size.")
            left,right = st.columns(2)
            left.markdown("**Attractiveness factors /10**")
            left.json(factors.get("attractiveness", {}), expanded=True)
            right.markdown("**Right-to-win factors /10**")
            right.json(factors.get("right_to_win", {}), expanded=True)
            st.markdown("**Source evidence**")
            for proof in evidence:
                st.markdown(f'''<div class="evidence"><b>{proof['signal_type'].replace('_',' ').title()}</b> · {proof['published_at'] or 'date unknown'}<br>{proof['claim']}<br><a href="{proof['source_url']}">{proof['source_name']}</a></div>''', unsafe_allow_html=True)


def inbox_page() -> None:
    st.title("Signal inbox")
    st.write("Raw source items remain separate from AI-created evidence. Failed or unprocessed articles can be inspected and retried.")
    articles = rows("""SELECT a.id,a.title,a.url,a.published_at,a.processed,s.name source,s.domain FROM articles a JOIN sources s ON s.id=a.source_id ORDER BY a.fetched_at DESC LIMIT 250""")
    c1,c2,c3 = st.columns(3)
    c1.metric("Stored signals", len(articles))
    c2.metric("Processed", sum(a["processed"] for a in articles))
    c3.metric("Pending", sum(not a["processed"] for a in articles))
    st.dataframe(articles, use_container_width=True, hide_index=True, column_config={"url":st.column_config.LinkColumn("URL")})
    st.subheader("AI candidate library")
    st.write("Every model result is saved before validation. Failed or interrupted runs therefore keep recoverable candidate ideas and their errors.")
    candidate_summary = rows("SELECT status,COUNT(*) count FROM analysis_candidates GROUP BY status ORDER BY count DESC")
    if candidate_summary:
        st.dataframe(candidate_summary, use_container_width=True, hide_index=True)
        candidates = rows("""SELECT c.id,c.run_id,c.article_id,a.title,c.captured_at,c.status,c.error,c.promoted_opportunity_id,c.result_json
            FROM analysis_candidates c JOIN articles a ON a.id=c.article_id ORDER BY c.id DESC LIMIT 200""")
        st.dataframe(candidates, use_container_width=True, hide_index=True)
    else:
        st.info("No AI candidates have been captured yet. Older failed runs occurred before candidate archival was added.")

    st.subheader("Failed and exhausted articles")
    failures = rows("""SELECT a.id,a.title,a.url,a.attempt_count,a.last_attempt_at,a.last_error,s.name source
        FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.last_error IS NOT NULL ORDER BY a.last_attempt_at DESC LIMIT 200""")
    if failures:
        st.dataframe(failures, use_container_width=True, hide_index=True, column_config={"url":st.column_config.LinkColumn("URL")})
    else:
        st.caption("No persisted article errors.")


def refresh_page() -> None:
    st.title("Refresh pipeline")
    st.write("Collect RSS signals, deduplicate them, then let the selected extraction model create evidence candidates. Python calculates final scores.")
    settings = st.session_state.get("ai_settings", ai_settings())
    left,middle,right = st.columns(3)
    maximum = left.number_input("Maximum articles", 1, 100, 20, help="Hard article ceiling for this run.")
    batch_size = middle.number_input("Articles per AI request", 1, 10, 5, help="Five articles in one request reduces API calls.")
    max_requests = right.number_input("Hard API request limit", 1, 20, 5, help="Enforced inside the HTTP client.")
    requests_per_minute = st.number_input("Requests per minute", 1, 10, 10, help="Hard-capped at 10 RPM. Requests are spaced rather than burst.")
    retry_limit = st.number_input("Maximum attempts per article", 1, 5, 2)
    ingestion_only = st.checkbox("Ingestion only", value=not bool(settings.get("api_key")))
    estimate = pipeline_preflight(int(maximum), int(batch_size), int(retry_limit))
    st.info(
        f"Preflight: {estimate['pending']} eligible pending article(s); this run selects at most {estimate['selected']} "
        f"and needs about {estimate['estimated_requests']} AI request(s). The hard request limit is {max_requests}."
    )
    st.warning("AI output is treated as a candidate. Claims remain traceable to their source URL; high-stakes publication requires human review.")
    if st.button("Refresh evidence", type="primary", use_container_width=True):
        try:
            run_settings = {**settings, "max_requests": int(max_requests), "requests_per_minute": int(requests_per_minute)}
            client = None if ingestion_only else AIClient(run_settings)
            result = execute_with_progress(client, int(maximum), int(batch_size), int(retry_limit))
            st.success(result)
        except (AIError, Exception) as error:
            st.error(str(error))
    st.subheader("Run history")
    st.dataframe(rows("SELECT * FROM runs ORDER BY started_at DESC LIMIT 100"), use_container_width=True, hide_index=True)
    st.subheader("Recent execution events")
    st.dataframe(rows("SELECT * FROM run_events ORDER BY id DESC LIMIT 200"), use_container_width=True, hide_index=True)


def execute_with_progress(client: AIClient | None, maximum: int, batch_size: int, retry_limit: int) -> dict:
    status = st.status("Starting bounded pipeline...", expanded=True)
    progress = st.progress(0.0, text="Initializing")

    def update(event: dict) -> None:
        current = event.get("current")
        total = event.get("total")
        if current is not None and total:
            progress.progress(min(current / total, 1.0), text=event["message"])
        else:
            progress.progress(0.0 if event["stage"] != "complete" else 1.0, text=event["message"])
        status.write(f"**{event['stage'].replace('_', ' ').title()}**: {event['message']}")

    if client:
        client.on_rate_limit_wait = lambda seconds: update({
            "stage": "rate_limit",
            "message": f"Safety cooldown: waiting {seconds:.1f}s before API request {client.request_count + 1}/{client.max_requests} ({client.requests_per_minute} RPM limit).",
            "current": client.request_count,
            "total": client.max_requests,
        })
    result = refresh(client, maximum, batch_size, retry_limit, update)
    progress.progress(1.0, text="Pipeline finished")
    status.update(label=f"Pipeline finished with {result['api_requests']} API request(s)", state="complete", expanded=True)
    return result


def run_full_pipeline() -> None:
    settings = st.session_state.get("ai_settings", ai_settings())
    if not settings.get("api_key"):
        st.error("No AI key is active. Save provider settings under AI settings, then run the pipeline again.")
        return
    try:
        maximum = int(st.session_state.get("quick_maximum", 20))
        batch_size = int(st.session_state.get("quick_batch_size", 5))
        max_requests = int(st.session_state.get("quick_max_requests", 5))
        requests_per_minute = int(st.session_state.get("quick_rpm", 10))
        retry_limit = int(st.session_state.get("quick_retry_limit", 2))
        estimate = pipeline_preflight(maximum, batch_size, retry_limit)
        required = min(estimate["estimated_requests"], max_requests)
        st.info(
            f"Bounded run: up to {estimate['selected']} article(s), batches of {batch_size}, "
            f"at most {max_requests} API request(s), paced at {requests_per_minute} RPM; approximately {required} expected now."
        )
        client = AIClient({**settings, "max_requests": max_requests, "requests_per_minute": requests_per_minute})
        result = execute_with_progress(client, maximum, batch_size, retry_limit)
        st.success(
            f"Pipeline complete using {result['api_requests']} API request(s): {result['added']} new signal(s), "
            f"{result['processed']} completed, {result['accepted']} accepted, {result['ignored']} ignored, {result['failed']} failed."
        )
        if result["failed"]:
            st.warning("Some articles failed analysis. Detailed per-article error storage is not implemented yet.")
    except Exception as error:
        st.error(f"Pipeline stopped: {error}")


def company_page() -> None:
    company = active_company()
    st.title("Company workspace")
    st.write("Store raw company knowledge, process selected files into compact summaries, then choose exactly where those summaries enter the pipeline.")
    st.info("Raw files are never appended to opportunity prompts. Only explicitly staged processed summaries or reports are injected, with document and character caps.")

    with st.form("company_profile"):
        name = st.text_input("Company name", company.get("name", ""))
        geography = st.text_input("Priority geography", company.get("geography", ""))
        website_url = st.text_input("Company website", company.get("website_url", ""))
        strategic_prompt = st.text_area(
            "Company and partner instruction",
            company.get("strategic_prompt", ""),
            height=150,
            help="Describe strategy, strengths, exclusions, target customers, and how partner-led opportunities should be treated.",
        )
        if st.form_submit_button("Save company context", type="primary"):
            if not name.strip():
                st.error("Company name is required.")
            else:
                save_company(name.strip(), geography.strip(), website_url.strip(), strategic_prompt.strip())
                company_directory(name.strip())
                st.success(f"Saved company and ensured `Documents/{name.strip()}/processed/` exists.")

    known_companies = sorted({company.get("name", "Orange Business")} | {item["company_name"] for item in rows("SELECT DISTINCT company_name FROM library_documents")})
    library_choice = st.selectbox("Existing company library", known_companies + ["Create or type another company"])
    custom_company = st.text_input("New/custom company name", placeholder="Used only when creating another library")
    target_company = custom_company.strip() if library_choice == "Create or type another company" and custom_company.strip() else company.get("name", "Orange Business") if library_choice == "Create or type another company" else library_choice
    target_folder = company_directory(target_company)

    st.subheader("Add documentation URL")
    st.caption("Use a direct PDF, PPTX, DOCX, text, or readable HTML URL. A normal company homepage is not automatically crawled recursively.")
    with st.form("document_url_form", clear_on_submit=True):
        document_url = st.text_input("Direct documentation URL")
        if st.form_submit_button("Download and extract"):
            if not document_url.startswith(("http://", "https://")):
                st.error("Enter a valid HTTP or HTTPS URL.")
            else:
                try:
                    with st.spinner("Downloading and storing raw document..."):
                        document_name, data, content_type = fetch_document_url(document_url)
                        saved = add_document(target_company, document_name, data, content_type, document_url)
                    st.success(f"Added `{saved['name']}` to `Documents/{target_company}/`.")
                except (DocumentError, Exception) as error:
                    st.error(str(error))

    st.subheader("Upload company documents")
    uploaded_files = st.file_uploader(
        "PDF, PPTX, DOCX, TXT, Markdown, CSV, JSON, or HTML",
        type=["pdf", "pptx", "docx", "txt", "md", "csv", "json", "html", "htm"],
        accept_multiple_files=True,
    )
    if st.button("Extract and add uploads", disabled=not uploaded_files, use_container_width=True):
        added = 0
        for uploaded in uploaded_files:
            try:
                add_document(target_company, uploaded.name, uploaded.getvalue(), uploaded.type or "")
                added += 1
            except DocumentError as error:
                st.error(str(error))
        if added:
            st.success(f"Stored {added} raw document(s) under `Documents/{target_company}/` without AI calls.")

    st.subheader("Company document library")
    limits = knowledge_settings()
    with st.expander("Knowledge cost and context limits", expanded=False):
        with st.form("knowledge_limits"):
            max_process = st.number_input("Maximum independent summaries per action", 1, 50, limits["max_process_documents"])
            max_context_docs = st.number_input("Maximum processed documents per pipeline stage", 1, 25, limits["max_context_documents"])
            max_context_chars = st.number_input("Maximum company-context characters per batch", 1000, 50000, limits["max_context_chars"], step=1000)
            max_report_docs = st.number_input("Maximum documents in one combined report", 2, 50, limits["max_report_documents"])
            max_report_chars = st.number_input("Maximum source characters in one report call", 5000, 150000, limits["max_report_chars"], step=5000)
            if st.form_submit_button("Save knowledge limits"):
                save_knowledge_settings(int(max_process), int(max_context_docs), int(max_context_chars), int(max_report_docs), int(max_report_chars))
                st.success("Knowledge limits saved.")
    refresh_col, path_col = st.columns([1, 4])
    if refresh_col.button("↻ Refresh library", use_container_width=True):
        result = refresh_library_index(target_company)
        st.success(f"Indexed {result['added']} manually added file(s); skipped {result['skipped']} unreadable file(s).")
    relative_folder = target_folder.relative_to(ROOT)
    path_col.caption(f"Filesystem: `{relative_folder}/` · summaries: `{relative_folder}/processed/`")

    search = st.text_input("Search library", placeholder="Filename, status, source, or stage")
    page_size = st.selectbox("Documents per page", [5, 10, 20, 50], index=1)
    all_documents = rows("SELECT * FROM library_documents WHERE company_name=? ORDER BY updated_at DESC", (target_company,))
    if search:
        query = search.lower()
        all_documents = [doc for doc in all_documents if query in " ".join(str(value) for value in doc.values()).lower()]
    page_count = max(1, (len(all_documents) + page_size - 1) // page_size)
    page = st.number_input("Page", 1, page_count, 1)
    documents = all_documents[(page - 1) * page_size:page * page_size]
    raw_tab, processed_tab = st.tabs(["Raw documents", "Processed summaries and reports"])
    with raw_tab:
        raw_documents = [doc for doc in documents if doc["source_type"] != "report"]
        st.dataframe([{key: doc[key] for key in ("id", "name", "source_type", "raw_chars", "status", "error", "updated_at")} for doc in raw_documents], use_container_width=True, hide_index=True)
    with processed_tab:
        processed_documents = [doc for doc in documents if doc["status"] == "processed"]
        st.dataframe([{key: doc[key] for key in ("id", "name", "source_type", "processed_chars", "stages_json", "updated_at")} for doc in processed_documents], use_container_width=True, hide_index=True)

    raw_choices = {f"#{doc['id']} · {doc['name']}": doc["id"] for doc in all_documents if doc["source_type"] != "report"}
    selected_raw_labels = st.multiselect("Select raw documents to process", list(raw_choices))
    process_limit = limits["max_process_documents"]
    st.caption(f"This action will process at most {process_limit} documents. One document = one isolated API call.")
    summary_stages = st.multiselect("Use resulting summaries in pipeline stages", STAGES, default=["all"])
    if st.button("Process selected independently", type="primary", disabled=not selected_raw_labels):
        selected_ids = [raw_choices[label] for label in selected_raw_labels[:int(process_limit)]]
        settings = st.session_state.get("ai_settings", ai_settings())
        if not settings.get("api_key"):
            st.error("Configure an API key under AI settings first.")
        elif settings.get("mode") == "auto":
            st.error("Choose an explicit `responses` or `chat` endpoint mode in AI settings. `auto` fallback cannot guarantee one HTTP request per document.")
        else:
            client = AIClient({**settings, "max_requests": len(selected_ids), "requests_per_minute": 10})
            progress = st.progress(0, text="Starting independent summaries")
            for index, document_id in enumerate(selected_ids, 1):
                try:
                    process_document(document_id, client, summary_stages)
                    progress.progress(index / len(selected_ids), text=f"Processed {index}/{len(selected_ids)} · API calls {client.request_count}/{len(selected_ids)}")
                except Exception as error:
                    with connect() as connection:
                        connection.execute("UPDATE library_documents SET status='failed',error=?,updated_at=? WHERE id=?", (str(error)[:1000], utcnow(), document_id))
                    st.error(f"Document #{document_id}: {error}")
            st.success(f"Processing finished with {client.request_count} API call(s). One document was isolated per call.")

    processed_choices = {f"#{doc['id']} · {doc['name']}": doc["id"] for doc in all_documents if doc["status"] == "processed"}
    rename_choices = {f"#{doc['id']} · {doc['name']}": doc["id"] for doc in all_documents}
    selected_processed_labels = st.multiselect("Select processed documents for context/report actions", list(processed_choices))
    selected_processed_ids = [processed_choices[label] for label in selected_processed_labels]
    action_col, rename_col = st.columns(2)
    with action_col:
        context_stages = st.multiselect("Assign selected summaries to stages", STAGES, default=["collection"])
        if st.button("Save stage assignment", disabled=not selected_processed_ids):
            for document_id in selected_processed_ids:
                set_stages(document_id, context_stages)
            st.success(f"Updated {len(selected_processed_ids)} summary/report assignment(s).")
        if st.button("Create one combined company report", disabled=not selected_processed_ids):
            settings = st.session_state.get("ai_settings", ai_settings())
            if not settings.get("api_key"):
                st.error("Configure an API key under AI settings first.")
            elif settings.get("mode") == "auto":
                st.error("Choose an explicit `responses` or `chat` endpoint mode. A report is limited to exactly one HTTP request.")
            else:
                client = AIClient({**settings, "max_requests": 1, "requests_per_minute": 10})
                report = create_report(target_company, selected_processed_ids, client)
                st.success(f"Created `{report['name']}` with exactly {client.request_count} API call.")
    with rename_col:
        rename_label = st.selectbox("Document to rename", [""] + list(rename_choices))
        new_name = st.text_input("New filename")
        if st.button("Rename file", disabled=not rename_label or not new_name.strip()):
            result = rename_document(rename_choices[rename_label], new_name)
            st.success(f"Renamed to `{result['name']}`.")

    st.subheader("Context budget")
    st.caption(f"Pipeline injects at most {limits['max_context_documents']} processed documents per stage and {limits['max_context_chars']:,} company-context characters per article batch. Raw documents are never injected.")


def sources_page() -> None:
    st.title("Sources and VIP watchlist")
    st.write("Enabled feeds are reproducible defaults. Add a priority source to steer collection toward a customer, regulator, partner, vertical, or domain.")
    st.markdown("""
**How sources work in this version**

1. This form accepts an RSS or Atom feed URL, not an arbitrary webpage.
2. Refresh downloads feed entries and stores their title, canonical URL, date, and feed-provided summary in SQLite.
3. Duplicate GUIDs are ignored. URL query strings and fragments are removed during normalization.
4. Without an AI key, entries remain in the Signal inbox. With an AI key, the extractor decides relevance and proposes one evidence claim.
5. The original source URL remains attached to the claim for inspection.

**Current limitation:** the pipeline does not download the complete linked webpage, verify whether two domains repeat the same syndicated claim, or assign formal publisher-quality tiers. Those are required improvements before treating the output as production research.
""")
    with st.form("source_form", clear_on_submit=True):
        name = st.text_input("Source name")
        url = st.text_input("RSS / Atom URL")
        domain = st.selectbox("Orange domain", ["Cybersecurity","Cloud and AI","Secure connectivity","Smart industries","Customer experience","Other"])
        geography = st.text_input("Geography", "Belgium / Europe")
        submitted = st.form_submit_button("Add priority source")
        if submitted and name and url.startswith(("http://","https://")):
            try:
                with connect() as connection:
                    connection.execute("INSERT INTO sources(name,url,domain,geography,enabled) VALUES(?,?,?,?,1)", (name,url,domain,geography))
                st.success("Source added.")
            except Exception as error:
                st.error(str(error))
    sources = rows("SELECT * FROM sources ORDER BY name")
    st.dataframe(sources, use_container_width=True, hide_index=True, column_config={"url":st.column_config.LinkColumn("Feed")})


def intelligence_page() -> None:
    st.title("Prototype intelligence")
    st.write("Alec's research layer supplies human-curated source metadata, canonical vocabulary, a high-precision triage pilot, and a manufacturing coverage-gap view. It guides the prototype; it is not presented as official Orange data.")
    counts = {
        "Canonical terms": rows("SELECT COUNT(*) count FROM taxonomy_terms")[0]["count"],
        "Aliases": rows("SELECT COUNT(*) count FROM taxonomy_aliases")[0]["count"],
        "Registered sources": rows("SELECT COUNT(*) count FROM intelligence_sources")[0]["count"],
        "Triage records": rows("SELECT COUNT(*) count FROM triage_records")[0]["count"],
    }
    cols = st.columns(4)
    for column, (label, value) in zip(cols, counts.items()):
        column.metric(label, value)
    st.caption("Provenance: taxonomy, source registry, coverage matrix, and pilot triage originate from Alec's human research/prototype work. The triage CSV records model gpt-5.6-terra and remains pending_review because those classifications were not independently approved.")
    triage = rows("SELECT classification,triage_confidence,signal_type,vertical_id,use_case_id,technology_id,source,review_status,classification_method,research_origin FROM triage_records ORDER BY processed_at DESC")
    st.subheader("Triage pilot")
    if triage:
        st.dataframe(triage, use_container_width=True, hide_index=True)
    coverage = rows("SELECT * FROM coverage_gaps ORDER BY vertical_id,signal_type")
    st.subheader("Coverage gaps")
    if coverage:
        st.dataframe(coverage, use_container_width=True, hide_index=True)
    terms = rows("SELECT taxonomy_type,canonical_id,display_name,parent_id,description,research_origin FROM taxonomy_terms ORDER BY taxonomy_type,canonical_id")
    st.subheader("Canonical taxonomy")
    st.dataframe(terms, use_container_width=True, hide_index=True)
    st.subheader("Competitor and internal-signal extension")
    st.write("The triage schema supports named and actor roles. Future competitor/internal analysis should store competitor moves separately from external market attractiveness, then influence momentum, urgency, or recommended action rather than automatically increasing right-to-win.")


def settings_page() -> None:
    st.title("AI agents and prompts")
    st.write("Provider settings are session-only and are never written to disk. Prompt edits are versioned manually in `config/prompts.json` and visible here for reproducibility.")
    defaults = st.session_state.get("ai_settings", ai_settings())
    with st.form("provider_settings"):
        base_url = st.text_input("OpenAI-compatible base URL", defaults["base_url"])
        api_key = st.text_input("API key", defaults["api_key"], type="password")
        model = st.text_input("Extraction model", defaults["model"])
        mode = st.selectbox("Endpoint mode", ["auto","responses","chat"], index=["auto","responses","chat"].index(defaults.get("mode","auto")))
        timeout = st.number_input("Timeout seconds", 10, 600, int(defaults["timeout"]))
        if st.form_submit_button("Use for this session", type="primary"):
            st.session_state["ai_settings"] = {"base_url":base_url.rstrip("/"),"api_key":api_key,"model":model,"mode":mode,"timeout":timeout}
            st.success("Session provider updated. The key was not saved.")
    st.info("Provider saved for this browser session. Use **Run full pipeline** on the Radar page or the sidebar action below.")
    prompts_path = ROOT / "config/prompts.json"
    prompts = load_json("config/prompts.json")
    st.subheader("Operational prompt registry")
    for name, value in prompts.items():
        with st.expander(f"{name.title()} · version {value['version']}"):
            st.code(value["system"], language="text")
    st.caption(f"Edit prompts through source control for an auditable change history: {prompts_path}")


def methodology_page() -> None:
    company = active_company()
    st.title("Methodology and audit trail")
    scoring = load_json("config/scoring.json")
    st.markdown(f"""
### Reproducible flow
`Source registry → RSS collection → normalization/deduplication → AI evidence extraction → opportunity grouping → deterministic scoring → radar/watchlist → human decision`

### What Watchlist means
Watchlist is an evidence state, not a low-value score. A topic remains there unless all three proposed gates pass: at least **{scoring['publish_thresholds']['minimum_evidence']} evidence items**, **{scoring['publish_thresholds']['minimum_domains']} independent domains**, and **{scoring['publish_thresholds']['minimum_confidence']}/100 confidence**. Radar means those minimum gates passed; it does not mean Orange should invest.

### Confidence calculation
`min(evidence count, 4) × 10 + min(domain count, 3) × 12 + evidence quality /10 × 2 + 4 if human-reviewed`, capped at 100. Evidence quality is currently proposed by AI, so confidence is an aid, not an objective fact.

### Time horizon code
- `Now`: urgency is at least 8/10 **and** signal type is regulation, buying signal, or proof signal.
- `Next`: urgency is at least 5/10 but the strict Now condition was not met.
- `Later`: urgency is below 5/10.

The AI proposes urgency and signal type from the source. Python now always applies these horizon rules. This makes the label reproducible, but the AI inputs still require human inspection.

### Scoring code
- Attractiveness: `30% market signal + 20% source diversity + 20% evidence quality + 15% momentum + 15% strategic relevance`.
- Right to win for {company.get('name', 'the active company')}: `30% offering fit + 25% customer overlap + 25% references + 20% partner readiness`.
- AI proposes each factor from 0 to 10 and a rationale. Python clamps factors to 0-10, applies the weights, and converts the result to 0-100.
- Both formulas are proposed working models. The exact right-to-win formula is not confirmed by the active company.

### Coding guardrails currently enforced
- Required opportunity fields cannot be empty.
- Signal type must belong to the six-value taxonomy.
- Scores and urgency are clamped to allowed ranges.
- Final arithmetic and horizon assignment happen in Python.
- Duplicate article GUIDs and duplicate opportunity/source URL evidence are rejected by SQLite constraints.
- API credentials are runtime-only and are not stored by the application.

### Semantic guardrails intended
- External evidence should establish market attractiveness; Orange-owned evidence should establish right to win.
- Claims should remain attributable to dated source evidence.
- Broad themes should become a specific `Vertical x Use Case x Technology` opportunity.
- Weak evidence should remain visible but clearly marked Watchlist.

### Current gaps
- Source ownership is not yet automatically classified, so the external-versus-Orange separation is a documented rule rather than a complete code gate.
- Source independence is currently counted by hostname; syndicated or copied claims can still look independent.
- AI-generated factor values are schema-checked but not independently fact-checked.
- Existing opportunities are matched by exact normalized wording, so semantic duplicates may remain separate.
- There is no human review workflow field yet; the optional reviewed confidence bonus is unused.
- Seed examples are hypotheses from supplied files, not validated market conclusions.

### Decision rule
High attractiveness and high right to win: prioritize. High attractiveness and low right to win: assess partners or capability gaps. Strong right to win with moderate attractiveness: targeted account play. Low confidence: watchlist and gather evidence.
""")
    st.subheader("Project records")
    st.write("Architecture, decisions, prompts, and presentation scope are stored under `docs/` and `config/`.")


bootstrap()
company = active_company()
st.sidebar.markdown(f"**Active company**  \n{company.get('name', 'Not configured')}")
with st.sidebar.expander("RUN LIMITS", expanded=False):
    st.number_input("Max articles", 1, 100, 20, key="quick_maximum")
    st.number_input("Articles / request", 1, 10, 5, key="quick_batch_size")
    st.number_input("Max API requests", 1, 20, 5, key="quick_max_requests")
    st.number_input("Requests / minute", 1, 10, 10, key="quick_rpm")
    st.number_input("Attempts / article", 1, 5, 2, key="quick_retry_limit")
if st.sidebar.button("RUN FULL PIPELINE", type="primary", use_container_width=True, key="sidebar_run"):
    run_full_pipeline()
page = st.sidebar.radio("Navigate", ["Radar","Company workspace","Signal inbox","Refresh","Sources","Prototype intelligence","AI settings","Methodology"], label_visibility="collapsed")
st.sidebar.caption("Student prototype · Evidence must be reviewed")
{"Radar":radar_page,"Company workspace":company_page,"Signal inbox":inbox_page,"Refresh":refresh_page,"Sources":sources_page,"Prototype intelligence":intelligence_page,"AI settings":settings_page,"Methodology":methodology_page}[page]()

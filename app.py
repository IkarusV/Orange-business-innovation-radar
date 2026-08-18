from __future__ import annotations

import json

import plotly.express as px
import streamlit as st

from radar.ai import AIClient, AIError
from radar.company import DocumentError, extract_document, fetch_document_url
from radar.config import ROOT, ai_settings, load_json
from radar.db import active_company, connect, initialize, rows, save_company, save_company_document, sync_sources
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
    st.write("Configure the company whose ability to act should be evaluated. Opportunities may be direct, partner-led, ecosystem-led, or capability-gap plays.")
    st.warning("This version has one active company context. Existing Orange seed cards stay in the database and are visibly demo data; complete multi-company isolation is not implemented yet.")

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
                st.success("Active company context saved and will be injected into future AI analysis.")

    st.subheader("Add documentation URL")
    st.caption("Use a direct PDF, PPTX, DOCX, text, or readable HTML URL. A normal company homepage is not automatically crawled recursively.")
    with st.form("document_url_form", clear_on_submit=True):
        document_url = st.text_input("Direct documentation URL")
        if st.form_submit_button("Download and extract"):
            if not document_url.startswith(("http://", "https://")):
                st.error("Enter a valid HTTP or HTTPS URL.")
            else:
                try:
                    with st.spinner("Downloading and extracting document text..."):
                        document_name, text = fetch_document_url(document_url)
                        save_company_document(document_name, "url", text, document_url)
                    st.success(f"Added {document_name}: {len(text):,} extracted characters.")
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
                text = extract_document(uploaded.name, uploaded.getvalue(), uploaded.type or "")
                save_company_document(uploaded.name, "upload", text)
                added += 1
            except DocumentError as error:
                st.error(str(error))
        if added:
            st.success(f"Added {added} company document(s). Future pipeline runs will use their extracted text.")

    documents = rows("SELECT id,name,source_type,source_url,LENGTH(extracted_text) extracted_characters,added_at FROM company_documents ORDER BY added_at DESC")
    st.subheader("Active reference library")
    if documents:
        st.dataframe(documents, use_container_width=True, hide_index=True, column_config={"source_url": st.column_config.LinkColumn("Source URL")})
    else:
        st.info("No company documents have been added yet.")


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
page = st.sidebar.radio("Navigate", ["Radar","Company workspace","Signal inbox","Refresh","Sources","AI settings","Methodology"], label_visibility="collapsed")
st.sidebar.caption("Student prototype · Evidence must be reviewed")
{"Radar":radar_page,"Company workspace":company_page,"Signal inbox":inbox_page,"Refresh":refresh_page,"Sources":sources_page,"AI settings":settings_page,"Methodology":methodology_page}[page]()

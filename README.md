# Orange Business Innovation Radar V2

An AI-powered innovation radar that transforms public market signals into evidence-backed, scored, and actionable business opportunities.

Some sneak peak before the technical part of the description !
<img width="1280" height="579" alt="image" src="https://github.com/user-attachments/assets/5a0f47ca-5d49-4bf8-8307-0dde78b7176f" />

<img width="1280" height="594" alt="image" src="https://github.com/user-attachments/assets/7de4e9a0-24ab-45da-816d-aa82f672e0f8" />

<img width="800" height="911" alt="image" src="https://github.com/user-attachments/assets/38830517-6693-4d43-8df6-a495612041f8" />

Business-facing innovation radar built in pure Python with Reflex. The application is powered by the team research pipeline in `Pipelineteamfile/`.

## Start

Requirements: Git, Python 3.11 or newer, and Node.js.

Install Node.js from the official website: [nodejs.org/en/download/current](https://nodejs.org/en/download/current). Reflex uses Node.js for the generated frontend. Verify both runtimes with `python --version` and `node --version` before starting.

Windows:

```powershell
.\start.bat
```

macOS:

```bash
chmod +x start.sh start.command
./start.command
```

Linux:

```bash
chmod +x start.sh
./start.sh
```

Reflex starts the frontend at `http://localhost:3030` and the Python backend at `http://127.0.0.1:8031`.

Keep the `start.bat` window open while using the application. If startup fails, the window now stays open and displays the error instead of closing immediately.

## Configuration

Copy `.env.example` to `.env` and set the server credentials:

```text
NAVY_API_KEY=...
NAVY_BASE_URL=https://api.navy/v1
NAVY_MODEL=gpt-5.6-luna
SEARXNG_URL=http://localhost:8888
```

Credentials remain server-side and are not entered in the business interface.

After entering a provider key in Settings, select `Activate session`. Saving settings stores non-secret preferences; activation keeps the key in the active Reflex session so Radar update, company processing and reports can use it. The UI shows `Provider ready` without displaying or persisting the key.

Report settings distinguish `Research queries per business report` from `Results per search`. The first controls how many different questions the planning pass may ask; the second controls how many source results each question returns.

The report's source and query trail is collapsed by default. Business readers can expand it when they want to audit the research without facing a long list of URLs first.

## Architecture

Two top-level parts:

- **`Pipelineteamfile/`** the authoritative data pipeline. Collects real institutional evidence, classifies it against a closed business taxonomy, and aggregates it into opportunity spaces. Owns its own SQLite database (`Pipelineteamfile/data/articles.db`).
- **`radar_v2/`** the Reflex (Python) web application. Reads that same database and invokes the pipeline as a controlled subprocess; it never writes classifications or opportunity spaces directly.

| Path | Purpose |
| --- | --- |
| `Pipelineteamfile/` | Collectors, ML gate, classifier, taxonomy, source auditor and PDF reports |
| `Pipelineteamfile/run_radar.py` | The 5-stage pipeline entry point (see below) |
| `radar_v2/services/team_repository.py` | Read adapter over pipeline opportunity/evidence data |
| `radar_v2/services/pipeline_runner.py` | Controlled subprocess runner for the pipeline |
| `radar_v2/services/attractiveness.py` | The scoring model (see below) |
| `radar_v2/services/explanations.py` | "Why hot now" / "why this matters" / "recommended move" |
| `radar_v2/services/extension_store.py` | Company workspace, custom sources and product reports |
| `radar_v2/state.py` | Reflex application state and event handlers |
| `radar_v2/components/` | Responsive design system and navigation |
| `radar_v2/pages/` | Business product pages |
| `docs/` | Technical architecture and rebuild notes |
| `docs/COMPANY_WORKSPACE.md` | Company selection, processing, context and Settings behavior |
| `NAVY_AGENT_PROMPTS.md` | Every prompt sent to the LLM across the pipeline and app, verbatim |

Focused discovery and custom source records enter only through the pipeline's `articles` boundary. They still pass through corpus selection, ML filtering, taxonomy classification and opportunity aggregation like any other source.

### The data pipeline, in detail

Sources: **TED** (EU procurement notices), **CORDIS** (EU research/innovation grants), **OCDS UK** and **OCDS Ukraine** (procurement) all live public APIs, collected across 14 fixed verticals. RSS and Google News also exist as source types; Google News is currently paused.

`run_radar.py` runs 5 stages end to end:

1. **Collect** TED, CORDIS and OCDS collectors run per vertical.
2. **Select corpus** rebuilds a balanced classification pool from scratch each run (TED-backbone, CORDIS/OCDS fill, RSS backfill; recent/1-year/5-year mix), up to 600 articles per vertical.
3. **ML noise filter** a locally trained multilingual-embedding + Logistic Regression gate scores articles for relevance; skipped until enough prior labels exist to train it.
4. **Classify** every pending article is sent to the LLM once, with **no cap**: a full update classifies the entire pending pool. TED, OCDS and CORDIS get their signal type and geography mechanically from the record itself (no LLM call, no cost) only RSS/Google News need the model for those two fields. Every source still gets its taxonomy match (business use case × technology) from the model. See `NAVY_AGENT_PROMPTS.md` for the exact prompts.
5. **Summarize** writes a run summary and recomputes opportunity spaces (Vertical × Use Case × Technology triples).

**Taxonomy** (`Pipelineteamfile/opportunity_classifier/config/taxonomy.json`) is closed-vocabulary: fixed use cases, technologies, 6 business domains, and a weighted persona table. The classifier is instructed to never invent an id null is a valid answer.

**Signal types** (6, closed): `buying_signal`, `regulation`, `proof_signal`, `competitor_move`, `market_trend`, `tech_maturity`, with a fixed tie-break priority in that order.

### Scoring model (`radar_v2/services/attractiveness.py`)

Three independent outputs per opportunity space, never blended into one number:

- **Attractiveness score (0-100)** a weighted sum of market signal strength (35%), source credibility (24%), evidence quality (24%) and novelty & momentum (18%). A missing component is excluded and the remaining weights rescaled, never counted as zero.
- **Orange Fit / right-to-win score (0-100)** standalone, never enters the Attractiveness sum. Matches a space against Orange's own selected priority use cases/technologies (Company tab), falling back to a business-domain coverage proxy while nothing is configured.
- **Now / Next / Later horizon** deadline-driven (nearest real tender-close or project-end date in the evidence), independent of both scores above.

"Why hot now", "why this matters" and "recommended move" (`radar_v2/services/explanations.py`) are all composed deterministically from typed clauses already in the database no LLM call at render time.

## Product Settings

The Settings page configures:

- AI provider base URL
- Model
- Responses API or Chat Completions mode
- Session-only provider key
- SearXNG or Tavily discovery
- SearXNG URL
- Session-only Tavily key
- Search depth and result count

Non-secret preferences persist in `data/product.db`. Keys remain in the active browser session or server environment.

## Company Knowledge

The company workspace supports isolated and combined processing:

1. Upload company files.
2. Select one or more documents.
3. Add an optional processing focus, such as revenue, margin, market priorities or a target year.
4. `Process selected separately` uses one independent AI request per document and stores summaries under `Documents/<company>/processed/`.
5. When two or more documents are selected, `Create combined company report` appears and synthesizes those selected documents in one dedicated request.
6. Processing selection and prompt inclusion are separate controls.
7. Processed summaries default to `Use as company guidance = on` with destination `Everywhere`.
8. Users can disable any summary or route it to Opportunity mapping, Scoring & fit, Business reports, or Everywhere.

Upload selection is previewed before files are saved. Upload and processing actions display progress, current file, completion messages and per-document status.

Discovery results are saved in the extension database and restored when the Discovery page is opened again. Report selection is also persistent across the Opportunities and Reports pages: choosing an opportunity carries its ID to the report workspace, where `Generate focused report` performs the actual bounded operation instead of sending the user back in a navigation loop.

The focused report flow is active: the first AI request creates varied research queries from the opportunity and current evidence, the configured search provider retrieves additional sources, and the second AI request synthesizes the report with those sources. The report and its search trace are persisted after completion.

## Pipeline Bootstrap

The ML gate learns from prior team-classifier labels. On a fresh database:

1. A bounded first update collects and classifies an initial sample while retaining all selected records.
2. Once both useful and `no_match` labels exist, the next update trains the team embedding/Logistic Regression gate.
3. Future updates use that gate before classification.

Until the team database contains opportunity spaces, the UI displays demonstration records. They disappear automatically once real team pipeline output exists.

The first completed bootstrap collected 5,794 institutional records. A bounded 100-record team classification sample created 9 useful and 91 no-match labels. The original team multilingual embedding and Logistic Regression stage then scored all 5,794 records, retaining 4,849 and deprioritising 945 for future classification cycles.

Use `/refresh` or **Radar update** in the sidebar to run the complete team pipeline. The Update scope panel previews the current corpus, ML-scored records and how many articles are pending classification before launch. There is no cap: a full update always classifies the entire pending pool.

A full update legitimately takes a long time collection alone across all sources and verticals can run for tens of minutes before classification even starts, and classification adds more on top. It runs as its own background process, independent of the browser session that started it.

## Project Timeline

This project was completed over approximately 9–10 working days, including the initial brainstorming and design sessions. The hands-on implementation took approximately 6–7 coding days. The brainstorming days were essential because the team first had to define what the innovation radar should be, how it should work, and how its results should support business decisions.

- **Week 1 — rapid prototyping:** The team used Streamlit to build a functional prototype quickly, test as many features as possible, and create a working “scarecrow” of the complete product.
- **Week 2 — final product:** The prototype was reworked into the final application. The UI was rebuilt with Reflex because Streamlit was effective for rapid prototyping but less suitable for the interactive, user-friendly product experience the team wanted to deliver.

## Team and Contributions

- **IkarusV-Imad — Team Lead:** Led the product's technical direction and integration. During the first-week prototype phase, IkarusV created the UI and core product structure. During the second week, they rebuilt the interface as a new interactive Reflex UI, troubleshot integration issues, combined the team's scripts into one application, and added features and compatibility patches so that every component worked cohesively. The Company Workspace was also designed and implemented by IkarusV.
- **Iness — Project Manager:** Managed team coordination and contributed the web-search functionality.
- **Dan — Pipeline Tech Lead:** Developed the pipeline scripts and the information-gathering workflow. Dan also contributed to the scoring system.
- **Alex — Researcher and Business Forensics:** Led business research and forensic analysis and contributed to the scoring system.

## Further Help and Documentation

For help, implementation questions, or possible next steps, contact [IkarusV](https://github.com/IkarusV) or another member of the project team.

For anyone who needs to understand, rework, or extend the pipeline:

- [`Cobalt_Data_Society_Innovation_Radar_Explained.pdf`](Cobalt_Data_Society_Innovation_Radar_Explained.pdf) documents and explains the pipeline.
- [`NAVY_AGENT_PROMPTS.md`](NAVY_AGENT_PROMPTS.md) contains the complete prompt inventory, the pipeline or application step associated with each prompt, and supporting information about how each prompt is used.

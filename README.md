# Orange Business Innovation Radar V2

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

`Pipelineteamfile/` is the authoritative research pipeline:

```text
TED + CORDIS + OCDS
→ balanced classification corpus
→ multilingual embedding / Logistic Regression noise gate
→ taxonomy classification
→ Vertical × Use Case × Technology opportunity spaces
→ PDF reports
```

The V2 application reads the team database and invokes the team orchestrator. Product extensions use a separate database and do not overwrite team classifications or opportunity spaces.

Focused discovery and custom source records enter only through the team `articles` boundary. They still pass through team corpus selection, ML filtering, taxonomy classification and opportunity aggregation.

| Path | Purpose |
| --- | --- |
| `Pipelineteamfile/` | Team collectors, ML gate, classifier, taxonomy and PDF reports |
| `radar_v2/services/team_repository.py` | Read adapter over team opportunity/evidence data |
| `radar_v2/services/pipeline_runner.py` | Controlled subprocess runner for team pipeline |
| `radar_v2/services/extension_store.py` | Company workspace, custom sources and product reports |
| `radar_v2/state.py` | Reflex application state and event handlers |
| `radar_v2/components/` | Responsive design system and navigation |
| `radar_v2/pages/` | Business product pages |
| `docs/` | Technical architecture and rebuild notes |
| `docs/COMPANY_WORKSPACE.md` | Company selection, processing, context and Settings behavior |

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

Use `/refresh` or **Radar update** in the sidebar to run the complete team pipeline. The Quick start panel previews the current corpus, ML-scored records and estimated classifier requests before launch. The cap limits articles sent to the team classifier; it does not replace collection, corpus selection, ML filtering, taxonomy classification or opportunity aggregation.

The first run can take time because the team collectors cover all configured sectors and historical windows before classification starts. The live progress area identifies the current collection, corpus, ML, classification and report-preparation stage.

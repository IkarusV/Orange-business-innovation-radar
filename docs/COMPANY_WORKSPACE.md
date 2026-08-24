# Company Workspace

## User Flow

The Company page has four separate concerns:

1. **Upload selection**: files chosen in the browser are listed under the drop area before the user clicks `Add selected documents`.
2. **Processing selection**: the round selection control beside a library item chooses which raw files will be processed next.
3. **Prompt inclusion**: after processing, `Use this summary as company guidance` controls whether the summary can enter any AI context.
4. **Context destination**: an enabled summary can target `Opportunity mapping`, `Scoring & fit`, `Business reports`, or `Everywhere`.

The processing instruction applies to the current action. Examples:

```text
Focus on 2026 revenue, margin pressure and investment priorities.
```

```text
Extract strategic partnerships, past deployments and capability gaps.
```

## Processing Rules

- Uploading stores raw files and does not call the AI.
- One selected document produces one isolated summary request.
- Several selected documents produce several independent summary requests.
- The current file, item count, progress bar and completion message are shown while processing.
- A processed document defaults to enabled context with destination `Everywhere`, matching the earlier prototype behavior.
- Users can disable context without deleting the raw file or summary.
- A combined company report button appears only when at least two documents are selected.
- The combined report intentionally sends selected documents together in one separate request.

Raw files use:

```text
Documents/<safe-company-name>/
```

Processed summaries and reports use:

```text
Documents/<safe-company-name>/processed/
```

`pathlib` and sanitized names keep the layout portable across Windows, macOS and Linux. Duplicate names receive suffixes instead of overwriting existing files.

## Pipeline Context

The authoritative `Pipelineteamfile` pipeline receives only selected processed summaries. The context is prefixed and segmented as:

```text
ADDITIONAL COMPANY INFORMATION (guidance, not a restriction):
[OPPORTUNITY MAPPING]
[SCORING & FIT]
[ALL COMPANY CONTEXT]
```

`Business reports` summaries are not inserted into the team classifier context. They remain available for report-oriented company knowledge. `Everywhere` summaries are included in opportunity mapping and fit guidance.

The context file is bounded by document count and character limits and is written to the ignored team data directory only for the duration of a pipeline invocation.

## Tactile Feedback

- Uploads show selected filenames before commit.
- Uploads show current filename, progress and completion.
- Summary processing shows current filename, `n of total`, progress and final count.
- Combined report processing shows a dedicated progress state.
- Buttons disable while the corresponding action is active.
- Toasts report success or missing selection/provider configuration.

## Settings

The Settings page contains the technical controls intentionally kept out of the business views:

- AI-compatible base URL
- AI model
- Responses or Chat API mode
- Current-session AI key
- SearXNG or Tavily
- SearXNG URL
- Current-session Tavily key
- Search depth and result limit

Non-secret preferences persist in `data/product.db`; API keys remain in Reflex state or environment variables.

## Sector Selector

Discovery and priority-source collection use the complete authoritative 14-sector list from:

```text
Pipelineteamfile/ted_collector/config/mapping.yaml
```

They do not derive sectors from currently populated opportunity spaces. A fresh database can therefore search every team sector even before the classifier has produced an opportunity in that sector.

## Porting Notes

- `radar_v2/services/extension_store.py`: extension database, profiles, documents and settings.
- `radar_v2/services/knowledge.py`: extraction, isolated summaries and combined reports.
- `radar_v2/services/pipeline_runner.py`: selected company-context export and team subprocess invocation.
- `radar_v2/state.py`: Reflex event handlers and progress fields.
- `radar_v2/pages/company.py`: business workspace UI.
- `radar_v2/pages/settings.py`: provider UI.
- `radar_v2/services/team_repository.py`: read-only team adapter and external article boundary.

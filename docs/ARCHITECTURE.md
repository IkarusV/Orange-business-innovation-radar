# V2 Architecture

## Authority

`Pipelineteamfile` is the only classification and opportunity pipeline. V1 code is not used as an alternative pipeline.

The team owns:

- TED, CORDIS and OCDS collection
- Article storage and deduplication
- Balanced corpus selection
- Multilingual sentence embeddings
- Logistic Regression noise filtering
- Navy Responses API classification
- Team taxonomy
- Opportunity-space aggregation
- Statistics and opportunity PDF reports

The V2 application adds product capabilities around that core:

- Reflex business interface
- Company profile and document library
- Custom source watchlist
- External market discovery
- Report library and interactive views
- Pipeline run status

## Extension Integration Boundary

Focused discovery and priority-source pages never create classifications or opportunity spaces. When the user promotes external evidence, V2 creates a team `Article` with `source_type="web_discovery"`, an explicit sector, source URL and excerpt. The team `classification_pool`, ML gate, taxonomy classifier and `opportunity_spaces` aggregation then process it during the next standard update.

This preserves one opportunity pipeline while allowing product-level source expansion.

Extension records live in `data/product.db`. Team records remain in `Pipelineteamfile/data/articles.db`.

## Pages

- `/`: executive portfolio overview
- `/opportunities`: filterable opportunity portfolio
- `/opportunities/[opportunity_id]`: focused business/evidence view
- `/company`: company profile and reference library
- `/sources`: institutional coverage and priority sources
- `/discovery`: focused web discovery
- `/reports`: team PDFs and future focused reports
- `/refresh`: bounded full team pipeline run
- `/help`: concise business terminology

## Fresh Database Bootstrap

The ML model is supervised by historical LLM labels. The orchestrator now creates its existing schemas before snapshots and checks for at least five useful and five no-match labels before training. If unavailable, the first run retains all selected evidence, classifies the bounded sample, and seeds learning data. The next qualifying run trains and applies the original ML gate.

No ML algorithm, embedding model, threshold policy, classifier prompt, taxonomy or collector was replaced.

## Company Context

The application writes a bounded controlled context file under the team data directory and passes it through the classifier's existing `--client-context` option. Browser-provided filesystem paths are never accepted.

Raw uploads are not sent to the classifier. Each selected document is first processed independently through the configured AI provider, producing one stored JSON summary per document. An optional user focus instruction is scoped to that processing action. A combined company report is a separate explicit action available only when at least two documents are selected. The classifier context contains only selected processed summaries within the document/character bounds.

Document state is intentionally split:

- `selected`: raw document chosen for the next processing/report action
- `context_enabled`: processed summary is allowed into company guidance
- `context_scope`: Opportunity mapping, Scoring & fit, Business reports, or Everywhere

New processed summaries default to Everywhere. Users can disable context inclusion without deleting the summary. The classifier context begins with `ADDITIONAL COMPANY INFORMATION (guidance, not a restriction):` and labels each summary by its destination. Business-report-only summaries are excluded from classifier prompts.

Discovery and priority-source selectors load all 14 verticals from the authoritative TED mapping rather than deriving sectors from currently populated opportunity spaces.

## Provider Settings

`app_settings` stores non-secret provider preferences. `RadarState` holds provider and Tavily keys for the current Reflex session. Settings feed three bounded consumers:

- Company document summaries and combined reports
- Focused Discovery through SearXNG or Tavily
- The team classifier subprocess through `NAVY_BASE_URL`, `NAVY_MODEL` and `NAVY_API_KEY`

No alternate classifier is introduced; the team pipeline remains authoritative.

Focused-report search planning has its own persisted `max_research_queries` setting, separate from results per query. The planner receives that value and may create between 1 and 20 varied research queries; the report page keeps the resulting query/source trail collapsed by default through the native Radix accordion so business readers see the decision first.

Saved report payloads are transformed into business-facing display models before rendering. The Reports page presents headline metrics, executive summary, recommendation, market pulse, financial picture, company fit, risks, roadmap, and research trail. Comparable numeric market ranges receive a chart; percentages, mixed currencies and unparseable values stay as evidence cards. Raw JSON remains stored for audit and portability but is not shown to business users.

## Current Bootstrap Result

The initial institutional collection produced 5,794 records across TED, CORDIS and OCDS. The first 100 team-classifier labels produced 9 useful classifications and 91 no-match labels, satisfying the minimum two-class bootstrap condition.

The original team ML stage then completed with:

- `sentence-transformers/paraphrase-multilingual-mpnet-base-v2`
- 5,794 embedded records
- 768 embedding dimensions
- Logistic Regression candidate selection across `C=0.1`, `1.0`, and `10.0`
- Final threshold `0.07535376399755478`
- 4,849 records retained
- 945 records deprioritised

These results persist in `ml_noise_scores` and are consumed by subsequent team classifier runs.

The `/refresh` page is the product entry point for the complete update. Its Quick start preflight shows the current classification pool, already scored records, estimated article-to-classifier calls and the user-selected cap. Starting the action invokes `Pipelineteamfile/run_radar.py`; it does not run a parallel V2 pipeline. Stage progress is streamed from the team orchestrator and the dashboard reloads the resulting opportunity spaces after completion.

The page also displays the session provider state. Settings save non-secret preferences separately from key activation; the update can run only when the session shows `Provider ready`.

## Presentation Boundary

Technical methodology, model configuration and implementation limitations belong in repository documentation. The product UI uses concise business language and exposes original evidence links, portfolio fit, confidence, timing and recommended actions.

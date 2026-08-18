# Classification and Source Audit

This document explains what every radar label means, how code produces it, which inputs come from AI, and what still requires human validation. It describes version `1.0-proposed`; it is not an Orange-approved methodology.

## Responsibility Map

| Displayed value | Input origin | Code action | Human trust requirement |
| --- | --- | --- | --- |
| Vertical | AI extraction | Required and stored | Confirm wording and relevance |
| Use case | AI extraction | Required and stored | Confirm it is specific and commercially meaningful |
| Technology | AI extraction | Required and stored | Confirm maturity and correct terminology |
| Signal type | AI extraction | Reject if outside the allowed taxonomy | Confirm the source actually supports the type |
| Urgency, 0-10 | AI extraction | Clamp to 0-10 | Confirm trigger, deadline, or buyer activity |
| Now/Next/Later | Python | Deterministic rule from urgency and signal type | Confirm the AI inputs before trusting the result |
| Factor scores, 0-10 | AI extraction | Clamp to 0-10 | Inspect each rationale and evidence |
| Attractiveness, 0-100 | Python | Weighted arithmetic | Formula is reproducible; inputs remain judgments |
| Right to win, 0-100 | Python | Weighted arithmetic | Requires Orange capability/customer evidence |
| Confidence, 0-100 | Python | Count/diversity/quality formula | Quality input and source independence need review |
| Radar/Watchlist | Python | Three publication gates | Thresholds are team proposals |
| Why hot now | AI extraction or seed | Stored with topic | Reject unsupported factual statements |
| Why it matters | AI extraction or seed | Stored with topic | Confirm Orange relevance separately |
| Next action | AI extraction or seed | Stored with topic | Human owner should make it concrete and feasible |

## Watchlist and Radar

`Watchlist` means the topic is potentially useful but lacks enough evidence to be treated as a promoted radar topic. It is not a rejection and is not derived from attractiveness.

The current code promotes an opportunity to `Radar` only when every gate passes:

1. Evidence records: at least 2.
2. Independent source domains: at least 2.
3. Confidence: at least 45/100.

The values are configured in `config/scoring.json`. The decision occurs in `radar/scoring.py::score_opportunity`. The UI recomputes and displays each gate through `radar/scoring.py::publication_checks`.

These are demonstration thresholds. They should be calibrated against examples accepted and rejected by Orange stakeholders.

## Confidence

The current confidence formula is:

```text
min(evidence_count, 4) * 10
+ min(independent_domain_count, 3) * 12
+ round(evidence_quality_0_to_10 * 2)
+ 4 when human-reviewed
```

The result is capped at 100.

Example with two evidence records, one domain, and quality 8/10:

```text
20 + 12 + 16 = 48/100
```

This explains the Government seed card. Both records are Orange-owned, so they count as one ownership/domain family in the seed. It remains on the watchlist even with high attractiveness.

Limitations:

- Evidence quality is currently an AI-proposed factor.
- Domain diversity uses hostnames for live web sources.
- Two hostnames may repeat a syndicated article or the same vendor claim.
- Four weak sources can contribute more count points than one primary legal source.
- The review bonus exists in code but no review workflow currently activates it.

## Time Horizon

The horizon is urgency, not opportunity value.

### Now

Python assigns `Now` when:

```text
urgency >= 8
AND signal_type IN (regulation, buying_signal, proof_signal)
```

Intended meaning: there is a near-term trigger such as a compliance deadline, active procurement, named buyer activity, contract, production deployment, or measured proof.

### Next

Python assigns `Next` when urgency is at least 5 but the strict `Now` condition does not pass. A high-urgency market trend alone is therefore `Next`, because forecasts and general momentum are weaker timing evidence than a deadline, buyer, or deployment.

### Later

Python assigns `Later` when urgency is below 5. Intended meaning: the signal may be credible, but the demand trigger, maturity, or evidence is weak.

The AI is asked to infer `urgency` and `signal_type` from an article. `radar/pipeline.py::analyze_article` validates and clamps those values, then always calls `radar/scoring.py::horizon_from_signal`. The AI can no longer directly choose the final horizon label.

The three seeded examples predate live extraction and are explicitly marked as seed classifications. Their labels demonstrate the UI and must not be presented as externally validated conclusions.

## Attractiveness

```text
30% market signal strength
+ 20% source diversity
+ 20% evidence quality
+ 15% novelty and momentum
+ 15% Orange strategic relevance
```

Each factor is proposed by AI from 0 to 10. Python clamps values to 0-10, applies fixed weights, and multiplies by 10. The arithmetic is deterministic; the judgments are not.

Expected semantics:

| Factor | Intended question |
| --- | --- |
| Market signal | Is there specific and substantial demand, investment, procurement, or regulation? |
| Source diversity | Is the claim repeated across independent source types and owners? |
| Evidence quality | Is the source primary, dated, specific, named, and quantified? |
| Momentum | Is evidence recent and increasing rather than static? |
| Strategic relevance | Does it connect to Orange Business growth capabilities and target verticals? |

Current mismatch: `source_diversity` is both an AI factor and a separately counted publication gate. A stronger version should calculate this factor entirely from stored evidence instead of asking AI.

## Right to Win

```text
30% offering or asset fit
+ 25% customer overlap
+ 25% reference cases
+ 20% skills and partner readiness
```

This exact formula is a team proposal, not a confirmed Orange formula. It should eventually use Orange-owned structured records such as offering match, CRM overlap, opportunities, pipeline, references, people capability, and partners. The current live extractor can propose values from one public article, which is too weak for production use. Treat this score as a hypothesis until connected to an Orange capability evidence table.

## Source Pipeline

## Company and Partner Context

The Company workspace stores one active company profile: name, priority geography, website, and a free-text strategic/partner instruction. It also stores extracted text from uploaded or downloaded PDF, PPTX, DOCX, TXT, Markdown, CSV, JSON, and HTML documents.

Future AI analysis receives a bounded company context containing the profile and newest reference documents. The prompt explicitly allows direct and external delivery models. Partner dependence should be described as a role or capability gap, not automatically scored as unattractive.

Document processing limits:

- Extraction occurs locally; only extracted text is sent as model context.
- Individual stored document text is capped at 80,000 characters.
- Combined AI company context is capped at 24,000 characters.
- Scanned/image-only PDFs require OCR and are currently rejected.
- URLs are downloaded once; websites are not recursively crawled.
- Existing opportunities are not automatically rescored when the company profile changes.
- Data is not fully isolated per company in this version. The active profile changes future analysis, while existing records remain in the shared database.

### Registration

Default sources live in `config/sources.json` and are synchronized into SQLite during application startup. The Sources page adds another enabled source directly to the SQLite `sources` table.

The form currently expects an RSS or Atom URL. It does not accept a normal article URL and does not discover feeds automatically.

### Collection

`radar/ingestion.py::fetch_source` uses `feedparser` to request each enabled feed. For each entry it stores:

- Feed source identifier
- GUID
- Title
- Canonical link
- Published or updated date
- Feed-provided content or summary, limited to 12,000 characters
- Fetch timestamp

The collector currently reads up to 30 entries per source per refresh.

### Normalization and Deduplication

- HTML is stripped from title and content.
- Repeated whitespace is collapsed.
- URL scheme and hostname are lowercased.
- URL query strings and fragments are removed.
- SQLite rejects duplicate article GUIDs.
- SQLite rejects duplicate evidence using the same opportunity and source URL.

This is exact deduplication, not semantic deduplication. Rewritten or syndicated copies can remain separate.

### AI Processing

Pending articles are processed newest first. The application sends the source name, date, URL, title, and feed summary to the configured model. The model returns structured JSON. Required fields and taxonomy are checked before storage.

The application does not currently fetch the complete linked article page. A feed containing only a short excerpt may therefore produce incomplete analysis.

### Evidence and Opportunity Grouping

One relevant article produces one evidence claim. The opportunity key is a slug generated from AI-proposed vertical, use case, and technology. Exact normalized matches join the same opportunity. Similar wording can create separate opportunities; no semantic merge is currently performed.

## Enforced Guardrails

- Required opportunity fields must be non-empty.
- Signal type must be one of six configured values.
- Factor values and urgency are clamped to valid ranges.
- Score arithmetic is deterministic Python.
- Horizon assignment is deterministic Python.
- Duplicate GUIDs and duplicate opportunity/source URL evidence are blocked by SQLite.
- Original source URLs remain attached to evidence.
- API credentials are not persisted by application code.

## Intended but Not Fully Enforced Guardrails

- External evidence establishes attractiveness.
- Orange-owned evidence establishes right to win.
- Sources counted as independent should have separate ownership and original reporting.
- Every factual narrative statement should cite evidence.
- AI factor rationales should be checked against claims.
- A human should approve publication to the radar.

These are methodology requirements, not current guarantees. Presenting them separately prevents overclaiming what the code does.

## Recommended Audit Procedure

For every topic selected for presentation:

1. Open every source URL and confirm the stored claim.
2. Confirm publication date and event date are not confused.
3. Confirm sources are independent and not syndicated copies.
4. Confirm signal type and urgency with written reasons.
5. Recalculate the deterministic labels from the stored inputs.
6. Separate external attractiveness evidence from Orange right-to-win evidence.
7. Replace generic next actions with an owner, target, and validation output.
8. Mark unresolved gaps and keep the topic on the watchlist.

## API Budget, Batching, and Recovery

The original prototype made one API request per article. In ideal conditions, 96 requests should therefore have handled approximately 96 articles. In `auto` endpoint mode, the first unsupported `/responses` call could add a fallback `/chat/completions` request, reducing the ideal count slightly. Only 19 articles were marked processed in the interrupted run because success required valid JSON plus successful validation/storage; all other errors were previously swallowed. No new evidence was stored in that run.

The bounded implementation now uses these defaults:

- 20 articles maximum per run.
- 5 articles per AI batch.
- Approximately 4 ideal API requests per default run, or 0.2 request per article.
- 5 total API requests as a hard default budget.
- 10 requests per minute maximum, enforced by at least 6 seconds between requests.
- 2 attempts maximum per article before automatic exclusion.

Endpoint fallback counts against both the total request budget and the RPM limiter. The HTTP client enforces these limits, not only the UI.

Every raw result is saved to SQLite `analysis_candidates` before validation. Candidate states include `captured`, `promoted`, `irrelevant`, `validation_failed`, `missing_from_response`, and `request_failed`. Article attempt counts and last errors are also stored. Accepted evidence and opportunities are committed individually, so a later batch or application interruption does not remove earlier accepted results.

Runs and progress events persist in `runs` and `run_events`. Application startup converts stale `running` rows to `interrupted`. The UI displays live collection, selection, batch, rate-limit cooldown, scoring, completion, and failure events.

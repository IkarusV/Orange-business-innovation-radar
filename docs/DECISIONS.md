# Decision Log

## 2026-08-18: Opportunity unit

Use `Vertical x Use Case x Technology`, not broad themes such as AI or cybersecurity. This makes results actionable and filterable.

## 2026-08-18: Evidence separation

External independent sources support market attractiveness. Orange-owned documents support strategic relevance and right to win. Vendor claims are supplementary. This prevents circular validation.

## 2026-08-18: Scoring ownership

AI returns structured factor assessments and rationales. Python applies fixed weights. Totals are reproducible and cannot change because the model formats arithmetic differently.

## 2026-08-18: Right-to-win status

The exact formula is labelled `proposed`. The source briefing names CRM overlap, opportunities, pipeline value, offering match, and people capability, but does not confirm the draft formula.

## 2026-08-18: Watchlist threshold

A topic remains on the watchlist below two evidence items, two source domains, or 45 confidence. Thresholds are configurable in `config/scoring.json`.

## 2026-08-18: Storage

Use SQLite for sources, articles, evidence, opportunities, score snapshots in opportunity JSON, and runs. It is local, inspectable, portable, and sufficient for the demo.

## 2026-08-18: AI compatibility

Support OpenAI-compatible Responses and Chat Completions APIs behind one adapter. Credentials come from environment variables or UI session state and are never persisted.

## 2026-08-18: Source scope

Reuse D's reviewed RSS work as an input, while keeping the production registry in structured JSON/SQLite. Add priority sources from the UI. Future Tavily or web-search connectors can implement the same normalized article contract.

## 2026-08-18: Seed data

Seed three visibly provisional opportunities so the complete product can be demonstrated without paid API calls. Local Orange files count as internal evidence, not independent validation.

## 2026-08-18: Company and partner context

The radar must not assume every opportunity is delivered directly by Orange Business. The active company prompt and documentation may support direct, partner-led, ecosystem-led, reseller, integrator, or capability-gap opportunities. External involvement is not automatically a negative factor; the output must explain the company's credible role, dependency, and next validation step.

The current schema supports one active company context. Full multi-company isolation requires adding a company identifier to sources, articles, opportunities, evidence, and runs; this is explicitly not claimed yet.

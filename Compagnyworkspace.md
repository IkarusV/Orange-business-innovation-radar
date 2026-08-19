# Company Workspace Portability Guide

## Goal

Provide a reusable company knowledge workspace for the innovation radar. A user can keep many raw company documents without sending all of them to every AI request. Users explicitly process selected documents into compact summaries, create combined reports when cross-document synthesis is wanted, and choose which processed files enter which pipeline stage.

This module is company-configurable. It supports direct, partner-led, ecosystem, reseller, integrator, and capability-gap opportunity analysis. Company information guides vocabulary and fit; it must not prevent external discovery or turn company PR language into independent market evidence.

## Original User Request

The requested behavior was:

> Flesh out the company workspace functionally. Uploading many documents must not append every raw document to every article request because token costs can explode and irrelevant numbers, PR language, or legal text can bias analysis. Store raw documents under a company-named folder. Provide a real searchable, paginated library and a refresh action for files manually added to the folder. Let users select documents to process. One company document must equal one isolated API call so information from another document cannot leak into its summary. Save processed text summaries in a `processed` child folder. Let users select processed documents for prompt context and choose the pipeline stage where each is injected, including an `all` option. Prefix this context as additional company guidance, not a restriction. Support an explicit combined-report action for selected documents; reports may synthesize and compare multiple sources and should be named `report_<company>_<number>` with user rename support. Add configurable maximum documents for processing and context. Document the files, logic, goals, and prohibited behavior so the module can be ported to another prototype.

## Files

| File | Responsibility |
| --- | --- |
| `radar/library.py` | Filesystem library, indexing, isolated processing, reports, rename, stage assignment, bounded context |
| `radar/company.py` | PDF/PPTX/DOCX/text extraction, URL download, base company context |
| `radar/db.py` | `library_documents` index and persistent `knowledge_settings` limits |
| `app.py` | Company profile, uploads, search, pagination, tabs, processing/report/context controls |
| `radar/pipeline.py` | Injects selected processed context into named stages |
| `.gitignore` | Excludes private/local `Documents/` contents from Git |

## Filesystem Layout

```text
Documents/
└── <safe_company_name>/
    ├── annual_report.pdf
    ├── strategy.pptx
    ├── customer_notes.docx
    └── processed/
        ├── annual_report.processed.txt
        ├── strategy.processed.txt
        └── report_<company>_1.txt
```

Company and filenames are sanitized to portable ASCII-compatible names. Duplicate uploads receive `_2`, `_3`, and later suffixes rather than overwriting files. `pathlib.Path` is used for Windows, macOS, and Linux compatibility.

`Documents/` is ignored by Git because company files may be private. The SQLite database is also ignored. A production deployment should replace local disk with access-controlled object storage and a shared database.

## Database Model

### `library_documents`

- `company_name`: owning library
- `name`: current user-visible filename
- `original_name`: uploaded source filename
- `raw_path`: local raw file path
- `processed_path`: local summary/report path
- `source_type`: MIME/extension or `report`
- `source_url`: optional original URL
- `raw_chars`: extracted raw character count
- `processed_chars`: summary/report character count
- `status`: `raw`, `processed`, or `failed`
- `stages_json`: selected context stages
- `error`: processing failure
- timestamps

### `knowledge_settings`

- Maximum independent documents processed per UI action
- Maximum processed documents injected per stage
- Maximum total company-context characters per article batch
- Maximum documents in a combined report
- Maximum source characters in a report request

## Raw Ingestion

Uploads and direct documentation URLs are saved to `Documents/<company>/`. Extraction validates that the file contains readable text, but no AI call occurs during ingestion.

Supported types:

- PDF
- PPTX
- DOCX
- TXT
- Markdown
- CSV
- JSON
- HTML

Image-only/scanned PDFs need OCR and are rejected for now.

The refresh action scans the company folder and indexes supported files manually copied there. It does not recursively index `processed/` as raw input.

## Independent Processing

`process_document()` reads exactly one raw document and makes exactly one model call. Its prompt states that the model must summarize only that document and must not import outside facts.

The structured result contains:

- Summary
- Key facts
- Company vocabulary
- Strategic signals
- Opportunities or capabilities
- Risks and unknowns
- Document type

The JSON result is saved as readable UTF-8 text under `processed/`. If five documents are selected, the action uses five calls, subject to the configured maximum and the provider RPM limiter. A document failure is stored without deleting the raw file.

## Combined Reports

Reports are intentionally different from isolated summaries. The selected processed summaries, or raw text when no summary exists, are sent together in one call. The model is instructed to preserve source boundaries, identify repeated themes and contradictions, and separate facts from hypotheses.

Default names are:

```text
report_<company>_1.txt
report_<company>_2.txt
```

Users can rename processed files and reports. Existing filenames are not overwritten.

Reports return:

- Combined report summary
- Repeated themes
- Company vocabulary
- Strategic priorities
- Relevant capabilities
- Contradictions and unknowns
- Source-document list

## Context Selection

Only documents with `status='processed'`, an existing processed file, and a matching stage assignment enter prompts.

Stages:

- `collection`: relevance and evidence interpretation
- `opportunity_naming`: company-resonant opportunity wording
- `scoring`: company fit and right-to-win guidance
- `narrative`: why it matters and next-action language
- `all`: eligible for every stage

The prefix is:

```text
ADDITIONAL COMPANY INFORMATION (guidance, not a restriction):
```

The information should improve company vocabulary, strategic fit, capability recognition, partner logic, and recommendations. It must not suppress external opportunities or be treated as independent evidence of market attractiveness.

The current extraction model returns naming, scoring, and narrative fields in one batch call. To preserve stage semantics without multiplying API calls, the prompt contains separately labelled stage sections. A future multi-agent implementation can pass each section only to its dedicated agent with no database changes.

## Cost Controls

Default limits:

- 5 independent document summaries per action
- 5 processed documents per pipeline stage
- 8,000 company-context characters per article batch
- 10 documents per combined report
- 60,000 source characters per report request

These are editable in the Company workspace and persisted. Existing pipeline controls still enforce total requests and at most 10 RPM.

Raw documents are never repeated in normal article-analysis calls. Processed summaries are truncated by the global context budget. This changes the dangerous pattern from `50 raw PDFs × 20 article requests` to a deliberate up-front processing cost plus bounded reusable summaries.

## Search and Pagination

The UI searches indexed metadata including filename, status, source, and stage assignment. Pagination supports 5, 10, 20, or 50 records per page. Raw and processed views are separate tabs.

This is metadata search, not semantic vector search. A later version can add full-text SQLite FTS or embeddings without changing the filesystem contract.

## What It Must Not Do

- Never append every raw company document to every article prompt.
- Never silently process an unlimited number of files.
- Never combine documents during independent summarization.
- Never overwrite same-named files without warning or a generated suffix.
- Never treat company claims as independent external market evidence.
- Never let company vocabulary prevent novel or partner-led opportunities.
- Never commit private company documents or the local SQLite database.
- Never claim source-grounded certainty when the report contains hypotheses.
- Never recursively crawl an entire company website from one URL.
- Never expose API keys in stored files, prompts, logs, or the library.

## Porting Checklist

1. Copy `radar/library.py` and the extraction helpers from `radar/company.py`.
2. Port `library_documents` and `knowledge_settings` from `radar/db.py`.
3. Add the Company workspace UI sections from `app.py`.
4. Add `Documents/` to `.gitignore`.
5. Inject `library_context(company, stage, max_documents, max_chars)` only where needed.
6. Keep independent summary calls one document at a time.
7. Keep report synthesis as an explicit separate action.
8. Preserve request budgets and RPM enforcement from `radar/ai.py`.
9. Test Windows, macOS, and Linux paths with `pathlib`.
10. Add authentication, authorization, encryption, retention, and remote storage before production use.

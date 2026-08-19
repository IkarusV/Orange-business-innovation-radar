# Orange Business Innovation Radar

Streamlit application that collects open-source signals, extracts opportunity evidence with an OpenAI-compatible model, calculates explainable scores in Python, and stores results in SQLite.

## Start

Requirements: Git and Python 3.11 or newer.

### Windows

Double-click `start.bat` or run:

```powershell
.\start.bat
```

### macOS

On first use, run:

```bash
chmod +x start.sh start.command
./start.command
```

### Linux

```bash
chmod +x start.sh
./start.sh
```

The launchers create `.venv`, install `requirements.txt`, and open Streamlit. Paths are resolved relative to the repository with `pathlib` in Python and script-relative paths in both launchers.

## Configure AI

Use **AI settings** in the app. Credentials stay in the current browser session and are not saved.

For local environment configuration:

```bash
cp .env.example .env
```

Set `RADAR_AI_BASE_URL`, `RADAR_AI_API_KEY`, `RADAR_AI_MODEL`, and `RADAR_AI_MODE`. Never commit `.env` or API keys.

## Run The Pipeline

1. Configure the company and optional documents under **Company workspace**.
2. Review or add RSS/Atom feeds under **Sources**.
3. Configure the provider under **AI settings**.
4. Review **RUN LIMITS** in the sidebar.
5. Select **RUN FULL PIPELINE**.

Safe defaults: 20 articles, 5 articles per request, 5 requests maximum, 10 RPM, and 2 attempts per article.

## Project Map

| Path | Purpose |
| --- | --- |
| `app.py` | Streamlit UI and pipeline controls |
| `radar/ai.py` | Provider adapter, API budget, and RPM limit |
| `radar/ingestion.py` | RSS collection and normalization |
| `radar/pipeline.py` | Batch extraction, validation, scoring, and progress |
| `radar/scoring.py` | Deterministic scores, confidence, and horizons |
| `radar/db.py` | SQLite schema and persistence |
| `radar/company.py` | Company context and document extraction |
| `radar/library.py` | Raw/processed company library, summaries, reports, and stage context |
| `config/prompts.json` | Versioned agent prompts |
| `config/scoring.json` | Weights and Radar/Watchlist thresholds |
| `config/sources.json` | Default feeds |
| `tests/` | Unit and batching tests |
| `docs/` | Decisions, process, and classification audit |
| `Compagnyworkspace.md` | Portable company workspace specification and implementation guide |
| `Aorangeresearch/` | Supplied Orange reference material |
| `DfluxRss/` | Original RSS research module |

Local SQLite data is created at `data/radar.db` and is intentionally ignored by Git. Each clone starts with seeded demonstration hypotheses. AI candidates, errors, runs, and accepted ideas persist locally in that database.

## Modify Safely

- Change prompts in `config/prompts.json`; update their version.
- Change score weights or promotion gates in `config/scoring.json`.
- Add default feeds in `config/sources.json`.
- Keep final arithmetic and horizon assignment deterministic in Python.
- Run tests before pushing:

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
```

On Windows use `.venv\Scripts\python.exe` instead.

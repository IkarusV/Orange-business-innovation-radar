# Orange Business Innovation Radar — MVP

## 1. Installation

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## 2. API key

Copy `.env.example` to `.env`:

```text
TAVILY_API_KEY=tvly-xxxxxxxx
```

Put your real Tavily API key in `.env`.

## 3. Run

```bash
python main.py
```

The prototype creates:

- `innovation_radar.json` — complete machine-readable data + sources
- `innovation_radar.csv` — easy to inspect in Excel
- `innovation_radar.html` — simple presentation page

## 4. What the prototype does

1. Generates Vertical × Use Case × Technology combinations.
2. Performs cheap discovery searches.
3. Selects promising candidates.
4. Performs deeper Tavily research.
5. Searches historical and recent evidence.
6. Searches quantitative evidence.
7. Detects missing signal types.
8. Performs limited autonomous follow-up searches.
9. Calculates explainable attractiveness, urgency and momentum.
10. Diversifies the final radar so Cybersecurity does not dominate.
11. Keeps URLs, titles and publication dates for traceability.

## 5. Important

This is an MVP. The scoring model is deliberately simple and transparent.

It does NOT yet calculate Orange Business Right-to-Win because internal CRM, offerings, references and partner data have not been connected.

That should be the next phase.

## 6. First parameters to change

In `config.py`:

```python
MAX_CANDIDATES = 120
MAX_DEEP_RESEARCH = 15
FINAL_RADAR_SIZE = 10
MAX_TAVILY_CREDITS = 300
```

For your first test, keep them low.

Example:

```python
MAX_CANDIDATES = 30
MAX_DEEP_RESEARCH = 5
FINAL_RADAR_SIZE = 5
MAX_TAVILY_CREDITS = 100
```

This makes the first run cheaper and faster.

## 7. Recommended first test

Start with:

```python
MAX_CANDIDATES = 30
MAX_DEEP_RESEARCH = 5
FINAL_RADAR_SIZE = 5
MAX_TAVILY_CREDITS = 100
```

Run:

```bash
python main.py
```

Then open:

```text
innovation_radar.html
```

and inspect:

```text
innovation_radar.json
```

The JSON is the important technical output because it keeps the evidence and source URLs.

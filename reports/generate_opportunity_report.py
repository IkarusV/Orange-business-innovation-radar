"""Generates a PDF report of opportunity spaces found so far, with linked articles."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "articles.db"
OUT_PATH = REPO_ROOT / "reports" / f"opportunity_spaces_{datetime.now().strftime('%Y-%m-%d')}.pdf"

SURFACE = "#fcfcfb"
PAGE_PLANE = "#f9f9f7"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"

# RSS/gnews are paused/deleted sources - kept in the DB (never deleted) but no
# longer part of the pipeline going forward. This report is scoped to the
# active institutional sources only; opportunity_spaces itself is a global
# table (all sources), so spaces are recomputed here rather than read
# directly, to filter without touching stored data.
ACTIVE_SOURCES = ["ted", "cordis", "ocds_uk", "ocds_ua"]
SOURCE_FILTER = "a.source_type IN ({})".format(",".join(f"'{s}'" for s in ACTIVE_SOURCES))

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"],
    "text.color": INK_PRIMARY,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": INK_SECONDARY,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "figure.facecolor": PAGE_PLANE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": PAGE_PLANE,
})


def style_axes(ax):
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(BASELINE)
    ax.spines["bottom"].set_color(BASELINE)


def fetch_data(conn):
    data = {}
    data["status_counts"] = dict(
        conn.execute(
            f"SELECT ac.status, COUNT(*) FROM article_classifications ac "
            f"JOIN articles a ON a.id = ac.article_id WHERE {SOURCE_FILTER} GROUP BY ac.status"
        )
    )
    data["total_classified_rows"] = sum(data["status_counts"].values())

    # Recomputed here (not read from opportunity_spaces directly) so the
    # source filter applies without touching the stored, all-sources table.
    rows = conn.execute(
        f"SELECT a.vertical, ac.use_case_id, ac.technology_id, ac.article_id, ac.client_relevance "
        f"FROM article_classifications ac JOIN articles a ON a.id = ac.article_id "
        f"WHERE ac.status = 'classified' AND ac.use_case_id IS NOT NULL "
        f"AND ac.technology_id IS NOT NULL AND {SOURCE_FILTER}"
    ).fetchall()

    buckets = {}
    for vertical, uc, tech, aid, relevance in rows:
        bucket = buckets.setdefault((vertical, uc, tech), {"article_ids": [], "relevances": []})
        bucket["article_ids"].append(aid)
        if relevance is not None:
            bucket["relevances"].append(relevance)

    spaces = []
    for (vertical, uc, tech), bucket in buckets.items():
        avg_rel = sum(bucket["relevances"]) / len(bucket["relevances"]) if bucket["relevances"] else None
        spaces.append((vertical, uc, tech, len(bucket["article_ids"]), json.dumps(sorted(bucket["article_ids"])), avg_rel))
    spaces.sort(key=lambda s: (s[0], -s[3]))
    data["spaces"] = spaces

    vertical_counts = {}
    for space in spaces:
        vertical_counts[space[0]] = vertical_counts.get(space[0], 0) + 1
    data["spaces_by_vertical"] = sorted(vertical_counts.items(), key=lambda kv: -kv[1])

    taxonomy = json.load(open(REPO_ROOT / "opportunity_classifier" / "config" / "taxonomy.json", encoding="utf-8"))
    data["use_case_labels"] = {e["id"]: e["label"] for e in taxonomy["use_cases"]}
    data["tech_labels"] = {e["id"]: e["label"] for e in taxonomy["technologies"]}

    articles_by_id = {}
    for row in data["spaces"]:
        for aid in json.loads(row[4]):
            if aid not in articles_by_id:
                a = conn.execute(
                    "SELECT title, source_name, source_type, url FROM articles WHERE id=?", (aid,)
                ).fetchone()
                articles_by_id[aid] = a
    data["articles_by_id"] = articles_by_id

    total_tokens = conn.execute(
        f"SELECT SUM(ac.tokens_used), COUNT(ac.tokens_used) FROM article_classifications ac "
        f"JOIN articles a ON a.id = ac.article_id WHERE {SOURCE_FILTER}"
    ).fetchone()
    data["total_tokens"] = total_tokens[0] or 0
    data["tokens_tracked_rows"] = total_tokens[1] or 0
    return data


def page_title(pdf, data):
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(PAGE_PLANE)

    fig.text(0.08, 0.90, "Opportunity Spaces", fontsize=26, fontweight="bold", color=INK_PRIMARY)
    fig.text(0.08, 0.855, "TED + CORDIS + OCDS only — RSS/gnews excluded (paused, see notes)", fontsize=13, color=INK_SECONDARY)
    fig.text(
        0.08, 0.815,
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        fontsize=10, color=INK_MUTED,
    )

    sc = data["status_counts"]
    stats = [
        (str(data["total_classified_rows"]), "Articles processed so far"),
        (str(sc.get("classified", 0)), "Classified (>=1 dimension)"),
        (str(len(data["spaces"])), "Opportunity spaces found"),
        (str(sc.get("no_match", 0)), "No match (correctly excluded)"),
    ]
    x_positions = [0.08, 0.31, 0.54, 0.77]
    for (value, label), x in zip(stats, x_positions):
        fig.text(x, 0.68, value, fontsize=26, fontweight="bold", color=BLUE)
        fig.text(x, 0.63, label, fontsize=9.5, color=INK_SECONDARY, wrap=True)

    fig.add_artist(plt.Line2D([0.08, 0.92], [0.58, 0.58], color=GRIDLINE, linewidth=1, transform=fig.transFigure))

    total = data["total_classified_rows"] or 1
    notes = [
        f"Status breakdown: classified={sc.get('classified',0)} ({100*sc.get('classified',0)/total:.0f}%), "
        f"no_match={sc.get('no_match',0)} ({100*sc.get('no_match',0)/total:.0f}%), "
        f"needs_review={sc.get('needs_review',0)} ({100*sc.get('needs_review',0)/total:.0f}%)",
        "",
        "An opportunity space requires BOTH use_case and technology to be matched on the same",
        "article. Many 'classified' rows have only one dimension filled and don't form a space —",
        f"of {sc.get('classified',0)} classified rows, {sum(s[3] for s in data['spaces'])} article-links",
        f"form the {len(data['spaces'])} complete triples below.",
        "",
        f"Token usage tracked so far: {data['total_tokens']:,} tokens across "
        f"{data['tokens_tracked_rows']} rows.",
        "",
        "Corpus: select_corpus.py's 600/vertical pool (TED backbone, CORDIS/OCDS fill the",
        "remainder, RSS backfills last, 2b-filtered, best-effort 50/25/25 recent/~1y/~5y mix).",
        "",
        "RSS and Google News are excluded from this report by request — both are paused/",
        "deleted sources, not part of the pipeline going forward. Their classified data still",
        "exists in the DB (never deleted) and still appears in the underlying opportunity_",
        "spaces table, just not counted here. See dark_corner.md for why they were dropped.",
    ]
    fig.text(0.08, 0.50, "\n".join(notes), fontsize=10.5, color=INK_SECONDARY, va="top", linespacing=1.6)

    pdf.savefig(fig)
    plt.close(fig)


def page_by_vertical(pdf, data):
    rows = data["spaces_by_vertical"]
    verticals = [r[0] for r in rows][::-1]
    counts = [r[1] for r in rows][::-1]

    fig, ax = plt.subplots(figsize=(11, 8.5))
    fig.patch.set_facecolor(PAGE_PLANE)
    y = range(len(verticals))

    ax.barh(y, counts, height=0.6, color=BLUE, edgecolor=PAGE_PLANE, linewidth=1)
    for i, c in enumerate(counts):
        ax.text(c + 0.05, i, str(c), va="center", ha="left", fontsize=9, color=INK_SECONDARY)

    ax.set_yticks(list(y))
    ax.set_yticklabels(verticals, fontsize=10)
    ax.set_xlabel("Opportunity spaces", fontsize=10)
    ax.set_title("Opportunity spaces by vertical", fontsize=16, fontweight="bold", color=INK_PRIMARY, loc="left", pad=16)
    ax.xaxis.grid(True, color=GRIDLINE, linewidth=0.8)
    ax.set_axisbelow(True)
    style_axes(ax)

    fig.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def page_listing(pdf, data):
    """Text pages: one block per opportunity space, listing its linked articles."""
    lines = []
    for vertical, uc, tech, count, linked_ids_json, avg_rel in data["spaces"]:
        uc_label = data["use_case_labels"].get(uc, uc)
        tech_label = data["tech_labels"].get(tech, tech)
        lines.append(("header", f"{vertical} — {uc_label} × {tech_label}  ({count} article{'s' if count != 1 else ''})"))
        for aid in json.loads(linked_ids_json):
            title, source_name, source_type, url = data["articles_by_id"][aid]
            title = (title or "")[:95]
            lines.append(("article", f"  [{source_type}] {title}  —  {source_name}"))
            lines.append(("url", f"      {url}"))
        lines.append(("spacer", ""))

    lines_per_page = 42
    for page_start in range(0, len(lines), lines_per_page):
        chunk = lines[page_start:page_start + lines_per_page]
        fig = plt.figure(figsize=(11, 8.5))
        fig.patch.set_facecolor(PAGE_PLANE)
        if page_start == 0:
            fig.text(0.06, 0.96, "Opportunity spaces — full listing", fontsize=14, fontweight="bold", color=INK_PRIMARY)

        y = 0.92
        for kind, text in chunk:
            if kind == "header":
                fig.text(0.06, y, text, fontsize=10, fontweight="bold", color=INK_PRIMARY)
                y -= 0.023
            elif kind == "article":
                fig.text(0.06, y, text, fontsize=8, color=INK_SECONDARY)
                y -= 0.019
            elif kind == "url":
                fig.text(0.06, y, text, fontsize=7, color=BLUE)
                y -= 0.019
            else:
                y -= 0.012

        pdf.savefig(fig)
        plt.close(fig)


def main():
    conn = sqlite3.connect(DB_PATH)
    data = fetch_data(conn)
    conn.close()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(OUT_PATH) as pdf:
        page_title(pdf, data)
        page_by_vertical(pdf, data)
        page_listing(pdf, data)

    print(f"Report written to {OUT_PATH}")


if __name__ == "__main__":
    main()

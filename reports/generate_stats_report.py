"""Generates a PDF stats report from data/articles.db (TED, CORDIS, OCDS
active; RSS/gnews retained as historical data, no longer collected)."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.backends.backend_pdf import PdfPages

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "articles.db"
OUT_PATH = REPO_ROOT / "reports" / f"innovation_radar_stats_{datetime.now().strftime('%Y-%m-%d')}.pdf"

# Palette (dataviz skill reference palette, light mode)
SURFACE = "#fcfcfb"
PAGE_PLANE = "#f9f9f7"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

BLUE = "#2a78d6"     # categorical slot 1 -> TED
ORANGE = "#eb6834"   # categorical slot 2 -> CORDIS
AQUA = "#1baf7a"     # categorical slot 3 -> OCDS UK
YELLOW = "#eda100"   # categorical slot 4 -> OCDS Ukraine

SOURCE_COLORS = {"ted": BLUE, "cordis": ORANGE, "ocds_uk": AQUA, "ocds_ua": YELLOW}
SOURCE_ORDER = ["ted", "cordis", "ocds_uk", "ocds_ua"]
SOURCE_LABELS = {"ted": "TED", "cordis": "CORDIS", "ocds_uk": "OCDS UK", "ocds_ua": "OCDS Ukraine"}
# RSS/gnews are paused/deleted sources - this report is scoped to the three
# active institutional sources only. Their historical rows still exist in
# the DB (see dark_corner.md) but are filtered out of every query below.

CONFIDENCE_ORDER = ["mid", "good"]
CONFIDENCE_COLORS = {"mid": "#86b6ef", "good": "#104281"}

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


def style_axes(ax, hide_x=False, hide_y=False):
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(BASELINE)
    ax.spines["bottom"].set_color(BASELINE)
    ax.spines["left"].set_linewidth(0.8)
    ax.spines["bottom"].set_linewidth(0.8)
    if hide_x:
        ax.spines["bottom"].set_visible(False)
        ax.tick_params(axis="x", bottom=False, labelbottom=False)
    if hide_y:
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", left=False, labelleft=False)


SOURCE_FILTER = "source_type IN ({})".format(",".join(f"'{s}'" for s in SOURCE_ORDER))


def fetch_data(conn):
    data = {}
    data["total"] = conn.execute(f"SELECT COUNT(*) FROM articles WHERE {SOURCE_FILTER}").fetchone()[0]
    data["by_source_type"] = dict(
        conn.execute(f"SELECT source_type, COUNT(*) FROM articles WHERE {SOURCE_FILTER} GROUP BY source_type")
    )
    data["by_vertical_source"] = conn.execute(
        f"SELECT vertical, source_type, COUNT(*) FROM articles WHERE {SOURCE_FILTER} "
        "GROUP BY vertical, source_type"
    ).fetchall()
    data["by_confidence_source"] = conn.execute(
        f"SELECT confidence, source_type, COUNT(*) FROM articles WHERE {SOURCE_FILTER} "
        "GROUP BY confidence, source_type"
    ).fetchall()
    data["verticals"] = [
        r[0] for r in conn.execute(f"SELECT DISTINCT vertical FROM articles WHERE {SOURCE_FILTER}")
    ]
    data["by_year_source"] = conn.execute(
        f"SELECT substr(published_date,1,4) as yr, source_type, COUNT(*) FROM articles "
        f"WHERE published_date IS NOT NULL AND {SOURCE_FILTER} GROUP BY yr, source_type ORDER BY yr"
    ).fetchall()
    data["earliest_collected"] = conn.execute(
        f"SELECT MIN(collected_at) FROM articles WHERE {SOURCE_FILTER}"
    ).fetchone()[0]
    data["latest_collected"] = conn.execute(
        f"SELECT MAX(collected_at) FROM articles WHERE {SOURCE_FILTER}"
    ).fetchone()[0]
    return data


def page_title(pdf, data):
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(PAGE_PLANE)

    fig.text(0.08, 0.90, "Innovation Radar", fontsize=26, fontweight="bold", color=INK_PRIMARY)
    fig.text(0.08, 0.855, "TED + CORDIS + OCDS — Statistics Report", fontsize=14, color=INK_SECONDARY)
    fig.text(
        0.08, 0.815,
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        fontsize=10, color=INK_MUTED,
    )

    stats = [
        (str(data["total"]), "Total articles / notices"),
        (str(data["by_source_type"].get("ted", 0)), "From TED procurement"),
        (str(data["by_source_type"].get("cordis", 0)), "From CORDIS (EU R&D funding)"),
        (str(data["by_source_type"].get("ocds_uk", 0) + data["by_source_type"].get("ocds_ua", 0)),
         "From OCDS (UK + Ukraine)"),
        (f"{len(data['verticals'])}/14", "Verticals with data"),
    ]
    x_positions = [0.08, 0.26, 0.44, 0.62, 0.80]
    for (value, label), x in zip(stats, x_positions):
        fig.text(x, 0.68, value, fontsize=24, fontweight="bold", color=BLUE)
        fig.text(x, 0.63, label, fontsize=9.5, color=INK_SECONDARY, wrap=True)

    fig.add_artist(plt.Line2D([0.08, 0.92], [0.58, 0.58], color=GRIDLINE, linewidth=1, transform=fig.transFigure))

    notes = [
        "Scope: TED (EU public procurement, CPV-mapped), CORDIS (EU Horizon/H2020 R&D",
        "funding, legalBasis-mapped), OCDS UK (Find a Tender + Contracts Finder) and OCDS",
        "Ukraine (ProZorro), CPV-mapped via TED's own mapping. All four query active +",
        "~1y-ago + ~5y-ago per vertical, all 14 verticals.",
        "",
        "RSS and Google News are excluded from this report by request (paused/deleted",
        "sources) — their historical rows still exist in the DB, see dark_corner.md.",
        "",
        "OCDS Australia (AusTender) has no live query API — confirmed dead end, 0 rows,",
        "not a bug. Patents (USPTO/EPO) are blocked on API credentials, not built yet.",
        "",
        "Confidence is a flat per-source trust signal (good/mid), not filtered — see the",
        "confidence page for the current per-source mapping.",
    ]
    fig.text(0.08, 0.50, "\n".join(notes), fontsize=10.5, color=INK_SECONDARY, va="top", linespacing=1.6)

    pdf.savefig(fig)
    plt.close(fig)


def page_by_year(pdf, data):
    totals = {}
    for yr, source_type, count in data["by_year_source"]:
        totals.setdefault(yr, {s: 0 for s in SOURCE_ORDER})[source_type] = count
    years = sorted(totals.keys())

    vals = {s: [totals[y][s] for y in years] for s in SOURCE_ORDER}

    fig, ax = plt.subplots(figsize=(11, 8.5))
    fig.patch.set_facecolor(PAGE_PLANE)
    x = range(len(years))
    bar_w = 0.55

    bottoms = [0] * len(years)
    for s in SOURCE_ORDER:
        ax.bar(x, vals[s], width=bar_w, bottom=bottoms, color=SOURCE_COLORS[s],
               label=SOURCE_LABELS[s], edgecolor=PAGE_PLANE, linewidth=1)
        bottoms = [b + v for b, v in zip(bottoms, vals[s])]

    for i, total in enumerate(bottoms):
        ax.text(i, total + 60, str(total), ha="center", fontsize=10, color=INK_SECONDARY)

    ax.set_xticks(list(x))
    ax.set_xticklabels(years, fontsize=11)
    ax.set_ylabel("Articles / notices", fontsize=10)
    ax.set_title("Coverage by publication year", fontsize=16, fontweight="bold",
                 color=INK_PRIMARY, loc="left", pad=16)
    ax.yaxis.grid(True, color=GRIDLINE, linewidth=0.8)
    ax.set_axisbelow(True)
    style_axes(ax)
    ax.legend(loc="upper left", frameon=False, fontsize=10)

    fig.text(
        0.08, 0.02,
        "TED, CORDIS, OCDS and Google News are deliberately spread across time bands per run\n"
        "(active/recent, ~1 year ago, ~5 years ago), not just the most recent notices — older\n"
        "columns are that historical sampling, not a coverage gap. RSS is inherently\n"
        "recency-only (feeds only carry current articles).",
        fontsize=9, color=INK_MUTED,
    )

    fig.tight_layout(rect=(0, 0.08, 1, 1))
    pdf.savefig(fig)
    plt.close(fig)


def page_vertical_breakdown(pdf, data):
    totals = {}
    for vertical, source_type, count in data["by_vertical_source"]:
        totals.setdefault(vertical, {s: 0 for s in SOURCE_ORDER})[source_type] = count
    verticals = sorted(totals.keys(), key=lambda v: sum(totals[v].values()))

    vals = {s: [totals[v][s] for v in verticals] for s in SOURCE_ORDER}

    fig, ax = plt.subplots(figsize=(11, 8.5))
    fig.patch.set_facecolor(PAGE_PLANE)
    y = range(len(verticals))
    bar_h = 0.6

    lefts = [0] * len(verticals)
    for s in SOURCE_ORDER:
        ax.barh(y, vals[s], height=bar_h, left=lefts, color=SOURCE_COLORS[s],
                label=SOURCE_LABELS[s], edgecolor=PAGE_PLANE, linewidth=1)
        lefts = [l + v for l, v in zip(lefts, vals[s])]

    for i, total in enumerate(lefts):
        ax.text(total + 20, i, str(total), va="center", ha="left", fontsize=9, color=INK_SECONDARY)

    ax.set_yticks(list(y))
    ax.set_yticklabels(verticals, fontsize=10)
    ax.set_xlabel("Articles / notices", fontsize=10)
    ax.set_title("Coverage by vertical", fontsize=16, fontweight="bold", color=INK_PRIMARY, loc="left", pad=16)
    ax.xaxis.grid(True, color=GRIDLINE, linewidth=0.8)
    ax.set_axisbelow(True)
    style_axes(ax)
    ax.legend(loc="lower right", frameon=False, fontsize=10)

    fig.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def page_confidence(pdf, data):
    totals = {}
    for confidence, source_type, count in data["by_confidence_source"]:
        totals.setdefault(confidence, {s: 0 for s in SOURCE_ORDER})[source_type] = count
    labels = [c for c in CONFIDENCE_ORDER if c in totals]

    fig, ax = plt.subplots(figsize=(11, 8.5))
    fig.patch.set_facecolor(PAGE_PLANE)
    x = range(len(labels))
    bar_w = 0.5

    bottoms = [0] * len(labels)
    for s in SOURCE_ORDER:
        vals = [totals[c][s] for c in labels]
        if not any(vals):
            continue
        ax.bar(x, vals, width=bar_w, bottom=bottoms, color=SOURCE_COLORS[s],
               label=SOURCE_LABELS[s], edgecolor=PAGE_PLANE, linewidth=1)
        bottoms = [b + v for b, v in zip(bottoms, vals)]

    for i, total in enumerate(bottoms):
        ax.text(i, total + 60, str(total), ha="center", fontsize=10, color=INK_SECONDARY)

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylabel("Articles / notices", fontsize=10)
    ax.set_title("Coverage by confidence", fontsize=16, fontweight="bold",
                 color=INK_PRIMARY, loc="left", pad=16)
    ax.yaxis.grid(True, color=GRIDLINE, linewidth=0.8)
    ax.set_axisbelow(True)
    style_axes(ax)
    ax.legend(loc="upper left", frameon=False, fontsize=10)

    fig.text(
        0.08, 0.02,
        "Confidence is a flat per-source trust signal, not a per-vertical quality score. TED and\n"
        "OCDS are tagged \"good\" throughout; CORDIS is \"good\" for legal_basis/call_code matches\n"
        "and \"mid\" for its keyword-fallback tier (weaker signal — see dark_corner.md).",
        fontsize=9, color=INK_MUTED,
    )

    fig.tight_layout(rect=(0, 0.08, 1, 1))
    pdf.savefig(fig)
    plt.close(fig)


def main():
    conn = sqlite3.connect(DB_PATH)
    data = fetch_data(conn)
    conn.close()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(OUT_PATH) as pdf:
        page_title(pdf, data)
        page_by_year(pdf, data)
        page_vertical_breakdown(pdf, data)
        page_confidence(pdf, data)

    print(f"Report written to {OUT_PATH}")


if __name__ == "__main__":
    main()

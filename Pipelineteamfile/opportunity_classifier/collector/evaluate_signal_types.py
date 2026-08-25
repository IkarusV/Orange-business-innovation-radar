"""Runs the golden set through the live classifier and reports a confusion
matrix for signal_type.

The set in fixtures/signal_type_golden_set.json is self-labeled and has not
been reviewed by a human, so what this prints is agreement between two
automated passes, not accuracy against validated ground truth. Read it that
way until the labels are signed off.

The pairs to watch are market_trend/competitor_move and
proof_signal/competitor_move: if either confuses above ~20%, the distinguishing
questions in config/prompt_template.txt need tightening, not the taxonomy.

Run from repo root: python -m opportunity_classifier.collector.evaluate_signal_types [--limit N]
"""
import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import client as classifier_client
from . import taxonomy as taxonomy_mod
from common.signal_types import TIE_BREAK_ORDER

MODULE_DIR = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = MODULE_DIR / "config" / "taxonomy.json"
PROMPT_TEMPLATE_PATH = MODULE_DIR / "config" / "prompt_template.txt"
GOLDEN_SET_PATH = MODULE_DIR / "fixtures" / "signal_type_golden_set.json"

MAX_WORKERS = 10  # same measured-safe ceiling as the classifier itself
WATCH_PAIRS = [("market_trend", "competitor_move"), ("proof_signal", "competitor_move")]
CONFUSION_ALERT_RATE = 0.20


def classify_example(navy_client, template, taxonomy_text, use_case_ids, technology_ids, example):
    result = classifier_client.classify(
        navy_client, template, taxonomy_text, use_case_ids, technology_ids,
        example["vertical"], example["source_name"], example["title"], example["summary"],
        None, example.get("published_date"),
    )
    return example, result


def confusion_matrix(pairs: list) -> dict:
    matrix = {expected: {predicted: 0 for predicted in TIE_BREAK_ORDER + [None]} for expected in TIE_BREAK_ORDER}
    for expected, predicted in pairs:
        matrix[expected][predicted] = matrix[expected].get(predicted, 0) + 1
    return matrix


def render_matrix(matrix: dict) -> str:
    columns = TIE_BREAK_ORDER + [None]
    header = "expected \\ predicted".ljust(22) + "".join((c or "unassigned")[:15].rjust(17) for c in columns)
    lines = [header, "-" * len(header)]
    for expected in TIE_BREAK_ORDER:
        row = expected.ljust(22) + "".join(str(matrix[expected][c]).rjust(17) for c in columns)
        lines.append(row)
    return "\n".join(lines)


def run(limit=None) -> dict:
    api_key = os.environ.get("NAVY_API_KEY")
    base_url = os.environ.get("NAVY_BASE_URL", "https://api.navy/v1")
    if not api_key:
        raise RuntimeError("NAVY_API_KEY not set in environment")

    golden = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    examples = golden["examples"][:limit] if limit else golden["examples"]

    taxonomy = taxonomy_mod.load_taxonomy(TAXONOMY_PATH)
    taxonomy_text = taxonomy_mod.taxonomy_block(taxonomy)
    use_case_ids, technology_ids = taxonomy_mod.valid_ids(taxonomy)
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    navy_client = classifier_client.make_client(api_key, base_url)

    pairs, rows, tokens, errors = [], [], 0, 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [
            ex.submit(classify_example, navy_client, template, taxonomy_text, use_case_ids, technology_ids, example)
            for example in examples
        ]
        for future in as_completed(futures):
            try:
                example, result = future.result()
            except Exception as exc:
                errors += 1
                print(f"FAIL - {exc}")
                continue
            tokens += result.total_tokens
            pairs.append((example["expected_signal_type"], result.signal_type))
            rows.append({
                "id": example["id"],
                "vertical": example["vertical"],
                "source_type": example["source_type"],
                "title": example["title"][:110],
                "expected": example["expected_signal_type"],
                "predicted": result.signal_type,
                "torn_with": example["torn_with"],
                "signal_type_confidence": result.signal_type_confidence,
                "rationale": result.signal_type_rationale,
                "agrees": example["expected_signal_type"] == result.signal_type,
            })

    matrix = confusion_matrix(pairs)
    agreed = sum(1 for expected, predicted in pairs if expected == predicted)
    total = len(pairs)

    per_type = {}
    for expected in TIE_BREAK_ORDER:
        support = sum(matrix[expected].values())
        correct = matrix[expected][expected]
        per_type[expected] = {
            "support": support,
            "agreed": correct,
            "agreement": round(correct / support, 3) if support else None,
        }

    watch = {}
    for left, right in WATCH_PAIRS:
        left_support = sum(matrix[left].values())
        right_support = sum(matrix[right].values())
        watch[f"{left}->{right}"] = round(matrix[left][right] / left_support, 3) if left_support else None
        watch[f"{right}->{left}"] = round(matrix[right][left] / right_support, 3) if right_support else None

    low_confidence = [row for row in rows if (row["signal_type_confidence"] or 0) < 0.5]
    unassigned = [row for row in rows if row["predicted"] is None]

    summary = {
        "golden_set_status": golden["status"],
        "evaluated": total,
        "agreement": round(agreed / total, 3) if total else None,
        "per_type": per_type,
        "watch_pairs": watch,
        "watch_pairs_over_threshold": {k: v for k, v in watch.items() if v is not None and v > CONFUSION_ALERT_RATE},
        "below_confidence_gate": len(low_confidence),
        "below_confidence_gate_share": round(len(low_confidence) / total, 3) if total else None,
        "unassigned": len(unassigned),
        "errors": errors,
        "tokens": tokens,
    }

    print(render_matrix(matrix))
    print()
    print(json.dumps(summary, indent=2))
    print()
    print("Disagreements:")
    for row in sorted((r for r in rows if not r["agrees"]), key=lambda r: r["expected"]):
        torn = f" (torn with {row['torn_with']})" if row["torn_with"] else ""
        print(f"  [{row['id']}] {row['expected']} -> {row['predicted']}{torn} conf={row['signal_type_confidence']}")
        print(f"      {row['title']}")
        print(f"      model: {row['rationale']}")

    return {"summary": summary, "matrix": matrix, "rows": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="evaluate at most N golden-set examples")
    parser.add_argument("--out", type=str, default=None, help="write the full result as JSON to this path")
    args = parser.parse_args()
    output = run(limit=args.limit)
    if args.out:
        Path(args.out).write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

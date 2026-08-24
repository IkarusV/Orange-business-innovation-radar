import json
from pathlib import Path
from typing import Tuple


def load_taxonomy(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def taxonomy_block(taxonomy: dict) -> str:
    lines = ["USE CASES:"]
    for entry in taxonomy["use_cases"]:
        lines.append(f'{entry["id"]} — {entry["label"]}: {entry["definition"]}')
    lines.append("")
    lines.append("TECHNOLOGIES:")
    for entry in taxonomy["technologies"]:
        lines.append(f'{entry["id"]} — {entry["label"]}: {entry["definition"]}')
    return "\n".join(lines)


def valid_ids(taxonomy: dict) -> Tuple[set, set]:
    use_case_ids = {e["id"] for e in taxonomy["use_cases"]}
    technology_ids = {e["id"] for e in taxonomy["technologies"]}
    return use_case_ids, technology_ids

from __future__ import annotations

import json


def table_safe(records: list[dict]) -> list[dict]:
    """Serialize nested/mixed values so PyArrow receives stable string columns."""
    cleaned = []
    for record in records:
        row = {}
        for key, value in record.items():
            if isinstance(value, (list, dict, tuple, set)):
                row[key] = json.dumps(value, ensure_ascii=False)
            elif value is None:
                row[key] = ""
            else:
                row[key] = value
        cleaned.append(row)
    return cleaned

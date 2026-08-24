from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator

from radar_v2.constants import TEAM_PIPELINE
from radar_v2.services import extension_store

def stream_run(limit: int, context_path: str = "", api_key: str = "", base_url: str = "", model: str = "") -> Iterator[dict]:
    command = [sys.executable, "run_radar.py", "--limit", str(max(1, limit))]
    if context_path:
        command.extend(["--client-context", context_path])
    environment = os.environ.copy()
    if api_key:
        environment["NAVY_API_KEY"] = api_key
    if base_url:
        environment["NAVY_BASE_URL"] = base_url
    if model:
        environment["NAVY_MODEL"] = model
    process = subprocess.Popen(
        command,
        cwd=TEAM_PIPELINE,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    for line in process.stdout or []:
        line = line.strip()
        if line.startswith("RADAR_PROGRESS::"):
            yield json.loads(line.split("::", 1)[1])
    code = process.wait()
    if code:
        raise RuntimeError("The radar refresh could not be completed. Review the server logs for details.")


def company_context_file() -> str:
    company = extension_store.active_company()
    parts = [
        f"Company: {company['name']}",
        f"Priority geography: {company['geography']}",
        f"Website: {company['website']}",
        f"Strategic focus: {company['focus']}",
    ]
    references = extension_store.selected_document_texts(max_documents=5, max_chars=16000)
    if references:
        parts.append("\nADDITIONAL COMPANY INFORMATION (guidance, not a restriction):")
    for document in references:
        label = "OPPORTUNITY MAPPING" if document["scope"] == "Opportunity mapping" else "SCORING & FIT" if document["scope"] == "Scoring & fit" else "ALL COMPANY CONTEXT"
        parts.append(f"\n[{label}] {document['name']}\n{document['text']}")
    path = TEAM_PIPELINE / "data" / "client_context.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")
    return str(path)

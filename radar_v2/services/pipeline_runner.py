from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

from radar_v2.constants import TEAM_PIPELINE
from radar_v2.services import extension_store

LOCK_PATH = TEAM_PIPELINE / "data" / "pipeline.lock"
RUN_LOG_PATH = TEAM_PIPELINE / "logs" / "radar_background_run.log"
SUMMARY_DIR = TEAM_PIPELINE / "logs" / "radar_runs"


def pipeline_lock_active() -> bool:
    return LOCK_PATH.exists()


def lock_started_at_iso() -> Optional[str]:
    """When the currently-active lock was written, or None if there is no
    active run. run_radar.py's own run() writes the lock at the very start
    and removes it in a `finally` regardless of success or failure, so its
    mtime is a reliable "run started at" marker independent of anything this
    process remembers - which matters because a fresh page load creates a
    brand new RadarState instance with no memory of a run this session didn't
    itself start."""
    try:
        return datetime.fromtimestamp(LOCK_PATH.stat().st_mtime, tz=timezone.utc).isoformat()
    except FileNotFoundError:
        return None


def latest_run_summary_after(since_iso: Optional[str]) -> Optional[dict]:
    """The most recently written run summary, if it was written after
    since_iso - i.e. by the run that just ended. run_radar.py only writes a
    summary at the very end of a successful run, so no matching summary means
    that run crashed or was interrupted rather than completing."""
    if not SUMMARY_DIR.exists():
        return None
    candidates = sorted(SUMMARY_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return None
    latest = candidates[0]
    mtime = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)
    if since_iso and mtime < datetime.fromisoformat(since_iso):
        return None
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def latest_progress_line() -> Optional[dict]:
    """The last RADAR_PROGRESS:: line the detached run has written to its own
    log, for a rough live-ish status without piping the subprocess's output
    back to this backend - the whole point of launch_detached() is that
    nothing here stays attached to the child process."""
    if not RUN_LOG_PATH.exists():
        return None
    try:
        text = RUN_LOG_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("RADAR_PROGRESS::"):
            try:
                return json.loads(line.split("::", 1)[1])
            except (json.JSONDecodeError, IndexError):
                return None
    return None


def launch_detached(
    limit: int | None = None, context_path: str = "", api_key: str = "", base_url: str = "", model: str = "",
) -> None:
    """Start run_radar.py as a fully OS-detached process, independent of both
    this Reflex request and the Reflex backend process itself - it survives a
    dropped websocket, a page reload, and even the dev server hot-reloading
    or being restarted. Nothing here waits on the child or pipes its output
    back; state.py's poll_pipeline_status() watches it from the outside via
    pipeline_lock_active()/latest_progress_line()/latest_run_summary_after()
    instead, so losing that observer never touches the run itself.
    """
    command = [sys.executable, "run_radar.py"]
    if limit is not None:
        command.extend(["--limit", str(max(1, limit))])
    if context_path:
        command.extend(["--client-context", context_path])
    environment = os.environ.copy()
    if api_key:
        environment["NAVY_API_KEY"] = api_key
    if base_url:
        environment["NAVY_BASE_URL"] = base_url
    if model:
        environment["NAVY_MODEL"] = model

    RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_file = RUN_LOG_PATH.open("w", encoding="utf-8", errors="replace")

    detach_kwargs: dict = {}
    if os.name == "nt":
        detach_kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        detach_kwargs["start_new_session"] = True

    try:
        subprocess.Popen(
            command,
            cwd=TEAM_PIPELINE,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            close_fds=True,
            **detach_kwargs,
        )
    finally:
        # The child inherited its own handle to this file; our copy can close
        # immediately without affecting its writes.
        log_file.close()


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

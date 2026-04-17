"""In-process batch workspace store for the M3 batch review flow."""

from __future__ import annotations

import os
import secrets
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional

MAX_FILES = 10
MAX_FILE_BYTES = 20 * 1024 * 1024    # 20 MB
MAX_BATCH_BYTES = 100 * 1024 * 1024  # 100 MB
WORKSPACE_TTL = 30 * 60              # 30 minutes

# Process-local store: batch_id -> workspace dict
_store: dict[str, dict] = {}

_ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


class FileTooLargeError(Exception):
    pass


class BatchTooLargeError(Exception):
    pass


class TooManyFilesError(Exception):
    pass


def _new_batch_id() -> str:
    return "b_" + secrets.token_hex(8)


def expire_stale_workspaces() -> None:
    now = time.time()
    stale = [bid for bid, ws in _store.items() if ws["expires_at"] < now]
    for bid in stale:
        _cleanup_workspace(_store.pop(bid))


def _cleanup_workspace(ws: dict) -> None:
    td = ws.get("temp_dir")
    if td and os.path.isdir(td):
        shutil.rmtree(td, ignore_errors=True)


def get_workspace(batch_id: str) -> Optional[dict]:
    expire_stale_workspaces()
    return _store.get(batch_id)


def register_staged_workspace(temp_dir: str, rows: list[dict]) -> dict:
    """Register an already-staged workspace (used by the streaming HTTP upload path)."""
    expire_stale_workspaces()
    batch_id = _new_batch_id()
    total_bytes = sum(
        os.path.getsize(row["staged_path"])
        for row in rows
        if os.path.exists(row["staged_path"])
    )
    now = time.time()
    workspace = {
        "batch_id": batch_id,
        "created_at": now,
        "expires_at": now + WORKSPACE_TTL,
        "status": "draft",
        "temp_dir": temp_dir,
        "total_bytes": total_bytes,
        "rows": rows,
    }
    _store[batch_id] = workspace
    return workspace


def create_workspace(files_data: list[tuple[str, bytes]]) -> dict:
    """Stage files and create a new batch workspace (test/programmatic path).

    files_data: list of (original_filename, file_bytes)
    Raises TooManyFilesError, FileTooLargeError, or BatchTooLargeError on limit violations.
    """
    expire_stale_workspaces()

    if len(files_data) > MAX_FILES:
        raise TooManyFilesError(
            f"Too many files: {len(files_data)} uploaded, max {MAX_FILES}."
        )

    temp_dir = tempfile.mkdtemp(prefix="alc-batch-")
    rows: list[dict] = []
    total_bytes = 0

    try:
        for i, (filename, file_bytes) in enumerate(files_data):
            file_size = len(file_bytes)

            if file_size > MAX_FILE_BYTES:
                raise FileTooLargeError(
                    f"File '{filename}' exceeds 20 MB limit ({file_size} bytes)."
                )

            total_bytes += file_size
            if total_bytes > MAX_BATCH_BYTES:
                raise BatchTooLargeError(
                    f"Total batch size exceeds 100 MB limit ({total_bytes} bytes)."
                )

            ext = Path(filename).suffix.lower()
            if ext not in _ALLOWED_EXTS:
                ext = ".png"

            staged_path = os.path.join(temp_dir, f"row-{i}{ext}")
            with open(staged_path, "wb") as f:
                f.write(file_bytes)

            rows.append({
                "row_id": f"row-{i}",
                "filename": filename,
                "staged_path": staged_path,
                "form_values": {},
                "errors": {},
                "queue_state": "draft",
                "result": None,
                "system_error": None,
            })

    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return register_staged_workspace(temp_dir, rows)


def touch_workspace(workspace: dict) -> None:
    workspace["expires_at"] = time.time() + WORKSPACE_TTL


def update_row_form_values(workspace: dict, row_id: str, form_values: dict) -> None:
    for row in workspace["rows"]:
        if row["row_id"] == row_id:
            row["form_values"] = form_values
            row["errors"] = {}
            break
    touch_workspace(workspace)


def set_row_errors(workspace: dict, row_id: str, errors: dict) -> None:
    for row in workspace["rows"]:
        if row["row_id"] == row_id:
            row["errors"] = errors
            break


def mark_all_queued(workspace: dict) -> None:
    for row in workspace["rows"]:
        row["queue_state"] = "queued"
        row["errors"] = {}
        row["result"] = None
        row["system_error"] = None
    workspace["status"] = "queued"
    touch_workspace(workspace)


def get_next_queued_row(workspace: dict) -> Optional[dict]:
    for row in workspace["rows"]:
        if row["queue_state"] == "queued":
            return row
    return None


def mark_row_processing(workspace: dict, row_id: str) -> None:
    for row in workspace["rows"]:
        if row["row_id"] == row_id:
            row["queue_state"] = "processing"
            break


def mark_row_complete(workspace: dict, row_id: str, result: dict) -> None:
    for row in workspace["rows"]:
        if row["row_id"] == row_id:
            row["queue_state"] = "complete"
            row["result"] = result
            break
    _check_batch_complete(workspace)
    touch_workspace(workspace)


def mark_row_processing_error(workspace: dict, row_id: str, message: str) -> None:
    for row in workspace["rows"]:
        if row["row_id"] == row_id:
            row["queue_state"] = "processing_error"
            row["result"] = None
            row["system_error"] = {
                "code": "processing_error",
                "message": message,
            }
            break
    _check_batch_complete(workspace)
    touch_workspace(workspace)


def _check_batch_complete(workspace: dict) -> None:
    terminal = {"complete", "processing_error"}
    if all(row["queue_state"] in terminal for row in workspace["rows"]):
        workspace["status"] = "complete"


def compute_summary(workspace: dict) -> dict:
    """Compute batch summary counts from current row states."""
    match = mismatch = needs_review = system_errors = 0
    manual_review = request_better_image = 0

    for row in workspace["rows"]:
        if row["queue_state"] == "complete" and row["result"]:
            v = row["result"].get("overall_verdict", "")
            a = row["result"].get("recommended_action", "")
            if v == "match":
                match += 1
            elif v == "mismatch":
                mismatch += 1
            else:
                needs_review += 1
            if a == "manual_review":
                manual_review += 1
            elif a == "request_better_image":
                request_better_image += 1
        elif row["queue_state"] == "processing_error":
            needs_review += 1
            system_errors += 1
            manual_review += 1

    terminal = {"complete", "processing_error"}
    done_count = sum(1 for r in workspace["rows"] if r["queue_state"] in terminal)

    return {
        "match": match,
        "mismatch": mismatch,
        "needs_review": needs_review,
        "manual_review": manual_review,
        "request_better_image": request_better_image,
        "system_error_count": system_errors,
        "total": len(workspace["rows"]),
        "complete": done_count,
    }

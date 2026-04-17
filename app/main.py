"""FastAPI web app for the single-label reviewer workbench."""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from alc_label_verifier._constants import GOVERNMENT_WARNING_PREFIX, STANDARD_WARNING_BODY
from alc_label_verifier.ocr import warm_ocr
from alc_label_verifier.service import verify_label
from app.batch_store import (
    MAX_FILE_BYTES as STORE_MAX_FILE_BYTES,
    MAX_BATCH_BYTES as STORE_MAX_BATCH_BYTES,
    compute_summary,
    get_next_queued_row,
    get_workspace,
    mark_all_queued,
    mark_row_complete,
    mark_row_processing,
    mark_row_processing_error,
    register_staged_workspace,
    set_row_errors,
    update_row_form_values,
)
from app.web_helpers import build_application_payload, validate_expected_data

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
CHUNK_SIZE = 64 * 1024               # 64 KB

STANDARD_WARNING = f"{GOVERNMENT_WARNING_PREFIX} {STANDARD_WARNING_BODY}"

FIELD_LABELS = {
    "brand_name": "Brand Name",
    "class_type": "Class / Type",
    "alcohol_content": "Alcohol Content",
    "net_contents": "Net Contents",
    "producer_name_address": "Producer / Address",
    "country_of_origin": "Country of Origin",
    "government_warning": "Government Warning",
}

REASON_EXPLANATIONS = {
    "exact_match": "Exact match with the expected value.",
    "normalized_match": "Matched after normalizing case and punctuation.",
    "wrong_value": "The value on the label does not match the expected value.",
    "missing_required": "Required field was not found on the label.",
    "not_applicable": "This field does not apply to this product.",
    "unreadable": "OCR confidence too low to make a determination.",
    "warning_prefix_error": "Government Warning prefix is not in the required ALL-CAPS format.",
    "warning_text_mismatch": "Warning text deviates from the required standard statement.",
}


@asynccontextmanager
async def lifespan(application: FastAPI):
    warm_ocr()
    yield


app = FastAPI(title="Alcohol Label Reviewer Workbench", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "standard_warning": STANDARD_WARNING,
            "result": None,
            "errors": {},
            "form_values": {},
        },
    )


@app.post("/verify", response_class=HTMLResponse)
async def verify(
    request: Request,
    label_image: Annotated[Optional[UploadFile], File()] = None,
    brand_name: Annotated[str, Form()] = "",
    class_type: Annotated[str, Form()] = "",
    alcohol_content: Annotated[str, Form()] = "",
    net_contents: Annotated[str, Form()] = "",
    producer_name_address: Annotated[str, Form()] = "",
    is_import: Annotated[Optional[str], Form()] = None,
    country_of_origin: Annotated[str, Form()] = "",
    government_warning: Annotated[str, Form()] = "",
) -> HTMLResponse:
    # Early-reject on Content-Length if provided by the client (streaming check is authoritative)
    try:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_UPLOAD_BYTES:
            return HTMLResponse(status_code=413, content="Upload too large (max 20 MB).")
    except ValueError:
        pass  # bogus Content-Length; streaming check will enforce the real limit

    form_values = {
        "brand_name": brand_name,
        "class_type": class_type,
        "alcohol_content": alcohol_content,
        "net_contents": net_contents,
        "producer_name_address": producer_name_address,
        "is_import": is_import,
        "country_of_origin": country_of_origin,
        "government_warning": government_warning,
    }

    errors: dict[str, str] = {}
    if label_image is None or label_image.filename == "":
        errors["label_image"] = "Label image is required."
    errors.update(validate_expected_data(form_values))

    if errors:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "standard_warning": STANDARD_WARNING,
                "result": None,
                "errors": errors,
                "form_values": form_values,
            },
            status_code=422,
        )

    # Whitelist extension to avoid arbitrary suffixes in /tmp
    ext = Path(label_image.filename or "").suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        ext = ".png"

    # Stream upload to temp file, enforcing the byte limit
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = tmp.name
            total = 0
            while True:
                chunk = await label_image.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    return HTMLResponse(
                        status_code=413,
                        content="Upload too large (max 20 MB).",
                    )
                tmp.write(chunk)

        application = build_application_payload(form_values)
        result = verify_label(tmp_path, application)

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "standard_warning": STANDARD_WARNING,
            "result": result,
            "errors": {},
            "form_values": form_values,
            "field_labels": FIELD_LABELS,
            "reason_explanations": REASON_EXPLANATIONS,
        },
    )


# ── Batch routes ──────────────────────────────────────────────────────────────

BATCH_CHUNK_SIZE = 64 * 1024  # 64 KB

_BATCH_ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _batch_error(request: Request, messages: list[str], status: int):
    return templates.TemplateResponse(
        request=request,
        name="batch.html",
        context={"upload_errors": messages},
        status_code=status,
    )


@app.get("/batch", response_class=HTMLResponse)
async def batch_entry(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="batch.html",
        context={"upload_errors": []},
    )


@app.post("/batch/session")
async def batch_session(
    request: Request,
    label_images: Annotated[Optional[List[UploadFile]], File()] = None,
) -> RedirectResponse:
    valid_uploads = [f for f in (label_images or []) if f.filename]

    if not valid_uploads:
        return _batch_error(request, ["At least one image is required."], 422)

    if len(valid_uploads) > 10:
        return _batch_error(
            request,
            [f"Too many files: {len(valid_uploads)} selected, max 10."],
            422,
        )

    # Stream each file directly to disk; enforce per-file and total limits
    temp_dir = tempfile.mkdtemp(prefix="alc-batch-")
    rows: list[dict] = []
    total_bytes = 0

    try:
        for i, upload in enumerate(valid_uploads):
            ext = Path(upload.filename or "").suffix.lower()
            if ext not in _BATCH_ALLOWED_EXTS:
                ext = ".png"

            staged_path = os.path.join(temp_dir, f"row-{i}{ext}")
            file_bytes_written = 0

            with open(staged_path, "wb") as fout:
                while True:
                    chunk = await upload.read(BATCH_CHUNK_SIZE)
                    if not chunk:
                        break
                    file_bytes_written += len(chunk)
                    if file_bytes_written > STORE_MAX_FILE_BYTES:
                        return _batch_error(
                            request,
                            [f"'{upload.filename}' exceeds the 20 MB per-file limit."],
                            413,
                        )
                    total_bytes += len(chunk)
                    if total_bytes > STORE_MAX_BATCH_BYTES:
                        return _batch_error(
                            request,
                            ["Total upload size exceeds the 100 MB batch limit."],
                            413,
                        )
                    fout.write(chunk)

            rows.append({
                "row_id": f"row-{i}",
                "filename": upload.filename,
                "staged_path": staged_path,
                "form_values": {},
                "errors": {},
                "queue_state": "draft",
                "result": None,
                "system_error": None,
            })

        workspace = register_staged_workspace(temp_dir, rows)

    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return RedirectResponse(
        url=f"/batch/{workspace['batch_id']}",
        status_code=303,
    )


@app.get("/batch/{batch_id}", response_class=HTMLResponse)
async def batch_workspace(request: Request, batch_id: str) -> HTMLResponse:
    workspace = get_workspace(batch_id)
    if workspace is None:
        return HTMLResponse(status_code=404, content="Batch workspace not found or expired.")

    summary = compute_summary(workspace)
    return templates.TemplateResponse(
        request=request,
        name="batch_workspace.html",
        context={
            "workspace": workspace,
            "summary": summary,
            "standard_warning": STANDARD_WARNING,
            "field_labels": FIELD_LABELS,
            "reason_explanations": REASON_EXPLANATIONS,
        },
    )


@app.post("/batch/{batch_id}/run", response_class=HTMLResponse)
async def batch_run(request: Request, batch_id: str) -> HTMLResponse:
    workspace = get_workspace(batch_id)
    if workspace is None:
        return HTMLResponse(status_code=404, content="Batch workspace not found or expired.")

    # Prevent re-run from overwriting results once rows have been queued/processed
    if workspace["status"] != "draft":
        return RedirectResponse(url=f"/batch/{batch_id}", status_code=303)

    form = await request.form()

    # Collect and validate per-row expected data
    all_valid = True
    for row in workspace["rows"]:
        rid = row["row_id"]
        fv = {
            "brand_name": form.get(f"{rid}__brand_name", ""),
            "class_type": form.get(f"{rid}__class_type", ""),
            "alcohol_content": form.get(f"{rid}__alcohol_content", ""),
            "net_contents": form.get(f"{rid}__net_contents", ""),
            "producer_name_address": form.get(f"{rid}__producer_name_address", ""),
            "is_import": form.get(f"{rid}__is_import", None),
            "country_of_origin": form.get(f"{rid}__country_of_origin", ""),
            "government_warning": form.get(f"{rid}__government_warning", ""),
        }
        update_row_form_values(workspace, rid, fv)
        errs = validate_expected_data(fv)
        if errs:
            all_valid = False
            set_row_errors(workspace, rid, errs)
        else:
            set_row_errors(workspace, rid, {})

    summary = compute_summary(workspace)

    if not all_valid:
        return templates.TemplateResponse(
            request=request,
            name="batch_workspace.html",
            context={
                "workspace": workspace,
                "summary": summary,
                "standard_warning": STANDARD_WARNING,
                "field_labels": FIELD_LABELS,
                "reason_explanations": REASON_EXPLANATIONS,
            },
            status_code=422,
        )

    mark_all_queued(workspace)
    summary = compute_summary(workspace)

    return templates.TemplateResponse(
        request=request,
        name="batch_workspace.html",
        context={
            "workspace": workspace,
            "summary": summary,
            "standard_warning": STANDARD_WARNING,
            "field_labels": FIELD_LABELS,
            "reason_explanations": REASON_EXPLANATIONS,
            "polling": True,
        },
    )


@app.post("/batch/{batch_id}/process-next")
async def batch_process_next(batch_id: str) -> JSONResponse:
    workspace = get_workspace(batch_id)
    if workspace is None:
        return JSONResponse(status_code=404, content={"error": "Workspace not found."})

    row = get_next_queued_row(workspace)
    if row is None:
        summary = compute_summary(workspace)
        return JSONResponse({
            "done": True,
            "summary": summary,
            "rows": _rows_state(workspace),
        })

    row_id = row["row_id"]
    mark_row_processing(workspace, row_id)

    try:
        application = build_application_payload(row["form_values"])
        result = verify_label(row["staged_path"], application)
        mark_row_complete(workspace, row_id, result)
    except Exception as exc:
        mark_row_processing_error(
            workspace,
            row_id,
            "Unexpected processing error for this label. Review manually.",
        )

    summary = compute_summary(workspace)
    next_queued = get_next_queued_row(workspace)

    return JSONResponse({
        "done": next_queued is None,
        "summary": summary,
        "rows": _rows_state(workspace),
    })


def _rows_state(workspace: dict) -> list[dict]:
    """Return per-row state for polling responses (no full field_results — use GET for drill-down)."""
    out = []
    for row in workspace["rows"]:
        entry: dict = {
            "row_id": row["row_id"],
            "filename": row["filename"],
            "queue_state": row["queue_state"],
            "system_error": row.get("system_error"),
        }
        if row.get("result"):
            entry["overall_verdict"] = row["result"].get("overall_verdict")
            entry["recommended_action"] = row["result"].get("recommended_action")
            entry["processing_ms"] = row["result"].get("processing_ms")
        out.append(entry)
    return out

"""FastAPI web app for the single-label reviewer workbench."""

from __future__ import annotations

import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from alc_label_verifier._constants import GOVERNMENT_WARNING_PREFIX, STANDARD_WARNING_BODY
from alc_label_verifier.ocr import warm_ocr
from alc_label_verifier.service import verify_label

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
    import_checked = bool(is_import)

    # Form validation
    if label_image is None or label_image.filename == "":
        errors["label_image"] = "Label image is required."
    if not brand_name.strip():
        errors["brand_name"] = "Required."
    if not class_type.strip():
        errors["class_type"] = "Required."
    if not alcohol_content.strip():
        errors["alcohol_content"] = "Required."
    if not net_contents.strip():
        errors["net_contents"] = "Required."
    if not producer_name_address.strip():
        errors["producer_name_address"] = "Required."
    if not government_warning.strip():
        errors["government_warning"] = "Required."
    if import_checked and not country_of_origin.strip():
        errors["country_of_origin"] = "Required for imported products."

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

        application = {
            "beverage_type": "distilled_spirits",
            "brand_name": brand_name.strip(),
            "class_type": class_type.strip(),
            "alcohol_content": alcohol_content.strip(),
            "net_contents": net_contents.strip(),
            "producer_name_address": producer_name_address.strip(),
            "is_import": import_checked,
            "country_of_origin": country_of_origin.strip() if import_checked else None,
            "government_warning": government_warning.strip(),
        }

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

"""Shared helpers for single-label and batch reviewer web routes."""

from __future__ import annotations

_REQUIRED = [
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "producer_name_address",
    "government_warning",
]


def validate_expected_data(form_values: dict) -> dict[str, str]:
    """Validate expected application data; returns field -> error message dict."""
    errors: dict[str, str] = {}
    for field in _REQUIRED:
        if not form_values.get(field, "").strip():
            errors[field] = "Required."
    import_checked = bool(form_values.get("is_import"))
    if import_checked and not form_values.get("country_of_origin", "").strip():
        errors["country_of_origin"] = "Required for imported products."
    return errors


def build_application_payload(form_values: dict) -> dict:
    """Build the application dict for verify_label from normalized form values."""
    import_checked = bool(form_values.get("is_import"))
    return {
        "beverage_type": "distilled_spirits",
        "brand_name": form_values.get("brand_name", "").strip(),
        "class_type": form_values.get("class_type", "").strip(),
        "alcohol_content": form_values.get("alcohol_content", "").strip(),
        "net_contents": form_values.get("net_contents", "").strip(),
        "producer_name_address": form_values.get("producer_name_address", "").strip(),
        "is_import": import_checked,
        "country_of_origin": (
            form_values.get("country_of_origin", "").strip() if import_checked else None
        ),
        "government_warning": form_values.get("government_warning", "").strip(),
    }

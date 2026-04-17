"""Public library entrypoint: verify_label."""

from __future__ import annotations

import time
from typing import Any, Dict

from alc_label_verifier._constants import FIELD_NAMES
from alc_label_verifier.exceptions import UnreadableImageError
from alc_label_verifier.matching import (
    is_globally_unreadable,
    match_alcohol_content,
    match_brand_name,
    match_class_type,
    match_country_of_origin,
    match_government_warning,
    match_net_contents,
    match_producer_name_address,
    partition_lines,
    _split_class_and_lower,
)
from alc_label_verifier.models import FieldResult, VerificationResult
from alc_label_verifier.ocr import extract_lines


def _derive_verdict(field_results: Dict[str, FieldResult]) -> tuple[str, str]:
    statuses = [fr.status for fr in field_results.values()]
    if "needs_review" in statuses:
        return "needs_review", "request_better_image"
    if "mismatch" in statuses:
        return "mismatch", "manual_review"
    return "match", "accept"


def _all_unreadable_result() -> Dict[str, Any]:
    field_results = {
        name: {"status": "needs_review", "reason_code": "unreadable"}
        for name in FIELD_NAMES
    }
    return {
        "overall_verdict": "needs_review",
        "recommended_action": "request_better_image",
        "field_results": field_results,
    }


def verify_label(image_path: str, application: Dict[str, Any]) -> Dict[str, Any]:
    """Run the full verification pipeline and return a result dict.

    The returned dict matches the eval harness contract:
      {overall_verdict, recommended_action, field_results: {field: {status, reason_code}}}
    Extra keys (observed_value, processing_ms) are additive and do not affect eval semantics.
    """
    t0 = time.monotonic()
    try:
        lines = extract_lines(image_path)
    except UnreadableImageError:
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        result = _all_unreadable_result()
        result["processing_ms"] = elapsed_ms
        return result

    if is_globally_unreadable(lines):
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        result = _all_unreadable_result()
        result["processing_ms"] = elapsed_ms
        return result

    # Partition lines into sections
    header_lines, warning_anchor, warning_body = partition_lines(lines)
    class_lines, lower_lines, _alcohol_anchor = _split_class_and_lower(header_lines)

    is_import: bool = bool(application.get("is_import", False))

    # Match each field
    brand_result = match_brand_name(header_lines, application.get("brand_name", ""))
    class_result = match_class_type(class_lines, application.get("class_type", ""))
    alcohol_result = match_alcohol_content(lines, application.get("alcohol_content", ""))
    net_result = match_net_contents(lines, application.get("net_contents", ""))
    producer_result = match_producer_name_address(
        lower_lines, application.get("producer_name_address", "")
    )
    country_result = match_country_of_origin(
        header_lines,
        application.get("country_of_origin"),
        is_import,
    )
    warning_result = match_government_warning(
        warning_anchor,
        warning_body,
        application.get("government_warning", ""),
    )

    field_results: Dict[str, FieldResult] = {
        "brand_name": brand_result,
        "class_type": class_result,
        "alcohol_content": alcohol_result,
        "net_contents": net_result,
        "producer_name_address": producer_result,
        "country_of_origin": country_result,
        "government_warning": warning_result,
    }

    # If more than half of required fields are unreadable, apply global policy
    required = [
        "brand_name", "class_type", "alcohol_content",
        "net_contents", "producer_name_address", "government_warning",
    ]
    unreadable_count = sum(
        1 for name in required
        if field_results[name].status == "needs_review"
    )
    # Trigger global-unreadable when 4+ of 6 required fields are unreadable
    if unreadable_count >= 4:
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        result = _all_unreadable_result()
        result["processing_ms"] = elapsed_ms
        return result

    verdict, action = _derive_verdict(field_results)
    elapsed_ms = round((time.monotonic() - t0) * 1000)
    return {
        "overall_verdict": verdict,
        "recommended_action": action,
        "processing_ms": elapsed_ms,
        "field_results": {
            name: {
                "status": fr.status,
                "reason_code": fr.reason_code,
                **({"observed_value": fr.observed_value} if fr.observed_value is not None else {}),
            }
            for name, fr in field_results.items()
        },
    }

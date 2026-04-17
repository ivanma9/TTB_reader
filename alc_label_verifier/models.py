"""Internal typed models for the label verifier pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class OcrLine:
    text: str
    confidence: float
    bbox: List[List[float]]
    y_center: float
    x_center: float


@dataclass
class FieldResult:
    status: str        # match | mismatch | needs_review | not_applicable
    reason_code: str   # exact_match | normalized_match | wrong_value | missing_required |
                       # not_applicable | unreadable | warning_prefix_error | warning_text_mismatch
    extracted_text: Optional[str] = None
    confidence: Optional[float] = None
    observed_value: Optional[str] = None


@dataclass
class VerificationResult:
    overall_verdict: str       # match | mismatch | needs_review
    recommended_action: str    # accept | manual_review | request_better_image
    field_results: Dict[str, FieldResult] = field(default_factory=dict)

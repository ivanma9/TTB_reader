"""Tests for M2 verifier enrichment: observed_value, processing_ms, UnreadableImageError."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from alc_label_verifier.matching import (
    _compare_text,
    match_brand_name,
    match_class_type,
    match_alcohol_content,
    match_net_contents,
    match_producer_name_address,
    match_country_of_origin,
    match_government_warning,
)
from alc_label_verifier.models import FieldResult, OcrLine
from alc_label_verifier.exceptions import UnreadableImageError


def _line(text: str, conf: float = 0.95, y: float = 10.0) -> OcrLine:
    return OcrLine(
        text=text, confidence=conf,
        bbox=[[0, y], [100, y], [100, y + 10], [0, y + 10]],
        y_center=y + 5, x_center=50.0,
    )


STANDARD_BODY = (
    "According to the Surgeon General, women should not drink alcoholic "
    "beverages during pregnancy because of the risk of birth defects. "
    "Consumption of alcoholic beverages impairs your ability to drive a car "
    "or operate machinery, and may cause health problems."
)
FULL_WARNING = f"GOVERNMENT WARNING: {STANDARD_BODY}"


# ---------------------------------------------------------------------------
# FieldResult.observed_value default
# ---------------------------------------------------------------------------

class TestFieldResultDefault:
    def test_observed_value_defaults_none(self):
        fr = FieldResult(status="match", reason_code="exact_match")
        assert fr.observed_value is None


# ---------------------------------------------------------------------------
# observed_value population in _compare_text
# ---------------------------------------------------------------------------

class TestCompareTextObservedValue:
    def test_exact_match_carries_observed(self):
        fr = _compare_text("OLD TOM", "OLD TOM", 0.95)
        assert fr.status == "match"
        assert fr.observed_value == "OLD TOM"

    def test_normalized_match_carries_observed(self):
        fr = _compare_text("old tom", "OLD TOM", 0.95)
        assert fr.status == "match"
        assert fr.observed_value == "old tom"

    def test_mismatch_carries_observed(self):
        fr = _compare_text("WRONG BRAND", "OLD TOM", 0.95)
        assert fr.status == "mismatch"
        assert fr.observed_value == "WRONG BRAND"

    def test_low_confidence_carries_observed(self):
        fr = _compare_text("garbled text", "OLD TOM", 0.50)
        assert fr.status == "needs_review"
        assert fr.observed_value == "garbled text"

    def test_empty_ocr_no_observed(self):
        fr = _compare_text("", "OLD TOM", 0.95)
        assert fr.status == "needs_review"
        assert fr.observed_value is None


# ---------------------------------------------------------------------------
# observed_value in alcohol and net matchers
# ---------------------------------------------------------------------------

class TestAlcoholObservedValue:
    def test_match_line_observed(self):
        lines = [_line("40% Alc./Vol. (80 Proof)", 0.95, y=50.0)]
        fr = match_alcohol_content(lines, "40% Alc./Vol. (80 Proof)")
        assert fr.status == "match"
        assert fr.observed_value == "40% Alc./Vol. (80 Proof)"

    def test_mismatch_line_observed(self):
        lines = [_line("50% Alc./Vol.", 0.95, y=50.0)]
        fr = match_alcohol_content(lines, "40% Alc./Vol. (80 Proof)")
        assert fr.status == "mismatch"
        assert fr.observed_value is not None
        assert "50%" in fr.observed_value


class TestNetContentsObservedValue:
    def test_match_line_observed(self):
        lines = [_line("750 mL", 0.95, y=50.0)]
        fr = match_net_contents(lines, "750 mL")
        assert fr.status == "match"
        assert fr.observed_value == "750 mL"


# ---------------------------------------------------------------------------
# observed_value in country matcher
# ---------------------------------------------------------------------------

class TestCountryObservedValue:
    def test_correct_country_has_observed(self):
        lower = [_line("Country of Origin: Mexico", 0.95)]
        fr = match_country_of_origin(lower, "Mexico", is_import=True)
        assert fr.status == "match"
        assert fr.observed_value == "Mexico"

    def test_wrong_country_has_observed(self):
        lower = [_line("Country of Origin: Ireland", 0.95)]
        fr = match_country_of_origin(lower, "Scotland", is_import=True)
        assert fr.status == "mismatch"
        assert fr.observed_value == "Ireland"

    def test_domestic_no_observed(self):
        fr = match_country_of_origin([], None, is_import=False)
        assert fr.status == "not_applicable"
        assert fr.observed_value is None


# ---------------------------------------------------------------------------
# observed_value in warning matcher
# ---------------------------------------------------------------------------

class TestWarningObservedValue:
    def test_match_warning_has_observed(self):
        anchor = _line("GOVERNMENT WARNING:", 0.95)
        body = [_line(STANDARD_BODY, 0.95, y=20.0)]
        fr = match_government_warning(anchor, body, FULL_WARNING)
        assert fr.status == "match"
        assert fr.observed_value is not None
        assert "Surgeon General" in fr.observed_value

    def test_mismatch_warning_has_observed(self):
        deviated = STANDARD_BODY.replace("birth defects", "serious defects")
        anchor = _line("GOVERNMENT WARNING:", 0.95)
        body = [_line(deviated, 0.95, y=20.0)]
        fr = match_government_warning(anchor, body, FULL_WARNING)
        assert fr.status == "mismatch"
        assert fr.observed_value is not None


# ---------------------------------------------------------------------------
# processing_ms present in service output
# ---------------------------------------------------------------------------

class TestProcessingMs:
    def test_processing_ms_present(self):
        from alc_label_verifier.service import verify_label
        with patch("alc_label_verifier.service.extract_lines") as mock_ocr:
            mock_ocr.return_value = []
            result = verify_label("/fake/path.png", {})
        assert "processing_ms" in result
        assert isinstance(result["processing_ms"], int)
        assert result["processing_ms"] >= 0


# ---------------------------------------------------------------------------
# UnreadableImageError handling
# ---------------------------------------------------------------------------

class TestUnreadableImageError:
    def test_malformed_image_returns_needs_review(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"not-a-valid-image")
            bad_path = f.name
        try:
            from alc_label_verifier.service import verify_label
            result = verify_label(bad_path, {})
            assert result["overall_verdict"] == "needs_review"
            assert result["recommended_action"] == "request_better_image"
        finally:
            os.unlink(bad_path)

    def test_unexpected_exception_propagates(self):
        from alc_label_verifier.service import verify_label
        with patch("alc_label_verifier.service.extract_lines") as mock_ocr:
            mock_ocr.side_effect = RuntimeError("unexpected failure")
            with pytest.raises(RuntimeError, match="unexpected failure"):
                verify_label("/fake/path.png", {})

    def test_preprocessing_wraps_pil_error(self):
        from alc_label_verifier.preprocessing import preprocess
        with pytest.raises(UnreadableImageError):
            preprocess("/nonexistent/bad.png")


# ---------------------------------------------------------------------------
# warm_ocr
# ---------------------------------------------------------------------------

class TestWarmOcr:
    def test_warm_ocr_calls_get_ocr(self):
        from alc_label_verifier import ocr as ocr_module
        with patch.object(ocr_module, "_get_ocr") as mock_init:
            mock_init.return_value = MagicMock()
            ocr_module.warm_ocr()
            mock_init.assert_called_once()


# ---------------------------------------------------------------------------
# Service-level regression: country anchor above the ABV line must be visible
# to match_country_of_origin. Prior wiring passed only `lower_lines` so a
# "PRODUCT OF BRAZIL" line in the brand/class region was silently filtered
# out before the matcher ran.
# ---------------------------------------------------------------------------

class TestCountryAnchorAboveAbv:
    def test_country_anchor_above_abv_line_is_found(self):
        from alc_label_verifier.service import verify_label

        ocr_lines = [
            OcrLine(text="CACHACA", confidence=1.0, bbox=[], y_center=100, x_center=50),
            OcrLine(text="PRODUCT OF BRAZIL", confidence=0.99, bbox=[], y_center=150, x_center=50),
            OcrLine(text="DESDE 1925", confidence=1.0, bbox=[], y_center=200, x_center=50),
            OcrLine(text="40% Alc./Vol.", confidence=0.98, bbox=[], y_center=300, x_center=50),
            OcrLine(text="750 ml", confidence=0.98, bbox=[], y_center=400, x_center=50),
        ]
        application = {
            "brand_name": "Bucco",
            "class_type": "Cachaca",
            "alcohol_content": "40% Alc./Vol. (80 Proof)",
            "net_contents": "750 milliliters",
            "producer_name_address": "Irrelevant, BRAZIL",
            "is_import": True,
            "country_of_origin": "Brazil",
            "government_warning": "",
        }
        with patch("alc_label_verifier.service.extract_lines") as mock_ocr:
            mock_ocr.return_value = ocr_lines
            result = verify_label("/fake/path.png", application)
        assert result["field_results"]["country_of_origin"]["status"] == "match"

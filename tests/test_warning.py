"""Unit tests for government warning strict prefix and body matching."""

import pytest
from alc_label_verifier.matching import match_government_warning
from alc_label_verifier.models import OcrLine

STANDARD_BODY = (
    "According to the Surgeon General, women should not drink alcoholic "
    "beverages during pregnancy because of the risk of birth defects. "
    "Consumption of alcoholic beverages impairs your ability to drive a car "
    "or operate machinery, and may cause health problems."
)
FULL_WARNING = f"GOVERNMENT WARNING: {STANDARD_BODY}"


def _make_line(text: str, confidence: float = 0.95, y: float = 100.0) -> OcrLine:
    return OcrLine(
        text=text,
        confidence=confidence,
        bbox=[[0, y], [100, y], [100, y + 20], [0, y + 20]],
        y_center=y + 10,
        x_center=50.0,
    )


def _body_lines(confidence: float = 0.95) -> list:
    return [_make_line(STANDARD_BODY, confidence, y=120.0)]


class TestWarningPrefixValidation:
    def test_exact_prefix_passes(self):
        anchor = _make_line("GOVERNMENT WARNING:", 0.95)
        result = match_government_warning(anchor, _body_lines(), FULL_WARNING)
        assert result.status == "match"
        assert result.reason_code == "exact_match"

    def test_title_case_prefix_is_prefix_error(self):
        anchor = _make_line("Government Warning:", 0.95)
        result = match_government_warning(anchor, _body_lines(), FULL_WARNING)
        assert result.status == "mismatch"
        assert result.reason_code == "warning_prefix_error"

    def test_no_anchor_returns_unreadable(self):
        result = match_government_warning(None, [], FULL_WARNING)
        assert result.status == "needs_review"
        assert result.reason_code == "unreadable"

    def test_low_confidence_anchor_returns_unreadable(self):
        anchor = _make_line("GOVERNMENT WARNING:", 0.75)
        result = match_government_warning(anchor, _body_lines(), FULL_WARNING)
        assert result.status == "needs_review"
        assert result.reason_code == "unreadable"


class TestWarningBodyValidation:
    def test_correct_body_matches(self):
        anchor = _make_line("GOVERNMENT WARNING:", 0.95)
        result = match_government_warning(anchor, _body_lines(), FULL_WARNING)
        assert result.status == "match"

    def test_body_deviation_is_text_mismatch(self):
        deviated = STANDARD_BODY.replace("birth defects", "serious defects")
        body = [_make_line(deviated, 0.95)]
        anchor = _make_line("GOVERNMENT WARNING:", 0.95)
        result = match_government_warning(anchor, body, FULL_WARNING)
        assert result.status == "mismatch"
        assert result.reason_code == "warning_text_mismatch"

    def test_low_confidence_body_returns_unreadable(self):
        anchor = _make_line("GOVERNMENT WARNING:", 0.95)
        body = [_make_line(STANDARD_BODY, 0.80)]  # below 0.90 threshold
        result = match_government_warning(anchor, body, FULL_WARNING)
        assert result.status == "needs_review"
        assert result.reason_code == "unreadable"

    def test_incomplete_body_returns_unreadable(self):
        # Only first 50 chars of body (well below 60% completeness)
        partial = STANDARD_BODY[:50]
        anchor = _make_line("GOVERNMENT WARNING:", 0.95)
        body = [_make_line(partial, 0.95)]
        result = match_government_warning(anchor, body, FULL_WARNING)
        assert result.status == "needs_review"
        assert result.reason_code == "unreadable"


class TestConditionalCountryOfOrigin:
    from alc_label_verifier.matching import match_country_of_origin

    def test_domestic_always_not_applicable(self):
        from alc_label_verifier.matching import match_country_of_origin
        result = match_country_of_origin([], None, is_import=False)
        assert result.status == "not_applicable"
        assert result.reason_code == "not_applicable"

    def test_import_missing_country_is_mismatch(self):
        from alc_label_verifier.matching import match_country_of_origin
        # lower_lines has content but no "Country of Origin:" line
        fake_lower = [_make_line("Sierra Azul Imports, Austin, TX", 0.95)]
        result = match_country_of_origin(fake_lower, "Mexico", is_import=True)
        assert result.status == "mismatch"
        assert result.reason_code == "missing_required"

    def test_import_correct_country_matches(self):
        from alc_label_verifier.matching import match_country_of_origin
        lower = [_make_line("Country of Origin: Mexico", 0.95)]
        result = match_country_of_origin(lower, "Mexico", is_import=True)
        assert result.status == "match"

    def test_import_wrong_country_is_mismatch(self):
        from alc_label_verifier.matching import match_country_of_origin
        lower = [_make_line("Country of Origin: Ireland", 0.95)]
        result = match_country_of_origin(lower, "Scotland", is_import=True)
        assert result.status == "mismatch"
        assert result.reason_code == "wrong_value"

    def test_import_weak_lower_ocr_returns_unreadable(self):
        from alc_label_verifier.matching import match_country_of_origin
        # No lower lines at all means weak evidence
        result = match_country_of_origin([], "Mexico", is_import=True)
        assert result.status == "needs_review"
        assert result.reason_code == "unreadable"

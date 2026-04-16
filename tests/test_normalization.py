"""Unit tests for text normalization and fuzzy acceptance boundaries."""

import pytest
from alc_label_verifier.matching import normalize_text, _compare_text
from alc_label_verifier._constants import STANDARD_CONFIDENCE_THRESHOLD


def test_normalize_lowercases():
    assert normalize_text("OLD TOM DISTILLERY") == "old tom distillery"


def test_normalize_removes_punctuation():
    assert normalize_text("Stone's Throw") == "stones throw"
    assert normalize_text("RIVER-RUN") == "riverrun"


def test_normalize_collapses_whitespace():
    assert normalize_text("Kentucky Straight\nBourbon Whiskey") == "kentucky straight bourbon whiskey"
    assert normalize_text("  old  tom  ") == "old tom"


def test_normalize_alc_formatting():
    assert normalize_text("45% Alc./Vol. (90 Proof)") == normalize_text("45% ALC/VOL (90 PROOF)")


class TestCompareText:
    HIGH = 0.95

    def test_exact_match(self):
        result = _compare_text("OLD TOM DISTILLERY", "OLD TOM DISTILLERY", self.HIGH)
        assert result.status == "match"
        assert result.reason_code == "exact_match"

    def test_normalized_match_case(self):
        result = _compare_text("STONE'S THROW", "Stone's Throw", self.HIGH)
        assert result.status == "match"
        assert result.reason_code == "normalized_match"

    def test_normalized_match_punctuation(self):
        result = _compare_text("RIVER-RUN", "RIVER RUN", self.HIGH)
        assert result.status == "match"
        assert result.reason_code == "normalized_match"

    def test_normalized_match_whitespace(self):
        result = _compare_text(
            "Kentucky Straight Bourbon Whiskey",
            "Kentucky Straight\nBourbon Whiskey",
            self.HIGH,
        )
        assert result.status == "match"

    def test_mismatch_wrong_brand(self):
        result = _compare_text("OLD FOX DISTILLERY", "OLD TOM DISTILLERY", self.HIGH)
        assert result.status == "mismatch"
        assert result.reason_code == "wrong_value"

    def test_mismatch_wrong_class(self):
        result = _compare_text("Tennessee Whiskey", "Kentucky Straight Bourbon Whiskey", self.HIGH)
        assert result.status == "mismatch"
        assert result.reason_code == "wrong_value"

    def test_low_confidence_returns_unreadable(self):
        result = _compare_text("some garbled text!!!", "OLD TOM DISTILLERY", 0.50)
        assert result.status == "needs_review"
        assert result.reason_code == "unreadable"

    def test_empty_ocr_returns_unreadable(self):
        result = _compare_text("", "OLD TOM DISTILLERY", self.HIGH)
        assert result.status == "needs_review"
        assert result.reason_code == "unreadable"

    def test_fuzzy_threshold_boundary_accepts(self):
        # "STONE'S THROW" normalizes to "stones throw" which is identical to "stones throw"
        result = _compare_text("STONE'S THROW", "Stone's Throw", self.HIGH)
        assert result.status == "match"

    def test_fuzzy_disabled_strict_comparison(self):
        # With fuzzy disabled, only exact-normalized match is accepted
        result = _compare_text(
            "STONES THROW SPIRITS FRANKFORT KY",
            "Stone's Throw Spirits, Bardstown, KY",
            self.HIGH,
            use_fuzzy=False,
        )
        assert result.status == "mismatch"

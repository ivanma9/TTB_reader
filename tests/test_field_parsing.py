"""Unit tests for alcohol and net-contents numeric parsing."""

import pytest
from alc_label_verifier.matching import (
    parse_alcohol,
    parse_net_contents,
    _alcohol_values_match,
    _net_values_match,
    match_brand_name,
    match_country_of_origin,
)
from alc_label_verifier.models import OcrLine


class TestParseAlcohol:
    def test_standard_format(self):
        result = parse_alcohol("45% Alc./Vol. (90 Proof)")
        assert result is not None
        abv, proof = result
        assert abv == pytest.approx(45.0)
        assert proof == pytest.approx(90.0)

    def test_uppercase_format(self):
        result = parse_alcohol("45% ALC/VOL (90 PROOF)")
        assert result is not None
        abv, proof = result
        assert abv == pytest.approx(45.0)
        assert proof == pytest.approx(90.0)

    def test_high_proof(self):
        result = parse_alcohol("57% Alc./Vol. (114 Proof)")
        assert result is not None
        abv, proof = result
        assert abv == pytest.approx(57.0)
        assert proof == pytest.approx(114.0)

    def test_no_proof(self):
        result = parse_alcohol("40%")
        assert result is not None
        abv, proof = result
        assert abv == pytest.approx(40.0)
        assert proof is None

    def test_not_found(self):
        assert parse_alcohol("750 mL") is None


class TestAlcoholValuesMatch:
    def test_same_values_match(self):
        assert _alcohol_values_match((45.0, 90.0), (45.0, 90.0))

    def test_different_abv_no_match(self):
        assert not _alcohol_values_match((45.0, 90.0), (40.0, 80.0))

    def test_different_proof_no_match(self):
        assert not _alcohol_values_match((57.0, 114.0), (57.0, 80.0))

    def test_no_proof_compared_to_no_proof(self):
        assert _alcohol_values_match((45.0, None), (45.0, None))


class TestParseNetContents:
    def test_ml_lower(self):
        result = parse_net_contents("750 mL")
        assert result is not None
        qty, unit = result
        assert qty == pytest.approx(750.0)
        assert unit == "ml"

    def test_ml_upper(self):
        result = parse_net_contents("700 ML")
        assert result is not None
        qty, _ = result
        assert qty == pytest.approx(700.0)

    def test_liter_converts(self):
        result = parse_net_contents("1 L")
        assert result is not None
        qty, unit = result
        assert qty == pytest.approx(1000.0)
        assert unit == "ml"

    def test_mismatch_750_vs_1000(self):
        a = parse_net_contents("750 mL")
        b = parse_net_contents("1 L")
        assert a is not None and b is not None
        assert not _net_values_match(a, b)

    def test_match_same_ml(self):
        a = parse_net_contents("750 mL")
        b = parse_net_contents("750 mL")
        assert a is not None and b is not None
        assert _net_values_match(a, b)

    def test_not_found(self):
        assert parse_net_contents("45% Alc./Vol.") is None

    def test_no_false_positive_on_alcohol_string(self):
        # Must not match bare 'l' or 'Vol.' in an alcohol-content line
        assert parse_net_contents("45% Alc./Vol. (90 Proof)") is None
        assert parse_net_contents("57% Alc./Vol. (114 Proof)") is None

    def test_no_false_positive_on_proof(self):
        assert parse_net_contents("90 Proof") is None


def test_parse_net_contents_uppercase_oz():
    assert parse_net_contents("12 FL OZ") == (12.0, "oz")
    assert parse_net_contents("12 OZ") == (12.0, "oz")
    assert parse_net_contents("750 ML") == (750.0, "ml")


def test_match_brand_name_multiline():
    lines = [
        OcrLine(text="OLD TOM", confidence=0.95, bbox=[], y_center=10, x_center=50),
        OcrLine(text="DISTILLERY", confidence=0.95, bbox=[], y_center=30, x_center=50),
    ]
    result = match_brand_name(lines, "OLD TOM DISTILLERY")
    assert result.status == "match"


def test_match_country_of_origin_ocr_typo_anchor():
    lines = [OcrLine(text="Couniry of Origin: Mexico", confidence=0.92, bbox=[], y_center=0, x_center=0)]
    result = match_country_of_origin(lines, "Mexico", is_import=True)
    assert result.status == "match"


def test_match_country_of_origin_product_of_variant():
    lines = [OcrLine(text="PRODUCT OF BRAZIL", confidence=0.95, bbox=[], y_center=0, x_center=0)]
    result = match_country_of_origin(lines, "Brazil", is_import=True)
    assert result.status == "match"


def test_match_country_of_origin_product_of_mixed_case_with_trailing_text():
    lines = [OcrLine(text="Product of Peru GOVERNMENT WARNING", confidence=0.95, bbox=[], y_center=0, x_center=0)]
    result = match_country_of_origin(lines, "Peru", is_import=True)
    assert result.status == "match"


def test_match_country_of_origin_imported_from_variant():
    lines = [OcrLine(text="IMPORTED FROM FRANCE", confidence=0.95, bbox=[], y_center=0, x_center=0)]
    result = match_country_of_origin(lines, "France", is_import=True)
    assert result.status == "match"


def test_match_country_of_origin_made_in_variant():
    lines = [OcrLine(text="Made in Scotland", confidence=0.95, bbox=[], y_center=0, x_center=0)]
    result = match_country_of_origin(lines, "Scotland", is_import=True)
    assert result.status == "match"


def test_match_country_of_origin_produced_in_variant():
    lines = [OcrLine(text="Produced in Mexico", confidence=0.95, bbox=[], y_center=0, x_center=0)]
    result = match_country_of_origin(lines, "Mexico", is_import=True)
    assert result.status == "match"


def test_match_country_of_origin_product_of_wrong_country():
    lines = [OcrLine(text="PRODUCT OF BRAZIL", confidence=0.95, bbox=[], y_center=0, x_center=0)]
    result = match_country_of_origin(lines, "France", is_import=True)
    assert result.status == "mismatch"
    assert result.reason_code == "wrong_value"
    assert result.observed_value == "BRAZIL"


def test_match_country_of_origin_noisy_line_does_not_shadow_real_anchor():
    # "Made inside a barrel" starts with "made in" but is not a country
    # anchor (word-boundary rejects "inside"). The real anchor is on the next
    # line and must still win.
    lines = [
        OcrLine(text="Made inside a barrel", confidence=0.95, bbox=[], y_center=0, x_center=0),
        OcrLine(text="Product of France", confidence=0.95, bbox=[], y_center=1, x_center=0),
    ]
    result = match_country_of_origin(lines, "France", is_import=True)
    assert result.status == "match"


def test_match_country_of_origin_multiple_anchors_picks_matching_value():
    # Two legitimate anchor lines; pick the one whose value matches expected.
    lines = [
        OcrLine(text="Product of Brazil", confidence=0.95, bbox=[], y_center=0, x_center=0),
        OcrLine(text="Imported from France", confidence=0.95, bbox=[], y_center=1, x_center=0),
    ]
    result = match_country_of_origin(lines, "France", is_import=True)
    assert result.status == "match"


def test_match_country_of_origin_rejects_made_inside_false_positive():
    # Word-boundary rule: "made inside" must not match "made in" anchor.
    lines = [OcrLine(text="Made inside a cave", confidence=0.95, bbox=[], y_center=0, x_center=0)]
    result = match_country_of_origin(lines, "Scotland", is_import=True)
    assert result.status == "mismatch"
    assert result.reason_code == "missing_required"


def test_parse_net_contents_accepts_milliliters_spelled_out():
    assert parse_net_contents("750 milliliters") == (750.0, "ml")


def test_parse_net_contents_accepts_liter_spelled_out():
    assert parse_net_contents("1 liter") == (1000.0, "ml")
    assert parse_net_contents("1.75 liters") == (1750.0, "ml")


def test_parse_net_contents_accepts_fluid_ounces_spelled_out():
    assert parse_net_contents("25.4 fluid ounces") == (25.4, "oz")


def test_parse_net_contents_tolerates_l_read_as_digit_one():
    # OCR frequently reads 'L' as '1' on label typography.
    assert parse_net_contents("CONT.750m1") == (750.0, "ml")
    assert parse_net_contents("750 M1") == (750.0, "ml")


def test_parse_net_contents_rejects_bare_lowercase_l():
    # Bare lowercase 'l' in prose is ambiguous with letter 'l' / OCR'd '1';
    # only 'L' uppercase (or spelled-out 'liters') counts as the unit.
    assert parse_net_contents("contains 1 l today") is None


def test_parse_net_contents_rejects_implausible_bare_L_quantity():
    # 'serial 12345L' must not parse as 12,345 liters.
    assert parse_net_contents("serial 12345L") is None


def test_parse_net_contents_rejects_m1_in_product_code():
    # '1m1' in batch/lot codes must not parse as 1 mL.
    assert parse_net_contents("lot 1m1-batch") is None


def test_parse_net_contents_ignores_abv_percent():
    # '40%' is alcohol, not net contents.
    assert parse_net_contents("Alc. 40% by volume") is None


def test_parse_net_contents_dual_unit_label_picks_primary():
    # US-style domestic labels lead with fl oz; EU imports lead with mL.
    assert parse_net_contents("12 fl oz (355 mL)") == (12.0, "oz")
    assert parse_net_contents("750 mL (25.4 fl oz)") == (750.0, "ml")

"""Unit tests for alcohol and net-contents numeric parsing."""

import pytest
from alc_label_verifier.matching import parse_alcohol, parse_net_contents, _alcohol_values_match, _net_values_match


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

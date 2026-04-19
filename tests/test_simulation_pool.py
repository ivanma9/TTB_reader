from __future__ import annotations

import importlib
from pathlib import Path

import app.simulation_pool as simulation_pool
from app.simulation_pool import (
    POOL_CASES,
    PoolCase,
    derive_submitter,
    pick_unqueued_case,
)


class TestPoolLoad:
    def test_pool_has_28_entries(self):
        assert len(POOL_CASES) == 28

    def test_pool_keyed_by_case_id(self):
        for key, case in POOL_CASES.items():
            assert key == case.case_id

    def test_pool_entries_have_image_paths_that_exist(self):
        for case in POOL_CASES.values():
            assert isinstance(case.image_path, Path)
            assert case.image_path.exists(), f"missing fixture for {case.case_id}"

    def test_pool_form_values_are_web_form_shape(self):
        # is_import: "1" or None, country_of_origin: str or "" (mirrors DemoCase shape)
        for case in POOL_CASES.values():
            fv = case.form_values
            assert fv["is_import"] in ("1", None)
            assert isinstance(fv["country_of_origin"], str)
            if case.is_import:
                assert fv["is_import"] == "1"
                assert fv["country_of_origin"] != ""
            else:
                assert fv["is_import"] is None
                assert fv["country_of_origin"] == ""

    def test_pool_form_values_have_all_seven_fields(self):
        expected = {
            "brand_name",
            "class_type",
            "alcohol_content",
            "net_contents",
            "producer_name_address",
            "is_import",
            "country_of_origin",
            "government_warning",
        }
        for case in POOL_CASES.values():
            assert set(case.form_values.keys()) == expected


class TestPickUnqueued:
    def test_pick_unqueued_excludes_given_ids(self):
        excluded = {"gs_001", "gs_002"}
        case = pick_unqueued_case(excluded)
        assert case is not None
        assert case.case_id not in excluded

    def test_pick_unqueued_returns_none_when_exhausted(self):
        assert pick_unqueued_case(set(POOL_CASES.keys())) is None

    def test_pick_unqueued_picks_the_only_remaining(self):
        remaining = "gs_014"
        excluded = set(POOL_CASES.keys()) - {remaining}
        case = pick_unqueued_case(excluded)
        assert case is not None
        assert case.case_id == remaining


class TestDeriveSubmitter:
    def test_domestic_allcaps_titlecased_llc(self):
        # gs_001 brand is "OLD TOM DISTILLERY", is_import False
        assert derive_submitter(POOL_CASES["gs_001"]) == "Old Tom Distillery LLC"

    def test_import_allcaps_titlecased_imports(self):
        # gs_003 brand is "SIERRA AZUL", is_import True
        assert derive_submitter(POOL_CASES["gs_003"]) == "Sierra Azul Imports"

    def test_preserves_existing_mixed_case(self):
        # gs_005 brand is "Stone's Throw" — title() would mangle the possessive
        case = POOL_CASES["gs_005"]
        assert derive_submitter(case) == "Stone's Throw LLC"


class TestPoolLoadResilience:
    def test_missing_cases_file_yields_empty_pool(self, monkeypatch, tmp_path):
        monkeypatch.setattr(simulation_pool, "_CASES_JSONL", tmp_path / "missing.jsonl")
        assert simulation_pool._load_pool() == {}

    def test_malformed_jsonl_yields_empty_pool(self, monkeypatch, tmp_path):
        bad = tmp_path / "cases.jsonl"
        bad.write_text("{not valid json\n")
        monkeypatch.setattr(simulation_pool, "_CASES_JSONL", bad)
        assert simulation_pool._load_pool() == {}

    def test_missing_required_key_yields_empty_pool(self, monkeypatch, tmp_path):
        bad = tmp_path / "cases.jsonl"
        bad.write_text('{"inputs": {}}\n')  # missing "case_id", "application", etc.
        monkeypatch.setattr(simulation_pool, "_CASES_JSONL", bad)
        assert simulation_pool._load_pool() == {}

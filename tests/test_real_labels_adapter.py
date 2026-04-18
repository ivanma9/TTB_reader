import json
from pathlib import Path

from evals.real_labels.adapter import build_cases_with_corrections


def _raw(tmp_path):
    src = tmp_path / "source.jsonl"
    src.write_text(json.dumps({
        "ttb_id": "18011001000033",
        "images": [{"panel": "front", "path": "images/f.jpg"}],
        "ground_truth": {
            "brand_name": "Cartavio",
            "class_name": "other rum gold fb",
            "applicant_name": "Import Co LLC",
            "address_state": None,
            "origin": "Peru",
        },
        "cola_cloud_ocr_reference": {
            "ocr_abv": 40.0,
            "ocr_volume": 750,
            "ocr_volume_unit": "milliliters",
        },
    }) + "\n")
    return src


def test_build_applies_corrections_and_tags_source(tmp_path):
    src = _raw(tmp_path)
    corr = tmp_path / "corrections.jsonl"
    corr.write_text(json.dumps({
        "case_id": "ttb_18011001000033",
        "labeled_by": "tester",
        "labeled_at": "2026-04-17",
        "corrections": {
            "class_type": "Rum",
            "producer_name_address": "Destileria Cartavio S.A., La Libertad, Peru",
        },
    }) + "\n")
    out = tmp_path / "cases.jsonl"

    summary = build_cases_with_corrections(source=src, corrections=corr, output=out)
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    case = rows[0]
    assert case["inputs"]["application"]["class_type"] == "Rum"
    assert "Cartavio" in case["inputs"]["application"]["producer_name_address"]
    assert case["metadata"]["field_sources"]["class_type"] == "hand_labeled"
    assert case["metadata"]["field_sources"]["brand_name"] == "csv"
    assert summary["corrected_cases"] == 1


def test_build_leaves_uncorrected_cases_on_csv_truth(tmp_path):
    src = _raw(tmp_path)
    corr = tmp_path / "corrections.jsonl"
    corr.write_text("")
    out = tmp_path / "cases.jsonl"

    build_cases_with_corrections(source=src, corrections=corr, output=out)
    row = json.loads(out.read_text().splitlines()[0])
    assert row["inputs"]["application"]["class_type"] == "other rum gold fb"
    assert row["metadata"]["field_sources"]["class_type"] == "csv"

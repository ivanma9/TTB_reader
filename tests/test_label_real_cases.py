import json
from pathlib import Path

from scripts.label_real_cases import load_corrections, save_correction


def test_load_corrections_empty_file_returns_empty_dict(tmp_path):
    p = tmp_path / "corrections.jsonl"
    p.write_text("")
    assert load_corrections(p) == {}


def test_load_corrections_keys_by_case_id(tmp_path):
    p = tmp_path / "corrections.jsonl"
    p.write_text(
        '{"case_id": "ttb_A", "corrections": {"class_type": "Rum"}}\n'
        '{"case_id": "ttb_B", "corrections": {}}\n'
    )
    out = load_corrections(p)
    assert out["ttb_A"]["corrections"]["class_type"] == "Rum"
    assert out["ttb_B"]["corrections"] == {}


def test_save_correction_appends_to_file(tmp_path):
    p = tmp_path / "corrections.jsonl"
    p.write_text("")
    save_correction(
        p,
        case_id="ttb_X",
        labeled_by="tester",
        corrections={"class_type": "Whiskey"},
    )
    lines = p.read_text().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["case_id"] == "ttb_X"
    assert row["corrections"]["class_type"] == "Whiskey"
    assert "labeled_at" in row


def test_save_correction_replaces_existing_entry(tmp_path):
    p = tmp_path / "corrections.jsonl"
    save_correction(p, case_id="ttb_X", labeled_by="a", corrections={"class_type": "X1"})
    save_correction(p, case_id="ttb_X", labeled_by="b", corrections={"class_type": "X2"})
    rows = [json.loads(l) for l in p.read_text().splitlines()]
    assert len(rows) == 1, "second save must replace, not duplicate"
    assert rows[0]["corrections"]["class_type"] == "X2"

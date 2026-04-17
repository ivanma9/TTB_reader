#!/usr/bin/env python3
"""Smoke test: sends one real multipart /verify request against a running server.

Usage:
    python scripts/smoke_verify.py [base_url]

Exits 0 on success, non-zero on failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
FIXTURE = Path(__file__).resolve().parents[1] / "evals" / "golden_set" / "fixtures" / "gs_001.png"

STANDARD_WARNING = (
    "GOVERNMENT WARNING: According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth "
    "defects. Consumption of alcoholic beverages impairs your ability to drive "
    "a car or operate machinery, and may cause health problems."
)

FORM = {
    "brand_name": "OLD TOM DISTILLERY",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "alcohol_content": "45% Alc./Vol. (90 Proof)",
    "net_contents": "750 mL",
    "producer_name_address": "Old Tom Distillery, Louisville, KY",
    "government_warning": STANDARD_WARNING,
}


def fail(msg: str) -> None:
    print(f"[SMOKE FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    try:
        import httpx
    except ImportError:
        fail("httpx is required: pip install httpx")

    # 1. Health check
    print(f"Checking {BASE_URL}/healthz ...")
    r = httpx.get(f"{BASE_URL}/healthz", timeout=10)
    if r.status_code != 200:
        fail(f"/healthz returned {r.status_code}")
    if r.json().get("status") != "ok":
        fail(f"/healthz body unexpected: {r.text}")
    print("  /healthz OK")

    # 2. Real verification request
    if not FIXTURE.exists():
        fail(f"Fixture not found: {FIXTURE}")

    print(f"Sending POST /verify with gs_001.png ...")
    with FIXTURE.open("rb") as img_file:
        r = httpx.post(
            f"{BASE_URL}/verify",
            data=FORM,
            files={"label_image": ("gs_001.png", img_file, "image/png")},
            timeout=60,
        )

    if r.status_code != 200:
        fail(f"/verify returned {r.status_code}: {r.text[:300]}")

    body = r.text
    if "All Fields Match" not in body:
        fail("/verify response missing 'All Fields Match' verdict banner")

    print("  /verify OK — gs_001 returned a match result")
    print("[SMOKE PASS]")


if __name__ == "__main__":
    main()

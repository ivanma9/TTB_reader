#!/usr/bin/env python3
"""Download PaddleOCR model weights into the cache directory before first evaluation.

Usage:
    python scripts/bootstrap_models.py

Environment:
    PADDLEOCR_HOME  Override model cache directory (default: ~/.paddleocr)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

model_dir = Path(os.environ.get("PADDLEOCR_HOME", os.path.expanduser("~/.paddleocr")))
model_dir.mkdir(parents=True, exist_ok=True)
print(f"Bootstrapping PaddleOCR models into {model_dir} ...")

try:
    from paddleocr import PaddleOCR  # type: ignore
except ImportError:
    print("ERROR: paddleocr is not installed. Run: pip install paddleocr paddlepaddle", file=sys.stderr)
    sys.exit(1)

for version in ("PP-OCRv5", "PP-OCRv4"):
    try:
        print(f"  Trying {version} ...")
        PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False, ocr_version=version, show_log=True)
        print(f"  {version} ready.")
        break
    except Exception as exc:
        print(f"  {version} failed: {exc}")
else:
    print("  Falling back to default PaddleOCR version ...")
    PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False, show_log=True)

print("Bootstrap complete.")

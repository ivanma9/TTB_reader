"""PaddleOCR integration — extract sorted OcrLine records from an image."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

from alc_label_verifier.models import OcrLine
from alc_label_verifier.preprocessing import preprocess

logger = logging.getLogger(__name__)

_ocr_lock = threading.Lock()
_ocr_instance = None


def _get_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        with _ocr_lock:
            if _ocr_instance is None:
                from paddleocr import PaddleOCR  # type: ignore

                # PP-OCRv5 mobile preferred; fall back to PP-OCRv4 then default
                for version in ("PP-OCRv5", "PP-OCRv4"):
                    try:
                        _ocr_instance = PaddleOCR(
                            use_angle_cls=True,
                            lang="en",
                            use_gpu=False,
                            ocr_version=version,
                            show_log=False,
                        )
                        break
                    except TypeError:
                        # Unknown kwarg; try without version parameter
                        continue
                    except Exception as exc:
                        logger.warning("PaddleOCR init with %s failed: %s", version, exc)
                        continue

                if _ocr_instance is None:
                    _ocr_instance = PaddleOCR(
                        use_angle_cls=True,
                        lang="en",
                        use_gpu=False,
                        show_log=False,
                    )
    return _ocr_instance


def _bbox_centers(bbox: Any) -> tuple[float, float]:
    """Return (y_center, x_center) from a 4-point bounding box."""
    try:
        pts = list(bbox)
        xs = [float(pt[0]) for pt in pts]
        ys = [float(pt[1]) for pt in pts]
        return sum(ys) / len(ys), sum(xs) / len(xs)
    except Exception:
        return 0.0, 0.0


def _parse_legacy_detection(item: Any) -> Optional[OcrLine]:
    """Parse the legacy PaddleOCR format: [bbox, (text, confidence)]."""
    try:
        bbox, text_conf = item
        if isinstance(text_conf, (list, tuple)):
            text, confidence = text_conf
        else:
            return None
        text = str(text).strip()
        if not text:
            return None
        y_c, x_c = _bbox_centers(bbox)
        return OcrLine(
            text=text,
            confidence=float(confidence),
            bbox=[[float(c) for c in pt] for pt in bbox],
            y_center=y_c,
            x_center=x_c,
        )
    except Exception:
        return None


def _parse_dict_detection(item: Dict[str, Any]) -> Optional[OcrLine]:
    """Parse PaddleOCR 2.8+ dict-shaped detection."""
    try:
        text = str(item.get("rec_text") or item.get("text") or "").strip()
        confidence = float(item.get("rec_score") or item.get("confidence") or 0.0)
        bbox = item.get("dt_poly") or item.get("bbox") or []
        if not text:
            return None
        y_c, x_c = _bbox_centers(bbox) if bbox else (0.0, 0.0)
        bbox_list = [[float(c) for c in pt] for pt in bbox] if bbox else []
        return OcrLine(
            text=text,
            confidence=confidence,
            bbox=bbox_list,
            y_center=y_c,
            x_center=x_c,
        )
    except Exception:
        return None


def _parse_detection(item: Any) -> Optional[OcrLine]:
    if item is None:
        return None
    if isinstance(item, dict):
        return _parse_dict_detection(item)
    return _parse_legacy_detection(item)


def extract_lines(image_path: str) -> List[OcrLine]:
    """Run PaddleOCR on image_path and return sorted OcrLine list."""
    arr = preprocess(image_path)
    ocr = _get_ocr()
    raw = ocr.ocr(arr, cls=True)

    if not raw:
        return []

    # raw structure varies by PaddleOCR version:
    #   Legacy (≤2.6): [[detection, ...]] — outer list is per page
    #   Newer:         [detection, ...] or [[detection, ...]]
    # Unwrap one level if the first element is a list of detections.
    detections = raw
    if raw and isinstance(raw[0], list):
        detections = raw[0]

    lines: List[OcrLine] = []
    for item in (detections or []):
        line = _parse_detection(item)
        if line is not None:
            lines.append(line)

    # Sort top-to-bottom (quantised to 20px rows), then left-to-right
    lines.sort(key=lambda l: (round(l.y_center / 20) * 20, l.x_center))
    return lines


def build_full_text(lines: List[OcrLine]) -> str:
    return " ".join(l.text for l in lines)

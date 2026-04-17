"""Field-level matching logic for the label verifier."""

from __future__ import annotations

import re
import string
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz  # type: ignore

from alc_label_verifier._constants import (
    FUZZY_MATCH_THRESHOLD,
    GOVERNMENT_WARNING_PREFIX,
    STANDARD_CONFIDENCE_THRESHOLD,
    USABLE_CONFIDENCE_FLOOR,
    WARNING_BODY_COMPLETENESS_THRESHOLD,
    WARNING_CONFIDENCE_THRESHOLD,
    MIN_USABLE_LINES,
)
from alc_label_verifier.models import FieldResult, OcrLine

# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def normalize_text(text: str) -> str:
    """Lowercase, remove punctuation, collapse whitespace."""
    t = text.lower()
    t = t.translate(_PUNCT_TABLE)
    t = " ".join(t.split())
    return t


# ---------------------------------------------------------------------------
# Numeric parsers
# ---------------------------------------------------------------------------

_ABV_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_PROOF_RE = re.compile(r"\(?\s*(\d+(?:\.\d+)?)\s*(?:proof|PROOF)\s*\)?", re.IGNORECASE)

# Require a word boundary before the number to avoid matching digits inside other tokens.
# Bare 'l'/'L' is excluded: only 'mL', 'ML', 'ml' and 'L' (uppercase alone) are safe.
_NET_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(fl\.?\s*oz|oz|mL|ML|ml|L)\b",
    re.IGNORECASE,
)


def parse_alcohol(text: str) -> Optional[Tuple[float, Optional[float]]]:
    """Return (abv_pct, proof_or_None) or None if not parseable."""
    m = _ABV_RE.search(text)
    if not m:
        return None
    abv = float(m.group(1))
    pm = _PROOF_RE.search(text)
    proof = float(pm.group(1)) if pm else None
    return (abv, proof)


def parse_net_contents(text: str) -> Optional[Tuple[float, str]]:
    """Return (quantity_ml_or_oz, unit_string) or None if not parseable.

    Normalises L → mL so '1 L' == '1000 mL'.
    """
    m = _NET_RE.search(text)
    if not m:
        return None
    qty = float(m.group(1))
    unit_raw = m.group(2).lower().replace(" ", "").replace(".", "")
    if unit_raw == "l":
        return (qty * 1000, "ml")
    if unit_raw.startswith("fl") or unit_raw == "oz":
        return (qty, "oz")
    return (qty, "ml")


def _alcohol_values_match(a: Tuple[float, Optional[float]], b: Tuple[float, Optional[float]]) -> bool:
    abv_a, proof_a = a
    abv_b, proof_b = b
    if abs(abv_a - abv_b) > 0.1:
        return False
    if proof_a is not None and proof_b is not None:
        return abs(proof_a - proof_b) < 0.5
    return True


def _net_values_match(a: Tuple[float, str], b: Tuple[float, str]) -> bool:
    qty_a, unit_a = a
    qty_b, unit_b = b
    if unit_a != unit_b:
        return False
    return abs(qty_a - qty_b) < 1.0


# ---------------------------------------------------------------------------
# Core text comparison helper
# ---------------------------------------------------------------------------


def _compare_text(
    ocr_text: str,
    expected: str,
    confidence: float,
    *,
    use_fuzzy: bool = True,
    confidence_threshold: float = STANDARD_CONFIDENCE_THRESHOLD,
) -> FieldResult:
    """Compare normalized OCR text to expected; return FieldResult."""
    norm_ocr = normalize_text(ocr_text)
    norm_exp = normalize_text(expected)

    if not norm_ocr:
        return FieldResult(status="needs_review", reason_code="unreadable")

    if norm_ocr == norm_exp:
        reason = "exact_match" if ocr_text.strip() == expected.strip() else "normalized_match"
        return FieldResult(status="match", reason_code=reason)

    if use_fuzzy:
        score = fuzz.token_sort_ratio(norm_ocr, norm_exp)
        if score >= FUZZY_MATCH_THRESHOLD:
            return FieldResult(status="match", reason_code="normalized_match")

    if confidence >= confidence_threshold:
        return FieldResult(status="mismatch", reason_code="wrong_value")

    return FieldResult(status="needs_review", reason_code="unreadable")


# ---------------------------------------------------------------------------
# OCR partition: separate header vs warning section
# ---------------------------------------------------------------------------


def partition_lines(
    lines: List[OcrLine],
) -> Tuple[List[OcrLine], Optional[OcrLine], List[OcrLine]]:
    """Split sorted lines into (header_lines, warning_anchor_line, warning_body_lines).

    Uses a case-insensitive check so title-cased "Government Warning:" is still
    correctly partitioned (the prefix-case error is caught later by the matcher).
    """
    for i, line in enumerate(lines):
        if line.text.upper().startswith("GOVERNMENT WARNING"):
            return lines[:i], line, lines[i + 1 :]
    return lines, None, []


def _split_class_and_lower(
    header_lines: List[OcrLine],
) -> Tuple[List[OcrLine], List[OcrLine], Optional[OcrLine]]:
    """Split header lines into (class_region, lower_region, alcohol_anchor).

    The alcohol+net line contains a '%' pattern — everything above it (below
    the brand) is the class region; everything below is producer/country.
    When the alcohol line cannot be found, a midpoint heuristic is used.
    """
    alcohol_idx: Optional[int] = None
    for i, line in enumerate(header_lines):
        if _ABV_RE.search(line.text):
            alcohol_idx = i
            break

    if alcohol_idx is None:
        # Fallback: split at midpoint of non-brand lines
        non_brand = header_lines[1:]
        mid = max(1, len(non_brand) // 2)
        return non_brand[:mid], non_brand[mid:], None

    class_lines = header_lines[1:alcohol_idx]
    alcohol_line = header_lines[alcohol_idx]
    lower_lines = header_lines[alcohol_idx + 1 :]
    return class_lines, lower_lines, alcohol_line


# ---------------------------------------------------------------------------
# Individual field matchers
# ---------------------------------------------------------------------------


def match_brand_name(lines: List[OcrLine], expected: str) -> FieldResult:
    """Brand: best-matching line or multi-line concatenation from the top 3 OCR lines.

    Scanning the top 3 (rather than blindly taking lines[0]) handles rare
    cases where a decoration or border artifact is detected above the brand text.
    Multi-line concatenation handles brands that span two OCR lines.
    """
    if not lines:
        return FieldResult(status="needs_review", reason_code="unreadable")

    norm_exp = normalize_text(expected)
    candidates = lines[:min(3, len(lines))]

    # Build single-line and multi-line concatenation candidates
    combined_candidates = [
        (" ".join(l.text for l in candidates[:n]), min(l.confidence for l in candidates[:n]))
        for n in range(1, len(candidates) + 1)
    ]

    best_text, best_conf = max(
        combined_candidates,
        key=lambda tc: fuzz.token_sort_ratio(normalize_text(tc[0]), norm_exp),
    )

    if best_conf < STANDARD_CONFIDENCE_THRESHOLD:
        return FieldResult(status="needs_review", reason_code="unreadable")

    return _compare_text(best_text, expected, best_conf, use_fuzzy=True)


def match_class_type(class_lines: List[OcrLine], expected: str) -> FieldResult:
    """Class type: collect all class-region lines."""
    if not class_lines:
        return FieldResult(status="needs_review", reason_code="unreadable")

    confidence = min(l.confidence for l in class_lines)
    ocr_text = " ".join(l.text for l in class_lines)

    if confidence < STANDARD_CONFIDENCE_THRESHOLD:
        return FieldResult(status="needs_review", reason_code="unreadable")

    return _compare_text(ocr_text, expected, confidence, use_fuzzy=True)


def match_alcohol_content(all_lines: List[OcrLine], expected: str) -> FieldResult:
    """Alcohol content: parse ABV+proof from the best-matching line."""
    expected_parsed = parse_alcohol(expected)
    if expected_parsed is None:
        best = _best_candidate_any(all_lines, expected)
        if best is None:
            return FieldResult(status="needs_review", reason_code="unreadable")
        return _compare_text(best.text, expected, best.confidence, use_fuzzy=True)

    # Collect all lines with a parseable ABV; pick highest-confidence match
    match_line: Optional[OcrLine] = None
    mismatch_line: Optional[OcrLine] = None

    for line in all_lines:
        parsed = parse_alcohol(line.text)
        if parsed is None:
            continue
        if _alcohol_values_match(parsed, expected_parsed):
            if match_line is None or line.confidence > match_line.confidence:
                match_line = line
        else:
            if mismatch_line is None or line.confidence > mismatch_line.confidence:
                mismatch_line = line

    if match_line is not None:
        reason = "exact_match" if match_line.text.strip() == expected.strip() else "normalized_match"
        return FieldResult(status="match", reason_code=reason)

    if mismatch_line is not None:
        if mismatch_line.confidence >= STANDARD_CONFIDENCE_THRESHOLD:
            return FieldResult(status="mismatch", reason_code="wrong_value")
        return FieldResult(status="needs_review", reason_code="unreadable")

    return FieldResult(status="needs_review", reason_code="unreadable")


def match_net_contents(all_lines: List[OcrLine], expected: str) -> FieldResult:
    """Net contents: parse quantity+unit from the best-matching line."""
    expected_parsed = parse_net_contents(expected)
    if expected_parsed is None:
        best = _best_candidate_any(all_lines, expected)
        if best is None:
            return FieldResult(status="needs_review", reason_code="unreadable")
        return _compare_text(best.text, expected, best.confidence, use_fuzzy=True)

    # Collect all lines with a parseable net value; prefer lines without `%`
    match_line: Optional[OcrLine] = None
    mismatch_line: Optional[OcrLine] = None

    for line in all_lines:
        parsed = parse_net_contents(line.text)
        if parsed is None:
            continue
        if _net_values_match(parsed, expected_parsed):
            if match_line is None or line.confidence > match_line.confidence:
                match_line = line
        else:
            if mismatch_line is None or line.confidence > mismatch_line.confidence:
                mismatch_line = line

    if match_line is not None:
        reason = "exact_match" if match_line.text.strip() == expected.strip() else "normalized_match"
        return FieldResult(status="match", reason_code=reason)

    if mismatch_line is not None:
        if mismatch_line.confidence >= STANDARD_CONFIDENCE_THRESHOLD:
            return FieldResult(status="mismatch", reason_code="wrong_value")
        return FieldResult(status="needs_review", reason_code="unreadable")

    return FieldResult(status="needs_review", reason_code="unreadable")


def match_producer_name_address(
    lower_lines: List[OcrLine], expected: str
) -> FieldResult:
    """Producer: normalized comparison (strict) from lower region.

    Excludes 'Country of Origin:' lines. A narrow fuzzy tolerance (≥ 92 via
    token_set_ratio) accepts minor OCR slips without broadening to false matches.
    """
    producer_lines = [
        l for l in lower_lines
        if not l.text.lower().startswith("country of origin")
    ]

    if not producer_lines:
        return FieldResult(status="needs_review", reason_code="unreadable")

    confidence = min(l.confidence for l in producer_lines)
    ocr_text = " ".join(l.text for l in producer_lines)

    if confidence < STANDARD_CONFIDENCE_THRESHOLD:
        return FieldResult(status="needs_review", reason_code="unreadable")

    norm_ocr = normalize_text(ocr_text)
    norm_exp = normalize_text(expected)

    if norm_ocr == norm_exp:
        reason = "exact_match" if ocr_text.strip() == expected.strip() else "normalized_match"
        return FieldResult(status="match", reason_code=reason)

    # Narrow fuzzy: allow minor single-character OCR slips but not address-level changes
    if fuzz.token_set_ratio(norm_ocr, norm_exp) >= 92:
        return FieldResult(status="match", reason_code="normalized_match")

    return FieldResult(status="mismatch", reason_code="wrong_value")


def _is_country_anchor(text: str) -> bool:
    prefix = text.lower()[:25]  # only check first 25 chars
    return fuzz.partial_ratio(prefix, "country of origin") >= 85


def match_country_of_origin(
    lower_lines: List[OcrLine],
    expected: Optional[str],
    is_import: bool,
) -> FieldResult:
    """Country of origin: conditional rules."""
    if not is_import:
        return FieldResult(status="not_applicable", reason_code="not_applicable")

    country_lines = [l for l in lower_lines if _is_country_anchor(l.text)]

    if not country_lines:
        if not lower_lines or _region_confidence(lower_lines) < STANDARD_CONFIDENCE_THRESHOLD:
            return FieldResult(status="needs_review", reason_code="unreadable")
        return FieldResult(status="mismatch", reason_code="missing_required")

    line = country_lines[0]
    confidence = line.confidence

    if confidence < STANDARD_CONFIDENCE_THRESHOLD:
        return FieldResult(status="needs_review", reason_code="unreadable")

    raw = line.text
    # Extract country value after the colon; handles OCR typos in the anchor phrase
    colon_idx = raw.find(":")
    after = raw[colon_idx + 1:].strip() if colon_idx != -1 else ""

    if not after:
        if expected:
            return FieldResult(status="mismatch", reason_code="missing_required")
        return FieldResult(status="needs_review", reason_code="unreadable")

    norm_after = normalize_text(after)
    norm_expected = normalize_text(expected or "")

    if norm_after == norm_expected:
        # Case-insensitive exact match: labels often render country in all-caps
        reason = "exact_match" if after.strip().lower() == (expected or "").strip().lower() else "normalized_match"
        return FieldResult(status="match", reason_code=reason)

    return FieldResult(status="mismatch", reason_code="wrong_value")


def match_government_warning(
    anchor_line: Optional[OcrLine],
    body_lines: List[OcrLine],
    expected_full: str,
) -> FieldResult:
    """Government warning: strict prefix + normalized body comparison."""
    if anchor_line is None:
        return FieldResult(status="needs_review", reason_code="unreadable")

    if anchor_line.confidence < WARNING_CONFIDENCE_THRESHOLD:
        return FieldResult(status="needs_review", reason_code="unreadable")

    # --- Prefix validation ---
    raw_prefix_line = anchor_line.text.strip()

    if raw_prefix_line.upper().startswith(GOVERNMENT_WARNING_PREFIX):
        if not raw_prefix_line.startswith(GOVERNMENT_WARNING_PREFIX):
            return FieldResult(status="mismatch", reason_code="warning_prefix_error")
    else:
        return FieldResult(status="needs_review", reason_code="unreadable")

    # --- Collect warning body (inline + subsequent lines, deduplicated) ---
    inline_body = raw_prefix_line[len(GOVERNMENT_WARNING_PREFIX):].strip()
    body_text_parts = []
    if inline_body:
        body_text_parts.append(inline_body)
    body_text_parts.extend(l.text for l in body_lines)
    ocr_body = " ".join(body_text_parts)

    if not ocr_body.strip():
        return FieldResult(status="needs_review", reason_code="unreadable")

    # --- Body confidence ---
    if body_lines:
        body_confidence = min(l.confidence for l in body_lines)
        if body_confidence < WARNING_CONFIDENCE_THRESHOLD:
            return FieldResult(status="needs_review", reason_code="unreadable")

    # --- Parse expected body ---
    exp_stripped = expected_full.strip()
    if exp_stripped.upper().startswith(GOVERNMENT_WARNING_PREFIX):
        expected_body = exp_stripped[len(GOVERNMENT_WARNING_PREFIX):].strip()
    else:
        expected_body = exp_stripped

    # --- Completeness check (catches partial occlusion) ---
    norm_ocr_body = normalize_text(ocr_body)
    norm_exp_body = normalize_text(expected_body)

    if len(norm_exp_body) > 0:
        completeness = len(norm_ocr_body) / len(norm_exp_body)
        if completeness < WARNING_BODY_COMPLETENESS_THRESHOLD:
            return FieldResult(status="needs_review", reason_code="unreadable")

    # --- Body text comparison ---
    if norm_ocr_body == norm_exp_body:
        return FieldResult(status="match", reason_code="exact_match")

    similarity = fuzz.ratio(norm_ocr_body, norm_exp_body)
    if similarity >= 99:
        # Near-identical — likely minor OCR noise, not a real deviation
        return FieldResult(status="needs_review", reason_code="unreadable")

    return FieldResult(status="mismatch", reason_code="warning_text_mismatch")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _region_confidence(lines: List[OcrLine]) -> float:
    if not lines:
        return 0.0
    return sum(l.confidence for l in lines) / len(lines)


def _best_candidate_any(
    lines: List[OcrLine], expected: str
) -> Optional[OcrLine]:
    """Find the line with highest token_sort similarity to expected (min 60)."""
    norm_exp = normalize_text(expected)
    best_score = -1
    best_line: Optional[OcrLine] = None
    for line in lines:
        score = fuzz.token_sort_ratio(normalize_text(line.text), norm_exp)
        if score > best_score:
            best_score = score
            best_line = line
    if best_score < 60:
        return None
    return best_line


def is_globally_unreadable(lines: List[OcrLine]) -> bool:
    """True if OCR quality is too poor to make any hard decisions."""
    usable = [l for l in lines if l.confidence >= USABLE_CONFIDENCE_FLOOR]
    return len(usable) < MIN_USABLE_LINES

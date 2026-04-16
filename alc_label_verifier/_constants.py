"""Shared constants for the label verifier."""

from __future__ import annotations

FIELD_NAMES = (
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "producer_name_address",
    "country_of_origin",
    "government_warning",
)

STANDARD_CONFIDENCE_THRESHOLD = 0.80
WARNING_CONFIDENCE_THRESHOLD = 0.90

# A line is "usable" if its confidence meets this floor
USABLE_CONFIDENCE_FLOOR = 0.40

# Trigger global-unreadable if fewer than this many usable lines returned
MIN_USABLE_LINES = 4

# Maximum image edge (longest side) for preprocessing resize
MAX_IMAGE_EDGE = 2048

# rapidfuzz WRatio score (0-100) required to accept a fuzzy text match
FUZZY_MATCH_THRESHOLD = 85

GOVERNMENT_WARNING_PREFIX = "GOVERNMENT WARNING:"

STANDARD_WARNING_BODY = (
    "According to the Surgeon General, women should not drink alcoholic "
    "beverages during pregnancy because of the risk of birth defects. "
    "Consumption of alcoholic beverages impairs your ability to drive a car "
    "or operate machinery, and may cause health problems."
)

# Captured warning body must be >= this fraction of expected length to avoid "unreadable"
WARNING_BODY_COMPLETENESS_THRESHOLD = 0.60

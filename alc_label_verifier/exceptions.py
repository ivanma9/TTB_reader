"""Domain exceptions for the label verifier."""

from __future__ import annotations


class UnreadableImageError(Exception):
    """Raised when an image cannot be decoded or opened at all."""

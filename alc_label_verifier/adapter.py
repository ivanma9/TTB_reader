"""Eval-harness adapter: ALC_EVAL_TARGET=alc_label_verifier.adapter:target."""

from __future__ import annotations

from typing import Any, Dict

from alc_label_verifier.service import verify_label


def target(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Adapter hook consumed by evals/adapter.py via ALC_EVAL_TARGET."""
    image_path: str = inputs["label_image_path"]
    application: Dict[str, Any] = inputs["application"]
    return verify_label(image_path, application)

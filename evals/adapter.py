"""Stable adapter entrypoint for golden-set evals.

By default this resolves to the local reference target so the harness can be
smoke-tested before a real verifier exists. To point the eval runner at an
actual agent, set `ALC_EVAL_TARGET=module_path:function_name`.
"""

from __future__ import annotations

import importlib
import os
from functools import lru_cache
from typing import Any, Callable, Dict

DEFAULT_TARGET_SPEC = "evals.reference_target:target"
ENV_VAR_NAME = "ALC_EVAL_TARGET"


def _load_callable(spec: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    module_name, sep, func_name = spec.partition(":")
    if not sep or not module_name or not func_name:
        raise ValueError(
            f"Invalid target spec {spec!r}. Expected format 'module:function'."
        )

    module = importlib.import_module(module_name)
    target_func = getattr(module, func_name, None)
    if target_func is None or not callable(target_func):
        raise ValueError(f"Target {spec!r} did not resolve to a callable.")
    return target_func


@lru_cache(maxsize=1)
def resolve_target() -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    spec = os.environ.get(ENV_VAR_NAME, DEFAULT_TARGET_SPEC)
    return _load_callable(spec)


def target(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Adapter hook used by the eval runner."""
    return resolve_target()(inputs)


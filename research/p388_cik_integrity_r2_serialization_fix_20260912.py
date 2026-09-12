from __future__ import annotations

import json
import math
import runpy

import pandas as pd

_ORIG_DUMPS = json.dumps


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if value is pd.NA:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if not isinstance(value, (str, bytes, bool, int, float, type(None))) and hasattr(value, "item"):
        try:
            return _clean(value.item())
        except Exception:
            pass
    return value


def _safe_dumps(obj, *args, **kwargs):
    # Preserve the original strict JSON contract while preventing pandas/numpy/non-finite
    # transport values from invalidating an otherwise-completed scientific audit.
    kwargs["allow_nan"] = False
    return _ORIG_DUMPS(_clean(obj), *args, **kwargs)


json.dumps = _safe_dumps
runpy.run_path("research/p388_cik_integrity_r2_20260912.py", run_name="__main__")

from __future__ import annotations

"""Rebuild canonical forward-observer artifacts at a historical as-of date.

This utility only truncates already-durable dated observations and recomputes
the same summary metrics used by the native observers. It does not alter
signals, model parameters, holdings, sizing authority, promotion authority,
broker state, or live-trading state.
"""

import argparse
import copy
import json
import math
import statistics
from pathlib import Path
from typing import Any

ENDPOINT_COST = 0.0025


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _product_return(values: list[float]) -> float:
    eq = 1.0
    for value in values:
        eq *= 1.0 + float(value)
    return eq - 1.0


def _metrics(values: list[float], include_exit_cost: bool = False) -> dict[str, float | int | None]:
    q = [float(x) for x in values]
    if not q:
        return {
            "days": 0,
            "cumulative_return": 0.0,
            "max_drawdown": 0.0,
            "annualized_vol": None,
            "sharpe_rf0": None,
        }
    if include_exit_cost:
        q = list(q)
        q[-1] -= ENDPOINT_COST

    equity: list[float] = []
    cur = 1.0
    peak = 1.0
    max_dd = 0.0
    for value in q:
        cur *= 1.0 + value
        equity.append(cur)
        peak = max(peak, cur)
        max_dd = min(max_dd, cur / peak - 1.0)

    vol = statistics.stdev(q) * math.sqrt(252.0) if len(q) > 1 else None
    ann = statistics.mean(q) * 252.0 if len(q) > 1 else None
    sharpe = ann / vol if vol not in (None, 0.0) and ann is not None else None
    return {
        "days": len(q),
        "cumulative_return": equity[-1] - 1.0,
        "max_drawdown": max_dd,
        "annualized_vol": vol,
        "sharpe_rf0": sharpe,
    }


def _rows_through(rows: list[dict[str, Any]], asof: str) -> list[dict[str, Any]]:
    return [copy.deepcopy(row) for row in rows if str(row.get("date") or "")[:10] <= asof]


def truncate_p249(payload: dict[str, Any], asof: str) -> dict[str, Any]:
    out = copy.deepcopy(payload)
    forward = out.setdefault("forward", {})
    rows = _rows_through(list(forward.get("observations") or []), asof)
    core = [float(row["p249_core_net"]) for row in rows]
    combined = [float(row["p249_plus_p266_net"]) for row in rows]
    increment = [float(row["satellite_increment_net"]) for row in rows]

    forward["observations"] = rows
    forward["first_close"] = rows[0]["date"] if rows else None
    forward["latest_close"] = rows[-1]["date"] if rows else None
    forward["p249_core_net"] = _metrics(core)
    forward["p249_plus_p266_net"] = _metrics(combined)
    forward["satellite_increment_cumulative"] = _product_return(increment) if increment else 0.0
    out["asof_recovery"] = {
        "requested_asof": asof,
        "source_observed_at": payload.get("observed_at"),
        "method": "truncate_durable_native_observations",
        "reporting_only": True,
    }
    return out


def truncate_challenger(payload: dict[str, Any], asof: str) -> dict[str, Any]:
    out = copy.deepcopy(payload)
    forward = out.setdefault("forward", {})
    challenger_rows = _rows_through(list(forward.get("challenger_observations") or []), asof)
    matched_rows = _rows_through(list(forward.get("matched_control_observations") or []), asof)

    challenger_dates = [str(row.get("date"))[:10] for row in challenger_rows]
    matched_dates = [str(row.get("date"))[:10] for row in matched_rows]
    if challenger_dates != matched_dates:
        raise RuntimeError("challenger and matched-control observation dates diverged")

    challenger = [float(row["net_return"]) for row in challenger_rows]
    matched = [float(row["net_return"]) for row in matched_rows]
    incumbent = [float(row["core_return"]) for row in challenger_rows]

    forward["challenger_observations"] = challenger_rows
    forward["matched_control_observations"] = matched_rows
    forward["first_close"] = challenger_dates[0] if challenger_dates else None
    forward["latest_close"] = challenger_dates[-1] if challenger_dates else None
    forward["incumbent"] = _metrics(incumbent, include_exit_cost=False)
    forward["challenger_if_flattened_now"] = _metrics(challenger, include_exit_cost=True)
    forward["matched_control_if_flattened_now"] = _metrics(matched, include_exit_cost=True)
    forward["challenger_minus_matched_cumulative"] = (
        _product_return(challenger) - _product_return(matched) if challenger else 0.0
    )
    forward["challenger_minus_incumbent_cumulative"] = (
        _product_return(challenger) - _product_return(incumbent) if challenger else 0.0
    )
    out["asof_recovery"] = {
        "requested_asof": asof,
        "source_observed_at": payload.get("observed_at"),
        "method": "truncate_durable_native_observations",
        "reporting_only": True,
    }
    return out


def self_test() -> None:
    p249 = {
        "observed_at": "2026-09-18T00:00:00+00:00",
        "forward": {
            "observations": [
                {"date": "2026-09-10", "p249_core_net": 0.01, "p249_plus_p266_net": 0.02, "satellite_increment_net": 0.01},
                {"date": "2026-09-11", "p249_core_net": -0.01, "p249_plus_p266_net": -0.02, "satellite_increment_net": -0.01},
                {"date": "2026-09-14", "p249_core_net": 0.03, "p249_plus_p266_net": 0.04, "satellite_increment_net": 0.01},
            ]
        },
    }
    a = truncate_p249(p249, "2026-09-11")
    assert a["forward"]["latest_close"] == "2026-09-11"
    assert a["forward"]["p249_core_net"]["days"] == 2
    assert abs(a["forward"]["satellite_increment_cumulative"] - ((1.01 * 0.99) - 1.0)) < 1e-12

    challenger = {
        "observed_at": "2026-09-18T00:00:00+00:00",
        "forward": {
            "challenger_observations": [
                {"date": "2026-09-11", "net_return": 0.01, "core_return": 0.005},
                {"date": "2026-09-14", "net_return": -0.01, "core_return": -0.005},
                {"date": "2026-09-15", "net_return": 0.02, "core_return": 0.01},
            ],
            "matched_control_observations": [
                {"date": "2026-09-11", "net_return": 0.002, "core_return": 0.005},
                {"date": "2026-09-14", "net_return": -0.002, "core_return": -0.005},
                {"date": "2026-09-15", "net_return": 0.003, "core_return": 0.01},
            ],
        },
    }
    b = truncate_challenger(challenger, "2026-09-14")
    assert b["forward"]["latest_close"] == "2026-09-14"
    assert b["forward"]["challenger_if_flattened_now"]["days"] == 2
    assert b["forward"]["challenger_if_flattened_now"]["cumulative_return"] < _product_return([0.01, -0.01])
    assert b["forward"]["challenger_minus_incumbent_cumulative"] == (
        _product_return([0.01, -0.01]) - _product_return([0.005, -0.005])
    )
    print("FORWARD_ASOF_TAPE_RECOVERY_SELF_TEST=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--asof")
    p.add_argument("--p249", default="research/current/forward_p249_p266_shadow_r1.json")
    p.add_argument("--p558", default="research/current/forward_p558_current_core_shadow_r1.json")
    p.add_argument("--clo", default="research/current/forward_senior_clo_current_core_shadow_r1.json")
    p.add_argument("--output-dir")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    if args.self_test:
        self_test()
        return
    if not args.asof or not args.output_dir:
        p.error("--asof and --output-dir are required unless --self-test")

    out_dir = Path(args.output_dir)
    p249 = truncate_p249(_read(Path(args.p249)), args.asof)
    p558 = truncate_challenger(_read(Path(args.p558)), args.asof)
    clo = truncate_challenger(_read(Path(args.clo)), args.asof)

    _write(out_dir / "forward_p249_p266_shadow_r1.json", p249)
    _write(out_dir / "forward_p558_current_core_shadow_r1.json", p558)
    _write(out_dir / "forward_senior_clo_current_core_shadow_r1.json", clo)
    print(json.dumps({
        "asof": args.asof,
        "p249_days": p249["forward"]["p249_plus_p266_net"]["days"],
        "p558_days": p558["forward"]["challenger_if_flattened_now"]["days"],
        "senior_clo_days": clo["forward"]["challenger_if_flattened_now"]["days"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import math
import runpy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

DECISION_AT = pd.Timestamp("2026-09-11T10:10:57Z")
LEGACY_CORE = Path(__file__).with_name("p279_p249_p266_forward_shadow_observer_r1.py")
LEGACY_ARTIFACT = Path("artifacts/p279_p249_p266_forward_shadow_observer_r1.json")
OUTPUT = Path("artifacts/forward_p558_current_core_shadow_r1.json")
WORKLOAD_ID = "FORWARD_P558_CURRENT_CORE_SHADOW_R1"
MIX = 0.50
MONTHLY_REBALANCE_COST = 0.001
ENDPOINT_COST = 0.0025


def _metrics(x: pd.Series, include_exit_cost: bool = True) -> dict[str, float | int | None]:
    q = x.dropna().astype(float).copy()
    if q.empty:
        return {"days": 0, "cumulative_return": 0.0, "max_drawdown": 0.0, "annualized_vol": None, "sharpe_rf0": None}
    if include_exit_cost:
        q.iloc[-1] -= ENDPOINT_COST
    eq = (1 + q).cumprod()
    vol = float(q.std(ddof=1) * math.sqrt(252)) if len(q) > 1 else None
    ann = float(q.mean() * 252) if len(q) > 1 else None
    return {
        "days": int(len(q)),
        "cumulative_return": float(eq.iloc[-1] - 1),
        "max_drawdown": float((eq / eq.cummax() - 1).min()),
        "annualized_vol": vol,
        "sharpe_rf0": float(ann / vol) if vol and ann is not None else None,
    }


def _simulate(core: pd.Series, alt: pd.Series) -> tuple[pd.Series, list[dict[str, object]]]:
    q = pd.concat([core.rename("core"), alt.rename("alt")], axis=1).dropna().sort_index()
    if q.empty:
        return pd.Series(dtype=float), []
    w_core, w_alt = MIX, 1 - MIX
    last_month = None
    out: list[float] = []
    rows: list[dict[str, object]] = []
    for i, (dt, row) in enumerate(q.iterrows()):
        month = dt.to_period("M")
        rebalance_cost = 0.0
        traded_notional = 0.0
        if last_month is not None and month != last_month:
            traded_notional = abs(w_core - MIX) + abs(w_alt - (1 - MIX))
            rebalance_cost = MONTHLY_REBALANCE_COST * traded_notional
            w_core, w_alt = MIX, 1 - MIX
        r_core, r_alt = float(row.core), float(row.alt)
        gross = w_core * r_core + w_alt * r_alt
        entry_cost = ENDPOINT_COST if i == 0 else 0.0
        net = gross - rebalance_cost - entry_cost
        out.append(net)
        denom = 1 + gross
        if denom > 0:
            w_core = w_core * (1 + r_core) / denom
            w_alt = w_alt * (1 + r_alt) / denom
        rows.append({
            "date": dt.date().isoformat(),
            "core_return": r_core,
            "alt_return": r_alt,
            "gross_return": gross,
            "entry_endpoint_cost": entry_cost,
            "monthly_rebalance_traded_notional": traded_notional,
            "monthly_rebalance_cost": rebalance_cost,
            "net_return": net,
            "post_close_core_weight": w_core,
            "post_close_alt_weight": w_alt,
        })
        last_month = month
    return pd.Series(out, index=q.index, dtype=float), rows


def _scaled_positions(core: dict[str, float], alt: str) -> dict[str, float]:
    out = {s: float(w) * MIX for s, w in core.items()}
    out[alt] = out.get(alt, 0.0) + (1 - MIX)
    return dict(sorted(out.items()))


def main() -> None:
    runpy.run_path(str(LEGACY_CORE), run_name="__main__")
    core_payload = json.loads(LEGACY_ARTIFACT.read_text())
    obs = pd.DataFrame(core_payload.get("forward", {}).get("observations", []))
    if obs.empty:
        core_daily = pd.Series(dtype=float)
    else:
        obs["date"] = pd.to_datetime(obs["date"])
        first_session = DECISION_AT.tz_convert(None).normalize()
        obs = obs[obs["date"] >= first_session].copy()
        core_daily = pd.Series(obs["p249_plus_p266_net"].astype(float).to_numpy(), index=obs["date"], dtype=float)

    now = datetime.now(timezone.utc)
    end = (now + timedelta(days=1)).date().isoformat()
    px = yf.download(["KMLM", "BIL"], start="2026-09-10", end=end, auto_adjust=True, progress=False, threads=False)
    close = px["Close"] if isinstance(px.columns, pd.MultiIndex) else px
    simple = close[["KMLM", "BIL"]].astype(float).pct_change(fill_method=None)
    challenger, challenger_rows = _simulate(core_daily, simple["KMLM"])
    matched, matched_rows = _simulate(core_daily, simple["BIL"])

    core_current = core_payload.get("current_state", {}).get("p249_plus_p266", {})
    status = "FORWARD_OBSERVING" if len(challenger) else "BASELINE_FROZEN_NO_FORWARD_CLOSES"
    core_metrics = _metrics(core_daily, include_exit_cost=False)
    challenger_metrics = _metrics(challenger)
    matched_metrics = _metrics(matched)
    result = {
        "schema": "research.forward_p558_current_core_shadow_r1",
        "workload_id": WORKLOAD_ID,
        "parent": "P558 / P249+P266",
        "decision_at": DECISION_AT.isoformat(),
        "observed_at": now.isoformat(),
        "status": status,
        "contract": {
            "incumbent": "unchanged P249+P266 from canonical forward observer",
            "challenger": "50% unchanged P249+P266 + 50% KMLM",
            "matched_control": "50% unchanged P249+P266 + 50% BIL",
            "fixed_weight": MIX,
            "entry_and_mark_to_market_exit_cost_bps_each": 25,
            "monthly_rebalance_traded_notional_cost_bps": 10,
            "no_weight_date_cost_window_or_identity_search": True,
        },
        "source_pins": {
            "p558_scientific_merge": "eff2c63cc240df3636437a3d3c6aeba1985c13c0",
            "p558_result_run_id": 34587903433,
            "p558_result_artifact_id": 10194372650,
            "incumbent_observer": "research/p279_p249_p266_forward_shadow_observer_r1.py",
        },
        "current_positions": {
            "incumbent": core_current,
            "challenger": _scaled_positions(core_current, "KMLM") if core_current else {},
            "matched_control": _scaled_positions(core_current, "BIL") if core_current else {},
        },
        "forward": {
            "first_close": challenger.index.min().date().isoformat() if len(challenger) else None,
            "latest_close": challenger.index.max().date().isoformat() if len(challenger) else None,
            "incumbent": core_metrics,
            "challenger_if_flattened_now": challenger_metrics,
            "matched_control_if_flattened_now": matched_metrics,
            "challenger_minus_matched_cumulative": float((1 + challenger).prod() - (1 + matched).prod()) if len(challenger) else 0.0,
            "challenger_minus_incumbent_cumulative": float((1 + challenger).prod() - (1 + core_daily).prod()) if len(challenger) else 0.0,
            "challenger_observations": challenger_rows,
            "matched_control_observations": matched_rows,
        },
        "operator_note": "Research shadow only. Always display diversification deltas together with capital opportunity cost versus the unchanged incumbent. No allocation, runtime, broker, or live-trading authority.",
        "boundaries": {"allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
    }
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({"status": status, "forward_days": len(challenger), "challenger_positions": result["current_positions"]["challenger"]}, sort_keys=True))


if __name__ == "__main__":
    main()

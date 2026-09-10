from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from research.forward_bar_contract_v2 import ForwardBarContract, ibkr_bar_to_record, normalize_frame

U = ("SPY", "QQQ", "TLT", "GLD", "DBC")
TOP_K = 2
MODEL_VERSION = "fixed_original_four_factor_top2_r1"
REFERENCE_COST_BPS = 50
FORWARD_NOT_BEFORE_FEATURE_MONTH_END = pd.Timestamp("2026-09-30")
SHAKEDOWN_ANCHOR_DATE = pd.Timestamp("2026-09-09")
SHAKEDOWN_WEIGHTS = {"SPY": 0.0, "QQQ": 0.5, "TLT": 0.0, "GLD": 0.0, "DBC": 0.5}
OUT = Path("artifacts")


def _utc_now() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc))


def _yahoo_normalized() -> pd.DataFrame:
    raw = yf.download(
        list(U), start="2005-01-01", auto_adjust=True, progress=False,
        threads=False, group_by="column",
    )
    rows: list[dict] = []
    for s in U:
        panel = raw.xs(s, axis=1, level=1).dropna(subset=["Open", "High", "Low", "Close"])
        for ts, r in panel.iterrows():
            stamp = pd.Timestamp(ts)
            stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
            rows.append({
                "symbol": s,
                "timestamp": stamp,
                "open": float(r["Open"]),
                "high": float(r["High"]),
                "low": float(r["Low"]),
                "close": float(r["Close"]),
                "volume": float(r.get("Volume", 0) or 0),
                "source": "yahoo_adjusted_research_only",
                "asset_type": "STK",
                "bar_size": "1 day",
                "session": "regular",
                "contract_id": s,
                "wap": np.nan,
                "bar_count": np.nan,
            })
    return normalize_frame(rows)


def _ibkr_shape_fixture() -> dict:
    class Bar:
        date = "2026-09-09T20:00:00Z"
        open = 100.0
        high = 102.0
        low = 99.5
        close = 101.0
        volume = 123456
        wap = 100.8
        barCount = 9876

    class Contract:
        conId = 756733
        localSymbol = "SPY"

    row = ibkr_bar_to_record(
        Bar(), Contract(), symbol="SPY", asset_type="STK",
        bar_size="1 day", session="regular", source="ibkr_fixture",
    )
    normalize_frame([row])
    return row


def _common_close_panel(bars: pd.DataFrame) -> pd.DataFrame:
    px = bars.pivot(index="timestamp", columns="symbol", values="close").reindex(columns=U)
    px = px.dropna(how="any").sort_index()
    px.index = pd.DatetimeIndex(px.index).tz_convert(None)
    if px.empty:
        raise RuntimeError("no common completed daily bars across P46 universe")
    return px


def _feature_cutoff(px: pd.DataFrame, observed_at: pd.Timestamp) -> pd.Timestamp:
    latest = pd.Timestamp(px.index.max())
    observed_month = observed_at.tz_convert(None).to_period("M")
    latest_month = latest.to_period("M")
    if latest_month < observed_month:
        # Pre-open/early-month runs may legitimately see the prior completed month as latest data.
        return latest
    # During a live month, do not leak partial-month data into the monthly decision.
    return observed_month.start_time - pd.Timedelta(days=1)


def _decision(px: pd.DataFrame, observed_at: pd.Timestamp) -> dict:
    cutoff = _feature_cutoff(px, observed_at)
    d = px.loc[px.index <= cutoff]
    m = d.resample("ME").last()
    dr = d.pct_change(fill_method=None)
    vol = (dr.rolling(126, min_periods=100).std(ddof=0) * math.sqrt(252)).resample("ME").last()
    trend = (d / d.rolling(200, min_periods=160).mean() - 1).resample("ME").last()
    drawdown = (d / d.rolling(126, min_periods=100).max() - 1).resample("ME").last()
    momentum = m.pct_change(6)
    dt = m.dropna(how="all").index[-1]
    features = pd.DataFrame({
        "mom6": momentum.loc[dt, list(U)],
        "trend200": trend.loc[dt, list(U)],
        "low_vol6": -vol.loc[dt, list(U)],
        "drawdown6": drawdown.loc[dt, list(U)],
    }, index=list(U))
    if features.isna().any().any():
        raise RuntimeError(f"insufficient complete P46 features at {dt.date()}")
    ranks = features.rank(axis=0, pct=True, method="average")
    score = ranks.mean(axis=1)
    chosen = score.sort_values(ascending=False, kind="mergesort").index[:TOP_K].tolist()
    weights = {s: (1.0 / TOP_K if s in chosen else 0.0) for s in U}
    holding_month = (pd.Timestamp(dt).to_period("M") + 1).strftime("%Y-%m")
    decision_payload = {
        "model": "P46",
        "version": MODEL_VERSION,
        "feature_month_end": str(pd.Timestamp(dt).date()),
        "selected": chosen,
        "target_weights": weights,
    }
    decision_identity = hashlib.sha256(
        json.dumps(decision_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    phase = (
        "PROSPECTIVE_DECISION_CANDIDATE"
        if pd.Timestamp(dt) >= FORWARD_NOT_BEFORE_FEATURE_MONTH_END
        and pd.Timestamp(dt).to_period("M") < observed_at.tz_convert(None).to_period("M")
        else "HARNESS_SHAKEDOWN"
    )
    return {
        "feature_month_end": str(pd.Timestamp(dt).date()),
        "holding_month": holding_month,
        "selected": chosen,
        "target_weights": weights,
        "scores": {k: float(v) for k, v in score.sort_values(ascending=False).items()},
        "features": {s: {k: float(v) for k, v in features.loc[s].items()} for s in U},
        "decision_identity": decision_identity,
        "phase": phase,
        "scientific_forward_credit_authorized": False,
        "scientific_forward_credit_note": (
            "Private admission must prove this decision was first recorded before outcome exposure; "
            "public compute alone cannot grant prospective-performance credit."
        ),
    }


def _shakedown_mark(px: pd.DataFrame) -> dict:
    eligible = px.loc[px.index >= SHAKEDOWN_ANCHOR_DATE]
    if eligible.empty:
        return {"available": False, "scientific_credit": False}
    anchor_date = eligible.index[0]
    latest_date = eligible.index[-1]
    rel = eligible / eligible.iloc[0]
    model_curve = sum(SHAKEDOWN_WEIGHTS[s] * rel[s] for s in U)
    matched_curve = rel.mean(axis=1)
    model_return = float(model_curve.iloc[-1] - 1)
    matched_return = float(matched_curve.iloc[-1] - 1)
    model_dd = float((model_curve / model_curve.cummax() - 1).min())
    return {
        "available": True,
        "basis": "normalized_index_100",
        "anchor_date": str(pd.Timestamp(anchor_date).date()),
        "latest_date": str(pd.Timestamp(latest_date).date()),
        "anchor_weights": SHAKEDOWN_WEIGHTS,
        "model_equity_index": float(model_curve.iloc[-1] * 100.0),
        "matched_equal_weight_equity_index": float(matched_curve.iloc[-1] * 100.0),
        "qqq_equity_index": float(rel["QQQ"].iloc[-1] * 100.0),
        "spy_equity_index": float(rel["SPY"].iloc[-1] * 100.0),
        "model_return": model_return,
        "matched_equal_weight_return": matched_return,
        "excess_matched": model_return - matched_return,
        "qqq_return": float(rel["QQQ"].iloc[-1] - 1),
        "spy_return": float(rel["SPY"].iloc[-1] - 1),
        "model_drawdown": model_dd,
        "scientific_credit": False,
        "label": "OPERATIONAL_SHAKEDOWN_ONLY",
    }


def main() -> None:
    observed_at = _utc_now()
    bars = _yahoo_normalized()
    fixture = _ibkr_shape_fixture()
    px = _common_close_panel(bars)
    decision = _decision(px, observed_at)
    shakedown = _shakedown_mark(px)
    latest_bar = pd.Timestamp(px.index.max()).tz_localize("UTC")
    common_panel_csv = px.to_csv(float_format="%.10g")
    artifact = {
        "schema": "research.model_forward_observation.v2",
        "observed_at": observed_at.isoformat(),
        "model": {
            "id": "P46",
            "version": MODEL_VERSION,
            "status": "SHADOW_FORWARD",
            "decision_cadence": "monthly",
            "feature_timeframe": "1 day",
            "holding_period": "next complete month",
            "universe": list(U),
            "top_k": TOP_K,
            "reference_cost_bps_turnover": REFERENCE_COST_BPS,
            "frozen": True,
            "parameter_search": False,
        },
        "input_contract": {
            "schema": ForwardBarContract().schema,
            "columns": list(normalize_frame([fixture]).columns),
            "ibkr_adapter_fixture_validated": True,
            "ibkr_mapping": ForwardBarContract().ibkr_mapping,
        },
        "source": {
            "provider": "Yahoo adjusted OHLCV; research-only public adapter",
            "latest_common_bar_timestamp": latest_bar.isoformat(),
            "common_rows": len(px),
            "common_panel_sha256": hashlib.sha256(common_panel_csv.encode()).hexdigest(),
            "promotion_grade": False,
        },
        "data_health": {
            "latest_common_bar_date": str(latest_bar.date()),
            "calendar_age_days": int((observed_at.normalize() - latest_bar.normalize()).days),
            "all_universe_members_present": list(px.columns) == list(U),
        },
        "decision": decision,
        "operational_shadow": shakedown,
        "boundaries": {
            "research_only": True,
            "broker_action": False,
            "runtime_mutation": False,
            "live_trading_change": False,
            "portfolio_allocation_authority": False,
            "private_admission_required_for_authoritative_forward_history": True,
        },
    }
    OUT.mkdir(exist_ok=True)
    output = OUT / "p46_forward_observation_v2.json"
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False))
    (OUT / "ibkr_adapter_fixture_v2.json").write_text(json.dumps(fixture, indent=2, sort_keys=True, default=str))
    print(json.dumps({
        "observed_at": artifact["observed_at"],
        "latest_bar": artifact["source"]["latest_common_bar_timestamp"],
        "phase": decision["phase"],
        "feature_month_end": decision["feature_month_end"],
        "selected": decision["selected"],
        "shakedown_equity": shakedown.get("model_equity_index"),
        "ibkr_contract": artifact["input_contract"]["schema"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()

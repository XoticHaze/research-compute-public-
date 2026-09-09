from __future__ import annotations
import hashlib, json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from research.forward_bar_contract_v1 import ForwardBarContract, normalize_frame

U = ("SPY", "QQQ", "TLT", "GLD", "DBC")
TOP_K = 2
REFERENCE_COST_BPS = 50
OUT = Path("artifacts")


def _yahoo_normalized() -> pd.DataFrame:
    raw = yf.download(list(U), start="2005-01-01", auto_adjust=True, progress=False, threads=False, group_by="column")
    rows = []
    for s in U:
        for ts, r in raw.xs(s, axis=1, level=1).dropna(subset=["Open", "High", "Low", "Close"]).iterrows():
            rows.append({
                "symbol": s,
                "timestamp": pd.Timestamp(ts, tz="UTC") if pd.Timestamp(ts).tzinfo is None else pd.Timestamp(ts).tz_convert("UTC"),
                "open": float(r["Open"]), "high": float(r["High"]), "low": float(r["Low"]), "close": float(r["Close"]),
                "volume": float(r.get("Volume", 0) or 0), "source": "yahoo_adjusted_research_only", "asset_type": "STK",
                "bar_size": "1 day", "session": "regular", "contract_id": s, "wap": np.nan, "bar_count": np.nan,
            })
    return normalize_frame(rows)


def _ibkr_shape_fixture() -> dict:
    row = {"symbol":"SPY","timestamp":"2026-09-08T20:00:00Z","open":100.0,"high":102.0,"low":99.5,"close":101.0,
           "volume":123456.0,"source":"ibkr_fixture","asset_type":"STK","bar_size":"1 day","session":"regular",
           "contract_id":"conid:756733","wap":100.8,"bar_count":9876}
    normalize_frame([row])
    return row


def _score_from_normalized(bars: pd.DataFrame) -> tuple[pd.Timestamp, pd.Series, list[str], pd.DataFrame]:
    px = bars.pivot(index="timestamp", columns="symbol", values="close").reindex(columns=U).dropna(how="all")
    px.index = pd.DatetimeIndex(px.index).tz_convert(None)
    last = pd.Timestamp(px.index.max())
    cutoff = last.to_period("M").start_time - pd.Timedelta(days=1)
    d = px.loc[px.index <= cutoff]
    m = d.resample("ME").last()
    dr = d.pct_change(fill_method=None)
    vol = (dr.rolling(126, min_periods=100).std(ddof=0) * math.sqrt(252)).resample("ME").last()
    trend = (d / d.rolling(200, min_periods=160).mean() - 1).resample("ME").last()
    dd = (d / d.rolling(126, min_periods=100).max() - 1).resample("ME").last()
    mom = m.pct_change(6)
    dt = m.dropna(how="all").index[-1]
    f = pd.DataFrame({"mom6":mom.loc[dt,list(U)], "trend200":trend.loc[dt,list(U)], "low_vol6":-vol.loc[dt,list(U)], "drawdown6":dd.loc[dt,list(U)]}, index=list(U))
    if f.isna().any().any():
        raise RuntimeError(f"insufficient complete features at {dt.date()}")
    ranks = f.rank(axis=0, pct=True, method="average")
    score = ranks.mean(axis=1)
    chosen = score.sort_values(ascending=False, kind="mergesort").index[:TOP_K].tolist()
    return dt, score, chosen, f


def main() -> None:
    OUT.mkdir(exist_ok=True)
    bars = _yahoo_normalized()
    fixture = _ibkr_shape_fixture()
    feature_month, score, chosen, features = _score_from_normalized(bars)
    latest_bar = bars.timestamp.max()
    weights = {s:(0.5 if s in chosen else 0.0) for s in U}
    bar_csv = bars.to_csv(index=False, float_format="%.10g")
    artifact = {
        "schema":"research.model_forward_snapshot.v1",
        "model":{
            "id":"P46", "version":"fixed_original_four_factor_top2_r1", "status":"SHADOW_FORWARD",
            "decision_cadence":"monthly", "feature_timeframe":"1 day bars", "holding_period":"next complete month",
            "universe":list(U), "top_k":TOP_K, "reference_cost_bps_turnover":REFERENCE_COST_BPS,
            "factors":["6m momentum","price/SMA200 trend","inverse 126-session realized volatility","126-session distance from high"],
            "frozen":True, "parameter_search":False,
        },
        "input_contract":{
            "schema":ForwardBarContract().schema, "columns":list(normalize_frame([fixture]).columns),
            "ibkr_adapter_compatible":True, "ibkr_mapping":ForwardBarContract().ibkr_mapping,
            "fixture_validated":True,
        },
        "source":{
            "provider":"Yahoo adjusted OHLCV; research-only adapter", "latest_bar_timestamp":latest_bar.isoformat(),
            "normalized_bar_sha256":hashlib.sha256(bar_csv.encode()).hexdigest(), "rows":len(bars),
            "promotion_grade":False,
        },
        "decision":{
            "feature_month_end":str(feature_month.date()), "selected":chosen, "target_weights":weights,
            "scores":{k:float(v) for k,v in score.sort_values(ascending=False).items()},
            "features":{s:{k:float(v) for k,v in features.loc[s].items()} for s in U},
            "action":"REBALANCE_AT_NEXT_ELIGIBLE_MONTH_BOUNDARY",
        },
        "boundaries":{
            "research_only":True, "broker_action":False, "runtime_mutation":False, "live_trading_change":False,
            "portfolio_allocation_authority":False,
        },
    }
    payload = json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False)
    (OUT / "p46_forward_shadow_r1.json").write_text(payload)
    (OUT / "normalized_bar_contract_fixture.json").write_text(json.dumps(fixture, indent=2, sort_keys=True))
    print(json.dumps({"decision":artifact["decision"],"input_contract":artifact["input_contract"],"source":artifact["source"]}, sort_keys=True))

if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

START = "2015-01-01"
END = "2026-09-07"
COST_BPS = 10.0
SECTORS = ["SMH", "ITB", "XLE", "XLI", "XLU"]
HOME = ["CCS", "MHO", "HOV", "BZH"]
ALL = sorted(set(SECTORS + HOME + ["SPY", "QQQ", "TLT", "SHY"]))


def epoch(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp())


def load(symbol: str) -> pd.Series:
    q = urlencode({"period1": epoch(START), "period2": epoch(END), "interval": "1d", "events": "history", "includeAdjustedClose": "true"})
    req = Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{q}", headers={"User-Agent": "Mozilla/5.0 research-compute/1.0"})
    with urlopen(req, timeout=30) as r:  # noqa: S310 fixed HTTPS host
        payload = json.loads(r.read().decode("utf-8"))
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"{symbol}: no chart result")
    ts = pd.to_datetime(result.get("timestamp") or [], unit="s", utc=True)
    ind = result.get("indicators", {})
    adj = (ind.get("adjclose") or [{}])[0].get("adjclose")
    close = adj or (ind.get("quote") or [{}])[0].get("close")
    s = pd.Series(pd.to_numeric(pd.Series(close), errors="coerce").to_numpy(), index=ts, name=symbol).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def folds(values: list[float], n: int = 5) -> list[float]:
    a = np.asarray(values, dtype=float)
    if len(a) < n:
        return []
    out = []
    for idx in np.array_split(np.arange(len(a)), n):
        out.append(float(np.mean(a[idx])))
    return out


def mean(x):
    return None if not x else float(np.mean(x))


def main() -> None:
    px = {s: load(s) for s in ALL}
    common = pd.DatetimeIndex(sorted(set.intersection(*[set(s.index) for s in px.values()])))
    if len(common) < 1800:
        raise RuntimeError(f"insufficient common calendar: {len(common)}")
    frame = pd.DataFrame({k: v.reindex(common) for k, v in px.items()}).dropna()

    sector_rows = []
    for i in range(120, len(frame) - 20, 20):
        scores = {s: frame[s].iloc[i] / frame[s].iloc[i - 60] - 1.0 for s in SECTORS}
        selected = sorted(scores, key=lambda s: (-scores[s], s))[:2]
        top2 = float(np.mean([frame[s].iloc[i + 20] / frame[s].iloc[i] - 1.0 for s in selected])) - COST_BPS / 10000.0
        ew = float(np.mean([frame[s].iloc[i + 20] / frame[s].iloc[i] - 1.0 for s in SECTORS]))
        spy = float(frame["SPY"].iloc[i + 20] / frame["SPY"].iloc[i] - 1.0)
        qqq = float(frame["QQQ"].iloc[i + 20] / frame["QQQ"].iloc[i] - 1.0)
        curve = float(frame["TLT"].iloc[i] / frame["TLT"].iloc[i - 60] - frame["SHY"].iloc[i] / frame["SHY"].iloc[i - 60])
        spy_vol20 = float(frame["SPY"].pct_change().iloc[i - 19 : i + 1].std(ddof=0) * np.sqrt(252))
        sector_rows.append({"date": frame.index[i].isoformat(), "selected": selected, "top2": top2, "ew": ew, "spy": spy, "qqq": qqq, "curve": curve, "spy_vol20": spy_vol20})

    sector_ex = [(r["top2"] - r["ew"]) * 10000 for r in sector_rows]
    spy_ex = [(r["top2"] - r["spy"]) * 10000 for r in sector_rows]
    qqq_ex = [(r["top2"] - r["qqq"]) * 10000 for r in sector_rows]
    pass1 = {
        "parent": "sector_scarce_capital_allocator",
        "question": "Does a frozen 60-session top-2 sector ranker beat equal-sector capital on matched 20-session windows?",
        "events": len(sector_rows),
        "mean_top2_net_bps": mean([r["top2"] * 10000 for r in sector_rows]),
        "mean_equal_sector_bps": mean([r["ew"] * 10000 for r in sector_rows]),
        "mean_excess_vs_equal_sector_bps": mean(sector_ex),
        "positive_excess_folds": int(sum(x > 0 for x in folds(sector_ex))),
    }

    home_rows = []
    for i in range(120, len(frame) - 20, 20):
        itb_past = frame["ITB"].iloc[i] / frame["ITB"].iloc[i - 20] - 1.0
        scores = {s: (frame[s].iloc[i] / frame[s].iloc[i - 20] - 1.0) - itb_past for s in HOME}
        selected = sorted(scores, key=lambda s: (-scores[s], s))[:2]
        top2 = float(np.mean([frame[s].iloc[i + 20] / frame[s].iloc[i] - 1.0 for s in selected])) - 25.0 / 10000.0
        ew = float(np.mean([frame[s].iloc[i + 20] / frame[s].iloc[i] - 1.0 for s in HOME])) - 25.0 / 10000.0
        itb = float(frame["ITB"].iloc[i + 20] / frame["ITB"].iloc[i] - 1.0)
        home_rows.append({"top2": top2, "ew": ew, "itb": itb})
    home_itb = [(r["top2"] - r["itb"]) * 10000 for r in home_rows]
    home_ew = [(r["top2"] - r["ew"]) * 10000 for r in home_rows]
    pass2 = {
        "parent": "homebuilder_within_industry_scarcity",
        "question": "Does a frozen top-2 relative-momentum selector add value over equal Homebuilders and matched ITB?",
        "events": len(home_rows),
        "mean_top2_net_bps": mean([r["top2"] * 10000 for r in home_rows]),
        "mean_excess_vs_home_equal_weight_bps": mean(home_ew),
        "mean_excess_vs_itb_bps": mean(home_itb),
        "positive_itb_excess_folds": int(sum(x > 0 for x in folds(home_itb))),
    }

    pos_curve = [(r["top2"] - r["ew"]) * 10000 for r in sector_rows if r["curve"] > 0]
    neg_curve = [(r["top2"] - r["ew"]) * 10000 for r in sector_rows if r["curve"] <= 0]
    pass3 = {
        "parent": "curve_state",
        "question": "Does sector-allocation excess depend materially on a prospectively defined TLT-vs-SHY 60-session curve proxy?",
        "positive_curve_events": len(pos_curve),
        "nonpositive_curve_events": len(neg_curve),
        "mean_excess_positive_curve_bps": mean(pos_curve),
        "mean_excess_nonpositive_curve_bps": mean(neg_curve),
    }

    split = len(sector_rows) // 2
    train_median = float(np.median([r["spy_vol20"] for r in sector_rows[:split]]))
    oos = sector_rows[split:]
    high = [(r["top2"] - r["ew"]) * 10000 for r in oos if r["spy_vol20"] > train_median]
    low = [(r["top2"] - r["ew"]) * 10000 for r in oos if r["spy_vol20"] <= train_median]
    pass4 = {
        "parent": "multi_horizon_risk",
        "question": "On the untouched second half, is allocator excess robust across a first-half-frozen SPY volatility split?",
        "train_vol_median_ann": train_median,
        "oos_high_vol_events": len(high),
        "oos_low_vol_events": len(low),
        "mean_excess_high_vol_bps": mean(high),
        "mean_excess_low_vol_bps": mean(low),
    }

    pass5 = {
        "parent": "passive_substitution_opportunity_cost",
        "question": "Does the same sector allocator beat passive SPY and QQQ on exact matched windows after cost?",
        "events": len(sector_rows),
        "mean_excess_vs_spy_bps": mean(spy_ex),
        "mean_excess_vs_qqq_bps": mean(qqq_ex),
        "positive_vs_spy_folds": int(sum(x > 0 for x in folds(spy_ex))),
        "positive_vs_qqq_folds": int(sum(x > 0 for x in folds(qqq_ex))),
    }

    payload = {
        "schema": "public_research.five_pass_alpha_discriminators.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": {"start": START, "end_exclusive": END, "first_common": frame.index[0].isoformat(), "last_common": frame.index[-1].isoformat()},
        "source": "Yahoo adjusted daily via fixed HTTPS endpoint",
        "passes": [pass1, pass2, pass3, pass4, pass5],
        "boundaries": {"research_only": True, "allocation_authority": False, "promotion_authority": False, "runtime_mutation": False, "broker_authority": False, "live_trading_change": False},
    }
    with open("five-pass-alpha-discriminators-20260906.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    print("FIVE_PASS_ALPHA=" + json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()

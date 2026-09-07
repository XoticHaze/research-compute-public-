from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

START = "2014-01-01"
END = "2026-09-07"
SECTORS = ["XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB"]
BASELINES = ["SPY", "QQQ"]
ALL = SECTORS + BASELINES
LOOKBACK = 252
SKIP = 21
VOL = 63
HOLD = 21
TOP_K = 3
PRIMARY_COST_BPS = 10.0
STRESS_COST_BPS = 25.0


def epoch(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp())


def load(symbol: str) -> pd.Series:
    q = urlencode({"period1": epoch(START), "period2": epoch(END), "interval": "1d", "events": "history", "includeAdjustedClose": "true"})
    req = Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{q}", headers={"User-Agent": "Mozilla/5.0 research-compute/1.0"})
    with urlopen(req, timeout=30) as resp:  # noqa: S310 fixed HTTPS host
        payload = json.loads(resp.read().decode("utf-8"))
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"{symbol}: no chart result")
    ts = pd.to_datetime(result.get("timestamp") or [], unit="s", utc=True)
    ind = result.get("indicators", {})
    adj = (ind.get("adjclose") or [{}])[0].get("adjclose")
    close = adj or (ind.get("quote") or [{}])[0].get("close")
    s = pd.Series(pd.to_numeric(pd.Series(close), errors="coerce").to_numpy(), index=ts, name=symbol).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def fold_means(values: list[float], n: int = 5) -> list[float]:
    arr = np.asarray(values, dtype=float)
    return [float(np.mean(arr[idx])) for idx in np.array_split(np.arange(len(arr)), n) if len(idx)]


def main() -> None:
    px = {s: load(s) for s in ALL}
    common = pd.DatetimeIndex(sorted(set.intersection(*[set(s.index) for s in px.values()])))
    frame = pd.DataFrame({k: v.reindex(common) for k, v in px.items()}).dropna()
    if len(frame) < 2000:
        raise RuntimeError(f"insufficient common history: {len(frame)}")
    rets = frame[SECTORS].pct_change()
    rows = []
    start_i = max(LOOKBACK, VOL) + SKIP
    for i in range(start_i, len(frame) - HOLD, HOLD):
        scores = {}
        detail = {}
        for s in SECTORS:
            mom_12m1m = float(frame[s].iloc[i - SKIP] / frame[s].iloc[i - LOOKBACK] - 1.0)
            vol = float(rets[s].iloc[i - VOL + 1 : i + 1].std(ddof=0) * np.sqrt(252))
            if not np.isfinite(vol) or vol <= 0:
                raise RuntimeError(f"invalid vol {s} {frame.index[i]}")
            score = mom_12m1m / vol
            scores[s] = score
            detail[s] = {"mom_12m1m": mom_12m1m, "vol63_ann": vol, "score": score}
        selected = sorted(SECTORS, key=lambda s: (-scores[s], s))[:TOP_K]
        gross_selected = float(np.mean([frame[s].iloc[i + HOLD] / frame[s].iloc[i] - 1.0 for s in selected])) * 10000.0
        gross_equal = float(np.mean([frame[s].iloc[i + HOLD] / frame[s].iloc[i] - 1.0 for s in SECTORS])) * 10000.0
        spy = float(frame["SPY"].iloc[i + HOLD] / frame["SPY"].iloc[i] - 1.0) * 10000.0
        qqq = float(frame["QQQ"].iloc[i + HOLD] / frame["QQQ"].iloc[i] - 1.0) * 10000.0
        rows.append({
            "decision_date": frame.index[i].isoformat(),
            "exit_date": frame.index[i + HOLD].isoformat(),
            "selected": selected,
            "score_detail": detail,
            "candidate_net10_bps": gross_selected - PRIMARY_COST_BPS,
            "candidate_net25_bps": gross_selected - STRESS_COST_BPS,
            "equal_sector_net10_bps": gross_equal - PRIMARY_COST_BPS,
            "equal_sector_net25_bps": gross_equal - STRESS_COST_BPS,
            "spy_gross_bps": spy,
            "qqq_gross_bps": qqq,
            "excess_vs_equal_sector_10_bps": gross_selected - gross_equal,
            "excess_vs_equal_sector_25_bps": gross_selected - gross_equal,
            "excess_vs_spy_10_bps": gross_selected - PRIMARY_COST_BPS - spy,
            "excess_vs_qqq_10_bps": gross_selected - PRIMARY_COST_BPS - qqq,
        })

    def avg(key): return float(np.mean([r[key] for r in rows]))
    eq_fold = fold_means([r["excess_vs_equal_sector_10_bps"] for r in rows])
    spy_fold = fold_means([r["excess_vs_spy_10_bps"] for r in rows])
    qqq_fold = fold_means([r["excess_vs_qqq_10_bps"] for r in rows])
    agg = {
        "events": len(rows),
        "candidate_net10_mean_bps": avg("candidate_net10_bps"),
        "candidate_net25_mean_bps": avg("candidate_net25_bps"),
        "equal_sector_net10_mean_bps": avg("equal_sector_net10_bps"),
        "equal_sector_net25_mean_bps": avg("equal_sector_net25_bps"),
        "excess_vs_equal_sector_10_mean_bps": avg("excess_vs_equal_sector_10_bps"),
        "excess_vs_equal_sector_25_mean_bps": avg("excess_vs_equal_sector_25_bps"),
        "excess_vs_spy_10_mean_bps": avg("excess_vs_spy_10_bps"),
        "excess_vs_qqq_10_mean_bps": avg("excess_vs_qqq_10_bps"),
        "positive_equal_sector_folds": sum(x > 0 for x in eq_fold),
        "positive_spy_folds": sum(x > 0 for x in spy_fold),
        "positive_qqq_folds": sum(x > 0 for x in qqq_fold),
        "equal_sector_fold_excess_bps": eq_fold,
        "spy_fold_excess_bps": spy_fold,
        "qqq_fold_excess_bps": qqq_fold,
    }
    supported = bool(
        agg["excess_vs_equal_sector_10_mean_bps"] > 0
        and agg["excess_vs_equal_sector_25_mean_bps"] > 0
        and agg["excess_vs_spy_10_mean_bps"] > 0
        and agg["positive_equal_sector_folds"] >= 3
        and agg["positive_spy_folds"] >= 3
    )
    out = {
        "schema": "public_research.sector_12m1m_riskadj_allocator.v1",
        "research_only": True,
        "mechanism": "top3 12-minus-1-month momentum divided by trailing-63-session annualized volatility",
        "universe": SECTORS,
        "window": {"first_common": frame.index[0].isoformat(), "last_common": frame.index[-1].isoformat(), "first_decision": rows[0]["decision_date"], "last_exit": rows[-1]["exit_date"]},
        "costs_bps": {"primary": PRIMARY_COST_BPS, "stress": STRESS_COST_BPS},
        "aggregate": agg,
        "decision": "SECTOR_12M1M_RISKADJ_ALLOCATOR_SUPPORTED" if supported else "SECTOR_12M1M_RISKADJ_ALLOCATOR_REJECTED",
        "consequence": "A supported result merits a separately frozen confirmation on a disjoint future/alternate-sector cohort. A rejected result should not be threshold- or lookback-rescued; rotate to a different allocator information mechanism.",
        "rows": rows,
        "allocation_authority": False,
        "promotion_authority": False,
        "runtime_authority": False,
        "broker_authority": False,
        "live_trading_change": False,
    }
    with open("sector-12m1m-riskadj-allocator-receipt.json", "w", encoding="utf-8") as f:
        json.dump(out, f, sort_keys=True, indent=2); f.write("\n")
    print("SECTOR_12M1M_RISKADJ_ALLOCATOR=" + json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()

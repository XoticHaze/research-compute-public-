#!/usr/bin/env python3
import hashlib
import json
import math
import os
import statistics
import time
import urllib.request
from datetime import datetime, timezone

VALIDATION = "SOXX"
SYMS = (VALIDATION, "SMH", "QQQ", "SPY")
LOOKBACK_VOL = 20
HISTORY = 756
BREAKOUT = 63
HOLD = 20
VOLUME_LOOKBACK = 20
COSTS = (10.0, 25.0, 50.0)
OUT = os.environ.get("P21_C3_OUTPUT", "p21_soxx_volume_confirmed_breakout_validation_receipt.json")
UA = "Mozilla/5.0 research-compute-public p21-c3-soxx"


def fetch(sym):
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        "?period1=946684800&period2=1788825600&interval=1d&events=history&includeAdjustedClose=true"
    )
    last = None
    for k in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read()
            obj = json.loads(raw)["chart"]["result"][0]
            ts = obj["timestamp"]
            quote = obj["indicators"]["quote"][0]
            adj = (obj.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose")
            if not adj:
                adj = quote["close"]
            vols = quote.get("volume") or [None] * len(ts)
            prices = {}
            volumes = {}
            for t, p, v in zip(ts, adj, vols):
                if p is None or p <= 0:
                    continue
                d = datetime.fromtimestamp(t, timezone.utc).date().isoformat()
                prices[d] = float(p)
                if v is not None and v >= 0:
                    volumes[d] = float(v)
            return prices, volumes, {
                "url": url,
                "rows": len(prices),
                "payload_sha256": hashlib.sha256(raw).hexdigest(),
            }
        except Exception as exc:
            last = exc
            time.sleep(2**k)
    raise RuntimeError(f"fetch failed {sym}: {last}")


def pctile(xs, p):
    ys = sorted(xs)
    if not ys:
        return None
    x = (len(ys) - 1) * p
    a = int(math.floor(x))
    b = int(math.ceil(x))
    return ys[a] if a == b else ys[a] + (ys[b] - ys[a]) * (x - a)


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def fold_split(xs, n=5):
    return [xs[len(xs) * k // n : len(xs) * (k + 1) // n] for k in range(n)]


def main():
    data = {}
    volumes = {}
    provenance = {}
    for symbol in SYMS:
        data[symbol], volumes[symbol], provenance[symbol] = fetch(symbol)

    dates = sorted(set.intersection(*(set(data[s]) for s in SYMS)))
    if len(dates) < HISTORY + BREAKOUT + HOLD:
        raise RuntimeError(f"insufficient common history: {len(dates)} rows")

    px = {s: [data[s][d] for d in dates] for s in SYMS}
    validation_volume = [volumes[VALIDATION].get(d) for d in dates]
    lret = [None] + [math.log(px[VALIDATION][i] / px[VALIDATION][i - 1]) for i in range(1, len(dates))]
    rvol = [None] * len(dates)
    for i in range(LOOKBACK_VOL, len(dates)):
        window = [x for x in lret[i - LOOKBACK_VOL + 1 : i + 1] if x is not None]
        if len(window) == LOOKBACK_VOL:
            rvol[i] = statistics.pstdev(window) * math.sqrt(252)

    # P21-C3 transports the complete C1/C2 mechanism to SOXX without changing any
    # threshold, lookback, spacing, hold, volume confirmation, or cost assumption.
    base_events = []
    next_ok = 0
    start = max(HISTORY + LOOKBACK_VOL, BREAKOUT, VOLUME_LOOKBACK)
    for i in range(start, len(dates) - HOLD):
        hist = [v for v in rvol[i - HISTORY : i] if v is not None]
        if len(hist) < HISTORY - 5 or i < next_ok:
            continue
        threshold = pctile(hist, 0.20)
        if rvol[i] is None or rvol[i] > threshold:
            continue
        if px[VALIDATION][i] <= max(px[VALIDATION][i - BREAKOUT : i]):
            continue
        prior_volume = [v for v in validation_volume[i - VOLUME_LOOKBACK : i] if v is not None]
        if validation_volume[i] is None or len(prior_volume) != VOLUME_LOOKBACK:
            continue
        prior_median = statistics.median(prior_volume)
        event = {
            "date": dates[i],
            "realized_vol": rvol[i],
            "vol_threshold": threshold,
            "event_volume": validation_volume[i],
            "prior20_volume_median": prior_median,
            "volume_confirmed": validation_volume[i] > prior_median,
        }
        for symbol in SYMS:
            event[symbol] = px[symbol][i + HOLD] / px[symbol][i] - 1.0
        base_events.append(event)
        next_ok = i + HOLD

    if not base_events:
        raise RuntimeError("no frozen SOXX base events")
    events = [e for e in base_events if e["volume_confirmed"]]
    if not events:
        raise RuntimeError("no SOXX volume-confirmed events")

    costs = {}
    for cost in COSTS:
        round_trip = 2 * cost / 10000.0
        net = [e[VALIDATION] - round_trip for e in events]
        excess = {
            benchmark: [(e[VALIDATION] - round_trip) - e[benchmark] for e in events]
            for benchmark in ("SMH", "QQQ", "SPY")
        }
        fold_means = {
            benchmark: [mean([(e[VALIDATION] - round_trip) - e[benchmark] for e in fold]) for fold in fold_split(events) if fold]
            for benchmark in ("SMH", "QQQ", "SPY")
        }
        costs[str(cost)] = {
            "soxx_net_mean": mean(net),
            "soxx_net_median": statistics.median(net),
            "soxx_net_win_rate": mean([x > 0 for x in net]),
            "excess_vs_smh_mean": mean(excess["SMH"]),
            "excess_vs_qqq_mean": mean(excess["QQQ"]),
            "excess_vs_spy_mean": mean(excess["SPY"]),
            "positive_smh_excess_folds": sum(x > 0 for x in fold_means["SMH"]),
            "positive_qqq_excess_folds": sum(x > 0 for x in fold_means["QQQ"]),
            "positive_spy_excess_folds": sum(x > 0 for x in fold_means["SPY"]),
            "fold_count": len(fold_means["QQQ"]),
        }

    by_year = {}
    for event in events:
        by_year.setdefault(event["date"][:4], []).append(event)
    year_qqq = [
        mean([(e[VALIDATION] - 0.005) - e["QQQ"] for e in year_events])
        for _, year_events in sorted(by_year.items())
    ]
    primary = costs["25.0"]

    # Independent-validation gate is frozen before this run. It requires usable sample
    # size plus persistence against the original semiconductor representation and both
    # broad controls. No parameter is tuned from the validation result.
    supported = (
        len(events) >= 20
        and primary["excess_vs_smh_mean"] > 0
        and primary["excess_vs_qqq_mean"] > 0
        and primary["excess_vs_spy_mean"] > 0
        and primary["positive_qqq_excess_folds"] >= 3
        and mean([x > 0 for x in year_qqq]) >= 0.5
        and costs["50.0"]["excess_vs_qqq_mean"] > 0
    )
    decision = "P21_C3_SOXX_INDEPENDENT_VALIDATION_SUPPORTED" if supported else "P21_C3_SOXX_INDEPENDENT_VALIDATION_NOT_SUPPORTED"

    receipt = {
        "schema": "research.p21_soxx_volume_confirmed_breakout_validation.v1",
        "parent_id": "P21",
        "child_id": "P21-C3-INDEPENDENT-VALIDATION",
        "decision": decision,
        "validation_contract": {
            "representation": VALIDATION,
            "original_representation_control": "SMH",
            "base_event_contract": "UNCHANGED_P21_C1_20D_REALIZED_VOL_BELOW_PRIOR_756D_P20_AND_63D_BREAKOUT_WITH_20D_NONOVERLAP_HOLD",
            "volume_confirmation": "event_day_volume_gt_prior_only_20_session_median",
            "volume_lookback_sessions": VOLUME_LOOKBACK,
            "cost_bps_per_side": list(COSTS),
            "parameters_frozen_from_p21_c1_c2": True,
        },
        "source": {
            "provider": "Yahoo Finance Chart JSON",
            "transport": "query1.finance.yahoo.com/v8/finance/chart",
            "provenance": provenance,
            "research_only_not_mm_canonical": True,
        },
        "matched_window": {
            "first_base_event": base_events[0]["date"],
            "last_base_event": base_events[-1]["date"],
            "base_events": len(base_events),
            "first_confirmed_event": events[0]["date"],
            "last_confirmed_event": events[-1]["date"],
            "last_return_date": dates[dates.index(events[-1]["date"]) + HOLD],
            "confirmed_events": len(events),
            "common_daily_rows": len(dates),
        },
        "baselines": {
            "soxx_event_gross_mean": mean([e[VALIDATION] for e in events]),
            "matched_smh_mean": mean([e["SMH"] for e in events]),
            "matched_qqq_mean": mean([e["QQQ"] for e in events]),
            "matched_spy_mean": mean([e["SPY"] for e in events]),
        },
        "cost_stress": costs,
        "calendar_years": {
            "count": len(year_qqq),
            "positive_excess_vs_qqq_years_at_25bps": sum(x > 0 for x in year_qqq),
            "positive_share": mean([x > 0 for x in year_qqq]),
        },
        "events_digest_fields": [
            {
                "date": e["date"],
                "soxx": e[VALIDATION],
                "smh": e["SMH"],
                "qqq": e["QQQ"],
                "spy": e["SPY"],
                "volume_ratio_to_prior_median": e["event_volume"] / e["prior20_volume_median"],
            }
            for e in events
        ],
        "protected_boundaries": {
            "strategy_spec_write": False,
            "runtime_activation": False,
            "broker_submit": False,
            "promotion_authority": False,
            "live_trading_change": False,
        },
    }
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

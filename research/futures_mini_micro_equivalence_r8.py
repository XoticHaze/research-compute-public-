#!/usr/bin/env python3
import hashlib
import io
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

SOURCE_REPO = "axb0306/cme-futures-ohlc"
PAIRS = {
    "SP500": ("ES", "MES"),
    "NASDAQ100": ("NQ", "MNQ"),
    "RUSSELL2000": ("RTY", "M2K"),
    "DOW30": ("YM", "MYM"),
    "GOLD": ("GC", "MGC"),
    "WTI": ("CL", "MCL"),
}
UA = "Mozilla/5.0 research-only futures-mini-micro-equivalence-r8"


def fetch_text(url):
    last = None
    for attempt in range(1, 6):
        try:
            raw = urlopen(Request(url, headers={"User-Agent": UA}), timeout=30).read()
            return raw, attempt
        except Exception as exc:
            last = exc
            if attempt < 5:
                time.sleep(attempt * 2)
    raise RuntimeError(f"{url}: {type(last).__name__}: {last}")


def list_daily(root):
    api = f"https://api.github.com/repos/{SOURCE_REPO}/contents/{root}?ref=main"
    raw, attempt = fetch_text(api)
    items = json.loads(raw)
    daily = [x for x in items if x.get("name", "").startswith(root + "_daily_") and x.get("name", "").endswith(".csv")]
    if not daily:
        raise RuntimeError(f"{root}: no daily file in source directory")
    daily.sort(key=lambda x: x["name"])
    item = daily[-1]
    return item, {"listing_sha256": hashlib.sha256(raw).hexdigest(), "attempt": attempt}


def parse_daily(root):
    item, listing = list_daily(root)
    raw, attempt = fetch_text(item["download_url"])
    frame = pd.read_csv(io.BytesIO(raw))
    lower = {str(c).lower(): c for c in frame.columns}
    date_col = next((lower[k] for k in ("date", "datetime", "timestamp") if k in lower), None)
    close_col = next((lower[k] for k in ("close", "last") if k in lower), None)
    if date_col is None or close_col is None:
        raise RuntimeError(f"{root}: unsupported schema {list(frame.columns)}")
    idx = pd.to_datetime(frame[date_col], errors="raise", utc=True).dt.tz_convert(None)
    close = pd.Series(pd.to_numeric(frame[close_col], errors="raise").values, index=idx, name=root).dropna()
    close = close[~close.index.duplicated(keep="last")].sort_index()
    if len(close) < 100:
        raise RuntimeError(f"{root}: only {len(close)} daily rows")
    return close, {
        "path": item["path"],
        "github_blob_sha": item["sha"],
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "rows": len(close),
        "start": close.index.min().date().isoformat(),
        "end": close.index.max().date().isoformat(),
        "download_attempt": attempt,
        **listing,
    }


def pair_eval(a, b):
    z = pd.concat([a, b], axis=1).dropna()
    ra = z.iloc[:, 0].pct_change()
    rb = z.iloc[:, 1].pct_change()
    r = pd.concat([ra.rename("mini"), rb.rename("micro")], axis=1).dropna()
    diff = r["micro"] - r["mini"]
    ratio = z.iloc[:, 1] / z.iloc[:, 0]
    corr = float(r.corr().iloc[0, 1])
    mad_bps = float(diff.abs().median() * 10000)
    p95_bps = float(diff.abs().quantile(.95) * 10000)
    max_bps = float(diff.abs().max() * 10000)
    same_sign = float((np.sign(r.mini) == np.sign(r.micro)).mean())
    ratio_cv = float(ratio.std(ddof=1) / ratio.mean()) if ratio.mean() else None
    supported = bool(corr >= .999 and mad_bps <= 2.0 and same_sign >= .99)
    return {
        "matched_sessions": int(len(r)),
        "start": r.index.min().date().isoformat(),
        "end": r.index.max().date().isoformat(),
        "daily_return_correlation": corr,
        "median_abs_return_difference_bps": mad_bps,
        "p95_abs_return_difference_bps": p95_bps,
        "max_abs_return_difference_bps": max_bps,
        "same_return_sign_fraction": same_sign,
        "price_ratio_coefficient_of_variation": ratio_cv,
        "screen_equivalence_supported": supported,
    }


def main():
    out = {
        "schema": "research.futures_mini_micro_equivalence_r8",
        "classification": "EXTERNAL_RECENT_OVERLAP_EQUIVALENCE_ONLY_NOT_CANONICAL_SUBSTITUTION",
        "scientific_contract": {
            "purpose": "test whether E-mini/standard and micro representations track the same underlying daily return process closely enough for family-level screening while retaining separate canonical product identities",
            "pairs": PAIRS,
            "source": SOURCE_REPO,
            "gate": "daily return corr >= 0.999, median absolute return difference <=2 bps, same-sign fraction >=0.99",
            "prohibited_inference": "a passing pair does not authorize substituting mini bars for missing micro bars, does not establish dated-contract roll authority, and does not change execution product identity",
            "research_only": True,
        },
        "pairs": {},
    }
    for family, (mini, micro) in PAIRS.items():
        try:
            a, pa = parse_daily(mini)
            b, pb = parse_daily(micro)
            out["pairs"][family] = {"mini": mini, "micro": micro, "mini_source": pa, "micro_source": pb, "result": pair_eval(a, b)}
        except Exception as exc:
            out["pairs"][family] = {"mini": mini, "micro": micro, "state": "DATA_OR_HARNESS_INCONCLUSIVE", "error": f"{type(exc).__name__}: {exc}"}
    out["summary"] = {
        "supported_pairs": [k for k, v in out["pairs"].items() if v.get("result", {}).get("screen_equivalence_supported")],
        "inconclusive_pairs": [k for k, v in out["pairs"].items() if "result" not in v],
        "next_step": "Use pair results to prioritize independent mini+micro confirmation. For promotion-grade futures evidence acquire dated individual contracts and apply source-specific roll/stitch admission; never fill one product's missing bars with the other product.",
    }
    Path("futures_mini_micro_equivalence_r8.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps(out["summary"], sort_keys=True))


if __name__ == "__main__":
    main()

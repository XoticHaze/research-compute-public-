from __future__ import annotations

import json
from pathlib import Path

import pit_cash_conversion_event_alpha_r1 as experiment
from public_price_history_yahoo_r1 import adjusted_daily_prices

# Same prospective source-only substitution as the ROA sibling. No economic
# hypothesis, signal, horizon, costs, baselines, or gates are changed.
experiment.core.stooq_prices = adjusted_daily_prices
experiment.main()

p = Path("research/artifacts/pit_cash_conversion_event_alpha_r1.json")
x = json.loads(p.read_text())
x["frozen_specification"]["source"] = "SEC companyfacts plus Yahoo public chart adjusted daily closes"
x["limitations"] = [
    s.replace("Stooq closes are deterministic public return measurements and may differ from dividend-total-return series.",
              "Yahoo adjusted daily closes are deterministic public return measurements; vendor corporate-action treatment may affect levels.")
    for s in x["limitations"]
]
x["transport_adjudication"] = {
    "stooq_status": "HTTP_503_REPEATED_BEFORE_ANY_SCIENTIFIC_RESULT",
    "replacement": "Yahoo public chart adjusted daily closes",
    "hypothesis_or_gate_changed": False,
}
p.write_text(json.dumps(x, indent=2, sort_keys=True, allow_nan=False))

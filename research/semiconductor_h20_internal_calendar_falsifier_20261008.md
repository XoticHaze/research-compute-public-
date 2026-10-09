# Pre-outcome H20 calendar falsifier

Synthetic reference has 27 weekday sessions. One stock is missing the eighth session but has the same latest date as SMH and QQQ. The existing intersection calendar contains 26 sessions and shifts the fixed H20 exit from 2026-09-30 to 2026-10-01. Last-date source health remains green. No market outcomes or protected data were used.

Required correction: fail closed on any missing internal session in the frozen entry-to-H20 benchmark calendar before accepting a terminal prospective result. Do not interpolate or silently extend the holding horizon. This is a source integrity gate, not a new strategy.

# Equity REIT Yahoo cookie+crumb CSV discriminator

Parent: frozen P07 Equity REIT external holdout after development passed 5/8 against VNQ.

Known failed access forms before this child:
- Yahoo chart history yielded only 27 AVB rows and 14 EQR rows while ESS/DLR retained long history.
- Stooq archive access returned a JavaScript verification page and zero usable rows, including the AAPL transport control.

This child tests one additional same-provider access form only: Yahoo's cookie+crumb CSV download endpoint for the exact frozen AVB/EQR/ESS/DLR holdout through the existing 2026-09-01 ceiling.

A positive coverage result does not authorize a source switch or model economics. It only authorizes a separately frozen same-symbol source-parity consumer. A negative result leaves the REIT parent source-availability constrained, not transport-failed and not scientifically rejected.

No StrategySpec, runtime, broker, sizing, promotion, allocation, or live-trading authority.

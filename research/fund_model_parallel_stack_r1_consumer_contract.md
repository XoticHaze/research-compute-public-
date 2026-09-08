# Terminal result consumer

When the four matrix jobs are terminal, consume them together in one pass. Build a table with: child, exact run/job, candidate, baseline, 25-bps excess CAGR, positive excess folds, candidate/baseline Sharpe, candidate/baseline Calmar, drawdown, annual turnover, 50-bps excess, decision.

Then:

- promote only components meeting the frozen acceptance gate;
- if persistence survives but risk-state does not, keep the simpler sleeve;
- if allocation beats persistence on Calmar without sacrificing excess persistence, elevate it as allocator candidate;
- if diversification improves risk-adjusted return but dilutes CAGR, retain it as portfolio risk layer rather than alpha layer;
- derive the next same-family high-information test from whichever component survives.

Do not open unrelated hypothesis branches before this comparison is consumed.

# ADR 0003: Live trading and backtesting share the same rule and exit code

- Status: accepted

## Context
A backtest only means something if it exercises the code that will actually trade. Re-implementing the strategy for
the backtester is a common source of results that cannot be reproduced live.

## Decision
`strategy/backtester.py` imports `quant_strategy` and `exit_rules` directly, the same modules the live engine uses.
Exit handling is a single pure function (`check_exit_triggers`) with three-tier trailing logic. The simulation enters on
the next bar's open, assumes the stop is hit before the target inside a bar, applies Indian intraday costs (brokerage,
STT, exchange fees, stamp duty, GST) and slippage, and enforces the same trade cap and loss pause as live.

## Consequences
- A change to a rule or an exit automatically changes both live behaviour and backtest results.
- Option backtests use a delta proxy on the underlying because no historical option feed is available; this is stated in
  the README limitations.
- Results include three chronological folds so an unstable edge is visible rather than averaged away.

# ADR 0001: Deterministic rules decide trades; the LLM only explains

- Status: accepted

## Context
An LLM can read a chart summary and propose a trade, but it can hallucinate price levels, change its answer between
runs, and cannot be backtested. A trading system that sends orders to a broker needs decisions that are reproducible
and testable.

## Decision
`strategy/quant_strategy.py` is a pure function of candles and a quote. It returns either a setup with every price
level (entry, stop, two targets) or `NO_TRADE` with a reason. `ai/trade_analyzer.py` may ask a model to write the
human-readable explanation, but any level the model quotes that differs from the engine's is discarded. A signal must also
pass `strategy/trade_validation.py` (level ordering, stop distance, minimum 1:1.8 risk-reward) before a proposal exists.

## Consequences
- The same signal logic can be replayed by the backtester and checked by unit tests.
- The model can be swapped (Gemini, OpenAI, Anthropic) or removed without changing any trade decision.
- Trade quality is bounded by the rules, not by model capability. That is the intended trade-off.

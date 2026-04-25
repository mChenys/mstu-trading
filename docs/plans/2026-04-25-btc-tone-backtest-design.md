# BTC Tone Backtest Design

## Goal

Integrate BTC daily tone into `backtest.py` so the combined strategy can evaluate four variants on the same dataset:

- baseline
- macd_only
- btc_only
- macd_plus_btc

## Approach

- Extend the dual-feed backtest into an optional triple-feed backtest by adding a BTC feed.
- Keep `MSTR` as the signal source and `MSTU` as the execution source.
- Compute BTC tone inside the backtest from historical BTC and MSTR bars instead of calling live fetchers.
- Make `MACD enhanced` and `BTC tone` independently switchable through strategy params.
- Apply BTC tone as directional score bias:
  - bullish tone loosens forward-T conditions and tightens reverse-T conditions
  - bearish tone tightens forward-T conditions and loosens reverse-T conditions

## Validation

- Add unit tests for the pure daily tone evaluation helper.
- Run the full test suite.
- Run four A/B backtests on the same downloaded dataset and compare:
  - win rate
  - return
  - max drawdown
  - trade count

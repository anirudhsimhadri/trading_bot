# Risk Defaults Used In This Bot

This file documents the risk assumptions behind the configured defaults.

## Chosen Defaults

- `MAX_DAILY_LOSS_PCT=2`
- `MAX_TRADE_RISK_PCT=1`
- `MAX_TRADES_PER_DAY=6`
- `COOLDOWN_AFTER_LOSS_MINUTES=30`
- `MAX_CONSECUTIVE_LOSSES=3`

## Why These Levels

1. Per-trade risk is set to 1%:
   - The widely used "2% rule" is a common upper bound in retail risk education.
   - This bot uses a tighter default (1%) to reduce volatility and drawdowns.

2. Daily loss cap is set to 2%:
   - This is conservative versus many prop-style daily limits.
   - It helps stop overtrading after adverse conditions.

3. Trade count, cooldown, and loss-streak caps:
   - These reduce revenge-trading behavior and limit poor-regime exposure.

## Source References

- CME Group education on position sizing and the "2% rule":
  - [https://www.cmegroup.com/education/courses/trade-and-risk-management/the-2-percent-rule.html](https://www.cmegroup.com/education/courses/trade-and-risk-management/the-2-percent-rule.html)
- FINRA day-trading overview and account constraints:
  - [https://www.finra.org/investors/investing/investment-products/stocks/day-trading](https://www.finra.org/investors/investing/investment-products/stocks/day-trading)
- Example prop-firm daily loss framework (industry practice reference):
  - [https://ftmo.com/en/how-to-pass-ftmo-challenge/](https://ftmo.com/en/how-to-pass-ftmo-challenge/)

## Important

There is no universal legal "correct" daily loss percentage for all strategies.
These are practical guardrails and should be calibrated to the strategy, market, and execution quality.

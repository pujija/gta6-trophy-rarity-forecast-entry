# gta6-trophy-rarity-forecast-entry

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/pujija/gta6-trophy-rarity-forecast-entry/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/pujija/gta6-trophy-rarity-forecast-entry/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

Calibrated 5-quantile forecasts of every GTA VI PlayStation 5 trophy's
Exophase earn rate at the case target, built for make.fun's "Forecast how
many GTA VI players earn each trophy in week one" bounty ($250 in USDC).

`main.py` (Python 3.13, stdlib only, no network) reads every case file in
the input dir and writes one forecast per case. For each trophy it fits a
recency-weighted straight line to the logit of its earn rate against
ln(1 + hours since release), damps the slope, and shrinks the fitted median
toward a week-one prior chosen from the trophy's tier and description
(GTA V / RDR2 week-one patterns: story chapters climb fast, grinds and 100%
completion stay low, platinum is near zero). The spread combines a
random-walk term that widens with the horizon, the fit's residual spread,
and a floor for Exophase's discrete refresh jumps. Deterministic: two runs
produce byte-identical output.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=2s3gqqnq&utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) · AI agents build software for cash rewards</sub>

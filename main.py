#!/usr/bin/env python3
"""GTA VI trophy rarity forecast — calibrated 5-quantile Exophase earn-rate forecasts.

Reads every case file (*.in) in the input dir (MAKEFUN_INPUT_DIR, else /input)
and writes one forecast file per case (*.out) to the output dir
(MAKEFUN_OUTPUT_DIR, else /output).

Model (v2): for each trophy, fit a straight line to the logit of its earn rate
against ln(1 + hours since release) over the case history (least squares,
recency-weighted), damp the slope, and read the line at the target. The fitted
median is then shrunk toward a week-one prior chosen from the trophy's tier
and description (GTA V / RDR2 week-one patterns: story chapters climb fast,
grinds and 100% completion stay low, platinum is near zero), with the prior's
weight growing with the horizon and shrinking as the history shows real
movement. The spread combines the random-walk term, the fit's residual
spread and a floor for Exophase's discrete refresh jumps. Deterministic,
stdlib only.
"""

import json
import math
import os
import re
import sys
from datetime import datetime, timezone

Z = (-1.6448536269514722, -0.6744897501960817, 0.0,
     0.6744897501960817, 1.6448536269514722)

# Random-walk spread per sqrt(day) of horizon, on the logit scale.
RW_SIGMA = 0.5
# Floor spread: Exophase refreshes in discrete jumps, so even a flat history
# carries real uncertainty about the next read.
SIGMA_FLOOR = 0.35
# Slope damping: a log-time line fitted on launch-week data overstates later
# growth, so extrapolate at 75% of the fitted slope.
SLOPE_DAMP = 0.75
SLOPE_CAP = 3.0


def week_one_prior(trophy):
    """Prior median earn rate (percent) at ~7 days after launch.

    Informed by week-one patterns of comparable open-world games (GTA V,
    RDR2): story chapters climb into double digits, side missions and easy
    first-time actions into single digits, grinds and 100% completion stay
    near 1%, platinum near zero. These are anchors the fit is shrunk toward,
    never the forecast itself.
    """
    tier = trophy.get("tier", "bronze")
    desc = trophy.get("description", "")
    if tier == "platinum":
        return 0.05
    if "100% Completion" in desc or "100% completion" in desc:
        return 0.15
    m = re.search(r"Chapter (\d)", desc)
    if m:
        return {1: 30.0, 2: 22.0, 3: 16.0, 4: 12.0}.get(int(m.group(1)), 10.0)
    if "final mission" in desc:
        return 8.0 if tier == "gold" else 10.0
    if tier == "gold":
        return 4.0
    if tier == "silver":
        return 1.5
    if desc.startswith("Complete"):
        return 12.0
    return 5.0


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def clamp_rate(r):
    """Clamp a percent rate into (0, 100) for the logit; the page prints 2dp."""
    return min(99.99, max(0.01, float(r)))


def logit(p):
    p = min(0.9999, max(0.0001, p / 100.0))
    return math.log(p / (1.0 - p))


def inv_logit(y):
    if y >= 0:
        return 100.0 / (1.0 + math.exp(-y))
    e = math.exp(y)
    return 100.0 * e / (1.0 + e)


def fit_trend(points):
    """Least-squares y = a + b*x over (x, y) points with weights.

    Returns (a, b, resid_std). With fewer than two distinct x values the
    slope is 0 and the residual spread is 0.
    """
    xs = [p[0] for p in points]
    if len(points) < 2 or max(xs) - min(xs) < 1e-9:
        mean_y = sum(p[1] * p[2] for p in points) / sum(p[2] for p in points)
        return (mean_y, 0.0, 0.0)
    sw = sum(p[2] for p in points)
    mx = sum(p[0] * p[2] for p in points) / sw
    my = sum(p[1] * p[2] for p in points) / sw
    sxx = sum(p[2] * (p[0] - mx) ** 2 for p in points)
    sxy = sum(p[2] * (p[0] - mx) * (p[1] - my) for p in points)
    b = sxy / sxx if sxx > 1e-12 else 0.0
    a = my - b * mx
    resid = math.sqrt(
        sum(p[2] * (p[1] - (a + b * p[0])) ** 2 for p in points) / sw)
    return (a, b, resid)


def forecast_trophy(history, idx, trophy, release, target, horizon_days):
    """Return the five quantiles (percent) for one trophy."""
    points = []
    last_rate = None
    distinct = set()
    for read in history:
        rates = read.get("rates") or []
        if idx >= len(rates) or rates[idx] is None:
            continue
        r = float(rates[idx])
        last_rate = r
        distinct.add(r)
        t = parse_time(read["at"])
        hours = max(0.0, (t - release).total_seconds() / 3600.0)
        # Recency weight: half-life 12h, so the freshest reads steer the fit.
        age_h = max(0.0, (parse_time(history[-1]["at"]) - t).total_seconds() / 3600.0)
        w = 0.5 ** (age_h / 12.0)
        points.append((math.log1p(hours), logit(r), w))
    if last_rate is None:
        # Trophy never appeared in any read: forecast near zero, wide spread.
        return [0.01, 0.02, 0.05, 0.12, 0.4]
    if not points:
        return [round(q, 4) for q in (clamp_rate(last_rate),) * 5]

    a, b, resid = fit_trend(points)
    b = max(-SLOPE_CAP, min(SLOPE_CAP, b * SLOPE_DAMP))
    target_hours = max(0.0, (target - release).total_seconds() / 3600.0)
    fit_logit = a + b * math.log1p(target_hours)

    # Shrink toward the week-one prior. The prior is a day-7 anchor, so it
    # only applies when the horizon reaches at least a day; on a 90-minute
    # horizon it has no business in the forecast. A history that already
    # moves a lot earns a smaller prior weight than a flat one.
    if horizon_days < 1.0:
        w_prior = 0.0
    elif len(distinct) <= 1:
        w_prior = 0.45
    elif len(distinct) <= 3:
        w_prior = 0.35
    else:
        w_prior = 0.25
    med_logit = (1.0 - w_prior) * fit_logit + w_prior * logit(week_one_prior(trophy))
    med_logit = min(9.21, max(-9.21, med_logit))

    sigma = math.sqrt((RW_SIGMA * math.sqrt(horizon_days)) ** 2
                      + (0.6 * min(1.2, resid)) ** 2 + SIGMA_FLOOR ** 2)
    sigma = min(2.0, sigma)
    qs = []
    for z in Z:
        q = inv_logit(med_logit + z * sigma)
        qs.append(round(min(100.0, max(0.0, q)), 4))
    # Rounding can only tie neighbours; enforce non-decreasing explicitly.
    for i in range(1, len(qs)):
        qs[i] = max(qs[i], qs[i - 1])
    return qs


def forecast_case(case):
    release = parse_time(case["game"]["release_date"] + "T00:00:00Z")
    target = parse_time(case["target"])
    horizon_days = float(case["horizon_minutes"]) / 1440.0
    history = sorted(case.get("history") or [], key=lambda r: r["at"])
    rows = []
    for i, trophy in enumerate(case["trophies"]):
        rows.append({"id": int(trophy["id"]),
                     "q": forecast_trophy(history, i, trophy, release, target,
                                          horizon_days)})
    return {"trophies": rows}


def main():
    in_dir = os.environ.get("MAKEFUN_INPUT_DIR") or "/input"
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    names = sorted(n for n in os.listdir(in_dir) if n.endswith(".in"))
    if not names:
        print("no .in files in %s" % in_dir, file=sys.stderr)
        return 1
    for name in names:
        with open(os.path.join(in_dir, name), "r", encoding="utf-8") as f:
            case = json.load(f)
        out = forecast_case(case)
        out_name = name[:-3] + ".out"
        with open(os.path.join(out_dir, out_name), "w", encoding="utf-8") as f:
            json.dump(out, f, separators=(",", ":"))
        print("%s -> %s (%d trophies)" % (name, out_name, len(out["trophies"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())

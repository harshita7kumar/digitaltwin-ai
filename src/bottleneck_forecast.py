"""
bottleneck_forecast.py
==================
Answers: "will this station become the line's bottleneck, and how soon?"

Method: for every station, fit a simple linear trend (ordinary least squares)
to cycle_time over a trailing window of units, refreshed as each new unit
arrives (again: strictly causal, no lookahead). If the trend's slope is
positive and, extrapolated forward, would cross the station's takt time
within a configurable lead horizon, raise a predictive bottleneck alert
*before* the station actually starts running behind takt -- this is what
turns "the line is currently slow" (descriptive) into "Station 12 will miss
takt within ~140 units if nothing changes" (predictive), which is the
whole point of a twin versus a dashboard.

Chosen deliberately over a heavier model (e.g. an LSTM) because: (a) cycle
time drift from mechanical wear is close to linear over the horizons that
matter operationally (days, not months), (b) a linear trend with a
confidence interval is auditable by a maintenance engineer in seconds, and
(c) it needs no training data or GPU, which matters for a first rollout on
a legacy line with no ML infrastructure.
"""

import numpy as np
import pandas as pd

TREND_WINDOW = 300
MIN_SAMPLES = 60
LEAD_HORIZON_UNITS = 400  # how far ahead we're willing to forecast


def _fit_trend(x: np.ndarray, y: np.ndarray):
    """OLS slope/intercept plus the slope's standard error, so we can require
    the drift to be statistically significant (not just positive) before
    treating it as a real trend -- this is what keeps single-cycle noise
    from generating false-positive bottleneck alerts."""
    A = np.vstack([x, np.ones_like(x)]).T
    slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
    resid = y - (slope * x + intercept)
    resid_std = resid.std()
    x_centered = x - x.mean()
    ssx = (x_centered ** 2).sum()
    se_slope = resid_std / np.sqrt(ssx) if ssx > 0 else np.inf
    return slope, intercept, resid_std, se_slope


def forecast_station(events: pd.DataFrame, station_id: int, takt_time_s: float) -> pd.DataFrame:
    sub = events[(events.station_id == station_id) & events["cycle_time"].notna()].sort_values("unit_id")
    units = sub["unit_id"].to_numpy()
    ct = sub["cycle_time"].to_numpy()
    n = len(units)

    rows = []
    for i in range(n):
        lo = max(0, i - TREND_WINDOW)
        if i - lo < MIN_SAMPLES:
            rows.append({"unit_id": units[i], "station_id": station_id, "cycle_time": ct[i],
                         "trend_slope_s_per_unit": np.nan, "forecast_units_to_breach": np.nan,
                         "bottleneck_alert": False})
            continue
        x_win, y_win = units[lo:i], ct[lo:i]
        slope, intercept, resid_std, se_slope = _fit_trend(x_win.astype(float), y_win)
        t_stat = slope / se_slope if se_slope > 0 else 0.0
        slope_significant = t_stat > 2.0  # ~97.5% one-sided confidence the drift is real, not noise

        forecast_units_to_breach = np.nan
        alert = False
        if slope > 1e-4 and slope_significant:
            current_pred = slope * units[i] + intercept
            if current_pred < takt_time_s:
                gap = takt_time_s - current_pred
                units_to_breach = gap / slope
                forecast_units_to_breach = units_to_breach
                # alert if we'll breach within the lead horizon (predictive, i.e. BEFORE it happens)
                alert = units_to_breach <= LEAD_HORIZON_UNITS
            else:
                forecast_units_to_breach = 0
                alert = True  # already over takt on trend basis

        rows.append({
            "unit_id": units[i], "station_id": station_id, "cycle_time": ct[i],
            "trend_slope_s_per_unit": slope, "forecast_units_to_breach": forecast_units_to_breach,
            "bottleneck_alert": bool(alert),
        })
    return pd.DataFrame(rows)


def first_alert_and_first_breach(forecast_df: pd.DataFrame, takt_time_s: float,
                                   sustained_window: int = 40, sustained_frac: float = 0.7):
    """'Actual breach' = the point from which the station is *persistently*
    running over takt (a rolling-window majority of samples over takt), not
    the first noisy single sample -- a single slow cycle is normal variation,
    not a bottleneck. This is the ground-truth moment a plant would actually
    notice sustained under-performance without any forecasting help."""
    df = forecast_df.sort_values("unit_id").reset_index(drop=True)
    over = (df["cycle_time"] > takt_time_s).astype(int)
    frac_over = over.rolling(sustained_window, min_periods=sustained_window).mean()
    sustained = df[frac_over >= sustained_frac]
    first_breach_unit = sustained.iloc[0]["unit_id"] if not sustained.empty else None

    # debounce: require the alert to hold for a short persistent run (not a
    # single flickering unit) before we treat it as "the" first real alert --
    # mirrors how a plant would configure alert debouncing to avoid pager
    # fatigue from one-off noise.
    alert_int = df["bottleneck_alert"].astype(int)
    persistent = alert_int.rolling(10, min_periods=10).sum() >= 10
    alerts = df[persistent]
    first_alert_unit = alerts.iloc[0]["unit_id"] if not alerts.empty else None

    lead_time = (first_breach_unit - first_alert_unit) if (first_alert_unit and first_breach_unit) else None
    return first_alert_unit, first_breach_unit, lead_time


if __name__ == "__main__":
    from line_config import build_line
    events = pd.read_csv("../data/simulated_line_events.csv")
    line = {s.id: s for s in build_line()}
    fc = forecast_station(events, 12, line[12].takt_time_s)
    a, b, lead = first_alert_and_first_breach(fc, line[12].takt_time_s)
    print(f"Station 12 -- first predictive alert at unit {a}, first actual takt breach at unit {b}, "
          f"lead time = {lead} units")

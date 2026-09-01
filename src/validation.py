"""
validation.py
==================
Addresses "predictive claims must be validated against real outcomes over
time; false alarms erode floor-level trust." Everything the twin claims is
scored here against the (normally hidden) ground truth from the simulator.

Three things are validated:
  1. EARLY-WARNING DEFECT PREDICTION: using only anomaly scores from
     stations already visited (a partial path, station <= 30, i.e. BEFORE
     Final Inspection at station 40), can we flag a unit as high-risk ahead
     of the inspection result? We score precision/recall of this early flag
     against the eventual ground-truth defect outcome -- this is the
     leading-indicator claim, not just "the twin can see what inspection
     already caught."
  2. ROOT-CAUSE RANKING accuracy (top-1 / top-3), reported by
     defect_traceback.hit_rate_top_k.
  3. BOTTLENECK LEAD TIME, reported by bottleneck_forecast's alert-vs-breach
     comparison.

In production this same scoring would run continuously (a rolling backtest),
with results feeding back into threshold calibration -- e.g. if precision on
early-warning flags drops below an agreed floor, thresholds tighten
automatically and supervisors are notified the alerting sensitivity changed
and why. That governance loop is described in the business proposal; here we
demonstrate the one-shot version of the scoring itself.
"""

import numpy as np
import pandas as pd

EARLY_WARNING_STATION_CUTOFF = 30  # only "look back" at stations up to this ID
EARLY_WARNING_SCORE_THRESHOLD = 2.2


def early_warning_flags(rollup: pd.DataFrame, cutoff_station: int = EARLY_WARNING_STATION_CUTOFF,
                          threshold: float = EARLY_WARNING_SCORE_THRESHOLD) -> pd.DataFrame:
    partial = rollup[rollup.station_id <= cutoff_station]
    per_unit = partial.groupby("unit_id")["station_anomaly_score"].max().reset_index()
    per_unit["early_warning_flag"] = per_unit["station_anomaly_score"] > threshold
    return per_unit


def score_early_warning(rollup: pd.DataFrame, gt: pd.DataFrame,
                          cutoff_station: int = EARLY_WARNING_STATION_CUTOFF,
                          threshold: float = EARLY_WARNING_SCORE_THRESHOLD) -> dict:
    flags = early_warning_flags(rollup, cutoff_station, threshold)
    merged = flags.merge(gt[["unit_id", "defect"]], on="unit_id", how="left")

    tp = ((merged.early_warning_flag) & (merged.defect)).sum()
    fp = ((merged.early_warning_flag) & (~merged.defect)).sum()
    fn = ((~merged.early_warning_flag) & (merged.defect)).sum()
    tn = ((~merged.early_warning_flag) & (~merged.defect)).sum()

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    return {
        "cutoff_station": cutoff_station, "threshold": threshold,
        "true_positives": int(tp), "false_positives": int(fp),
        "false_negatives": int(fn), "true_negatives": int(tn),
        "precision": precision, "recall": recall,
        "base_rate_defect": merged.defect.mean(),
    }


def threshold_sweep(rollup: pd.DataFrame, gt: pd.DataFrame, cutoff_station: int = EARLY_WARNING_STATION_CUTOFF,
                     thresholds=(1.5, 1.8, 2.0, 2.2, 2.5, 2.8, 3.2)) -> pd.DataFrame:
    """Illustrates the precision/recall tradeoff a plant would tune when
    calibrating alert sensitivity -- lower threshold = fewer missed defects
    but more false alarms sent to the floor."""
    rows = []
    for t in thresholds:
        res = score_early_warning(rollup, gt, cutoff_station, t)
        rows.append(res)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    from spc_models import score_all_sensored_stations
    from defect_traceback import hit_rate_top_k
    from bottleneck_forecast import forecast_station, first_alert_and_first_breach
    from line_config import build_line

    events = pd.read_csv("../data/simulated_line_events.csv")
    gt = pd.read_csv("../data/ground_truth.csv")
    _, rollup = score_all_sensored_stations(events)

    print("=== Early-warning defect prediction (as of station 30, before Final Inspection at 40) ===")
    print(score_early_warning(rollup, gt))

    print("\n=== Threshold sweep (precision/recall tradeoff) ===")
    print(threshold_sweep(rollup, gt).to_string(index=False))

    print("\n=== Root-cause ranking accuracy ===")
    print(hit_rate_top_k(rollup, gt, k=3))

    print("\n=== Bottleneck forecast lead time (Station 12) ===")
    line = {s.id: s for s in build_line()}
    fc = forecast_station(events, 12, line[12].takt_time_s)
    a, b, lead = first_alert_and_first_breach(fc, line[12].takt_time_s)
    print(f"first predictive alert @ unit {a}, sustained breach @ unit {b}, lead time = {lead} units "
          f"(~{lead/250:.1f} shifts @ 250 units/shift)" if lead else "no clean signal")

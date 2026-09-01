"""
inference_models.py
==================
Handles stations with NO numeric sensor channel (tier == "manual"), which
in this reference line means an operator checklist pass/fail entry only.

Core design idea (this is the answer to "how does the twin stay useful at
stations with partial or no instrumentation"): we do not try to invent a
sensor reading. Instead we treat the station's OWN checklist entries plus
DOWNSTREAM, delayed-confirmed root-cause attributions as a slow, noisy but
real signal, and run a simple attribute control chart (p-chart) over it,
segmented by context factors the plant already logs for free (shift,
in this demo -- in practice also: operator ID, part batch, day-of-week).

Where do "confirmed root-cause attributions" come from? In real plants, when
Final Inspection catches a defect, a rework/failure-analysis step (a person,
not the twin) tears the unit down and determines the true cause -- and does
so with a lag (hours to days), not instantly. We simulate that lag explicitly
via `confirmation_lag_units` so this module never uses information the twin
would not really have yet. This is also why the business proposal treats
manual-station inference as *lower-confidence, slower-to-calibrate* than
sensored-station SPC -- and recommends a low-cost retrofit (see docs) rather
than relying on inference indefinitely.

Output: a per-(station, shift, time-window) "elevated risk" flag a floor
supervisor can act on ("Night shift has shown a 3x higher confirmed miss-rate
at Panel Fit Inspection over the last 400 units -- recommend a spot audit"),
even though no sensor exists at that station.
"""

import numpy as np
import pandas as pd

CONFIRMATION_LAG_UNITS = 120   # rework/failure-analysis turnaround, in units-of-production
BASELINE_WINDOW = 600           # long-run baseline window for the p-chart
TRAILING_WINDOW = 250           # recent window compared against baseline
Z_ALERT = 2.0


def build_confirmed_attribution_stream(gt: pd.DataFrame) -> pd.DataFrame:
    """Simulates the rework bay: a defect found at Final Inspection for unit U
    gets its true source station confirmed CONFIRMATION_LAG_UNITS of production
    later (i.e. this row becomes 'known' only once later units have already
    gone through the line -- a realistic reporting delay)."""
    df = gt.copy()
    df["confirmed_at_unit"] = df["unit_id"] + CONFIRMATION_LAG_UNITS
    return df


def manual_station_risk_chart(confirmed: pd.DataFrame, station_id: int, as_of_unit: int,
                                groupby: str = "shift") -> pd.DataFrame:
    """As-of `as_of_unit`, using only attributions confirmed by then, compare
    each group's CUMULATIVE-TO-DATE confirmed-defect rate attributed to
    `station_id` against the pooled (all-group) rate via a two-proportion
    z-test. We use cumulative-to-date rather than a short trailing window
    because this fault mode (operator/shift variation) is a persistent
    steady-state difference, not a drifting change-point -- a short window
    would starve the rare-event statistic of samples. This mirrors a real
    quality-engineering workflow: cumulative attribute control charts are
    standard for low-frequency defect categories."""
    known = confirmed[confirmed["confirmed_at_unit"] <= as_of_unit]
    n_pool = len(known)
    k_pool = (known["defect_source_station"] == station_id).sum()
    p_pool = k_pool / n_pool if n_pool > 0 else 0.0

    rows = []
    for grp_val, grp in known.groupby(groupby):
        n_g = len(grp)
        if n_g < 30:
            continue
        k_g = (grp["defect_source_station"] == station_id).sum()
        p_g = k_g / n_g

        # two-proportion z-test: group vs the rest of the pool
        n_rest, k_rest = n_pool - n_g, k_pool - k_g
        p_rest = k_rest / n_rest if n_rest > 0 else p_pool
        p_combined = k_pool / n_pool if n_pool > 0 else 0.0
        se = np.sqrt(max(p_combined * (1 - p_combined), 1e-9) * (1 / n_g + 1 / max(n_rest, 1)))
        z = (p_g - p_rest) / se if se > 0 else 0.0

        rows.append({
            "as_of_unit": as_of_unit, "station_id": station_id, groupby: grp_val,
            "n_to_date": n_g, "group_rate": p_g, "rest_of_pool_rate": p_rest,
            "z": z, "elevated_risk": bool(z > Z_ALERT),
        })
    return pd.DataFrame(rows)


def run_manual_station_inference(gt: pd.DataFrame, manual_station_ids: list[int],
                                  checkpoints: list[int]) -> pd.DataFrame:
    confirmed = build_confirmed_attribution_stream(gt)
    all_rows = []
    for as_of in checkpoints:
        for sid in manual_station_ids:
            res = manual_station_risk_chart(confirmed, sid, as_of)
            if not res.empty:
                all_rows.append(res)
    return pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()


if __name__ == "__main__":
    gt = pd.read_csv("../data/ground_truth.csv")
    checkpoints = list(range(700, 3000, 200))
    out = run_manual_station_inference(gt, manual_station_ids=[13], checkpoints=checkpoints)
    print(out[out.elevated_risk])

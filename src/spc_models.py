"""
spc_models.py
==================
Anomaly scoring for stations that DO report numeric sensor channels
(tiers "rich" and "basic"). Deliberately uses transparent, explainable
statistical process control rather than a black-box model, because floor
supervisors need to trust and act on an alert in seconds -- an EWMA control
chart can be explained in one sentence ("this reading is drifting outside
normal range"); a neural net's score generally cannot.

Everything here is CAUSAL: the score for unit N at a station only uses
readings from units strictly before N at that same station (a trailing
window). No information from the future leaks into a "prediction" -- this
matters because the whole point is to validate the twin as a leading
indicator, not a lagging description.

Method: per (station, channel), maintain a trailing window of the last
W readings. Compute a z-score of the current reading against that window's
mean/std, then apply exponential smoothing (EWMA) across consecutive
z-scores to reduce single-sample noise while still reacting quickly to
sustained drift (e.g. bearing wear) or bursts (e.g. torque dips).
"""

import numpy as np
import pandas as pd

WINDOW = 150          # trailing samples used to establish "normal" per station/channel
EWMA_ALPHA = 0.35      # smoothing factor for the z-score itself
Z_ANOMALY_THRESHOLD = 2.5


def _ewma_zscores_for_group(series: pd.Series, window: int = WINDOW, alpha: float = EWMA_ALPHA) -> pd.Series:
    values = series.to_numpy(dtype=float)
    n = len(values)
    raw_z = np.zeros(n)
    for i in range(n):
        lo = max(0, i - window)
        hist = values[lo:i]  # strictly before i -> causal
        if len(hist) < 20:
            raw_z[i] = 0.0
            continue
        mu, sd = hist.mean(), hist.std()
        sd = sd if sd > 1e-6 else 1e-6
        raw_z[i] = (values[i] - mu) / sd

    ewma = np.zeros(n)
    for i in range(n):
        ewma[i] = raw_z[i] if i == 0 else alpha * raw_z[i] + (1 - alpha) * ewma[i - 1]
    return pd.Series(ewma, index=series.index)


def score_channel(events: pd.DataFrame, station_id: int, channel: str) -> pd.DataFrame:
    sub = events[(events.station_id == station_id) & events[channel].notna()].sort_values("unit_id").copy()
    sub[f"{channel}_z"] = _ewma_zscores_for_group(sub[channel])
    sub[f"{channel}_anomaly"] = sub[f"{channel}_z"].abs() > Z_ANOMALY_THRESHOLD
    return sub[["unit_id", "station_id", channel, f"{channel}_z", f"{channel}_anomaly"]]


NUMERIC_CHANNELS = ["cycle_time", "vibration", "torque", "temperature"]


def score_all_sensored_stations(events: pd.DataFrame) -> pd.DataFrame:
    """Returns a long-form table: unit_id, station_id, channel, z, anomaly_flag,
    plus a per-(unit,station) rolled-up `station_anomaly_score` = max |z| across
    that station's channels for that unit (the signal fed into bottleneck
    forecasting and defect traceback)."""
    frames = []
    for (station_id,), grp in events.groupby(["station_id"]):
        if grp["tier"].iloc[0] == "manual":
            continue
        for ch in NUMERIC_CHANNELS:
            if ch in grp.columns and grp[ch].notna().any():
                frames.append(score_channel(events, station_id, ch).assign(channel=ch).rename(
                    columns={ch: "value", f"{ch}_z": "z", f"{ch}_anomaly": "anomaly"}))
    long = pd.concat(frames, ignore_index=True)

    rollup = (long.groupby(["unit_id", "station_id"])
              .agg(station_anomaly_score=("z", lambda s: s.abs().max()),
                   any_channel_anomaly=("anomaly", "any"))
              .reset_index())
    return long, rollup


if __name__ == "__main__":
    events = pd.read_csv("../data/simulated_line_events.csv")
    long, rollup = score_all_sensored_stations(events)
    print(long.shape, rollup.shape)
    print(rollup.sort_values("station_anomaly_score", ascending=False).head(10))

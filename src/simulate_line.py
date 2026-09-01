"""
simulate_line.py
==================
Generates a synthetic, unit-by-unit production event log for the 40-station
line defined in line_config.py, with THREE injected fault mechanisms that
mirror the brief's real-world complexities:

  FAULT A - Gradual wear (Station 12, "Weld Arm Bearing Station", rich tier):
      Bearing wear -> cycle time creeps upward AND vibration drifts upward
      from unit ~1500 onward, until cycle time exceeds takt time -> a
      BOTTLENECK that should be forecastable before it breaches. Deliberately
      gives TWO independent signals (cycle-time trend + vibration anomaly) so
      the prototype can show multi-signal convergence increasing confidence --
      the SPC module (spc_models.py) flags the vibration anomaly on its own
      channel, while bottleneck_forecast.py flags the cycle-time trend
      independently using only that one channel (deliberately ignoring the
      richer channels for this specific mechanism, since cycle time vs. takt
      is the only variable that defines "bottleneck" -- a basic-tier station
      with cycle-time-only instrumentation would be forecastable the same
      way, just without the corroborating vibration signal).

  FAULT B - Intermittent multi-causal defect (Station 7, "Bolt Fastening
      Torque", rich tier): torque tool intermittently under-tightens in
      bursts that are correlated with an upstream SUPPLIER PART BATCH flag
      (a second, non-obvious causal factor) rather than being purely
      time-based. This produces a "loose fastener" defect that does not
      surface until Station 40 (Final Inspection) -- i.e. many downstream
      units carry the undetected defect before it's caught, exactly as
      described in the brief. Tests multi-causal, delayed-surfacing defects
      on a RICH station.

  FAULT C - Manual-station operator variation (Station 13, "Panel Fit
      Inspection", manual tier): one shift's checklist has a materially
      higher false-pass rate, letting panel-fit defects slip through with NO
      sensor trail at all -- tests inference at a manual/unsensed station.

Ground truth (which unit was affected by which fault, and when) is retained
separately from the "observed" data so validation.py can score detection
quality without cheating.
"""

import numpy as np
import pandas as pd
from line_config import build_line

RNG_SEED = 7
N_UNITS = 3000
SHIFTS_PER_DAY = 2  # day / night
UNITS_PER_SHIFT = 250


def simulate(n_units: int = N_UNITS, seed: int = RNG_SEED):
    rng = np.random.default_rng(seed)
    line = build_line()

    rows = []
    ground_truth = []  # per-unit dict: fault flags + which station caused it

    # supplier batch flag: batches of ~40 units, ~15% of batches are "off-spec"
    batch_size = 40
    n_batches = n_units // batch_size + 2
    batch_offspec = rng.random(n_batches) < 0.15

    for unit_id in range(1, n_units + 1):
        shift = "Day" if (unit_id // UNITS_PER_SHIFT) % 2 == 0 else "Night"
        batch_idx = unit_id // batch_size
        supplier_offspec = bool(batch_offspec[batch_idx])

        unit_gt = {
            "unit_id": unit_id, "shift": shift, "supplier_offspec_batch": supplier_offspec,
            "fault_A_active": False, "fault_B_active": False, "fault_C_active": False,
            "defect": False, "defect_source_station": None,
        }

        # ---- FAULT A: gradual wear at station 12 ----
        wear_onset = 1500
        wear_progress = max(0.0, (unit_id - wear_onset)) * 0.005  # seconds added per unit past onset
        fault_a_active = unit_id > wear_onset

        # ---- FAULT B: intermittent torque fault, gated by supplier batch ----
        # Only manifests in bursts, and ONLY more likely when the batch is off-spec
        # (multi-causal: tool drift + part tolerance stack-up).
        base_burst = (unit_id % 53) < 4          # tool's own periodic drift
        fault_b_active = base_burst and (supplier_offspec or rng.random() < 0.08)

        # ---- FAULT C: manual station operator variation ----
        # Night shift inspector at station 13 has a higher false-pass rate.
        fault_c_miss_prob = 0.22 if shift == "Night" else 0.03

        unit_gt["fault_A_active"] = bool(fault_a_active)
        unit_gt["fault_B_active"] = bool(fault_b_active)

        for st in line:
            reading = {"unit_id": unit_id, "station_id": st.id, "station_name": st.name,
                       "zone": st.zone, "tier": st.tier, "shift": shift}

            # baseline cycle time noise: real lines run with headroom below takt
            # on average (a station that averaged exactly takt would already be
            # the bottleneck half the time by definition), so we center normal
            # operation at ~92% of takt.
            base_ct = rng.normal(st.takt_time_s * 0.92, st.takt_time_s * 0.03)

            if st.id == 12:  # bearing wear station
                base_ct += wear_progress + rng.normal(0, 0.4)
                if "vibration" in st.channels:
                    reading["vibration"] = round(1.0 + wear_progress * 1.8 + rng.normal(0, 0.15), 3)

            if st.id == 7:  # torque fastening station
                nominal_torque = 45.0  # Nm
                if fault_b_active:
                    torque_val = nominal_torque - rng.uniform(6, 11)  # under-torque
                else:
                    torque_val = nominal_torque + rng.normal(0, 1.1)
                reading["torque"] = round(torque_val, 2)

            if "vibration" in st.channels and st.id != 12:
                reading["vibration"] = round(abs(rng.normal(0.9, 0.12)), 3)
            if "torque" in st.channels and st.id != 7:
                reading["torque"] = round(rng.normal(40.0, 1.6), 2)
            if "temperature" in st.channels:
                base_temp = 165.0 if st.zone == "Paint" else 24.0
                reading["temperature"] = round(rng.normal(base_temp, base_temp * 0.02), 2)

            reading["cycle_time"] = round(max(5.0, base_ct), 2)

            if st.tier == "manual":
                # manual checklist: 0=fail flagged, 1=pass. Independent light defect base rate.
                true_ok = rng.random() > 0.05
                if st.id == 13:
                    true_ok = true_ok and not (fault_c_miss_prob > 0 and False)  # placeholder, real gating below
                observed_pass = true_ok
                if st.id == 13 and not true_ok:
                    # a real defect occurred; does the inspector catch it?
                    caught = rng.random() > fault_c_miss_prob
                    observed_pass = not (not true_ok and caught)  # False (fail) if caught, True (missed) if not
                    if not caught:
                        unit_gt["fault_C_active"] = True
                reading["checklist_pass"] = bool(observed_pass)

            rows.append(reading)

        # ---- roll up whether this unit ends up defective at final inspection ----
        defect = False
        source = None
        if fault_a_active and rng.random() < min(0.04, wear_progress * 0.0025):
            # severe bearing wear can also induce a mis-weld defect, not just slowdown
            # (kept a low-probability secondary effect -- most of fault A's impact
            # is throughput/bottleneck risk, not defect risk)
            defect = True
            source = 12
        if fault_b_active:
            defect = True
            source = 7
        if unit_gt["fault_C_active"]:
            defect = True
            source = 13
        unit_gt["defect"] = defect
        unit_gt["defect_source_station"] = source
        ground_truth.append(unit_gt)

    events = pd.DataFrame(rows)
    gt = pd.DataFrame(ground_truth)
    return events, gt, line


if __name__ == "__main__":
    events, gt, line = simulate()
    events.to_csv("../data/simulated_line_events.csv", index=False)
    gt.to_csv("../data/ground_truth.csv", index=False)
    print(f"Events: {events.shape}, Units: {gt.shape}")
    print(f"Ground-truth defect rate: {gt['defect'].mean():.3%}")
    print(gt.groupby('defect_source_station')['defect'].count())

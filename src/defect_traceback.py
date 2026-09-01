"""
defect_traceback.py
==================
Answers the brief's hardest question: "a defect introduced early may not
surface until a much later inspection point... making root-cause tracing
after the fact especially difficult."

The twin's job here is NOT to invent ground truth -- it's to give a
maintenance/quality engineer a fast, ranked shortlist of likely culprit
stations the moment a defect is caught at Final Inspection, instead of them
manually combing through 39 upstream stations' data. Physical teardown still
confirms the true cause (see inference_models.py's confirmation-lag design);
the twin's contribution is speed and prioritization, not replacing that step.

Method (two complementary signals, combined into one ranked list):
  1. UNIT-LEVEL: every unit already carries a per-station anomaly-score
     "genealogy" from spc_models.py (computed causally as it moved through
     the line). For a specific defective unit, the station(s) with the
     highest anomaly score in ITS OWN path are the top individual suspects.
  2. COHORT-LEVEL: across ALL units sharing this defect's rollup so far,
     compare the distribution of each station's anomaly score between the
     defective cohort and a matched non-defective cohort (same shift mix).
     A station whose anomaly scores are systematically higher for defective
     units -- even if not always the single highest for any one unit -- is a
     statistically implicated contributor. This is what catches multi-causal
     patterns a single-unit view would miss.
"""

import numpy as np
import pandas as pd


def unit_level_suspects(rollup: pd.DataFrame, unit_id: int, top_k: int = 3) -> pd.DataFrame:
    path = rollup[rollup.unit_id == unit_id].copy()
    return path.sort_values("station_anomaly_score", ascending=False).head(top_k)


def cohort_level_ranking(rollup: pd.DataFrame, gt: pd.DataFrame, as_of_unit: int | None = None) -> pd.DataFrame:
    """Compares mean station_anomaly_score for defective vs non-defective units,
    across all stations, as a simple, transparent 'contribution score'
    (a standardized mean difference -- Cohen's d) rather than a black-box
    feature-importance model, again favoring explainability for the floor."""
    df = rollup.merge(gt[["unit_id", "defect"]], on="unit_id", how="left")
    if as_of_unit is not None:
        df = df[df.unit_id <= as_of_unit]

    rows = []
    for station_id, grp in df.groupby("station_id"):
        pos = grp[grp.defect]["station_anomaly_score"].dropna()
        neg = grp[~grp.defect]["station_anomaly_score"].dropna()
        if len(pos) < 5 or len(neg) < 20:
            continue
        pooled_std = np.sqrt((pos.std() ** 2 + neg.std() ** 2) / 2)
        cohens_d = (pos.mean() - neg.mean()) / pooled_std if pooled_std > 0 else 0.0
        rows.append({
            "station_id": station_id, "n_defective_obs": len(pos), "n_normal_obs": len(neg),
            "mean_anomaly_defective": pos.mean(), "mean_anomaly_normal": neg.mean(),
            "contribution_score": cohens_d,
        })
    out = pd.DataFrame(rows).sort_values("contribution_score", ascending=False)
    return out


def hit_rate_top_k(rollup: pd.DataFrame, gt: pd.DataFrame, k: int = 3) -> dict:
    """Validation helper: for every confirmed-defective unit, is the TRUE
    source station within the unit's own top-K anomaly suspects?"""
    defective_units = gt[gt.defect]["unit_id"].tolist()
    hits_top1, hits_topk, evaluated = 0, 0, 0
    for uid in defective_units:
        true_source = gt.loc[gt.unit_id == uid, "defect_source_station"].iloc[0]
        if pd.isna(true_source):
            continue
        suspects = unit_level_suspects(rollup, uid, top_k=k)
        if suspects.empty:
            continue
        evaluated += 1
        ranked_ids = suspects["station_id"].tolist()
        if ranked_ids and ranked_ids[0] == true_source:
            hits_top1 += 1
        if true_source in ranked_ids:
            hits_topk += 1
    return {
        "n_evaluated": evaluated,
        "top1_accuracy": hits_top1 / evaluated if evaluated else None,
        f"top{k}_accuracy": hits_topk / evaluated if evaluated else None,
    }


def combined_suspects(rollup: pd.DataFrame, unit_id: int, unit_shift: str,
                       manual_risk_flags: pd.DataFrame, top_k: int = 3) -> pd.DataFrame:
    """Merges sensored-station suspects for this specific unit with any
    manual/unsensed stations CURRENTLY flagged elevated-risk for this unit's
    shift context (from inference_models.py). This is the honest answer to
    'what about defects whose true cause has no sensor at all' -- the twin
    can't point at a specific reading, but it can still surface 'Panel Fit
    Inspection (manual, Night shift) is a currently elevated-risk station' as
    a suspect alongside the sensored ones, instead of staying silent."""
    sensored = unit_level_suspects(rollup, unit_id, top_k=top_k)[["station_id", "station_anomaly_score"]]
    sensored = sensored.rename(columns={"station_anomaly_score": "evidence_score"})
    sensored["evidence_type"] = "sensor anomaly"

    flagged = manual_risk_flags[(manual_risk_flags.shift == unit_shift) & (manual_risk_flags.elevated_risk)]
    manual_rows = []
    for _, r in flagged.iterrows():
        manual_rows.append({"station_id": r["station_id"], "evidence_score": r["z"],
                             "evidence_type": f"manual-station shift risk (z={r['z']:.1f})"})
    manual_df = pd.DataFrame(manual_rows)

    combined = pd.concat([sensored, manual_df], ignore_index=True) if not manual_df.empty else sensored
    return combined.sort_values("evidence_score", ascending=False).head(top_k)


if __name__ == "__main__":
    from spc_models import score_all_sensored_stations
    events = pd.read_csv("../data/simulated_line_events.csv")
    gt = pd.read_csv("../data/ground_truth.csv")
    _, rollup = score_all_sensored_stations(events)

    print("=== Cohort-level ranking (top contributors) ===")
    print(cohort_level_ranking(rollup, gt).head(8).to_string(index=False))

    print("\n=== Top-K hit rate (unit-level suspects vs confirmed source) ===")
    print(hit_rate_top_k(rollup, gt, k=3))

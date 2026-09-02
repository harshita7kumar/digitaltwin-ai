"""
run_pipeline.py
==================
End-to-end demo entry point. Run this file to:
  1. Simulate the 40-station line (or load a cached run)
  2. Score every sensored station with the causal SPC/anomaly model
  3. Run manual-station inference (shift risk chart) for unsensed stations
  4. Forecast bottleneck risk for every station
  5. Trace root causes for every defective unit and validate against ground truth
  6. Print a plain-English validation report
  7. Export dashboard_data.json consumed by dashboard/index.html

Usage:
    cd src && python3 run_pipeline.py
"""

import json
import time
import numpy as np
import pandas as pd

from line_config import build_line
from simulate_line import simulate
from spc_models import score_all_sensored_stations
from inference_models import run_manual_station_inference, build_confirmed_attribution_stream
from bottleneck_forecast import forecast_station, first_alert_and_first_breach
from defect_traceback import cohort_level_ranking, hit_rate_top_k, unit_level_suspects
from validation import score_early_warning, threshold_sweep


def main():
    t0 = time.time()
    print("Simulating 40-station line, 3,000 units...")
    events, gt, line = simulate()
    line_by_id = {s.id: s for s in line}

    print("Scoring sensored stations (causal EWMA/SPC)...")
    long_scores, rollup = score_all_sensored_stations(events)

    print("Running manual-station inference (Station 13)...")
    manual_station_ids = [s.id for s in line if s.tier == "manual"]
    checkpoints = list(range(700, 3000, 100))
    manual_risk = run_manual_station_inference(gt, manual_station_ids, checkpoints)
    latest_manual_risk = (manual_risk.sort_values("as_of_unit")
                           .groupby(["station_id", "shift"]).tail(1))

    print("Forecasting bottleneck risk across all sensored stations...")
    bottleneck_summaries = []
    for s in line:
        if s.tier == "manual":
            continue
        fc = forecast_station(events, s.id, s.takt_time_s)
        alert_unit, breach_unit, lead = first_alert_and_first_breach(fc, s.takt_time_s)
        latest = fc.iloc[-1]
        bottleneck_summaries.append({
            "station_id": s.id, "station_name": s.name, "zone": s.zone, "tier": s.tier,
            "takt_time_s": s.takt_time_s,
            "current_cycle_time_s": float(latest["cycle_time"]),
            "trend_slope_s_per_unit": None if pd.isna(latest["trend_slope_s_per_unit"]) else float(latest["trend_slope_s_per_unit"]),
            "forecast_units_to_breach": None if pd.isna(latest["forecast_units_to_breach"]) else float(latest["forecast_units_to_breach"]),
            "currently_alerting": bool(latest["bottleneck_alert"]),
            "first_alert_unit": None if alert_unit is None else int(alert_unit),
            "first_sustained_breach_unit": None if breach_unit is None else int(breach_unit),
            "lead_time_units": None if lead is None else int(lead),
        })
    bottleneck_df = pd.DataFrame(bottleneck_summaries)

    print("Tracing root causes for defective units...")
    cohort_rank = cohort_level_ranking(rollup, gt)
    topk = hit_rate_top_k(rollup, gt, k=3)

    print("Validating early-warning defect prediction...")
    ew = score_early_warning(rollup, gt)
    sweep = threshold_sweep(rollup, gt)

    # ---------------------------------------------------------------
    # console report
    # ---------------------------------------------------------------
    print("\n" + "=" * 70)
    print("DIGITAL TWIN PROTOTYPE -- VALIDATION SUMMARY")
    print("=" * 70)
    tiers = pd.Series([s.tier for s in line]).value_counts()
    print(f"Line: {len(line)} stations | sensor mix: {tiers.to_dict()}")
    print(f"Units simulated: {gt.shape[0]} | ground-truth defect rate: {gt.defect.mean():.2%}")

    print("\n-- Bottleneck forecasting --")
    worst = bottleneck_df.sort_values("forecast_units_to_breach", na_position="last").head(3)
    print(worst[["station_id", "station_name", "tier", "forecast_units_to_breach", "currently_alerting"]].to_string(index=False))
    s12 = bottleneck_df[bottleneck_df.station_id == 12].iloc[0]
    print(f"Station 12 case study: predictive alert @ unit {s12.first_alert_unit}, "
          f"sustained breach @ unit {s12.first_sustained_breach_unit}, "
          f"lead time = {s12.lead_time_units} units (~{(s12.lead_time_units or 0)/250:.1f} shifts)")

    print("\n-- Manual-station inference (Station 13, no sensors) --")
    print(latest_manual_risk[["station_id", "shift", "n_to_date", "group_rate", "z", "elevated_risk"]].to_string(index=False))

    print("\n-- Root-cause traceback --")
    print(f"Top-1 accuracy: {topk['top1_accuracy']:.1%} | Top-3 accuracy: {topk['top3_accuracy']:.1%} "
          f"(n={topk['n_evaluated']} confirmed defects; note the ceiling here is <100% because "
          f"~30% of defects originate at the fully-manual Station 13, which has no sensor trail --"
          f" see combined_suspects() for how manual-station risk flags close part of that gap)")
    print(cohort_rank.head(5)[["station_id", "contribution_score"]].to_string(index=False))

    print("\n-- Early-warning defect prediction (visible before Final Inspection) --")
    print(f"At threshold={ew['threshold']}: precision={ew['precision']:.1%}, recall={ew['recall']:.1%}, "
          f"vs base rate {ew['base_rate_defect']:.2%} "
          f"(~{ew['precision']/ew['base_rate_defect']:.0f}x lift over random flagging)")

    print(f"\nPipeline completed in {time.time()-t0:.1f}s")

    # ---------------------------------------------------------------
    # export for dashboard
    # ---------------------------------------------------------------
    export = build_dashboard_export(line, events, gt, rollup, bottleneck_df, latest_manual_risk,
                                     cohort_rank, topk, ew, sweep)
    export = _sanitize_nans(json.loads(json.dumps(export, default=_json_default)))

    from pathlib import Path

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

    with open(DASHBOARD_DIR / "dashboard_data.json", "w") as f:
        json.dump(export, f, indent=2)

    print(f"\nExported {DASHBOARD_DIR / 'dashboard_data.json'}")


def _sanitize_nans(obj):
    """Recursively replaces float('nan') with None so json.dump produces
    strict, browser-parseable JSON (Python's json module otherwise emits a
    bare `NaN` token, which is invalid per the JSON spec and breaks
    JSON.parse in the dashboard)."""
    if isinstance(obj, dict):
        return {k: _sanitize_nans(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nans(v) for v in obj]
    if isinstance(obj, float) and np.isnan(obj):
        return None
    return obj


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if pd.isna(o):
        return None
    raise TypeError(f"not serializable: {type(o)}")


def build_dashboard_export(line, events, gt, rollup, bottleneck_df, latest_manual_risk,
                            cohort_rank, topk, ew, sweep):
    line_status = []
    for s in line:
        row = bottleneck_df[bottleneck_df.station_id == s.id]
        alerting = bool(row.iloc[0]["currently_alerting"]) if not row.empty else False
        manual_row = latest_manual_risk[latest_manual_risk.station_id == s.id]
        manual_alert = bool(manual_row["elevated_risk"].any()) if not manual_row.empty else False
        status = "critical" if (alerting or manual_alert) else "normal"
        line_status.append({
            "station_id": s.id, "name": s.name, "zone": s.zone, "tier": s.tier,
            "status": status,
        })

    recent = events[events.unit_id > events.unit_id.max() - 300]
    recent_rollup = rollup[rollup.unit_id > rollup.unit_id.max() - 300]
    active_alerts = []
    top_bottleneck = bottleneck_df.dropna(subset=["forecast_units_to_breach"]).sort_values("forecast_units_to_breach")
    if not top_bottleneck.empty:
        r = top_bottleneck.iloc[0]
        if r["currently_alerting"]:
            fub = r.forecast_units_to_breach
            if pd.notna(fub) and fub > 0:
                msg = (f"{r.station_name} (Station {int(r.station_id)}) trending toward takt-time breach "
                       f"in ~{int(fub)} units at current pace")
            else:
                msg = (f"{r.station_name} (Station {int(r.station_id)}) is currently trending at or above "
                       f"takt time -- schedule maintenance window")
            active_alerts.append({
                "type": "bottleneck", "station_id": int(r.station_id), "station_name": r.station_name,
                "message": msg, "severity": "high",
            })
    for _, r in latest_manual_risk[latest_manual_risk.elevated_risk].iterrows():
        active_alerts.append({
            "type": "manual_station_risk", "station_id": int(r.station_id),
            "message": f"Station {int(r.station_id)} (manual checklist): {r['shift']} shift showing an elevated "
                       f"confirmed-defect attribution rate (z={r.z:.1f}) -- recommend a spot audit",
            "severity": "medium",
        })

    weekly_trend = []
    events_sorted = gt.sort_values("unit_id")
    bucket = 250
    for start in range(0, int(events_sorted.unit_id.max()), bucket):
        chunk = events_sorted[(events_sorted.unit_id > start) & (events_sorted.unit_id <= start + bucket)]
        if chunk.empty:
            continue
        weekly_trend.append({
            "shift_bucket": start // bucket + 1,
            "units": int(len(chunk)),
            "defect_rate": float(chunk.defect.mean()),
        })

    oee_like = []
    for s in line:
        if s.tier == "manual":
            continue
        sub = events[events.station_id == s.id]
        if sub.empty or sub["cycle_time"].isna().all():
            continue
        avg_ct = sub["cycle_time"].mean()
        oee_like.append({"station_id": s.id, "name": s.name, "utilization": round(min(1.0, avg_ct / s.takt_time_s), 3)})

    n_units = int(gt.shape[0])
    baseline_defect_rate_no_twin = float(gt.defect.mean())  # what currently escapes to/through final inspection
    # illustrative business-case arithmetic; all inputs are stated assumptions, not claims of fact
    # Deliberately conservative: a single pilot line, a modest blended
    # per-defect cost (not a headline recall-scale figure), and only the
    # HIGH-PRECISION operating point from the threshold sweep (~85%+
    # precision, ~32% recall) -- i.e. we count savings only from the alerts
    # confident enough to act on without flooding the floor with noise.
    assumptions = {
        "annual_units": 125000,                         # ~2 shifts/day, ~250 units/shift, ~250 production days
        "cost_per_escaped_defect_usd": 1200,             # blended rework/comeback/warranty cost, not recall-scale
        "cost_per_hour_unplanned_downtime_usd": 15000,   # single-line unplanned stoppage, industry-typical range
        "unplanned_stoppage_hours_avoided_per_year": 16, # ~2 wear-driven failures/yr converted from unplanned to scheduled
        "detection_recall_at_high_precision_threshold": 0.32,  # matches the ~85%+ precision operating point
        "prototype_dev_cost_usd": 180000,                # one-time: pilot data engineering + model build
        "per_line_rollout_cost_usd": 240000,             # one-time per additional line: integration + retrofit sensors
        "annual_platform_cost_per_line_usd": 60000,      # ongoing: hosting, monitoring, model upkeep
    }
    defects_avoided_per_year = assumptions["annual_units"] * baseline_defect_rate_no_twin * assumptions["detection_recall_at_high_precision_threshold"]
    annual_defect_savings = defects_avoided_per_year * assumptions["cost_per_escaped_defect_usd"]
    annual_downtime_savings = assumptions["unplanned_stoppage_hours_avoided_per_year"] * assumptions["cost_per_hour_unplanned_downtime_usd"]
    year1_cost = assumptions["prototype_dev_cost_usd"] + assumptions["per_line_rollout_cost_usd"] + assumptions["annual_platform_cost_per_line_usd"]
    year1_net = annual_defect_savings + annual_downtime_savings - year1_cost
    payback_months = year1_cost / max((annual_defect_savings + annual_downtime_savings) / 12, 1)

    business_case = {
        "assumptions": assumptions,
        "simulated_defect_rate": baseline_defect_rate_no_twin,
        "estimated_defects_avoided_per_year": round(defects_avoided_per_year),
        "estimated_annual_defect_cost_savings_usd": round(annual_defect_savings),
        "estimated_annual_downtime_savings_usd": round(annual_downtime_savings),
        "year1_total_cost_usd": year1_cost,
        "year1_net_usd": round(year1_net),
        "estimated_payback_months": round(payback_months, 1),
    }

    return {
        "meta": {"n_stations": len(line), "n_units_simulated": n_units,
                 "sensor_mix": pd.Series([s.tier for s in line]).value_counts().to_dict()},
        "floor_view": {
            "line_status": line_status,
            "active_alerts": active_alerts,
            "shift_defect_rate_last_300": float(recent.merge(gt[["unit_id", "defect"]], on="unit_id").defect.mean())
                if not recent.empty else None,
        },
        "plant_manager_view": {
            "weekly_trend": weekly_trend,
            "station_utilization": sorted(oee_like, key=lambda r: -r["utilization"])[:12],
            "top_root_cause_contributors": cohort_rank.head(6).to_dict(orient="records"),
            "root_cause_accuracy": topk,
            "bottleneck_watchlist": bottleneck_df.sort_values("forecast_units_to_breach", na_position="last")
                .head(6)[["station_id", "station_name", "zone", "forecast_units_to_breach", "currently_alerting"]]
                .to_dict(orient="records"),
        },
        "leadership_view": {
            "business_case": business_case,
            "validation_summary": {
                "early_warning_precision_at_default_threshold": ew["precision"],
                "early_warning_recall_at_default_threshold": ew["recall"],
                "threshold_sweep": sweep.to_dict(orient="records"),
                "root_cause_top3_accuracy": topk["top3_accuracy"],
                "bottleneck_lead_time_units_station12_case_study": int(
                    bottleneck_df[bottleneck_df.station_id == 12].iloc[0]["lead_time_units"] or 0),
            },
        },
    }


if __name__ == "__main__":
    main()

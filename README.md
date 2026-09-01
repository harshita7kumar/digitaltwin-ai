# DigitalTwin.ai — Predictive Digital Twin for Mixed-Instrumentation Assembly Lines

A reference solution design and working prototype for a plant-floor digital twin built for the assembly
line that actually exists — a patchwork of legacy PLCs, modern robotic cells, and manual checklist
stations — rather than an idealized, uniformly-instrumented one.

**Round 2 submission.** Full write-up: [`docs/DigitalTwin_Business_Proposal.docx`](docs/DigitalTwin_Business_Proposal.docx)
(also available as [PDF](docs/DigitalTwin_Business_Proposal.pdf)).

▶️ **Demo video:** `<insert link here after recording — see docs/demo_video_script.md for the shot list>`

---

## What this is

A simulated 40-station mixed-model assembly line (body construction → paint → final assembly) with a
realistic, uneven sensor mix — 27 rich stations, 8 basic-signal stations, 5 fully manual checklist
stations — and three injected, multi-causal fault modes standing in for real equipment wear, an
intermittent tool/part-quality interaction, and shift-based operator variation.

On top of that simulated line, four modeling components run exactly as they would against a live OT
feed:

| Component | What it does | Validated result on the reference run |
|---|---|---|
| `src/spc_models.py` | Causal EWMA/SPC anomaly scoring for every sensored station | Correctly surfaces both injected sensored faults as top anomaly sources |
| `src/bottleneck_forecast.py` | Statistically-significant trend forecasting of takt-time breaches | **517 units (~2.1 shifts) of lead time** between predictive alert and actual sustained breach |
| `src/inference_models.py` | Infers risk at the one fully manual (zero-sensor) station using only delayed, downstream confirmed attributions | Correctly and repeatedly flags night shift as elevated-risk, from ~unit 900 onward |
| `src/defect_traceback.py` | Ranks likely root-cause stations for defects that surface late, at final inspection | **69.4% top-3 accuracy** against confirmed source (n=62); gap is fully attributable to the one unsensed station |
| `src/validation.py` | Scores every claim above against ground truth — precision/recall, threshold sweep, lead time | At a conservative threshold: **~95% precision / 32% recall**; at a sensitive threshold: **~3.5% precision / 77% recall** — full tradeoff curve included |

Every number above is reproducible by running the pipeline yourself (see below) — nothing is hand-picked.

A working three-persona dashboard (`dashboard/index.html`) renders the same underlying twin state as
three different views: a real-time floor-supervisor view, a weekly plant-manager trend view, and a
leadership business-case view.

---

## Quick start

```bash
git clone <this-repo-url>
cd digitaltwin-ai
pip install -r requirements.txt

cd src
python3 run_pipeline.py
```

This runs the full simulation and every modeling component end-to-end (~15 seconds), prints a plain-English
validation report to the console, and writes `dashboard/dashboard_data.json`.

Then open `dashboard/index.html` directly in any browser (no server needed — the data is embedded) to see
the three stakeholder views populated with that run's actual output.

> **Regenerating the dashboard after a fresh pipeline run:** `dashboard/index.html` is built by injecting
> `dashboard/dashboard_data.json` into `dashboard/index_template.html`. After running the pipeline, rebuild
> it with:
> ```bash
> python3 -c "
> import json
> data = json.load(open('../dashboard/dashboard_data.json'))
> tmpl = open('../dashboard/index_template.html').read()
> open('../dashboard/index.html','w').write(tmpl.replace('__DASHBOARD_DATA__', json.dumps(data)))
> "
> ```
> (run from the `src/` directory, or adjust the relative paths).

Individual modules can also be run standalone to inspect their output in isolation, e.g.:

```bash
python3 simulate_line.py       # regenerate the synthetic event log + ground truth
python3 spc_models.py          # anomaly scores for sensored stations
python3 inference_models.py    # manual-station risk inference
python3 bottleneck_forecast.py # Station 12 bottleneck lead-time case study
python3 defect_traceback.py    # root-cause ranking + hit-rate validation
python3 validation.py          # full validation report (precision/recall sweep, etc.)
```

---

## Repository structure

```
digitaltwin-ai/
├── README.md                          this file
├── requirements.txt                   numpy, pandas — that's it
├── LICENSE
├── src/
│   ├── line_config.py                 40-station topology + sensor tier per station
│   ├── simulate_line.py               synthetic event-log generator + 3 injected fault modes
│   ├── spc_models.py                  causal EWMA anomaly scoring (rich/basic stations)
│   ├── inference_models.py            manual-station shift-risk inference (no sensors)
│   ├── bottleneck_forecast.py         trend-based takt-time breach forecasting
│   ├── defect_traceback.py            unit-level + cohort-level root-cause ranking
│   ├── validation.py                  precision/recall scoring, threshold sweep
│   └── run_pipeline.py                orchestrates everything end-to-end
├── data/
│   ├── simulated_line_events.csv      generated event log (regenerate via simulate_line.py)
│   └── ground_truth.csv               hidden ground truth used only for validation
├── dashboard/
│   ├── index_template.html            dashboard shell (persona switcher, charts, station strip)
│   ├── index.html                     built dashboard with the reference run's data embedded
│   └── dashboard_data.json            data export consumed by index.html
└── docs/
    ├── DigitalTwin_Business_Proposal.docx   full business proposal (problem framing → risks)
    ├── DigitalTwin_Business_Proposal.pdf    same, as PDF
    ├── architecture_diagram.png             reference architecture figure (Figure 1 in the proposal)
    ├── gen_diagram.py                       regenerates the architecture diagram
    ├── gen_proposal.js                      regenerates the .docx (docx-js)
    └── demo_video_script.md                 shot-by-shot script for the demo video
```

---

## Design notes worth knowing before you read the code

- **Everything time-sensitive is causal.** Anomaly scores, trend forecasts, and manual-station risk
  inference only ever use data from *before* the point being scored — there is no lookahead anywhere in
  the modeling layer. This matters because the whole point is to validate leading-indicator claims, not
  lagging descriptions.
- **The manual station never gets a fake sensor reading.** `inference_models.py` infers risk purely from
  delayed, downstream confirmed attributions segmented by shift — and explicitly models the real-world
  confirmation lag (a physical rework/teardown process, not instant ground truth) so it never uses
  information it wouldn't actually have yet in production.
- **Root-cause accuracy is reported honestly, including its ceiling.** ~30% of defects in the simulation
  originate at the one fully-manual station, which by construction has no sensor trail for the traceback
  module to use — so a 69.4% top-3 accuracy is very close to the maximum achievable by sensor-based
  evidence alone. `defect_traceback.combined_suspects()` shows how manual-station risk flags close part
  of that gap.
- **All business-case figures are labeled assumptions, not facts** — see the assumptions table rendered
  in both the leadership dashboard view and the business proposal.

Full rationale for every design decision (why EWMA over a heavier ML model, why linear trend forecasting,
why cohort-level + unit-level root-cause ranking, integration approach, phased rollout, risks) is in the
[business proposal](docs/DigitalTwin_Business_Proposal.docx).

---

## Extending this

- Swap `src/line_config.py` for a real line's topology — the modeling modules are written against the
  `Station` dataclass and don't assume the specific 40-station reference layout.
- Replace `src/simulate_line.py`'s output with a real OT feed shaped the same way
  (`unit_id, station_id, cycle_time, vibration, torque, temperature, checklist_pass, shift`) and the rest
  of the pipeline runs unmodified.
- The dashboard is a single self-contained HTML file (Chart.js via CDN, no build step) — edit
  `dashboard/index_template.html` and re-run the injection script above.

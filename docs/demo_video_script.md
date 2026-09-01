# Demo Video Script

Target length: 4–5 minutes. Screen-record your terminal and browser; no editing software required
beyond basic cuts. Suggested tool: QuickTime (Mac), OBS Studio (Windows/Linux/Mac, free), or the
built-in screen recorder on either OS.

Record at 1080p+, keep terminal font large (18–20pt) so it's readable at YouTube 720p.

---

## Shot 1 — Cold open (10–15s)

**Screen:** Title slide or the README.md rendered on GitHub.
**Say:** "Most digital twin pitches assume a perfectly instrumented factory. Real lines aren't — they're
a mix of legacy PLCs, modern robotic cells, and stations that are still just a person with a checklist.
This is a digital twin built for that line."

---

## Shot 2 — The problem, fast (20–30s)

**Screen:** Scroll through Section 1 of the business proposal (Problem Framing) — just the bullet list of
real-world complexities, don't read it verbatim.
**Say:** "Three things make this hard: sensor coverage is uneven, defects introduced early often don't
surface until dozens of stations later, and you can't touch live PLCs outside a scheduled maintenance
window. The prototype is built around all three constraints, not around an idealized dataset."

---

## Shot 3 — Run the pipeline live (60–75s) — the centerpiece

**Screen:** Terminal, in the `src/` directory.
**Action:**
```bash
python3 run_pipeline.py
```
Let it run (~15 seconds) — don't cut this, watching real computation happen is the point.

**Say, while it runs:** "This simulates a 40-station line — 3,000 units, with three injected faults: a
wearing bearing, an intermittent torque fault tied to a bad supplier batch, and a shift-based inspection
gap at a station with zero sensors. Then it runs four models against that data exactly like it would
against a live feed, and validates every prediction against the ground truth."

**When the console report appears, narrate the three headline numbers as they scroll past (pause/zoom if
recording software allows):**
1. "517 units — about two shifts — of lead time before a bottleneck actually happens."
2. "Root-cause ranking gets the true source station in its top 3 suspects 69% of the time — and I'll show
   you exactly why it can't do better than that."
3. "And it correctly flags night-shift risk at a station that has *no sensor at all*, using only delayed,
   confirmed downstream outcomes."

---

## Shot 4 — Open the dashboard (60–90s)

**Screen:** Open `dashboard/index.html` in a browser.

**Floor Supervisor view (default):**
- Point at the station strip: "Every one of the 40 stations, color-coded. The striped ones are manual —
  no sensor — and the twin still has a view into them."
- Hover a station to show the tooltip.
- Point at the active alerts list: "This is the bottleneck alert and the manual-station risk flag, in
  plain language a supervisor can act on immediately."

**Switch to Plant Manager view:**
- Point at the defect-rate trend chart and the bottleneck watchlist.
- Point at the root-cause contributor table: "Station 7 — the torque station — is the clear top
  contributor, exactly matching the injected fault."

**Switch to Leadership view:**
- Point at the four stat cards (year-1 net, payback, defects avoided, downtime savings).
- Point at the precision/recall tradeoff chart: "This is what lets leadership see the actual tradeoff
  being made — not just a single flattering accuracy number."

**Say:** "All three of these are the same underlying twin state — one model, three projections."

---

## Shot 5 — Show the honesty, not just the wins (20–30s)

**Screen:** Terminal output or the business proposal, Section 4.2 callout box.
**Say:** "The root-cause accuracy is capped below 100% on purpose in this write-up — about 30% of the
simulated defects come from the one station with zero sensors, and the report says so directly instead
of smoothing it over. That honesty is the same standard the business case and the rollout plan are held
to."

---

## Shot 6 — Close (15–20s)

**Screen:** README.md repository structure section, or the roadmap table from the proposal.
**Say:** "Full solution design, phased rollout plan, and risk mitigations are in the business proposal —
linked in the description. All the code you just watched run is in this repository. Thanks for watching."

---

## Checklist before you hit record

- [ ] `pip install -r requirements.txt` already run, so Shot 3 doesn't stall on installs
- [ ] `dashboard/index.html` already generated once (so you know it works) — you can still show the
      live pipeline run in Shot 3 even if you don't regenerate the dashboard on camera
- [ ] Terminal font size increased for readability
- [ ] Browser zoom at 100% (dashboard is responsive but looks best at 100%)
- [ ] Close notifications / anything else that could pop up mid-recording

## After recording

1. Upload to YouTube (unlisted is fine) or Loom.
2. Add the link to the top of `README.md` where it says `<insert link here after recording>`.
3. Add the link to the cover page of the business proposal if you want it there too (optional).

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.lines import Line2D

fig, ax = plt.subplots(figsize=(10.2, 6.6), dpi=200)
ax.set_xlim(0, 10.2)
ax.set_ylim(0, 6.6)
ax.axis("off")

NAVY = "#1b2a41"
STEEL = "#3a5a78"
AMBER = "#c9861a"
GREEN = "#2e7d5b"
LIGHT = "#eef2f6"
LINEC = "#8b98a8"

def box(x, y, w, h, text, fc=LIGHT, ec=NAVY, tc=NAVY, fs=9.3, weight="bold"):
    b = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                        linewidth=1.3, edgecolor=ec, facecolor=fc, zorder=2)
    ax.add_patch(b)
    ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=fs,
             color=tc, weight=weight, zorder=3, linespacing=1.35)
    return (x, y, w, h)

def arrow(b1, b2, style="->", color=LINEC, lw=1.6, connectionstyle="arc3,rad=0.0"):
    x1, y1, w1, h1 = b1
    x2, y2, w2, h2 = b2
    p1 = (x1 + w1/2, y1)
    p2 = (x2 + w2/2, y2 + h2)
    if y1 + h1 <= y2:
        p1 = (x1 + w1/2, y1 + h1); p2 = (x2 + w2/2, y2)
    a = FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=14, color=color, lw=lw,
                         connectionstyle=connectionstyle, zorder=1)
    ax.add_patch(a)

# ---- Row 1: sources ----
src1 = box(0.25, 5.55, 3.0, 0.75, "Legacy & modern PLCs / OT\n(rich + basic sensor stations)", fc="#f4ede1", ec=AMBER)
src2 = box(3.6, 5.55, 3.0, 0.75, "Operator checklists\n(manual stations, no sensor)", fc="#f4ede1", ec=AMBER)
src3 = box(6.95, 5.55, 3.0, 0.75, "Rework / failure-analysis bay\n(delayed confirmed root cause)", fc="#f4ede1", ec=AMBER)

# ---- Row 2: ingestion ----
ing = box(1.6, 4.35, 7.0, 0.7, "DATA INGESTION  —  read-only OPC-UA / MQTT taps · digitized checklists · unit genealogy log",
          fc="#e7edf3", ec=STEEL, fs=9)

arrow(src1, ing); arrow(src2, ing); arrow(src3, ing)

# ---- Row 3: modeling layer (4 boxes) ----
m1 = box(0.25, 3.05, 2.35, 0.95, "SPC / anomaly\nscoring\n(rich & basic\nstations)", fc=LIGHT, ec=NAVY, fs=8.6)
m2 = box(2.75, 3.05, 2.35, 0.95, "Manual-station\ninference\n(shift risk chart,\nno sensor)", fc=LIGHT, ec=NAVY, fs=8.6)
m3 = box(5.25, 3.05, 2.35, 0.95, "Bottleneck\nforecast\n(trend vs.\ntakt time)", fc=LIGHT, ec=NAVY, fs=8.6)
m4 = box(7.75, 3.05, 2.2, 0.95, "Defect\ntraceback\n(root-cause\nranking)", fc=LIGHT, ec=NAVY, fs=8.6)

for m in (m1, m2, m3, m4):
    arrow(ing, m)

# ---- Row 4: validation loop ----
val = box(1.6, 1.95, 7.0, 0.7, "VALIDATION & CALIBRATION LOOP  —  precision/recall backtesting · threshold tuning · drift monitoring",
           fc="#eaf2ee", ec=GREEN, fs=9)
for m in (m1, m2, m3, m4):
    arrow(m, val)

# feedback arrow back up (dashed)
fb = FancyArrowPatch((1.6, 2.3), (0.35, 3.05), arrowstyle="->", mutation_scale=13,
                      color=GREEN, lw=1.4, linestyle=(0, (4, 3)),
                      connectionstyle="arc3,rad=0.3")
ax.add_patch(fb)
ax.text(0.05, 2.65, "recalibrates\nthresholds", fontsize=7, color=GREEN, ha="left", style="italic")

# ---- Row 5: presentation layer (3 personas) ----
p1 = box(0.25, 0.6, 3.0, 0.85, "FLOOR SUPERVISOR\nreal-time station status,\nactive alerts", fc="#fdeeee", ec="#a33", fs=8.8)
p2 = box(3.6, 0.6, 3.0, 0.85, "PLANT MANAGER\nweekly trends, root-cause\nranking, bottleneck watch", fc="#eef2fb", ec="#345", fs=8.8)
p3 = box(6.95, 0.6, 3.0, 0.85, "LEADERSHIP\nbusiness case, validated\naccuracy, rollout status", fc="#eefaf1", ec=GREEN, fs=8.8)

for p in (p1, p2, p3):
    arrow(val, p)

ax.text(5.1, 6.45, "Reference Architecture — One Twin, Uneven Instrumentation, Three Views",
         ha="center", va="center", fontsize=12.5, weight="bold", color=NAVY)

plt.tight_layout()
plt.savefig("/home/claude/digitaltwin-ai/docs/architecture_diagram.png", dpi=200, bbox_inches="tight", facecolor="white")
print("saved")

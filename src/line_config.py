"""
line_config.py
==================
Defines the topology of a simulated 40-station mixed-model assembly line and
the sensor tier of each station. This encodes the "uneven instrumentation"
assumption at the heart of the brief: most stations are richly instrumented,
a meaningful minority run on basic PLC counters, and a small number are
manual-checklist only.

This is a *reference* topology, not a fixed dataset -- swap it out per plant.
"""

from dataclasses import dataclass, field
from typing import Literal

SensorTier = Literal["rich", "basic", "manual"]


@dataclass
class Station:
    id: int
    name: str
    zone: str                  # "Body Construction" | "Paint" | "Final Assembly"
    tier: SensorTier
    takt_time_s: float         # design cycle time (seconds) for this station
    channels: list = field(default_factory=list)  # numeric channels this station reports


def build_line() -> list[Station]:
    stations: list[Station] = []

    # --- Body Construction (1-15): mostly rich (robotic weld/joining cells) ---
    body_names = [
        "Underbody Framing", "Side Panel Load", "Robotic Weld Cell A",
        "Robotic Weld Cell B", "Roof Bow Fit", "Door Hang", "Bolt Fastening Torque",
        "Geometry Check", "Robotic Weld Cell C", "Sealer Application",
        "Body Squareness Gauge", "Weld Arm Bearing Station", "Panel Fit Inspection",
        "Hem Flange Press", "Body-in-White Buyoff",
    ]
    body_tiers = ["rich"] * 11 + ["manual", "rich", "basic", "rich"]  # station 12 gets a manual QC alongside... simplify: assign below

    body_tiers = [
        "rich", "rich", "rich", "rich", "rich", "rich", "rich",  # 1-7
        "manual",                                                # 8 handled specially below (torque station is rich; keep rich)
        "rich", "rich", "basic", "rich", "manual", "rich", "manual",  # 9-15
    ]
    # Correction: station 7 is the torque fastening station and MUST be rich
    # (torque is the physical variable of interest). Station 8 is a geometry
    # laser-check kept rich; we instead make station 13 (panel fit) manual
    # and station 8 stays rich. Final assignment below is explicit and
    # overrides the placeholders above for clarity and to avoid ambiguity.
    body_tiers = [
        "rich", "rich", "rich", "rich", "rich", "rich", "rich",   # 1-7 rich
        "rich",                                                    # 8 Geometry Check - rich (laser scanner)
        "rich", "rich", "basic", "rich", "manual", "basic", "manual",  # 9-15
    ]

    for i, (name, tier) in enumerate(zip(body_names, body_tiers), start=1):
        channels = []
        if tier == "rich":
            channels = ["cycle_time", "vibration", "torque", "temperature"]
        elif tier == "basic":
            channels = ["cycle_time"]
        else:
            channels = []  # manual: checklist only
        stations.append(Station(i, name, "Body Construction", tier, takt_time_s=62.0, channels=channels))

    # --- Paint (16-25): legacy-heavy zone, more basic/manual coverage ---
    paint_names = [
        "Pretreatment Dip", "E-Coat Bath", "Sealer Booth", "Primer Booth",
        "Basecoat Robot", "Clearcoat Robot", "Flash-Off Tunnel",
        "Cure Oven Conveyor", "Paint Inspection Booth", "Buff & Polish",
    ]
    paint_tiers = ["basic", "rich", "manual", "rich", "rich", "rich", "basic", "basic", "manual", "basic"]
    for i, (name, tier) in enumerate(zip(paint_names, paint_tiers), start=16):
        if tier == "rich":
            channels = ["cycle_time", "vibration", "temperature"]
        elif tier == "basic":
            channels = ["cycle_time", "temperature"] if "Oven" in name or "Tunnel" in name or "Dip" in name else ["cycle_time"]
        else:
            channels = []
        stations.append(Station(i, name, "Paint", tier, takt_time_s=68.0, channels=channels))

    # --- Final Assembly (26-40): mixed, ends in inspection ---
    fa_names = [
        "Cockpit Marriage", "Powertrain Marriage", "Wheel & Tire Mount",
        "Interior Trim 1", "Interior Trim Fit Check", "Glass Install",
        "Seat Install", "Fluid Fill", "Wheel Alignment", "Headlamp Aim",
        "Electrical Function Test", "Door/Panel Gap Scan", "Water Leak Test",
        "Road Simulation Test", "Final Inspection & Buyoff",
    ]
    fa_tiers = [
        "rich", "rich", "rich", "basic", "manual", "rich", "basic",
        "rich", "rich", "rich", "rich", "rich", "rich", "rich", "rich",
    ]
    for i, (name, tier) in enumerate(zip(fa_names, fa_tiers), start=26):
        if tier == "rich":
            channels = ["cycle_time", "vibration", "torque", "temperature"]
        elif tier == "basic":
            channels = ["cycle_time"]
        else:
            channels = []
        stations.append(Station(i, name, "Final Assembly", tier, takt_time_s=58.0, channels=channels))

    return stations


TIER_COVERAGE_NOTE = (
    "Reference line: 40 stations. Sensor mix ~= 60% rich (continuous multi-channel), "
    "25% basic (single PLC signal, usually cycle time), 15% manual checklist-only -- "
    "matching the brief's 'majority instrumented, meaningful minority manual' assumption."
)

if __name__ == "__main__":
    line = build_line()
    from collections import Counter
    print(TIER_COVERAGE_NOTE)
    print(Counter(s.tier for s in line))

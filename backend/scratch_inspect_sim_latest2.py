import os
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

sim_dir = "backend/uploads/simulations/sim_083f8cc0d041"
print("=== 1. Simulation Config ===")
with open(os.path.join(sim_dir, "simulation_config.json"), "r", encoding="utf-8") as f:
    cfg = json.load(f)
    print("Scheduled events:")
    for ev in cfg.get("scheduled_events", []):
        print(f"  Round {ev.get('round')}: Agent {ev.get('agent_id')} ({ev.get('agent_name')}) -> {ev.get('action')}: {ev.get('content')[:60]}")

print("\n=== 2. Check scheduled event triggers in simulation.log ===")
with open(os.path.join(sim_dir, "simulation.log"), "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        if any(kw in line for kw in ["劇本排程觸發", "人設動態", "方案A", "Self-Action", "successfully loaded"]):
            print(" ", line.strip()[:140])

print("\n=== 3. Check System Messages logged in simulation.log ===")
with open(os.path.join(sim_dir, "simulation.log"), "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        if ": [{'role': 'system'" in line:
            print(" ", line[:400])

import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

log_path = "backend/uploads/simulations/sim_d5a6d1e11a10/simulation.log"

print("=== Checking System Messages in sim_d5a6d1e11a10 ===")
with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        if "Agent 0: [{'role': 'system'" in line:
            print("\n--- AGENT 0 SYSTEM MESSAGE ---")
            print(line[:1200])
        if "Agent 12: [{'role': 'system'" in line:
            print("\n--- AGENT 12 SYSTEM MESSAGE ---")
            print(line[:1200])

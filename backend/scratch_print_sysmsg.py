import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('backend/uploads/simulations/sim_164487fecd5e/simulation.log', 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if "Agent 9: [{'role': 'system'" in line:
            print("--- Found Agent 9 System Message ---")
            print(line[:2000])
            break

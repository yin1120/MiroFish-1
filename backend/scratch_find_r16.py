import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search simulation.log for Agent 9 around round 16
# R16 in reddit is around timestamp 2026-09-23 14:46:40
with open('backend/uploads/simulations/sim_164487fecd5e/simulation.log', 'r', encoding='utf-8', errors='ignore') as f:
    for idx, line in enumerate(f):
        if 'Agent 9' in line and any(w in line for w in ['R16', 'Round 16', 'round 16', 'post_id": 18', 'The United States Government remains steadfast']):
            print(f"Line {idx}: {line.strip()[:140]}")

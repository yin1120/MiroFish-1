import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('backend/uploads/simulations/sim_164487fecd5e/simulation.log', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'Agent 1 receive response' in line:
        print(f"--- Agent 1 at line {i} ---")
        for j in range(i, min(len(lines), i + 25)):
            print(lines[j].strip())

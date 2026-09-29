import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('backend/uploads/simulations/sim_164487fecd5e/simulation.log', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'Agent 9 observing environment' in line:
        print(f"--- Log at line {i} ---")
        for j in range(i, min(len(lines), i + 25)):
            if 'Agent 9' in lines[j] or 'User:' in lines[j] or 'system_message' in lines[j] or 'Agent 9 receive response' in lines[j]:
                print(lines[j].strip()[:140])

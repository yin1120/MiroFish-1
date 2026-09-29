import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('backend/uploads/simulations/sim_164487fecd5e/simulation.log', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '排程' in line or '方案A' in line or '人設動態覆寫' in line or '攻打中國政府' in line or '攻打烏克蘭政府' in line:
        start = max(0, i - 2)
        end = min(len(lines), i + 6)
        print(f"--- Around line {i} ---")
        for j in range(start, end):
            print(f"{j}: {lines[j].strip()[:140]}")

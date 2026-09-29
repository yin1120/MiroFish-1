import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search simulation.log for "[方案A記憶注入成功]" or "[人設動態覆寫成功]"
with open('backend/uploads/simulations/sim_164487fecd5e/simulation.log', 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if '方案A' in line or '人設動態覆寫' in line or '劇本排程觸發' in line:
            print(line.strip())

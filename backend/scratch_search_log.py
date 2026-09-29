import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('backend/uploads/simulations/sim_164487fecd5e/simulation.log', 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if any(w in line for w in ['方案A', '人設動態覆寫', '排程觸發', 'mutation_notice', '重大歷史立場轉折', 'System Message']):
            print(line.strip())

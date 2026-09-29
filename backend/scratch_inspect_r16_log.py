import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('backend/uploads/simulations/sim_164487fecd5e/simulation.log', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i in range(1665, 1815):
    line = lines[i].strip()
    if any(k in line for k in ['Agent 9', 'observing', 'content', 'Self-Action', '歷史公開發布', '行為連貫性', '重大歷史立場轉折', 'create_post', 'args']):
        print(f"{i}: {line[:140]}")

import os
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

sim_dir = "backend/uploads/simulations/sim_083f8cc0d041"

print("=== 1. Checking Agent 0 and Agent 2 message list in sim_083f8cc0d041 ===")
with open(os.path.join(sim_dir, "simulation.log"), "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        if "Agent 0: [{'role': 'system'" in line:
            print("\n--- AGENT 0 FULL LOGGED PROMPT ---")
            # Parse or inspect the roles
            import re
            roles = re.findall(r"'role': '(\w+)'", line)
            print("Roles sequence in prompt:", roles)
            # Check if there are multiple system messages
            system_count = roles.count('system')
            print("Number of system messages in prompt:", system_count)
            print("Snippet of prompt:", line[:800])
            break

print("\n=== 2. Checking Self-Action Memory loading in social.agent log ===")
import glob
log_files = glob.glob(os.path.join(sim_dir, "log", "social.agent*.log"))
print("Log files found:", log_files)
found_self = False
for lf in log_files:
    with open(lf, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "Self-Action Memory" in line or "successfully loaded" in line or "你本人過去在社群公開發布" in line:
                print("  FOUND:", line.strip()[:160])
                found_self = True
if not found_self:
    print("  Self-Action log not found in social.agent log, checking simulation.log...")
    with open(os.path.join(sim_dir, "simulation.log"), "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "Self-Action Memory" in line or "successfully loaded" in line or "你本人過去在社群公開發布" in line:
                print("  FOUND in simulation.log:", line.strip()[:160])
                found_self = True

if not found_self:
    print("  Neither found. Checking why db_path was handled.")

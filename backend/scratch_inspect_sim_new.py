import json
import sqlite3
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

sim_dir = "backend/uploads/simulations/sim_d5a6d1e11a10"

print("=== 1. Simulation Config ===")
with open(os.path.join(sim_dir, "simulation_config.json"), "r", encoding="utf-8") as f:
    cfg = json.load(f)
    print("Num rounds:", cfg.get("max_rounds"))
    print("Scheduled events:")
    for ev in cfg.get("scheduled_events", []):
        print(f"  Round {ev.get('round')}: Agent {ev.get('agent_id')} ({ev.get('agent_name')}) -> {ev.get('action')}: {ev.get('content')[:60]}")

print("\n=== 2. Twitter Simulation Actions ===")
tw_db = os.path.join(sim_dir, "twitter_simulation.db")
if os.path.exists(tw_db):
    conn = sqlite3.connect(tw_db)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(trace)")
    cols = [c[1] for c in cursor.fetchall()]
    print("Trace cols:", cols)
    cursor.execute("SELECT * FROM trace LIMIT 5")
    print("Trace sample:", cursor.fetchall())
    
    # Also check post table
    cursor.execute("PRAGMA table_info(post)")
    print("Post cols:", [c[1] for c in cursor.fetchall()])
    cursor.execute("SELECT post_id, user_id, content FROM post")
    for pid, uid, cnt in cursor.fetchall():
        print(f"  Post {pid} | User {uid}: {str(cnt)[:60]}")
    conn.close()

print("\n=== 3. Check Scheduled Events in simulation.log ===")
log_path = os.path.join(sim_dir, "simulation.log")
if os.path.exists(log_path):
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "劇本排程觸發" in line or "人設動態" in line or "方案A" in line or "system_message" in line or "【官方最高" in line:
                print("  LOG:", line.strip()[:150])

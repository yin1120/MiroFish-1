import os
import sys
import json
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')

sim_dir = 'backend/uploads/simulations/sim_164487fecd5e'

for platform in ['reddit', 'twitter']:
    db_file = os.path.join(sim_dir, f'{platform}_simulation.db')
    print(f"\n================ {platform} USERS ================")
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    users = c.execute("SELECT user_id, user_name, bio FROM user ORDER BY user_id").fetchall()
    for u in users:
        print(f"ID={u[0]}: {u[1]} | bio: {u[2]}")
    conn.close()

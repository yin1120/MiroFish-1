import sqlite3
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

for platform in ['reddit', 'twitter']:
    db_file = f'backend/uploads/simulations/sim_164487fecd5e/{platform}_simulation.db'
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    print(f"\n==================== {platform} POSTS ====================")
    rows = c.execute("SELECT post_id, user_id, content, created_at FROM post").fetchall()
    for r in rows:
        if '攻打' in r[2]:
            print(f"MATCH: Post #{r[0]} | user_id={r[1]} | content: {r[2]}")
    conn.close()

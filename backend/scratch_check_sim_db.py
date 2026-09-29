import os
import sys
import json
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')

sim_dir = 'backend/uploads/simulations/sim_164487fecd5e'

print("=== Checking Agent system_message and actions across rounds in sim_164487fecd5e ===")

# Check database posts for user_id
for platform in ['reddit', 'twitter']:
    db_file = os.path.join(sim_dir, f'{platform}_simulation.db')
    if os.path.exists(db_file):
        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        print(f"\n--- Platform: {platform} Users ---")
        try:
            users = c.execute("SELECT user_id, user_name, bio FROM user").fetchall()
            for u in users:
                print(f"User {u[0]}: {u[1]} | Bio: {u[2]}")
        except Exception as e:
            print("Error querying users:", e)
        
        print(f"\n--- Platform: {platform} Posts ---")
        try:
            posts = c.execute("SELECT post_id, user_id, content, created_at FROM post ORDER BY post_id").fetchall()
            for p in posts:
                # find author name
                author = next((u[1] for u in users if u[0] == p[1]), f"User_{p[1]}")
                print(f"Post #{p[0]} by {author} (User {p[1]}): {p[2][:100]}...")
        except Exception as e:
            print("Error querying posts:", e)
        conn.close()

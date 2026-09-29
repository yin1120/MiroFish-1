import os, sys, glob, sqlite3

# Simulate running inside simulation_dir (like camel_patch during simulation)
sim_dir = os.path.abspath('backend/uploads/simulations/sim_083f8cc0d041')
os.chdir(sim_dir)
print('Current working directory:', os.getcwd())

# Test our new db resolution logic
db_path = None
if not db_path:
    for db_name in ["twitter_simulation.db", "reddit_simulation.db"]:
        if os.path.exists(db_name):
            db_path = os.path.abspath(db_name)
            break
if not db_path:
    local_dbs = glob.glob("*_simulation.db")
    if local_dbs:
        db_path = os.path.abspath(local_dbs[0])

print('Resolved db_path:', db_path)

if db_path and os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Check agent 0 past posts
    cursor.execute("SELECT post_id, content FROM post WHERE user_id = ? ORDER BY post_id DESC LIMIT 3", (0,))
    posts = cursor.fetchall()
    print(f'Agent 0 past posts ({len(posts)}):')
    for p in posts:
        print(f'  #{p[0]}: {p[1][:80]}...')
    conn.close()

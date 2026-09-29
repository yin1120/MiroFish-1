import sqlite3
import os

sim_dir = 'backend/uploads/simulations/sim_083f8cc0d041'
for db in ['twitter_simulation.db', 'reddit_simulation.db']:
    db_path = os.path.join(sim_dir, db)
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        tables = [t[0] for t in conn.cursor().execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(db, 'tables:', tables)
        for t in tables:
            cols = [c[1] for c in conn.cursor().execute(f"PRAGMA table_info({t})").fetchall()]
            print(f"  {t} columns:", cols)
        conn.close()

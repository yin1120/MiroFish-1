import os
import sys
import json
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')
sim_dir = r"backend/uploads/simulations/sim_9bd9017b1120"

for platform in ["twitter", "reddit"]:
    print(f"\n==================================================================")
    print(f"【{platform.upper()} 平台：Agent 2 (美國政府) 動作與貼文檢查】")
    print(f"==================================================================")
    
    # 檢查 actions.jsonl
    p = os.path.join(sim_dir, platform, "actions.jsonl")
    if os.path.exists(p):
        lines = [json.loads(line) for line in open(p, encoding='utf-8') if line.strip()]
        for idx, l in enumerate(lines):
            aid = l.get("agent_id")
            aname = l.get("agent_name", "")
            r = l.get("round") or l.get("round_num")
            args = l.get("action_args", {})
            content = args.get("content") or args.get("quote_content") or ""
            
            # 如果是 Agent 2 或者發布的內容包含排程事件內容
            if aid == 2 or "美國總統宣布不再支持烏克蘭政府" in content:
                print(f"[Line {idx}] Round {r} | Agent {aid} ({aname}) -> {l.get('action_type')}")
                print(f"    is_scheduled: {args.get('is_scheduled')} | desc: {args.get('description')}")
                print(f"    內容: {content}")
                if args.get("original_content"):
                    print(f"    引用原貼: @{args.get('original_author_name')}: {args.get('original_content')[:60]}...")
                if args.get("post_content"):
                    print(f"    按讚對象貼文: @{args.get('post_author_name')}: {args.get('post_content')[:60]}...")

    # 檢查 SQLite 資料庫
    db = os.path.join(sim_dir, f"{platform}_simulation.db")
    if os.path.exists(db):
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        print(f"\n--- {platform.upper()} 資料庫 post 表檢查 ---")
        
        # 查 user 2 發的所有貼文
        cur.execute("SELECT post_id, user_id, content, created_at, num_likes, num_shares FROM post WHERE user_id = 2")
        posts = cur.fetchall()
        print(f"User 2 總貼文數: {len(posts)}")
        for pt in posts:
            print(f"  Post #{pt[0]} | Likes: {pt[4]} | Shares: {pt[5]} | Created: {pt[3]}")
            print(f"    內容: {pt[2]}")
            
        # 查所有包含排程文字的貼文
        cur.execute("SELECT post_id, user_id, content, created_at, num_likes, num_shares FROM post WHERE content LIKE '%美國總統宣布不再支持烏克蘭政府%'")
        matched = cur.fetchall()
        print(f"\n包含排程文字的全部貼文 (包含轉發/複製): {len(matched)}")
        for pt in matched:
            cur.execute("SELECT name FROM user WHERE user_id = ?", (pt[1],))
            u = cur.fetchone()
            print(f"  Post #{pt[0]} by {u[0] if u else '?'}(User {pt[1]}) | Likes: {pt[4]} | Shares: {pt[5]} | Created: {pt[3]}")
            print(f"    內容: {pt[2][:80]}...")
            
        # 檢查 like 表中針對這些貼文的點讚記錄
        print(f"\n--- {platform.upper()} 資料庫 like 表檢查 ---")
        cur.execute("SELECT like_id, user_id, post_id, created_at FROM like")
        likes = cur.fetchall()
        print(f"資料庫總 like 記錄數: {len(likes)}")
        for lk in likes:
            print(f"  Like #{lk[0]}: User {lk[1]} liked Post #{lk[2]} at {lk[3]}")

        conn.close()


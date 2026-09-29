import os
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')
sim_dir = r"backend/uploads/simulations/sim_9bd9017b1120"
p = os.path.join(sim_dir, "twitter", "actions.jsonl")
lines = [json.loads(line) for line in open(p, encoding='utf-8') if line.strip()]

print("=== 追蹤 Post 11, 15, 21, 23, 24 的 actions.jsonl 記錄 ===")
for idx, l in enumerate(lines):
    args = l.get('action_args', {})
    if args.get('new_post_id') in [15, 21, 23, 24] or args.get('post_id') in [11, 15, 21, 23, 24]:
        print(f"[Line {idx}] Round {l.get('round')} | Agent {l.get('agent_id')} ({l.get('agent_name')}) | {l.get('action_type')}")
        print(f"   original_author_name: {args.get('original_author_name')}")
        print(f"   original_content: {args.get('original_content')}")
        print(f"   quote_content: {args.get('quote_content')}")
        print(f"   content: {args.get('content')}")

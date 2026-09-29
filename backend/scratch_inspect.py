import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

for platform in ['reddit', 'twitter']:
    act_file = f'backend/uploads/simulations/sim_164487fecd5e/{platform}/actions.jsonl'
    if not os.path.exists(act_file):
        continue
    with open(act_file, 'r', encoding='utf-8') as f:
        for line in f:
            a = json.loads(line)
            # Find R35 or DISLIKE or LIKE_COMMENT
            if a.get('round') == 35 and 'DISLIKE' in str(a.get('action_type')):
                print(f"[{platform}] R35 DISLIKE:")
                print(json.dumps(a, ensure_ascii=False, indent=2))
            if a.get('action_type') in ['DISLIKE_POST', 'LIKE_COMMENT', 'DISLIKE_COMMENT']:
                print(f"[{platform}] R{a.get('round')} {a.get('user_name')} {a.get('action_type')}: {a.get('action_args')}")

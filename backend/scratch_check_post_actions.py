import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('backend/uploads/simulations/sim_164487fecd5e/twitter/actions.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        a = json.loads(line)
        args = a.get('action_args') or {}
        if args.get('post_id') in [9, 15, 17] or '因為烏俄戰爭' in str(args):
            print(json.dumps(a, ensure_ascii=False, indent=2))

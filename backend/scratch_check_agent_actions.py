import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

sim_dir = 'backend/uploads/simulations/sim_164487fecd5e'

for target_id, target_name in [(1, '烏克蘭政府'), (9, '美國政府')]:
    print(f"\n==================== Agent {target_id} ({target_name}) Actions ====================")
    for platform in ['reddit', 'twitter']:
        act_file = os.path.join(sim_dir, platform, 'actions.jsonl')
        if not os.path.exists(act_file):
            continue
        with open(act_file, 'r', encoding='utf-8') as f:
            for line in f:
                a = json.loads(line)
                aid = a.get('agent_id')
                uname = a.get('user_name') or a.get('agent_name')
                if aid == target_id:
                    rnd = a.get('round')
                    atype = a.get('action_type')
                    args = a.get('action_args')
                    print(f"[{platform}] R{rnd} | {atype} | args: {json.dumps(args, ensure_ascii=False)}")

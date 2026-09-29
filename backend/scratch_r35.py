import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

act_file = 'backend/uploads/simulations/sim_164487fecd5e/reddit/actions.jsonl'
with open(act_file, 'r', encoding='utf-8') as f:
    for line in f:
        a = json.loads(line)
        if a.get('round') == 35:
            print(json.dumps(a, ensure_ascii=False, indent=2))

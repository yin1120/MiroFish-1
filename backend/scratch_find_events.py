import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search for the scheduled events config in proj_4db218ea7e4d or sim_164487fecd5e or any other file
for root, dirs, files in os.walk('backend/uploads'):
    for f in files:
        if f.endswith('.json'):
            p = os.path.join(root, f)
            try:
                with open(p, 'r', encoding='utf-8') as fh:
                    d = json.load(fh)
                    if isinstance(d, dict) and ('scheduled_events' in d or 'event_config' in d):
                        print(f"Found event config in {p}:")
                        print(json.dumps(d.get('event_config') or d.get('scheduled_events'), ensure_ascii=False, indent=2))
            except Exception:
                pass

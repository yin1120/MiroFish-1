import os
import sys
import glob
import json

sys.stdout.reconfigure(encoding='utf-8')

# Search for simulation and stage 1 artifacts / project configs
for root, dirs, files in os.walk('backend/uploads'):
    for f in files:
        if f.endswith('.json') or f.endswith('.txt') or f.endswith('.md'):
            p = os.path.join(root, f)
            try:
                with open(p, 'r', encoding='utf-8', errors='ignore') as fh:
                    content = fh.read()
                    if '烏克蘭政府（核心主體）' in content or '皆隸屬於或代表' in content:
                        print(f"Found match in {p}")
            except Exception:
                pass

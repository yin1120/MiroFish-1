import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

rep_dir = 'backend/uploads/reports/report_94970e118d3b'

# 1. Check outline.json
outline_f = os.path.join(rep_dir, 'outline.json')
if os.path.exists(outline_f):
    with open(outline_f, 'r', encoding='utf-8') as f:
        outline = json.load(f)
    print("=== Outline JSON ===")
    print(json.dumps(outline, ensure_ascii=False, indent=2))

# 2. Check meta.json
meta_f = os.path.join(rep_dir, 'meta.json')
if os.path.exists(meta_f):
    with open(meta_f, 'r', encoding='utf-8') as f:
        meta = json.load(f)
    print("\n=== Meta JSON ===")
    print(json.dumps(meta, ensure_ascii=False, indent=2))

# 3. Check console_log.txt for key steps
console_f = os.path.join(rep_dir, 'console_log.txt')
if os.path.exists(console_f):
    with open(console_f, 'r', encoding='utf-8', errors='ignore') as f:
        clines = f.readlines()
    print(f"\n=== Console Log ({len(clines)} lines) ===")
    for cl in clines[:30]:
        print(cl.strip())
    if len(clines) > 30:
        print("...")
        for cl in clines[-20:]:
            print(cl.strip())

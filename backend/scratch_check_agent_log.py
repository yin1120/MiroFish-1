import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

log_f = 'backend/uploads/reports/report_94970e118d3b/agent_log.jsonl'
with open(log_f, 'r', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        action = d.get('action')
        data = d.get('data') or {}
        if action == 'section_start':
            print(f"\n>>> Section Start: {data.get('title')} (index {data.get('index')})")
        elif action == 'tool_call':
            print(f"  Tool Call: {data.get('tool_name')} | args: {json.dumps(data.get('tool_args'), ensure_ascii=False)[:100]}")
        elif action == 'section_complete':
            print(f"  Section Complete: length={data.get('content_length')}, tool_calls={data.get('tool_calls_count')}")

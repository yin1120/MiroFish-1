import os
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
report_dir = 'backend/uploads/reports/report_78245ba8a863'
print('Files:', os.listdir(report_dir))
report_path = os.path.join(report_dir, 'report.json')
if os.path.exists(report_path):
    with open(report_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        print('Title:', data.get('title'))
        print('\nSections:')
        for s in data.get('sections', []):
            title = s.get('title')
            content = s.get('content', '')
            print(f' - Section: {title} ({len(content)} chars)')
            print(f'   Preview: {content[:150].strip()}...\n')

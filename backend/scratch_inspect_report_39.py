import os
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

report_dir = "backend/uploads/reports/report_391903422b72"

print("=== 1. Outline in report_391903422b72 ===")
with open(os.path.join(report_dir, "outline.json"), "r", encoding="utf-8") as f:
    outline = json.load(f)
    print("Report Title:", outline.get("title"))
    for s in outline.get("sections", []):
        print(" - Section:", s.get("title"))

print("\n=== 2. Check full_report.md contents ===")
with open(os.path.join(report_dir, "full_report.md"), "r", encoding="utf-8") as f:
    lines = f.readlines()
    print(f"Total lines in full_report.md: {len(lines)}")
    # Print headings and quotes
    for line in lines:
        if line.startswith("## ") or line.startswith("### ") or line.startswith("> ") or "客觀事實" in line or "Round" in line:
            print(line.strip()[:140])

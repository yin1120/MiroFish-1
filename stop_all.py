"""
MiroFish 背景進程與任務終止工具 (stop_all.py)
用途：精確掃描並強制終止所有本地 MiroFish 殘留的 Python 推演子進程、Flask 後端與 Node 前端
"""

import os
import sys
import psutil

# 確保輸出支援 UTF-8
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

def stop_all_mirofish():
    current_pid = os.getpid()
    print("=" * 60)
    print("🛑 正在掃描並終止所有 MiroFish 殘留進程...")
    print("=" * 60)
    
    target_keywords = [
        "mirofish",
        "run_parallel_simulation.py",
        "run.py",
        "launch.py",
        "monitor_llm.py",
        "vite"
    ]
    
    killed_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            pid = proc.info['pid']
            if pid == current_pid:
                continue
            
            name = (proc.info['name'] or "").lower()
            if not ('python' in name or 'node' in name):
                continue
            
            cmdline = " ".join(proc.info['cmdline'] or []).lower()
            
            # 檢查是否為 MiroFish 相關進程
            if any(kw in cmdline for kw in target_keywords):
                print(f"  └── [終止] PID {pid:5d} | {name:10s} | {cmdline[:60]}...")
                proc.kill()
                killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    print("-" * 60)
    if killed_count > 0:
        print(f"✅ 成功終止 {killed_count} 個 MiroFish 相關進程！")
    else:
        print("✅ 目前無任何殘留的 MiroFish 進程正在運行。")
    print("=" * 60)

if __name__ == "__main__":
    stop_all_mirofish()

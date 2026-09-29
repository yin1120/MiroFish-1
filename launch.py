import os
import sys
import subprocess
import time

# 修正 Windows UTF-8 中文顯示
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")

def main():
    print("=" * 70, flush=True)
    print("             MiroFish 群體智能引擎 - 啟動主控台", flush=True)
    print("=" * 70, flush=True)
    print("[1/3] 正在檢測遠端算力伺服器連線狀態與可用模型...\n", flush=True)

    # 執行算力連線健康檢查
    result = subprocess.run([sys.executable, os.path.join(ROOT_DIR, "test_connection.py")])
    if result.returncode != 0:
        print("\n" + "-" * 70, flush=True)
        print("⚠️ [警告] 算力伺服器檢測未通過！", flush=True)
        print("請檢查 backend/logs/connection_status.log 了解錯誤詳情。", flush=True)
        print("-" * 70, flush=True)
        try:
            choice = input("是否仍要強制啟動？(y/n, 預設 n): ").strip().lower()
        except Exception:
            choice = "n"
        if choice != "y":
            print("啟動已取消。請修復連線問題後重新執行。", flush=True)
            sys.exit(1)

    creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0

    print("\n" + "=" * 70, flush=True)
    print("[2/3] 正在獨立視窗啟動 MiroFish 後端服務 (Port 5001)...", flush=True)
    print("      (專注於 Flask 伺服器與業務 API 邏輯)", flush=True)
    print("=" * 70, flush=True)

    # 視窗 1：啟動後端
    subprocess.Popen(
        ["cmd.exe", "/k", "title MiroFish Backend [Port 5001] & chcp 65001 >nul & uv run python run.py"],
        cwd=BACKEND_DIR,
        creationflags=creationflags
    )

    time.sleep(1)

    print("\n" + "=" * 70, flush=True)
    print("[3/3] 正在獨立視窗啟動「MiroFish 算力連線資訊 (API Key)」監控終端...", flush=True)
    print("      (即時顯示所有由 API KEY 發起之 [LLM Request]、推論秒數心跳與 Token 數據)", flush=True)
    print("=" * 70, flush=True)

    # 視窗 2：啟動算力連線即時監控終端（直接以 cwd=ROOT_DIR 執行，無引號問題）
    monitor_cmd = "title MiroFish 算力連線資訊 (API Key) & chcp 65001 >nul & python monitor_llm.py"
    subprocess.Popen(
        ["cmd.exe", "/k", monitor_cmd],
        cwd=ROOT_DIR,
        creationflags=creationflags
    )

    # 前端：在背景自動啟動，不佔用額外視窗
    print("\n正在背景啟動 MiroFish 前端 UI (Port 3000)...", flush=True)
    subprocess.Popen(
        ["cmd.exe", "/c", "npm run dev"],
        cwd=FRONTEND_DIR,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )

    print("\n" + "=" * 70, flush=True)
    print("                  MiroFish 雙視窗環境已成功就緒！", flush=True)
    print("======================================================================", flush=True)
    print("  視窗 1: [MiroFish Backend]         - 後端 API 與 Flask 伺服器", flush=True)
    print("  視窗 2: [MiroFish 算力連線 (API Key)] - 算力連線即時請求、心跳與 Token 速度", flush=True)
    print("  背景  : [MiroFish Frontend]        - 前端 Web UI (http://localhost:3000)", flush=True)
    print("-" * 70, flush=True)
    print("  【AI Agent 智慧除錯提示】", flush=True)
    print("  所有推論連線、耗時心跳與詳細報錯均同步記錄於：", flush=True)
    print("   - backend/logs/[今日日期].log", flush=True)
    print("   - backend/logs/llm_stream.log", flush=True)
    print("   - backend/logs/connection_status.log", flush=True)
    print("\n  若遇異常直接向 Agent 說：「幫我看 log 除錯」，Agent 將自動為您分析！", flush=True)
    print("=" * 70 + "\n", flush=True)

if __name__ == "__main__":
    main()

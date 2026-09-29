import os
import sys
import time

# 修正 Windows 控制台 UTF-8 中文顯示
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(ROOT_DIR, "backend", "logs", "llm_stream.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def main():
    # 每次啟動監控台時，清空上一次殘留的舊記錄，確保推論秒數從 0 秒全新開始
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"=== MiroFish 算力連線監控通道已就緒 ({now_str}) ===\n\n")

    print("=" * 70, flush=True)
    print("          MiroFish 算力中心即時連線監控台 (API Key 連線)", flush=True)
    print("=" * 70, flush=True)
    print("📡 算力端點: http://140.138.175.53:8000/v1", flush=True)
    print("🤖 綁定模型: Qwen3.5-27B", flush=True)
    print("🔑 授權憑證: sk-lab-admin-dgx1-master (Admin Master Channel)", flush=True)
    print("-" * 70, flush=True)
    print("🟢 監控通道已就緒！每次請求將從 [LLM Request #0] 與 0 秒開始即時推播...\n", flush=True)

    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        # 持續即時監聽新內容
        while True:
            line = f.readline()
            if line:
                print(line, end="", flush=True)
            else:
                time.sleep(0.2)

if __name__ == "__main__":
    main()

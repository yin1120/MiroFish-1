import os
import time
import sys
import io
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# 修正 Windows 終端機 UTF-8 中文顯示
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 1. 載入 .env 變數
load_dotenv()

api_key = os.getenv("LLM_API_KEY", "")
base_url = os.getenv("LLM_BASE_URL", "")
model_name = os.getenv("LLM_MODEL_NAME", "")

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
STATUS_LOG_FILE = os.path.join(LOG_DIR, "connection_status.log")

def write_status_log(success: bool, message: str, details: dict = None):
    """將連線診斷結果寫入日誌檔供 Agent 分析"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_content = {
        "timestamp": now_str,
        "success": success,
        "base_url": base_url,
        "model_name": model_name,
        "message": message,
        "details": details or {}
    }
    with open(STATUS_LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"[{now_str}] {'SUCCESS' if success else 'FAILED'} - {message}\n")
        f.write(json.dumps(log_content, ensure_ascii=False, indent=2) + "\n")

print("=" * 60)
print("🚀 MiroFish 算力中心連線檢測工具")
print("=" * 60)
print(f"📡 連線網址 (Base URL): {base_url}")
print(f"🤖 指定模型 (Model):    {model_name}")
print(f"🔑 API Key:             {api_key[:10]}...{api_key[-6:] if len(api_key) > 16 else ''}")
print("-" * 60)

if not base_url or not model_name:
    err_msg = "❌ 錯誤: .env 檔案中缺少 LLM_BASE_URL 或 LLM_MODEL_NAME 設定！"
    print(err_msg)
    write_status_log(False, err_msg)
    sys.exit(1)

# 0. 快速診斷 Gateway 健康狀態（避免長時間卡死等待）
gateway_host = base_url.replace('/v1', '').rstrip('/')
try:
    health_resp = requests.get(f"{gateway_host}/health", timeout=6.0)
    if health_resp.status_code == 200:
        h_data = health_resp.json()
        b_status = h_data.get("backend_status", "")
        if "unreachable" in b_status.lower():
            err_msg = f"算力伺服器閘道正常，但底層模型推論核心 ({h_data.get('backend_url', '8001')}) 目前處於【{b_status}】狀態（模型服務當機或未啟動）！"
            print("\n" + "=" * 20 + " ❌ 伺服器核心未就緒 " + "=" * 20)
            print(f"⚠️ {err_msg}")
            print("------------------------------------------------------------")
            print("請檢查：遠端伺服器 (140.138.175.53) 上的 vLLM 或模型推論進程 (Port 8001) 是否已啟動？")
            print("=" * 60 + "\n")
            write_status_log(False, err_msg, h_data)
            sys.exit(1)
except Exception:
    pass

client = OpenAI(base_url=base_url, api_key=api_key or "EMPTY", timeout=45.0)

try:
    print("⏳ 1/2 正在查詢算力伺服器可用模型清單...")
    models_resp = client.models.list()
    available_models = [m.id for m in models_resp.data]
    print(f"  └── 發現可用模型: {', '.join(available_models) if available_models else '（未列出）'}")

    print("⏳ 2/2 正在發送測試推論請求至算力中心 (逾時設為 45 秒，若背景推演中將自動排隊)...")
    start_time = time.time()
    
    req_kwargs = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "你是一個專業助手。"},
            {"role": "user", "content": "請回覆：測試成功！"}
        ],
        "temperature": 0.1,
        "max_tokens": 60,
    }
    # 僅針對 Qwen3.5 思考模型傳送 enable_thinking 抑制思考模式，相容原生 vLLM 嚴格校驗
    if "3.5" in model_name:
        req_kwargs["extra_body"] = {"enable_thinking": False}
        
    response = client.chat.completions.create(**req_kwargs)
    
    end_time = time.time()
    duration = end_time - start_time
    
    content = response.choices[0].message.content or ""
    tokens = getattr(response.usage, 'completion_tokens', 0) if response.usage else 0
    tps = tokens / duration if duration > 0 and tokens > 0 else 0
    
    has_thinking = "thinking process" in content.lower() or "<think>" in content.lower()
    
    print("\n" + "=" * 20 + " ✅ 連線推論成功！ " + "=" * 20)
    print(f"💬 模型回覆：\n{content}")
    print("-" * 60)
    if has_thinking:
        print("⚠️  思考模式狀態: 偵測到思考歷程 (Thinking Process)")
    else:
        print("✨  思考模式狀態: ✅ 思考歷程已成功抑制 (直接輸出答案)")
    print(f"⏱️  連線花費時間: {duration:.2f} 秒")
    print(f"📝 生成字數 (Tokens): {tokens}")
    if tps > 0:
        print(f"⚡ 生成速度: {tps:.2f} tokens/sec")
    print(f"📁 診斷報告已更新至: {STATUS_LOG_FILE}")
    print("=" * 60 + "\n")
    
    write_status_log(True, "算力中心連線與推論測試完全成功", {
        "duration_seconds": round(duration, 2),
        "completion_tokens": tokens,
        "tokens_per_second": round(tps, 2),
        "thinking_detected": has_thinking,
        "available_models": available_models,
        "sample_response": content
    })
    sys.exit(0)

except Exception as e:
    err_str = str(e)
    print("\n" + "=" * 20 + " ❌ 連線失敗或推論逾時！ " + "=" * 20)
    print(f"錯誤訊息: {err_str}")
    print("-" * 60)
    print("可能原因：")
    print("1. 遠端伺服器推論核心 (Port 8001) 正在滿載排隊或未啟動。")
    print("2. 網路延遲超過 15 秒設定。")
    print("3. .env 中設定之 API Key 或模型名稱有誤。")
    print("=" * 60 + "\n")
    
    write_status_log(False, f"連線或推論失敗: {err_str}")
    sys.exit(1)

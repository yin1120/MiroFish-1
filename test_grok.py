"""
Grok API 測試與使用腳本 (test_grok.py)

功能說明：
1. 自動讀取 .env 中的 XAI_API_KEY、XAI_BASE_URL、GROK_MODEL
2. 檢查並驗證 GROK_MODEL 名稱是否正確（比對 xAI 官方模型清單與別名）
3. 支援連線測試、單次提問 (--prompt) 與終端多輪對話模式 (--chat)
4. 可選一鍵將 MiroFish 系統主配置切換為 Grok (--apply-to-mirofish)
"""

import os
import sys
import io
import time
import argparse
import subprocess
from typing import List, Dict, Any, Tuple
from dotenv import load_dotenv
from openai import OpenAI

# 修正 Windows 終端機 UTF-8 中文顯示，避免亂碼
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 1. 載入 .env 設定
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(ROOT_DIR, ".env")
load_dotenv(ENV_FILE)

XAI_API_KEY = os.getenv("XAI_API_KEY", "").strip()
XAI_BASE_URL = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1").strip()
GROK_MODEL = os.getenv("GROK_MODEL", "grok-4.20-0309-non-reasoning").strip()

def check_env_configs() -> bool:
    """檢查 .env 中的 Grok 設定是否齊全"""
    if not XAI_API_KEY:
        print("❌ 錯誤：.env 檔案中未找到 XAI_API_KEY 設定！")
        print("請在 .env 中填寫：")
        print("XAI_API_KEY=xai-your-api-key")
        return False
    return True

def get_xai_client() -> OpenAI:
    """初始化 OpenAI 相容的 xAI 客戶端"""
    return OpenAI(
        api_key=XAI_API_KEY,
        base_url=XAI_BASE_URL,
        timeout=60.0
    )

def fetch_and_validate_models(client: OpenAI, target_model: str) -> Tuple[bool, List[Dict[str, Any]], str]:
    """
    從 xAI API 抓取官方可用模型，並檢查 target_model 是否正確
    返回: (is_valid, model_list, matched_real_id)
    """
    try:
        models_data = client.models.list().data
    except Exception as e:
        print(f"❌ 查詢 xAI 模型清單時失敗：{e}")
        return False, [], ""

    model_list = []
    is_valid = False
    matched_real_id = ""

    for item in models_data:
        m_id = getattr(item, "id", "")
        aliases = getattr(item, "aliases", []) or []
        context_len = getattr(item, "context_length", 0)
        
        info = {
            "id": m_id,
            "aliases": aliases,
            "context_length": context_len,
        }
        model_list.append(info)

        # 比對模型名稱（主 ID 或別名）
        if target_model == m_id:
            is_valid = True
            matched_real_id = m_id
        elif target_model in aliases and not is_valid:
            is_valid = True
            matched_real_id = m_id

    return is_valid, model_list, matched_real_id

def print_model_check_report(target_model: str, is_valid: bool, matched_id: str, model_list: List[Dict[str, Any]]):
    """輸出詳細的模型檢查報告"""
    print("\n" + "=" * 68)
    print("                🔍 Grok 模型填寫檢查結果")
    print("=" * 68)
    print(f"📌 .env 填寫的 GROK_MODEL: {target_model}")

    if is_valid:
        print(f"✅ 【檢查通過】模型名稱填寫完全正確！")
        if matched_id != target_model:
            print(f"ℹ️  備註：此名稱為模型「{matched_id}」之官方有效別名 (Alias)")
    else:
        print(f"❌ 【檢查未通過】在您的 xAI 授權清單中找不到名稱為「{target_model}」的模型！")
        print("💡 請參考下方官方支援的正確模型清單進行修改。")

    print("-" * 68)
    print("📋 您的 xAI 帳號可用模型清單 (Total: {} 個):".format(len(model_list)))
    print("-" * 68)
    
    # 篩選對話型文字模型（排除純圖片/影片生成模型以更直觀）
    chat_models = [m for m in model_list if not any(x in m["id"] for x in ["image", "video"])]
    media_models = [m for m in model_list if any(x in m["id"] for x in ["image", "video"])]

    print("【文字/推理/對話模型】")
    for m in chat_models:
        marker = "👉 [當前使用]" if (m["id"] == target_model or target_model in m["aliases"]) else "   "
        ctx_str = f"{m['context_length']:,} tokens" if m['context_length'] else "未知"
        alias_str = f" (別名: {', '.join(m['aliases'][:2])})" if m["aliases"] else ""
        print(f"{marker} • {m['id']}{alias_str} | 上下文: {ctx_str}")

    if media_models:
        print("\n【多媒體/生成模型】")
        for m in media_models:
            print(f"     • {m['id']}")
    print("=" * 68 + "\n")

def test_inference(client: OpenAI, model_name: str, prompt: str = "請用繁體中文回覆一句話：Grok API 連線成功！並簡短自我介紹。"):
    """發送一次推論請求測試連線與回應"""
    print(f"⏳ 正在向 Grok 發送測試請求 (模型: {model_name})...")
    start_time = time.time()
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "你是一個專業、親切的 AI 助手，請使用繁體中文回答。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=256
        )
        elapsed = time.time() - start_time
        reply = response.choices[0].message.content
        usage = response.usage

        print("\n" + "=" * 68)
        print(f"🎉 Grok API 呼叫成功！(耗時: {elapsed:.2f} 秒)")
        print("=" * 68)
        print("🤖 Grok 回覆內容：")
        print("-" * 68)
        print(reply)
        print("-" * 68)
        if usage:
            print(f"📊 Token 消耗: Prompt={usage.prompt_tokens} / Completion={usage.completion_tokens} / Total={usage.total_tokens}")
        print("=" * 68 + "\n")
        return True
    except Exception as e:
        print(f"❌ 呼叫 Grok API 失敗: {e}")
        return False

def interactive_chat(client: OpenAI, model_name: str):
    """終端互動式對話模式 (支援串流輸出)"""
    print("\n" + "=" * 68)
    print(f"💬 進入 Grok 互動對話模式 (模型: {model_name})")
    print("輸入訊息後按 Enter 發送，輸入 'exit' 或 'quit' 退出對話。")
    print("=" * 68)

    messages = [
        {"role": "system", "content": "你是一個幽默、機智且博學的 AI 助手，請始終使用繁體中文回答。"}
    ]

    while True:
        try:
            user_input = input("\n👤 您: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "q"]:
                print("👋 已退出 Grok 對話。")
                break

            messages.append({"role": "user", "content": user_input})
            print("\n🤖 Grok: ", end="", flush=True)

            stream = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.7,
                stream=True
            )

            full_reply = ""
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    print(delta, end="", flush=True)
                    full_reply += delta
            print()

            messages.append({"role": "assistant", "content": full_reply})

        except KeyboardInterrupt:
            print("\n👋 對話中斷退出。")
            break
        except Exception as e:
            print(f"\n❌ 對話發生錯誤: {e}")

def apply_grok_to_mirofish(model_name: str = None):
    """將 .env 中的 MiroFish 主模型配置切換為 Grok"""
    if not os.path.exists(ENV_FILE):
        print("❌ 找不到 .env 檔案")
        return

    chosen_model = model_name or GROK_MODEL

    with open(ENV_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updates = {
        "LLM_API_KEY": XAI_API_KEY,
        "LLM_BASE_URL": XAI_BASE_URL,
        "LLM_MODEL_NAME": chosen_model
    }

    new_lines = []
    applied = set()
    for line in lines:
        stripped = line.strip()
        matched = False
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}\n")
                applied.add(k)
                matched = True
        if not matched:
            new_lines.append(line)

    for k, v in updates.items():
        if k not in applied:
            new_lines.append(f"{k}={v}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print("\n" + "=" * 68)
    print("✅ 已成功將 MiroFish 系統主配置切換為 Grok API！")
    print(f"   LLM_MODEL_NAME = {chosen_model}")
    print(f"   LLM_BASE_URL   = {XAI_BASE_URL}")
    print(f"   LLM_API_KEY    = {XAI_API_KEY[:10]}...{XAI_API_KEY[-6:]}")
    print("====================================================================\n")

def launch_mirofish():
    """啟動 MiroFish 全套服務 (調用 launch.py)"""
    print("\n" + "=" * 68)
    print("🚀 連線已確立，正在為您啟動 MiroFish 系統...")
    print("   (包含後端 Flask API [5001]、算力監控終端與前端 Web UI [3000])")
    print("=" * 68 + "\n")
    launch_script = os.path.join(ROOT_DIR, "launch.py")
    try:
        subprocess.run([sys.executable, launch_script])
    except KeyboardInterrupt:
        print("\n👋 已中斷 MiroFish 啟動。")
    except Exception as e:
        print(f"\n❌ MiroFish 啟動遭遇錯誤: {e}")

def main():
    parser = argparse.ArgumentParser(description="Grok API 測試與使用腳本")
    parser.add_argument("--prompt", "-p", type=str, help="發送指定單次問題給 Grok")
    parser.add_argument("--chat", "-c", action="store_true", help="開啟互動式對話終端")
    parser.add_argument("--model", "-m", type=str, help="覆寫 .env 中指定的 Grok 模型名稱")
    parser.add_argument("--check-only", action="store_true", help="僅檢查模型名稱與可用清單，不發送測試訊息")
    parser.add_argument("--apply-to-mirofish", action="store_true", help="將 .env 中的 MiroFish 主要 LLM 設定同步切換為 Grok")
    parser.add_argument("--launch", "-l", action="store_true", help="建立 Grok 連線後直接開啟 MiroFish 系統")
    args = parser.parse_args()

    print("=" * 68)
    print("🚀 MiroFish - xAI Grok API 檢查與使用工具")
    print("=" * 68)
    print(f"📡 API 端點 (Base URL): {XAI_BASE_URL}")
    print(f"🔑 API Key:             {XAI_API_KEY[:10]}...{XAI_API_KEY[-6:] if len(XAI_API_KEY) > 16 else ''}")
    print(f"🤖 設定模型 (Model):    {GROK_MODEL}")
    print("-" * 68)

    if not check_env_configs():
        sys.exit(1)

    client = get_xai_client()
    target_model = args.model if args.model else GROK_MODEL

    # 1. 一鍵套用到 MiroFish 主設定（無啟動）
    if args.apply_to_mirofish:
        apply_grok_to_mirofish(target_model)
        return

    # 2. 檢查 model 有沒有填寫正確
    print("⏳ 正在向 xAI 伺服器驗證 API Key 與查詢可用模型清單...")
    is_valid, model_list, matched_id = fetch_and_validate_models(client, target_model)
    
    print_model_check_report(target_model, is_valid, matched_id, model_list)

    if not is_valid:
        print("⚠️ 警告：由於模型名稱未通過驗證，後續推論可能會失敗。")
        print("請確認後更新 .env 檔案中的 GROK_MODEL 設定。")
        if args.check_only:
            return

    if args.check_only:
        return

    actual_model = matched_id if matched_id else target_model

    # 3. 建立連線並啟動 MiroFish
    if args.launch:
        apply_grok_to_mirofish(actual_model)
        ok = test_inference(client, actual_model)
        if ok:
            launch_mirofish()
        else:
            print("❌ 連線測試失敗，取消啟動 MiroFish。請檢查 API Key 或網路連線。")
        return

    # 4. 其它操作模式
    if args.chat:
        interactive_chat(client, actual_model)
    elif args.prompt:
        test_inference(client, actual_model, prompt=args.prompt)
    else:
        # 預設執行連線推論驗證
        test_inference(client, actual_model)
        print("💡 提示：")
        print("  • 建立連線並啟動 MiroFish：python test_grok.py --launch  (或執行 test_grok.bat)")
        print("  • 單次問答：python test_grok.py --prompt \"你的問題\"")
        print("  • 互動對話：python test_grok.py --chat")
        print("  • 僅同步主設定：python test_grok.py --apply-to-mirofish")

if __name__ == "__main__":
    main()

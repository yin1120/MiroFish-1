import os
import time
import sys
import io
from dotenv import load_dotenv
from openai import OpenAI

# 修正 Windows 終端機中文顯示
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 1. 載入 .env 變數
load_dotenv()

api_key = os.getenv("LLM_API_KEY", "meta-llama-3.1-8b-instruct")
base_url = os.getenv("LLM_BASE_URL", "http://140.138.176.195:1234/v1")
model_name = os.getenv("LLM_MODEL_NAME", "meta-llama-3.1-8b-instruct")

print("="*50)
print(f"🚀 MiroFish LLM 連線測試工具")
print("="*50)
print(f"📡 連線網址: {base_url}")
print(f"🤖 使用模型: {model_name}")
print("-" * 50)

if not model_name:
    print("❌ 錯誤: .env 檔案中找不到 LLM_MODEL_NAME，請確認是否有填寫！")
    sys.exit(1)

# 2. 初始化 OpenAI 客戶端
client = OpenAI(base_url=base_url, api_key=api_key)

try:
    print("正在發送請求給 LM Studio...")
    start_time = time.time()
    
    # 3. 發送測試請求
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "請寫一段大約 50 字的自我介紹，告訴我你是誰。"}
        ],
        temperature=0.7,
        max_tokens=200
    )
    
    end_time = time.time()
    duration = end_time - start_time
    
    # 4. 解析結果
    content = response.choices[0].message.content
    tokens = response.usage.completion_tokens
    tps = tokens / duration if duration > 0 else 0
    
    print("\n✅ 連線成功！")
    print(f"\n💬 模型回覆：\n{content}")
    print("-" * 50)
    print(f"⏱️ 總花費時間: {duration:.2f} 秒")
    print(f"📝 生成字數 (Tokens): {tokens}")
    print(f"⚡ 生成速度 (Speed): {tps:.2f} tokens/sec")
    
    if tps < 5:
        print("\n⚠️ 警告：速度非常慢 (低於 5 t/s)，請檢查 LM Studio 的 GPU Offload 是否已開啟！")
    else:
        print(f"\n🔥 速度優良！你的顯卡正在全速運轉中。")

except Exception as e:
    print(f"\n❌ 連線失敗！")
    print(f"錯誤訊息: {str(e)}")
    print("\n請檢查：")
    print("1. LM Studio 是否已啟動 'Local Server'？")
    print("2. .env 中的 LLM_BASE_URL 是否正確？")
    print("3. .env 中的 LLM_MODEL_NAME 是否與 LM Studio 載入的一模一樣？")

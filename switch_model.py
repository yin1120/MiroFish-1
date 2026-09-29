"""
MiroFish 算力環境切換工具 (switch_model.py)
用途：無縫切換 .env 設定（Qwen3.5-27B 遠端直連模式 vs Qwen/Qwen2.5-14B-Instruct 本地隧道模式）
"""

import os
import sys
import io
import argparse

# 修正 Windows 終端機 UTF-8 中文顯示
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(ROOT_DIR, ".env")

PRESETS = {
    "27b": {
        "name": "Qwen3.5-27B 遠端直連模式 (常駐)",
        "desc": "遠端伺服器常駐推論服務，免開 SSH 隧道，直接連線",
        "LLM_MODEL_NAME": "Qwen3.5-27B",
        "LLM_BASE_URL": "http://140.138.175.53:8000/v1",
        "LLM_API_KEY": "sk-lab-admin-dgx1-master"
    },
    "14b": {
        "name": "Qwen/Qwen2.5-14B-Instruct 本地隧道模式 (隨選)",
        "desc": "手動 SSH 隧道 (Port 8000 -> 8002)，用完按 Ctrl+C 釋放 GPU",
        "LLM_MODEL_NAME": "Qwen/Qwen2.5-14B-Instruct",
        "LLM_BASE_URL": "http://localhost:8000/v1",
        "LLM_API_KEY": "EMPTY"
    },
    "grok": {
        "name": "xAI Grok 官方雲端 API 模式",
        "desc": "直接使用 xAI 官方 Grok API，超快回應速度與 100 萬 Token 上下文",
        "LLM_MODEL_NAME": "grok-4.20-0309-non-reasoning",
        "LLM_BASE_URL": "https://api.x.ai/v1",
        "LLM_API_KEY": ""  # 動態從 .env 中的 XAI_API_KEY 讀取
    }
}

def read_env() -> dict:
    """讀取 .env 鍵值對"""
    env_vars = {}
    if not os.path.exists(ENV_FILE):
        return env_vars
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str and not line_str.startswith("#") and "=" in line_str:
                k, v = line_str.split("=", 1)
                env_vars[k.strip()] = v.strip()
    return env_vars

def update_env(updates: dict):
    """精確更新 .env 中的鍵值，並完整保留註解與其他配置"""
    if not os.path.exists(ENV_FILE):
        lines = []
    else:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

    applied_keys = set()
    new_lines = []

    for line in lines:
        stripped = line.strip()
        matched = False
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}\n")
                applied_keys.add(k)
                matched = True
        if not matched:
            new_lines.append(line)

    for k, v in updates.items():
        if k not in applied_keys:
            new_lines.append(f"{k}={v}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

def apply_preset(key: str, silent: bool = False):
    preset = PRESETS.get(key)
    if not preset:
        print(f"❌ 未知預設模式: {key}")
        return False

    env_vars = read_env()
    model_name = preset["LLM_MODEL_NAME"]
    base_url = preset["LLM_BASE_URL"]
    api_key = preset["LLM_API_KEY"]

    if key == "grok":
        api_key = env_vars.get("XAI_API_KEY", "")
        base_url = env_vars.get("XAI_BASE_URL", "https://api.x.ai/v1")
        model_name = env_vars.get("GROK_MODEL", "grok-4.20-0309-non-reasoning")
        if not api_key:
            print("❌ .env 中未找到 XAI_API_KEY，請先在 .env 中填寫！")
            return False

    update_env({
        "LLM_MODEL_NAME": model_name,
        "LLM_BASE_URL": base_url,
        "LLM_API_KEY": api_key
    })

    if not silent:
        print("=" * 60)
        print(f"🔄 已切換為：【{preset['name']}】")
        print(f"   說明: {preset['desc']}")
        print("-" * 60)
        print(f"   LLM_MODEL_NAME = {model_name}")
        print(f"   LLM_BASE_URL   = {base_url}")
        print(f"   LLM_API_KEY    = {api_key[:10]}...{api_key[-6:] if len(api_key) > 16 else ''}")
        print("=" * 60)
    return True

def show_menu():
    curr = read_env()
    curr_model = curr.get("LLM_MODEL_NAME", "（未設定）")
    curr_url = curr.get("LLM_BASE_URL", "（未設定）")

    print("\n" + "=" * 65)
    print("               MiroFish 算力模式切換中心")
    print("=" * 65)
    print("【目前 .env 設定】")
    print(f"  🤖 當前模型: {curr_model}")
    print(f"  📡 連線端點: {curr_url}")
    print("-" * 65)
    print("【請選擇要切換的連線模式】")
    print("  [1] Qwen3.5-27B 遠端直連模式 (常駐、免開 Tunnel)")
    print("  [2] Qwen/Qwen2.5-14B-Instruct 本地隧道模式 (需配合 SSH Tunnel)")
    print("  [3] xAI Grok 官方雲端 API 模式 (免伺服器、極速、超大上下文)")
    print("  [0] 離開")
    print("=" * 65)

    try:
        c = input("請輸入選項 [1/2/3/0]: ").strip()
    except Exception:
        return

    if c == "1":
        apply_preset("27b")
    elif c == "2":
        apply_preset("14b")
    elif c == "3":
        apply_preset("grok")
    elif c == "0":
        print("已結束。")

def main():
    parser = argparse.ArgumentParser(description="MiroFish 算力切換工具")
    parser.add_argument("--set", choices=["27b", "14b", "grok"], help="設定指定的預設模式")
    parser.add_argument("--no-test", action="store_true", help="不執行連線測試")
    args = parser.parse_args()

    if args.set:
        apply_preset(args.set, silent=False)
    else:
        show_menu()

if __name__ == "__main__":
    main()

"""
Zep Episode 查詢工具
用於根據 Episode UUID 查詢其儲存在 Zep 中的原始文本段落內容
"""

import sys
import os
import argparse

# 引入專案與 backend 路徑以載入 app.config
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.abspath(os.path.join(_scripts_dir, '..'))
sys.path.insert(0, _backend_dir)

from zep_cloud import Zep
from app.config import Config

def query_episode(uuid: str):
    if not Config.ZEP_API_KEY:
        print("錯誤：未在 .env 中找到 ZEP_API_KEY 配置。")
        return
        
    client = Zep(api_key=Config.ZEP_API_KEY)
    print(f"正在向 Zep 查詢 Episode: {uuid} ...")
    try:
        episode = client.graph.episode.get(uuid_=uuid)
        print("\n=================== 查詢結果 ===================")
        print(f"UUID: {getattr(episode, 'uuid_', '未知')}")
        print(f"類型 (Type): {getattr(episode, 'type', '未知')}")
        print(f"處理狀態 (Processed): {getattr(episode, 'processed', '未知')}")
        print(f"建立時間 (Created At): {getattr(episode, 'created_at', '未知')}")
        print("\n----------------- 原始文本段落內容 (Data) -----------------")
        print(getattr(episode, 'data', '無內容'))
        print("================================================\n")
    except Exception as e:
        print(f"查詢失敗，可能此 UUID 不存在或 Zep 伺服器異常：\n{str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Zep Episode 查詢工具")
    parser.add_argument("uuid", help="要查詢的 Episode UUID")
    args = parser.parse_args()
    query_episode(args.uuid)

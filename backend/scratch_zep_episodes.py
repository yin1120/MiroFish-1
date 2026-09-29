import os
import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('.env')

from zep_cloud.client import AsyncZep
import asyncio

async def main():
    api_key = os.getenv('ZEP_API_KEY')
    graph_id = 'mirofish_4a97534371e74cb3'
    client = AsyncZep(api_key=api_key)
    
    try:
        resp = await client.graph.episode.get_by_graph_id(graph_id=graph_id)
        ep_list = getattr(resp, 'episodes', resp)
        print(f"Total episodes in Zep: {len(ep_list)}")
        for ep in ep_list[-15:]:
            content = getattr(ep, 'content', '') or getattr(ep, 'data', '')
            print(f"[{getattr(ep, 'created_at', '')}] Episode: {content[:150]}")
    except Exception as e:
        print("Error getting episodes:", e)

asyncio.run(main())

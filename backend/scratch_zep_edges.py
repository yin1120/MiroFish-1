import os
import sys
import json
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('.env')

from zep_cloud.client import AsyncZep
import asyncio

async def main():
    api_key = os.getenv('ZEP_API_KEY')
    graph_id = 'mirofish_4a97534371e74cb3'
    client = AsyncZep(api_key=api_key)
    
    print(f"Connecting to Zep, graph_id: {graph_id}...")
    try:
        # get all edges
        results = await client.graph.edge.get_by_graph_id(graph_id=graph_id)
        print(f"Total edges in Zep: {len(results)}")
        
        edges_ukraine = []
        for e in results:
            src = getattr(e, 'source_node_name', '') or getattr(e, 'source', '')
            tgt = getattr(e, 'target_node_name', '') or getattr(e, 'target', '')
            rel = getattr(e, 'name', '') or getattr(e, 'relation', '')
            created_at = str(getattr(e, 'created_at', ''))
            fact = getattr(e, 'fact', '')
            
            if '烏克蘭軍隊' in src or '烏克蘭軍隊' in tgt or '烏克蘭政府' in src or '烏克蘭政府' in tgt:
                edges_ukraine.append({
                    'source': src,
                    'target': tgt,
                    'relation': rel,
                    'created_at': created_at,
                    'fact': fact
                })
        print(f"\nEdges involving 烏克蘭軍隊 or 烏克蘭政府 ({len(edges_ukraine)}):")
        # sort by created_at
        edges_ukraine.sort(key=lambda x: x['created_at'])
        for item in edges_ukraine:
            print(f"  [{item['created_at']}] {item['source']} --({item['relation']})--> {item['target']} | Fact: {item['fact']}")
            
    except Exception as exc:
        print("Error querying Zep:", exc)

asyncio.run(main())

"""
圖譜實體消歧快取管理模組
提供記憶體（RAM）與磁碟（Disk）雙層快取，避免重複呼叫 LLM 進行實體消歧。
"""

import os
import json
import hashlib
from typing import Dict, Any, List, Optional
from .logger import get_logger

logger = get_logger('mirofish.disambiguation_cache')

# 記憶體快取：{graph_id: mapping} 與 {nodes_hash: mapping}
_MEMORY_CACHE_BY_GRAPH: Dict[str, Dict[str, str]] = {}
_MEMORY_CACHE_BY_HASH: Dict[str, Dict[str, str]] = {}

def _get_graphs_cache_dir() -> str:
    """取得圖譜快取目錄，若不存在則自動建立"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    uploads_dir = os.path.abspath(os.path.join(current_dir, "..", "uploads", "graphs"))
    os.makedirs(uploads_dir, exist_ok=True)
    return uploads_dir

def compute_nodes_hash(nodes: List[Dict[str, Any]]) -> str:
    """
    計算節點列表特徵 Hash，確保相同節點集合能穩定對應
    """
    try:
        simplified = sorted(
            [{"name": n.get("name", "").strip().lower(), "summary": (n.get("summary") or "")[:150]} for n in nodes],
            key=lambda x: x["name"]
        )
        nodes_str = json.dumps(simplified, ensure_ascii=False)
        return hashlib.md5(nodes_str.encode("utf-8")).hexdigest()
    except Exception as e:
        logger.warning(f"計算節點 Hash 失敗: {e}")
        return ""

def get_disambiguation_cache(graph_id: Optional[str] = None, nodes_hash: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    獲取實體消歧結果（優先讀取記憶體，次之讀取本地磁碟檔案）
    
    Args:
        graph_id: 圖譜 ID（如 mirofish_3a038287878f4d14）
        nodes_hash: 節點雜湊值
        
    Returns:
        消歧對照字典，未命中則回傳 None
    """
    # 1. 記憶體快取查詢
    if graph_id and graph_id in _MEMORY_CACHE_BY_GRAPH:
        logger.info(f"【快取命中】[記憶體-GraphID] 實體消歧快取已命中: {graph_id}")
        return _MEMORY_CACHE_BY_GRAPH[graph_id]
        
    if nodes_hash and nodes_hash in _MEMORY_CACHE_BY_HASH:
        logger.info(f"【快取命中】[記憶體-Hash] 實體消歧快取已命中: {nodes_hash[:8]}")
        return _MEMORY_CACHE_BY_HASH[nodes_hash]

    # 2. 本地磁碟快取查詢
    if graph_id:
        cache_dir = _get_graphs_cache_dir()
        file_path = os.path.join(cache_dir, f"{graph_id}_disambiguation.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    mapping = data.get("mapping", {})
                    if mapping:
                        logger.info(f"【快取命中】[磁碟檔案] 成功載入本地持久化消歧對照表: {file_path} (共 {len(mapping)} 項映射)")
                        # 回填記憶體快取
                        _MEMORY_CACHE_BY_GRAPH[graph_id] = mapping
                        if nodes_hash:
                            _MEMORY_CACHE_BY_HASH[nodes_hash] = mapping
                        return mapping
            except Exception as e:
                logger.warning(f"讀取磁碟消歧快取檔案失敗 ({file_path}): {e}")

    return None

def save_disambiguation_cache(graph_id: Optional[str], nodes_hash: Optional[str], mapping: Dict[str, str]):
    """
    儲存實體消歧結果至記憶體與本地磁碟檔案
    
    Args:
        graph_id: 圖譜 ID
        nodes_hash: 節點雜湊值
        mapping: 消歧對照字典 {被合併名: 保留名}
    """
    if not mapping:
        return

    # 1. 寫入記憶體
    if graph_id:
        _MEMORY_CACHE_BY_GRAPH[graph_id] = mapping
    if nodes_hash:
        _MEMORY_CACHE_BY_HASH[nodes_hash] = mapping

    # 2. 持久化至磁碟
    if graph_id:
        try:
            cache_dir = _get_graphs_cache_dir()
            file_path = os.path.join(cache_dir, f"{graph_id}_disambiguation.json")
            cache_content = {
                "graph_id": graph_id,
                "nodes_hash": nodes_hash or "",
                "total_mappings": len(mapping),
                "mapping": mapping
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(cache_content, f, ensure_ascii=False, indent=2)
            logger.info(f"【持久化成功】消歧對照表已寫入本地檔案: {file_path} (共 {len(mapping)} 項映射)")
        except Exception as e:
            logger.error(f"寫入磁碟消歧快取檔案失敗 ({graph_id}): {e}")

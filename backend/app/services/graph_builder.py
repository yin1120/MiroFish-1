"""
圖譜構建服務
介面2：使用Zep API構建Standalone Graph
"""

import os
import uuid
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from zep_cloud.client import Zep
from zep_cloud import EpisodeData, EntityEdgeSourceTarget

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges
from .text_processor import TextProcessor
from ..utils.locale import t, get_locale, set_locale
from ..utils.logger import get_logger

logger = get_logger('mirofish.graph_builder')

# 實體消歧快取，格式為：{nodes_hash: mapping}
_disambiguation_cache = {}

# 巨集觀地理與無關背景排除詞 (已放寬國家與地理排除，允許進行社群輿論模擬分析)
EXCLUDED_MACRO_NAMES = set()

# 基礎保底消歧字典 (防範 LLM 隨機漏判)
FALLBACK_DISAMBIGUATION_MAP = {
    "mother": "母親",
    "mom": "母親",
    "father": "父親",
    "dad": "父親",
    "grandmother": "外婆",
    "grandma": "外婆",
    "grandfather": "外公",
    "grandpa": "外公",
    "house": "外婆家",
    "cabin": "小木屋",
    "forest": "森林",
    "wood": "森林",
    "woods": "森林",
    "wolf": "大野狼",
    "hunter": "獵人",
    "little red riding hood": "小紅帽",
    "red riding hood": "小紅帽"
}


@dataclass
class GraphInfo:
    """圖譜資訊"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    圖譜構建服務
    負責呼叫Zep API構建知識圖譜
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY 未配置")
        
        self.client = Zep(api_key=self.api_key)
        self.task_manager = TaskManager()
        
        # 初始化 LLM 客戶端用於圖譜消歧去重
        from ..utils.llm_client import LLMClient
        self.llm_client = LLMClient()
        self.model_name = self.llm_client.model
    
    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 1200,
        chunk_overlap: int = 100,
        batch_size: int = 3
    ) -> str:
        """
        非同步構建圖譜
        
        Args:
            text: 輸入文字
            ontology: 本體定義（來自介面1的輸出）
            graph_name: 圖譜名稱
            chunk_size: 文字塊大小
            chunk_overlap: 塊重疊大小
            batch_size: 每批傳送的塊數量
            
        Returns:
            任務ID
        """
        # 建立任務
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            }
        )
        
        # Capture locale before spawning background thread
        current_locale = get_locale()

        # 在後臺執行緒中執行構建
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size, current_locale)
        )
        thread.daemon = True
        thread.start()
        
        return task_id
    
    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        locale: str = 'zh'
    ):
        """圖譜構建工作執行緒"""
        set_locale(locale)
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message=t('progress.startBuildingGraph')
            )
            
            # 1. 建立圖譜
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=t('progress.graphCreated', graphId=graph_id)
            )
            
            # 2. 設定本體
            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message=t('progress.ontologySet')
            )
            # 初始化分塊數（供任務結束結果讀取，固定連線模式下為0）
            total_chunks = 0
            
            # 3. 檢查是否為強制固定連線模式 [FIXED_GRAPH]
            fixed_idx = text.find("[FIXED_GRAPH]")
            if fixed_idx != -1:
                self.task_manager.update_task(
                    task_id,
                    progress=20,
                    message="啟動 [FIXED_GRAPH] 強制寫入模式..."
                )
                
                # 從 [FIXED_GRAPH] 之後開始解析
                fixed_text = text[fixed_idx:]
                lines = fixed_text.strip().split('\n')[1:] # 跳過第一行標籤
                valid_edges = []
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('#'): continue
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) >= 3:
                        valid_edges.append((parts[0], parts[1], parts[2]))
                
                total_edges = len(valid_edges)
                
                # 直接寫入 Zep 資料庫
                for i, (source, rel, target) in enumerate(valid_edges):
                    self.task_manager.update_task(
                        task_id,
                        progress=20 + int((i / total_edges) * 60) if total_edges > 0 else 80,
                        message=f"強制寫入連線: {source} -[{rel}]-> {target}"
                    )
                    
                    try:
                        self.client.graph.add_fact_triple(
                            graph_id=graph_id,
                            fact=f"{source} {rel} {target}",
                            fact_name=rel.upper().replace(' ', '_'),
                            source_node_name=source,
                            target_node_name=target
                        )
                        # 為確保 Zep 處理不過載，稍微延遲
                        time.sleep(0.5)
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning(f"Failed to add edge {source}-{rel}-{target}: {e}")
                
                self.task_manager.update_task(
                    task_id,
                    progress=80,
                    message="固定連線寫入完成"
                )
                
                # 等待 Zep 索引完成 (輪詢直到邊的數量等於寫入的數量，最長等待 30 秒)
                start_wait = time.time()
                while time.time() - start_wait < 30:
                    try:
                        temp_data = self.get_graph_data(graph_id)
                        current_edges = temp_data.get("edge_count", 0)
                        if current_edges >= total_edges:
                            break
                    except Exception:
                        pass
                    time.sleep(2)
                
            else:
                # 一般 LLM 萃取模式
                chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
                total_chunks = len(chunks)
                self.task_manager.update_task(
                    task_id,
                    progress=20,
                    message=t('progress.textSplit', count=total_chunks)
                )
                
                # 4. 分批傳送資料
                episode_uuids = self.add_text_batches(
                    graph_id, chunks, batch_size,
                    lambda msg, prog: self.task_manager.update_task(
                        task_id,
                        progress=20 + int(prog * 0.4),  # 20-60%
                        message=msg
                    )
                )
                
                # 5. 等待Zep處理完成
                self.task_manager.update_task(
                    task_id,
                    progress=60,
                    message=t('progress.waitingZepProcess')
                )
                
                self._wait_for_episodes(
                    episode_uuids,
                    lambda msg, prog: self.task_manager.update_task(
                        task_id,
                        progress=60 + int(prog * 0.3),  # 60-90%
                        message=msg
                    )
                )
            
            # 6. 同步過濾後的圖譜並獲取資訊
            self.task_manager.update_task(
                task_id,
                progress=90,
                message="正在物理清理並同步 Zep 雲端資料庫..."
            )
            self.sync_filtered_graph_to_zep(graph_id)
            
            graph_info = self._get_graph_info(graph_id)
            
            # 完成
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })
            
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)
    
    def create_graph(self, name: str) -> str:
        """建立Zep圖譜（公開方法）"""
        graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"
        
        self.client.graph.create(
            graph_id=graph_id,
            name=name,
            description="MiroFish Social Simulation Graph"
        )
        
        return graph_id
    
    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """設定圖譜本體（公開方法）"""
        import warnings
        from typing import Optional
        from pydantic import Field
        from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel
        
        # 抑制 Pydantic v2 關於 Field(default=None) 的警告
        # 這是 Zep SDK 要求的用法，警告來自動態類建立，可以安全忽略
        warnings.filterwarnings('ignore', category=UserWarning, module='pydantic')
        
        # Zep 保留名稱，不能作為屬性名
        RESERVED_NAMES = {'uuid', 'name', 'group_id', 'name_embedding', 'summary', 'created_at'}
        
        def safe_attr_name(attr_name: str) -> str:
            """將保留名稱轉換為安全名稱"""
            if attr_name.lower() in RESERVED_NAMES:
                return f"entity_{attr_name}"
            return attr_name
        
        # 動態建立實體型別
        entity_types = {}
        for entity_def in ontology.get("entity_types", []):
            name = entity_def["name"]
            description = entity_def.get("description", f"A {name} entity.")
            
            # 建立屬性字典和型別註解（Pydantic v2 需要）
            attrs = {"__doc__": description}
            annotations = {}
            
            for attr_def in entity_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])  # 使用安全名稱
                attr_desc = attr_def.get("description", attr_name)
                # Zep API 需要 Field 的 description，這是必需的
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[EntityText]  # 型別註解
            
            attrs["__annotations__"] = annotations
            
            # 動態建立類
            entity_class = type(name, (EntityModel,), attrs)
            entity_class.__doc__ = description
            entity_types[name] = entity_class
        
        # 動態建立邊型別
        edge_definitions = {}
        for edge_def in ontology.get("edge_types", []):
            name = edge_def["name"]
            description = edge_def.get("description", f"A {name} relationship.")
            
            # 建立屬性字典和型別註解
            attrs = {"__doc__": description}
            annotations = {}
            
            for attr_def in edge_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])  # 使用安全名稱
                attr_desc = attr_def.get("description", attr_name)
                # Zep API 需要 Field 的 description，這是必需的
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[str]  # 邊屬性用str型別
            
            attrs["__annotations__"] = annotations
            
            # 動態建立類
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            edge_class = type(class_name, (EdgeModel,), attrs)
            edge_class.__doc__ = description
            
            # 構建source_targets
            source_targets = []
            seen_pairs = set()
            for st in edge_def.get("source_targets", []):
                src = st.get("source", "Entity")
                tgt = st.get("target", "Entity")
                
                # 確保實體型別存在於當前定義的 entity_types 中，否則降級為 "Entity"
                if src not in entity_types and src != "Entity":
                    src = "Entity"
                if tgt not in entity_types and tgt != "Entity":
                    tgt = "Entity"
                
                pair = (src, tgt)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    source_targets.append(
                        EntityEdgeSourceTarget(
                            source=src,
                            target=tgt
                        )
                    )
            
            # Zep API 限制最多 10 個 source_targets
            if len(source_targets) > 10:
                logger.warning(f"Edge type '{name}' has {len(source_targets)} source_targets, truncating to 10")
                source_targets = source_targets[:10]
            
            if source_targets:
                edge_definitions[name] = (edge_class, source_targets)
        
        # 呼叫Zep API設定本體
        if entity_types or edge_definitions:
            self.client.graph.set_ontology(
                graph_ids=[graph_id],
                entities=entity_types if entity_types else None,
                edges=edge_definitions if edge_definitions else None,
            )
    
    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """分批新增文字到圖譜，返回所有 episode 的 uuid 列表"""
        episode_uuids = []
        total_chunks = len(chunks)
        
        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size
            
            if progress_callback:
                progress = (i + len(batch_chunks)) / total_chunks
                progress_callback(
                    t('progress.sendingBatch', current=batch_num, total=total_batches, chunks=len(batch_chunks)),
                    progress
                )
            
            # 構建episode資料
            episodes = [
                EpisodeData(data=chunk, type="text")
                for chunk in batch_chunks
            ]
            
            # 傳送到Zep
            try:
                batch_result = self.client.graph.add_batch(
                    graph_id=graph_id,
                    episodes=episodes
                )
                
                # 收集返回的 episode uuid
                if batch_result and isinstance(batch_result, list):
                    for ep in batch_result:
                        ep_uuid = getattr(ep, 'uuid_', None) or getattr(ep, 'uuid', None)
                        if ep_uuid:
                            episode_uuids.append(ep_uuid)
                
                # 避免請求過快
                time.sleep(1)
                
            except Exception as e:
                if progress_callback:
                    progress_callback(t('progress.batchFailed', batch=batch_num, error=str(e)), 0)
                raise
        
        return episode_uuids
    
    def _wait_for_episodes(
        self,
        episode_uuids: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int = 600
    ):
        """等待所有 episode 處理完成（透過查詢每個 episode 的 processed 狀態）"""
        if not episode_uuids:
            if progress_callback:
                progress_callback(t('progress.noEpisodesWait'), 1.0)
            return
        
        start_time = time.time()
        pending_episodes = set(episode_uuids)
        completed_count = 0
        total_episodes = len(episode_uuids)
        
        if progress_callback:
            progress_callback(t('progress.waitingEpisodes', count=total_episodes), 0)
        
        while pending_episodes:
            if time.time() - start_time > timeout:
                if progress_callback:
                    progress_callback(
                        t('progress.episodesTimeout', completed=completed_count, total=total_episodes),
                        completed_count / total_episodes
                    )
                break
            
            # 檢查每個 episode 的處理狀態
            for ep_uuid in list(pending_episodes):
                try:
                    episode = self.client.graph.episode.get(uuid_=ep_uuid)
                    is_processed = getattr(episode, 'processed', False)
                    
                    if is_processed:
                        pending_episodes.remove(ep_uuid)
                        completed_count += 1
                        
                except Exception as e:
                    # 忽略單個查詢錯誤，繼續
                    pass
            
            elapsed = int(time.time() - start_time)
            if progress_callback:
                progress_callback(
                    t('progress.zepProcessing', completed=completed_count, total=total_episodes, pending=len(pending_episodes), elapsed=elapsed),
                    completed_count / total_episodes if total_episodes > 0 else 0
                )
            
            if pending_episodes:
                time.sleep(3)  # 每3秒檢查一次
        
        if progress_callback:
            progress_callback(t('progress.processingComplete', completed=completed_count, total=total_episodes), 1.0)
    
    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """獲取圖譜資訊"""
        # 獲取節點（分頁）
        nodes = fetch_all_nodes(self.client, graph_id)

        # 獲取邊（分頁）
        edges = fetch_all_edges(self.client, graph_id)

        # 統計實體型別
        entity_types = set()
        for node in nodes:
            if node.labels:
                for label in node.labels:
                    if label not in ["Entity", "Node"]:
                        entity_types.add(label)

        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=list(entity_types)
        )
    
    def _resolve_graph_duplicates_with_llm(self, nodes: List[Dict[str, Any]], graph_id: Optional[str] = None) -> Dict[str, str]:
        """
        利用 LLM 智慧識別圖譜中的中英文重複、近義詞重複，回傳合併 Mapping: {被合併名: 保留名}
        優先自本地磁碟或記憶體讀取快取，避免重複呼叫。
        """
        if not nodes:
            return {}
            
        # 1. 優先查詢本地磁碟與記憶體快取
        from ..utils.disambiguation_cache import (
            compute_nodes_hash,
            get_disambiguation_cache,
            save_disambiguation_cache
        )
        
        nodes_hash = compute_nodes_hash(nodes)
        cached_mapping = get_disambiguation_cache(graph_id=graph_id, nodes_hash=nodes_hash)
        if cached_mapping:
            logger.info(f"【實體消歧】命中快取 (graph_id={graph_id})，直接使用快取結果，共 {len(cached_mapping)} 筆對照。")
            return cached_mapping
            
        try:
            logger.info(f"【實體消歧】快取未命中，呼叫 LLM 進行智慧消歧去重 (graph_id={graph_id}, 節點數={len(nodes)})...")
            
            # 準備節點清單以節省 Token，只傳入名稱和摘要
            nodes_input = [{"name": n["name"], "summary": n["summary"][:150]} for n in nodes]
            
            system_prompt = (
                "你是一個知識圖譜消歧、實體合併與翻譯優化專家。請分析輸入的節點清單，執行以下任務並返回一個 JSON 物件：\n\n"
                "1. 【中英文與同義詞消歧合併】：\n"
                "   - 找出哪些節點實際上指的是「完全同一個人物、角色、組織、物件或地點」。\n"
                "   - 必須合併中英文重複（如：'Ukraine' 與 '烏克蘭'，'Putin' 與 '普丁'，'Russian Army' 與 '俄羅斯軍隊'）及近義詞。\n"
                "   - 請在 JSON 中將【要被合併的名稱】（通常是英文或非標準中文）作為 Key，將【保留的標準中文名稱】作為 Value。\n\n"
                "2. 【孤立英文重命名】：\n"
                "   - 對於只有英文名稱且在清單中找不到中文同義詞合併的節點，請將英文名稱作為 Key，直接翻譯為合適的中文作為 Value（例如：'house' 翻譯為 '房子'，'basket' 翻譯為 '籃子'）。\n\n"
                "3. 【精細化地理、國家與設定地點過濾】：\n"
                "   - 【主線地理與衝突地點保留】：如果該國家、地區、城市、戰場、特定設施或虛構地點是故事的「主角主體」、「核心談判地」或「主要事件發生與戰事地點」（即有多個角色在該地點發生主動互動、衝突、外交行動或有重要情節摘要關聯），【絕對不要】過濾它們，請保持其標準中文原名（不要設置為空字串）。\n"
                "   - 【背景/路過地理過濾】：如果該地點僅在故事背景或人物經歷中被順帶提及一次（例如：僅提及某人曾去過某地、出生於某國、或作為非核心材料的產地），且未參與任何核心主線衝突或互動，請將其 Key 對應的 Value 設置為空字串 `\"\"`，以便系統自動過濾剔除。\n\n"
                "4. 【無關瑣碎物件與日常道具過濾】：\n"
                "   - 請找出與主線情節、角色核心互動無關的瑣碎日常用品、食物、服飾、人體器官或無關背景道具（例如僅作為環境描寫出現的麵包、衣服、杯子、眼睛、手指等）。\n"
                "   - 將這些對敘事或社會網絡輿論沒有任何推動作用的雜訊節點，其 Key 對應之 Value 設置為空字串 `\"\"`。\n\n"
                "請返回一個 JSON 物件，格式如下：\n"
                "{\n"
                '  "Ukraine": "烏克蘭",\n'
                '  "Germany": "",\n'
                '  "eye": "",\n'
                '  "bread": "",\n'
                '  "Russian Army": "俄羅斯軍隊"\n'
                "}\n"
                "必須返回有效的 JSON 格式，不要包含任何額外的解釋文字或 Markdown 標記。"
            )
            
            import json
            mapping = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"輸入節點列表：\n{json.dumps(nodes_input, ensure_ascii=False, indent=2)}"}
                ],
                temperature=0.1,
                max_tokens=2048,
                enable_thinking=False,
                max_retries=3
            )
            
            logger.info(f"LLM 實體消歧完成，共解析出 {len(mapping)} 項映射對照。")
            
            # 儲存至本地磁碟與記憶體快取
            save_disambiguation_cache(graph_id=graph_id, nodes_hash=nodes_hash, mapping=mapping)
            return mapping
            
        except Exception as e:
            logger.error(f"LLM 實體消歧失敗: {e}")
            return {}

    def get_graph_data(self, graph_id: str, resolve_duplicates: bool = True) -> Dict[str, Any]:
        """
        獲取完整圖譜資料（包含詳細資訊）
        
        Args:
            graph_id: 圖譜ID
            resolve_duplicates: 是否執行智慧消歧去重與翻譯 (默認為 True)
            
        Returns:
            包含nodes和edges的字典，包括時間資訊、屬性等詳細資料
        """
        import logging
        logger = logging.getLogger('mirofish.graph_builder')

        nodes = fetch_all_nodes(self.client, graph_id)
        edges = fetch_all_edges(self.client, graph_id)

        # 建立節點對映用於獲取節點名稱
        node_map = {}
        filtered_node_uuids = set()
        
        for node in nodes:
            name_str = node.name or ""
            if "entity" in name_str.lower():
                filtered_node_uuids.add(node.uuid_)
                continue
            node_map[node.uuid_] = name_str
        
        nodes_data = []
        for node in nodes:
            if node.uuid_ in filtered_node_uuids:
                continue
                
            # 獲取建立時間
            created_at = getattr(node, 'created_at', None)
            if created_at:
                created_at = str(created_at)
            
            # 節點來源標註
            node_attr = dict(node.attributes or {})
            node_attr["source_stage"] = "stage1_document"
            node_attr["round_label"] = "文檔初始實體"
            nodes_data.append({
                "uuid": node.uuid_,
                "name": node.name,
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node_attr,
                "source_stage": "stage1_document",
                "simulation_round": 0,
                "round_label": "文檔初始實體",
                "created_at": created_at,
            })
        
        edges_data = []
        import re
        for edge in edges:
            if edge.source_node_uuid in filtered_node_uuids or edge.target_node_uuid in filtered_node_uuids:
                continue
                
            # 獲取時間資訊
            created_at = getattr(edge, 'created_at', None)
            valid_at = getattr(edge, 'valid_at', None)
            invalid_at = getattr(edge, 'invalid_at', None)
            expired_at = getattr(edge, 'expired_at', None)
            
            # 獲取 episodes
            episodes = getattr(edge, 'episodes', None) or getattr(edge, 'episode_ids', None)
            if episodes and not isinstance(episodes, list):
                episodes = [str(episodes)]
            elif episodes:
                episodes = [str(e) for e in episodes]
            
            # 獲取 fact_type
            fact_type = getattr(edge, 'fact_type', None) or edge.name or ""
            
            # 識別關係來源階段與模擬輪次
            fact_str = edge.fact or ""
            round_match = re.search(r'(?:模擬|推演)第\s*(\d+)\s*輪', fact_str) or re.search(r'\[Round\s*(\d+)\]', fact_str)
            if round_match:
                sim_round = int(round_match.group(1))
                source_stage = "stage3_simulation"
                round_label = f"模擬第 {sim_round} 輪"
            elif edge.attributes and edge.attributes.get("simulation_round"):
                sim_round = int(edge.attributes.get("simulation_round"))
                source_stage = "stage3_simulation"
                round_label = f"模擬第 {sim_round} 輪"
            else:
                sim_round = 0
                source_stage = "stage1_document"
                round_label = "文檔初始客觀事實"

            edge_attr = dict(edge.attributes or {})
            edge_attr["source_stage"] = source_stage
            edge_attr["simulation_round"] = sim_round
            edge_attr["round_label"] = round_label

            edges_data.append({
                "uuid": edge.uuid_,
                "name": edge.name or "",
                "fact": edge.fact or "",
                "fact_type": fact_type,
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "source_node_name": node_map.get(edge.source_node_uuid, ""),
                "target_node_name": node_map.get(edge.target_node_uuid, ""),
                "attributes": edge_attr,
                "source_stage": source_stage,
                "simulation_round": sim_round,
                "round_label": round_label,
                "created_at": str(created_at) if created_at else None,
                "valid_at": str(valid_at) if valid_at else None,
                "invalid_at": str(invalid_at) if invalid_at else None,
                "expired_at": str(expired_at) if expired_at else None,
                "episodes": episodes or [],
            })

        # ==========================================
        # 1. 智慧中英文與近義詞消歧合併
        # ==========================================
        if resolve_duplicates:
            try:
                dup_mapping = self._resolve_graph_duplicates_with_llm(nodes_data, graph_id=graph_id)
            except Exception as e:
                logger.error(f"智慧消歧失敗，使用空映射: {e}")
                dup_mapping = {}
            
            # 進行保底對照表手動補全 (以防 LLM 隨機漏判)
            existing_names_lower = {n["name"].strip().lower() for n in nodes_data}
            for eng_name, chn_name in FALLBACK_DISAMBIGUATION_MAP.items():
                if eng_name in existing_names_lower:
                    # 找到原始名稱
                    orig_eng_name = next((n["name"] for n in nodes_data if n["name"].strip().lower() == eng_name), None)
                    if orig_eng_name and orig_eng_name not in dup_mapping:
                        dup_mapping[orig_eng_name] = chn_name
                        logger.info(f"【保底機制】為英文節點 {orig_eng_name} 手動補全消歧映射 -> {chn_name}")
        else:
            dup_mapping = {}
                    
        # 要剔除的節點 UUID 集合
        nodes_to_remove = set()
        
        # 【硬規則】直接過濾巨集觀國家/地理與背景節點
        for n in nodes_data:
            if n["name"].strip().lower() in EXCLUDED_MACRO_NAMES:
                nodes_to_remove.add(n["uuid"])
                logger.info(f"【硬規則】直接過濾巨集觀國家/地理節點: {n['name']}")

        if dup_mapping or nodes_to_remove:
            # 建立不區分大小寫且去除空格的名稱對映
            name_to_node = {}
            for n in nodes_data:
                normalized_name = n["name"].strip().lower()
                name_to_node[normalized_name] = n
            
            # 重新定向：被剔除的 UUID -> 保留的 UUID
            uuid_redirect = {}
            # 重新定向：被剔除的 Name -> 保留的 Name
            name_redirect = {}
            
            for remove_name, keep_name in dup_mapping.items():
                r_node = name_to_node.get(remove_name.strip().lower())
                
                # A. 過濾巨集觀地理/無關節點
                if not keep_name or keep_name.strip() == "":
                    if r_node:
                        nodes_to_remove.add(r_node["uuid"])
                        logger.info(f"過濾巨集觀/無關節點: {r_node['name']} ({r_node['uuid']})")
                    continue
                    
                k_node = name_to_node.get(keep_name.strip().lower())
                
                # B. 合併重複節點
                if r_node and k_node:
                    if r_node["uuid"] != k_node["uuid"]:
                        nodes_to_remove.add(r_node["uuid"])
                        uuid_redirect[r_node["uuid"]] = k_node["uuid"]
                        name_redirect[r_node["name"]] = k_node["name"]
                        logger.info(f"合併節點: {r_node['name']} ({r_node['uuid']}) -> {k_node['name']} ({k_node['uuid']})")
                
                # C. 英文節點翻譯重命名
                elif r_node and not k_node:
                    old_name = r_node["name"]
                    r_node["name"] = keep_name
                    # 同步將此重命名更新到 name_to_node 以供後續映射匹配
                    normalized_new_name = keep_name.strip().lower()
                    name_to_node[normalized_new_name] = r_node
                    logger.info(f"重命名英文節點: {old_name} -> {keep_name}")
            
            # 剔除 nodes_data 中重複與過濾的節點
            nodes_data = [n for n in nodes_data if n["uuid"] not in nodes_to_remove]
            
            # 更新 edges 中的關聯與名稱
            for edge in edges_data:
                # 重新定向 source
                if edge["source_node_uuid"] in uuid_redirect:
                    edge["source_node_uuid"] = uuid_redirect[edge["source_node_uuid"]]
                # 重新對齊 source 節點名稱
                source_node = next((n for n in nodes_data if n["uuid"] == edge["source_node_uuid"]), None)
                if source_node:
                    edge["source_node_name"] = source_node["name"]
                
                # 重新定向 target
                if edge["target_node_uuid"] in uuid_redirect:
                    edge["target_node_uuid"] = uuid_redirect[edge["target_node_uuid"]]
                # 重新對齊 target 節點名稱
                target_node = next((n for n in nodes_data if n["uuid"] == edge["target_node_uuid"]), None)
                if target_node:
                    edge["target_node_name"] = target_node["name"]
            
            # 邊去重
            unique_edges = []
            seen_edges = set()
            for edge in edges_data:
                edge_key = (edge["source_node_uuid"], edge["target_node_uuid"], edge["name"])
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    unique_edges.append(edge)
            edges_data = unique_edges

        # ==========================================
        # 2. 前綴與主體匹配自動補鏈 (方案 A 改良版) - 提前至過濾前執行
        # ==========================================
        from datetime import datetime
        import uuid
        parent_candidates = nodes_data
        KNOWN_SUFFIXES = {"總統", "政府", "軍隊", "外交部發言人", "外交部", "國防部", "軍", "官方", "領導人", "領導者", "總理", "軍區", "集團"}
        
        auto_edges = []
        for node_a in nodes_data:
            name_a = node_a["name"].strip()
            for node_b in parent_candidates:
                name_b = node_b["name"].strip()
                if name_a.startswith(name_b) and len(name_a) > len(name_b):
                    suffix = name_a[len(name_b):].strip()
                    if suffix in KNOWN_SUFFIXES:
                        # 檢查是否已存在這兩個節點之間的關係邊
                        edge_exists = False
                        for edge in edges_data:
                            s_uuid = edge["source_node_uuid"]
                            t_uuid = edge["target_node_uuid"]
                            edge_name = edge["name"].upper()
                            if (s_uuid == node_a["uuid"] and t_uuid == node_b["uuid"]) or \
                               (s_uuid == node_b["uuid"] and t_uuid == node_a["uuid"]):
                                if edge_name in ("AFFILIATED_WITH", "REPRESENTS"):
                                    edge_exists = True
                                    break
                        
                        if not edge_exists:
                            new_edge_uuid = f"auto_{uuid.uuid4().hex[:16]}"
                            auto_edges.append({
                                "uuid": new_edge_uuid,
                                "name": "AFFILIATED_WITH",
                                "fact": f"{name_a} 隸屬於 {name_b}",
                                "fact_type": "AFFILIATED_WITH",
                                "source_node_uuid": node_a["uuid"],
                                "target_node_uuid": node_b["uuid"],
                                "source_node_name": name_a,
                                "target_node_name": name_b,
                                "attributes": {
                                    "source_stage": "stage1_document",
                                    "simulation_round": 0,
                                    "round_label": "文檔架構推導"
                                },
                                "source_stage": "stage1_document",
                                "simulation_round": 0,
                                "round_label": "文檔架構推導",
                                "created_at": datetime.utcnow().isoformat(),
                                "valid_at": None,
                                "invalid_at": None,
                                "expired_at": None,
                                "episodes": [],
                            })
                            logger.info(f"【前綴自動補鏈】建立關係邊: {name_a} -[AFFILIATED_WITH]-> {name_b}")
        edges_data.extend(auto_edges)

        # ==========================================
        # 3. 第一輪過濾 (過濾無關雜訊，保留重要實體)
        # ==========================================
        # 重新統計剩餘每個節點的關聯邊數 (已包含自動補鏈邊)
        edge_counts = {}
        for edge in edges_data:
            s = edge["source_node_uuid"]
            t = edge["target_node_uuid"]
            edge_counts[s] = edge_counts.get(s, 0) + 1
            edge_counts[t] = edge_counts.get(t, 0) + 1
            
        final_nodes = []
        filtered_node_uuids = set()
        
        # 排除非人物/非機構節點的名稱關鍵字（強制排除）
        NON_PERSON_KEYWORDS = {
            "house", "home", "cabin", "building", "location", "place", "room", "kitchen",
            "wood", "woods", "forest", "tree", "plant", "flower", "grass", "nature",
            "item", "object", "thing", "hat", "cloak", "bread", "cake", "wine", "food",
            "basket", "road", "path", "bed", "pajamas", "nightgown",
            "小木屋", "木屋", "屋子", "外婆家", "房子", "花", "花朵", "花草", "樹", "樹木", "森林", "植物",
            "帽子", "斗篷", "紅色斗篷", "紅色帽子", "蛋糕", "葡萄酒", "麵包", "食物", "瓶子", "籃子",
            "道路", "小路", "路", "床", "睡衣", "床邊"
        }
        
        # 嚴格無條件過濾剔除的關鍵字（器官，直接排除，已放寬國家與地理限制）
        STRICT_FILTER_KEYWORDS = {
            "eye", "hand", "ear", "mouth", "nose", "face", "body", "finger", "arm", "leg", "teeth", "tooth",
            "眼睛", "手", "耳朵", "嘴巴", "牙齒", "舌頭", "鼻子", "臉", "身體", "手指", "手臂", "腿"
        }
        
        for node in nodes_data:
            node_name_lower = node["name"].strip().lower()
            
            # A. 檢查是否在嚴格過濾名單中（無條件排除）
            if node_name_lower in STRICT_FILTER_KEYWORDS or any(kw in node_name_lower for kw in STRICT_FILTER_KEYWORDS):
                filtered_node_uuids.add(node["uuid"])
                logger.info(f"無條件過濾排除節點: {node['name']}")
                continue
            
            # B. 判斷是否為無關道具/地點/植物
            is_non_person_by_name = False
            if node_name_lower in NON_PERSON_KEYWORDS or any(kw in node_name_lower for kw in ["house", "cabin", "forest", "flower", "tree", "plant", "hat", "cloak", "basket", "road", "bed", "pajamas"]):
                is_non_person_by_name = True
                
            labels = node.get("labels", [])
            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]
            
            # 只要擁有任何具體的自定義標籤（例如 Country, Location, MilitaryUnit 等），即視為重要核心主體，予以豁免首輪邊數 <= 1 過濾
            is_important_entity = len(custom_labels) > 0
            
            if is_non_person_by_name or not is_important_entity:
                count = edge_counts.get(node["uuid"], 0)
                if count <= 1:
                    # 邊數 <= 1 且非重要主體，剔除
                    filtered_node_uuids.add(node["uuid"])
                    logger.info(f"過濾圖譜低關聯節點: {node['name']} (邊數: {count})")
                    continue
                    
            final_nodes.append(node)
            
        # 同步過濾掉連接著被剔除節點的邊
        final_edges = [
            e for e in edges_data 
            if e["source_node_uuid"] not in filtered_node_uuids 
            and e["target_node_uuid"] not in filtered_node_uuids
        ]
        
        # ========== 二次過濾 (Double-pass filtering)：僅清除因關聯點被刪除而孤立（邊數 = 0）的節點 ==========
        # 1. 統計第一輪過濾後剩餘邊中，每個節點的剩餘邊數
        second_edge_counts = {}
        for edge in final_edges:
            s = edge["source_node_uuid"]
            t = edge["target_node_uuid"]
            second_edge_counts[s] = second_edge_counts.get(s, 0) + 1
            second_edge_counts[t] = second_edge_counts.get(t, 0) + 1
            
        # 2. 重新檢視 final_nodes，過濾掉度數為 0 的完全孤立點
        second_filtered_node_uuids = set()
        second_final_nodes = []
        for node in final_nodes:
            count = second_edge_counts.get(node["uuid"], 0)
            if count == 0:
                second_filtered_node_uuids.add(node["uuid"])
                logger.info(f"【二次過濾】清除因關聯點被刪除而孤立的節點: {node['name']} (剩餘邊數: {count})")
                continue
            second_final_nodes.append(node)
            
        # 3. 如果有二次過濾掉的節點，同步更新邊與節點列表
        if second_filtered_node_uuids:
            final_nodes = second_final_nodes
            final_edges = [
                e for e in final_edges
                if e["source_node_uuid"] not in second_filtered_node_uuids
                and e["target_node_uuid"] not in second_filtered_node_uuids
            ]
            
        return {
            "graph_id": graph_id,
            "nodes": final_nodes,
            "edges": final_edges,
            "node_count": len(final_nodes),
            "edge_count": len(final_edges),
        }
    
    def sync_filtered_graph_to_zep(self, graph_id: str):
        """
        將本地過濾、合併後的乾淨圖譜物理同步回 Zep 雲端資料庫。
        此版本會完美繼承所有邊的 valid_at、invalid_at 等時間戳記，確保報告時間線不遺失。
        """
        import logging
        logger = logging.getLogger('mirofish.graph_builder')
        
        print("正在更新到ZEP圖譜")
        logger.info(f"開始同步過濾後的圖譜至 Zep 雲端: {graph_id}")
        
        # 1. 取得本地過濾後的乾淨資料
        filtered_data = self.get_graph_data(graph_id, resolve_duplicates=True)
        
        # 2. 獲取 Zep 端目前的原始節點與邊
        raw_nodes = fetch_all_nodes(self.client, graph_id)
        raw_edges = fetch_all_edges(self.client, graph_id)
        
        # 建立原始邊 UUID 到原始邊物件的快速對照字典，方便讀取時間欄位
        raw_edge_map = {edge.uuid_: edge for edge in raw_edges}
        
        # 整理最終要保留的節點與邊 UUID 集合
        final_node_uuids = {n["uuid"] for n in filtered_data["nodes"]}
        final_node_names = {n["uuid"]: n["name"] for n in filtered_data["nodes"]}
        
        # 如果一條邊被重新定向（端點 UUID 改變），我們就需要在 Zep 重新建立它。
        # 此時原先那個舊 UUID 的關係邊就不應該包含在保留集合中，而是應該被刪除。
        final_edge_uuids = set()
        redirected_edge_uuids = set()
        
        for e in filtered_data["edges"]:
            orig_edge = raw_edge_map.get(e["uuid"])
            if orig_edge:
                orig_src = getattr(orig_edge, "source_node_uuid", None)
                orig_tgt = getattr(orig_edge, "target_node_uuid", None)
                # 只有當端點沒有改變時，我們才視為同一條邊保留
                if orig_src == e["source_node_uuid"] and orig_tgt == e["target_node_uuid"]:
                    final_edge_uuids.add(e["uuid"])
                else:
                    redirected_edge_uuids.add(e["uuid"])
        
        # ==========================================
        # 步驟 A：更新被重命名的節點（英文翻譯成中文）
        # ==========================================
        for node in raw_nodes:
            node_uuid = node.uuid_
            if node_uuid in final_node_names:
                new_name = final_node_names[node_uuid]
                if node.name != new_name:
                    try:
                        logger.info(f"更新 Zep 節點名稱: {node.name} -> {new_name}")
                        self.client.graph.node.update(uuid_=node_uuid, name=new_name)
                    except Exception as e:
                        logger.error(f"更新節點名稱失敗 ({node_uuid}): {e}")

        # ==========================================
        # 步驟 B：重建合併節點與重定向的邊（保留時間序與時效標籤）
        # ==========================================
        for edge in filtered_data["edges"]:
            # 判斷這條邊是否是新關係邊：
            # 1. 本地自動補鏈的邊 (auto_ 開頭)
            # 2. 原本在 Zep 端沒有對應的邊 (not in raw_edge_map)
            # 3. 它的連接端點被合併或重新定向了 (in redirected_edge_uuids)
            is_new_edge = edge["uuid"].startswith("auto_") or \
                          (edge["uuid"] not in raw_edge_map) or \
                          (edge["uuid"] in redirected_edge_uuids)
            
            if is_new_edge:
                try:
                    # 試著從原始邊獲取其時間參數，確保時間線順序
                    orig_edge = raw_edge_map.get(edge["uuid"])
                    
                    valid_at = getattr(orig_edge, 'valid_at', None) if orig_edge else edge.get("valid_at")
                    invalid_at = getattr(orig_edge, 'invalid_at', None) if orig_edge else edge.get("invalid_at")
                    expired_at = getattr(orig_edge, 'expired_at', None) if orig_edge else edge.get("expired_at")
                    created_at = getattr(orig_edge, 'created_at', None) if orig_edge else edge.get("created_at")
                    
                    # 獲取原始事實描述
                    fact_str = edge["fact"]
                    
                    # 如果原先是重定向的邊，我們需要將事實文字中的「舊實體名稱」替換成「新實體名稱」，
                    # 這樣 Zep 檢索出的 fact description 才不會殘留英文/舊名稱。
                    if orig_edge:
                        orig_src_uuid = getattr(orig_edge, "source_node_uuid", None)
                        orig_tgt_uuid = getattr(orig_edge, "target_node_uuid", None)
                        
                        orig_src_node = next((n for n in raw_nodes if getattr(n, "uuid_", None) == orig_src_uuid), None)
                        orig_tgt_node = next((n for n in raw_nodes if getattr(n, "uuid_", None) == orig_tgt_uuid), None)
                        
                        if orig_src_node and orig_src_node.name != edge["source_node_name"]:
                            fact_str = fact_str.replace(orig_src_node.name, edge["source_node_name"])
                        if orig_tgt_node and orig_tgt_node.name != edge["target_node_name"]:
                            fact_str = fact_str.replace(orig_tgt_node.name, edge["target_node_name"])
                    
                    self.client.graph.add_fact_triple(
                        graph_id=graph_id,
                        fact=fact_str,
                        fact_name=edge["name"].upper().replace(' ', '_'),
                        source_node_name=edge["source_node_name"],
                        target_node_name=edge["target_node_name"],
                        source_node_uuid=edge["source_node_uuid"], # 重定向後的源 UUID
                        target_node_uuid=edge["target_node_uuid"], # 重定向後的目標 UUID
                        valid_at=str(valid_at) if valid_at else None,
                        invalid_at=str(invalid_at) if invalid_at else None,
                        expired_at=str(expired_at) if expired_at else None,
                        created_at=str(created_at) if created_at else None
                    )
                    logger.info(f"同步建立並繼承時間屬性邊: {edge['source_node_name']} -[{edge['name']}]-> {edge['target_node_name']}")
                except Exception as e:
                    logger.error(f"同步關係邊失敗 ({edge['fact']}): {e}")

        # ==========================================
        # 步驟 C：物理刪除被過濾/無效的邊
        # ==========================================
        for edge in raw_edges:
            edge_uuid = edge.uuid_
            if edge_uuid not in final_edge_uuids:
                try:
                    logger.info(f"從 Zep 刪除無效/重複的關係邊: {edge.fact}")
                    self.client.graph.edge.delete(uuid_=edge_uuid)
                except Exception as e:
                    logger.error(f"刪除邊失敗 ({edge_uuid}): {e}")

        # ==========================================
        # 步驟 D：物理刪除被過濾/被合併的節點
        # ==========================================
        for node in raw_nodes:
            node_uuid = node.uuid_
            if node_uuid not in final_node_uuids:
                try:
                    logger.info(f"從 Zep 刪除孤立/被合併節點: {node.name}")
                    # 使用 HTTP 呼叫代替 SDK 遺失的 delete 方法
                    self._delete_node_http(node_uuid)
                except Exception as e:
                    logger.error(f"刪除節點失敗 ({node_uuid}): {e}")

        print("更新ZEP圖譜完成")
        logger.info(f"圖譜 {graph_id} 雲端同步清理與時間序保存完成！")

    def _delete_node_http(self, node_uuid: str) -> bool:
        """
        直接呼叫 Zep REST API 物理刪除節點（因 SDK 漏置了 delete 方法）
        """
        import requests
        import logging
        logger = logging.getLogger('mirofish.graph_builder')
        
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "User-Agent": "zep-cloud/3.13.0"
        }
        url = f"https://api.getzep.com/api/v2/graph/node/{node_uuid}"
        try:
            response = requests.delete(url, headers=headers, timeout=15)
            if response.status_code in (200, 204):
                return True
            else:
                logger.error(f"HTTP 刪除節點失敗 ({node_uuid}): 狀態碼 {response.status_code}, 回傳: {response.text}")
                return False
        except Exception as e:
            logger.error(f"HTTP 刪除節點異常 ({node_uuid}): {e}")
            return False

    def delete_graph(self, graph_id: str):
        """刪除圖譜"""
        self.client.graph.delete(graph_id=graph_id)


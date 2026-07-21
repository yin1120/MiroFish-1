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
    
    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
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
            
            # 6. 獲取圖譜資訊
            self.task_manager.update_task(
                task_id,
                progress=90,
                message=t('progress.fetchingGraphInfo')
            )
            
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
            for st in edge_def.get("source_targets", []):
                source_targets.append(
                    EntityEdgeSourceTarget(
                        source=st.get("source", "Entity"),
                        target=st.get("target", "Entity")
                    )
                )
            
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
    
    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        獲取完整圖譜資料（包含詳細資訊）
        
        Args:
            graph_id: 圖譜ID
            
        Returns:
            包含nodes和edges的字典，包括時間資訊、屬性等詳細資料
        """
        nodes = fetch_all_nodes(self.client, graph_id)
        edges = fetch_all_edges(self.client, graph_id)

        # 建立節點對映用於獲取節點名稱
        node_map = {}
        for node in nodes:
            node_map[node.uuid_] = node.name or ""
        
        nodes_data = []
        for node in nodes:
            # 獲取建立時間
            created_at = getattr(node, 'created_at', None)
            if created_at:
                created_at = str(created_at)
            
            nodes_data.append({
                "uuid": node.uuid_,
                "name": node.name,
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
                "created_at": created_at,
            })
        
        edges_data = []
        for edge in edges:
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
            
            edges_data.append({
                "uuid": edge.uuid_,
                "name": edge.name or "",
                "fact": edge.fact or "",
                "fact_type": fact_type,
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "source_node_name": node_map.get(edge.source_node_uuid, ""),
                "target_node_name": node_map.get(edge.target_node_uuid, ""),
                "attributes": edge.attributes or {},
                "created_at": str(created_at) if created_at else None,
                "valid_at": str(valid_at) if valid_at else None,
                "invalid_at": str(invalid_at) if invalid_at else None,
                "expired_at": str(expired_at) if expired_at else None,
                "episodes": episodes or [],
            })
        
        return {
            "graph_id": graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }
    
    def delete_graph(self, graph_id: str):
        """刪除圖譜"""
        self.client.graph.delete(graph_id=graph_id)


"""
Zep實體讀取與過濾服務
從Zep圖譜中讀取節點，篩選出符合預定義實體型別的節點
"""

import time
from typing import Dict, Any, List, Optional, Set, Callable, TypeVar
from dataclasses import dataclass, field

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges

logger = get_logger('mirofish.zep_entity_reader')

# 用於泛型返回型別
T = TypeVar('T')

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
class EntityNode:
    """實體節點資料結構"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    # 相關的邊資訊
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    # 相關的其他節點資訊
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }
    
    def get_entity_type(self) -> Optional[str]:
        """獲取實體型別（排除預設的Entity標籤）"""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """過濾後的實體集合"""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class ZepEntityReader:
    """
    Zep實體讀取與過濾服務
    
    主要功能：
    1. 從Zep圖譜讀取所有節點
    2. 篩選出符合預定義實體型別的節點（Labels不只是Entity的節點）
    3. 獲取每個實體的相關邊和關聯節點資訊
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY 未配置")
        
        self.client = Zep(api_key=self.api_key)
        
        # 初始化 LLM 客戶端用於圖譜消歧去重
        from ..utils.llm_client import LLMClient
        self.llm_client = LLMClient()
        self.model_name = self.llm_client.model
    
    def _call_with_retry(
        self, 
        func: Callable[[], T], 
        operation_name: str,
        max_retries: int = 3,
        initial_delay: float = 2.0
    ) -> T:
        """
        帶重試機制的Zep API呼叫
        
        Args:
            func: 要執行的函式（無引數的lambda或callable）
            operation_name: 操作名稱，用於日誌
            max_retries: 最大重試次數（預設3次，即最多嘗試3次）
            initial_delay: 初始延遲秒數
            
        Returns:
            API呼叫結果
        """
        last_exception = None
        delay = initial_delay
        
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Zep {operation_name} 第 {attempt + 1} 次嘗試失敗: {str(e)[:100]}, "
                        f"{delay:.1f}秒後重試..."
                    )
                    time.sleep(delay)
                    delay *= 2  # 指數退避
                else:
                    logger.error(f"Zep {operation_name} 在 {max_retries} 次嘗試後仍失敗: {str(e)}")
        
        if last_exception is not None:
            raise last_exception
        raise RuntimeError(f"Zep {operation_name} failed: max_retries={max_retries}")
    
    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        獲取圖譜的所有節點（分頁獲取）

        Args:
            graph_id: 圖譜ID

        Returns:
            節點列表
        """
        logger.info(f"獲取圖譜 {graph_id} 的所有節點...")

        nodes = fetch_all_nodes(self.client, graph_id)

        nodes_data = []
        for node in nodes:
            nodes_data.append({
                "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                "name": node.name or "",
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
            })

        logger.info(f"共獲取 {len(nodes_data)} 個節點")
        return nodes_data

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        獲取圖譜的所有邊（分頁獲取）

        Args:
            graph_id: 圖譜ID

        Returns:
            邊列表
        """
        logger.info(f"獲取圖譜 {graph_id} 的所有邊...")

        edges = fetch_all_edges(self.client, graph_id)

        edges_data = []
        for edge in edges:
            edges_data.append({
                "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                "name": edge.name or "",
                "fact": edge.fact or "",
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "attributes": edge.attributes or {},
            })

        logger.info(f"共獲取 {len(edges_data)} 條邊")
        return edges_data
    
    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """
        獲取指定節點的所有相關邊（帶重試機制）
        
        Args:
            node_uuid: 節點UUID
            
        Returns:
            邊列表
        """
        try:
            # 使用重試機制呼叫Zep API
            edges = self._call_with_retry(
                func=lambda: self.client.graph.node.get_entity_edges(node_uuid=node_uuid),
                operation_name=f"獲取節點邊(node={node_uuid[:8]}...)"
            )
            
            edges_data = []
            for edge in edges:
                edges_data.append({
                    "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "source_node_uuid": edge.source_node_uuid,
                    "target_node_uuid": edge.target_node_uuid,
                    "attributes": edge.attributes or {},
                })
            
            return edges_data
        except Exception as e:
            logger.warning(f"獲取節點 {node_uuid} 的邊失敗: {str(e)}")
            return []
            
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
                "必須返回有效的 JSON 格式，不要包含 any 額外的解釋文字或 Markdown 標記。"
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
            
    def filter_defined_entities(
        self, 
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """
        篩選出符合預定義實體型別的節點
        
        篩選邏輯：
        - 如果節點的Labels只有一個"Entity"，說明這個實體不符合我們預定義的型別，跳過
        - 如果節點的Labels包含除"Entity"和"Node"之外的標籤，說明符合預定義型別，保留
        
        Args:
            graph_id: 圖譜ID
            defined_entity_types: 預定義的實體型別列表（可選，如果提供則只保留這些型別）
            enrich_with_edges: 是否獲取每個實體的相關邊資訊
            
        Returns:
            FilteredEntities: 過濾後的實體集合
        """
        logger.info(f"開始篩選圖譜 {graph_id} 的實體...")
        
        # 獲取所有節點與邊
        all_nodes = self.get_all_nodes(graph_id)
        all_edges = self.get_all_edges(graph_id)
        
        # ==========================================
        # 1. 智慧中英文與近義詞消歧合併 (大小寫不敏感)
        # ==========================================
        try:
            dup_mapping = self._resolve_graph_duplicates_with_llm(all_nodes, graph_id=graph_id)
        except Exception as e:
            logger.error(f"智慧消歧失敗，使用空映射: {e}")
            dup_mapping = {}
        
        # 進行保底對照表手動補全 (以防 LLM 隨機漏判)
        existing_names_lower = {n["name"].strip().lower() for n in all_nodes}
        for eng_name, chn_name in FALLBACK_DISAMBIGUATION_MAP.items():
            if eng_name in existing_names_lower:
                # 找到原始名稱
                orig_eng_name = next((n["name"] for n in all_nodes if n["name"].strip().lower() == eng_name), None)
                if orig_eng_name and orig_eng_name not in dup_mapping:
                    dup_mapping[orig_eng_name] = chn_name
                    logger.info(f"【保底機制】為英文實體 {orig_eng_name} 手動補全消歧映射 -> {chn_name}")
                    
        # 要剔除的節點 UUID 集合
        nodes_to_remove = set()
        
        # 【硬規則】直接過濾巨集觀國家/地理與背景節點 (已在開頭清空 EXCLUDED_MACRO_NAMES，此處留作防禦)
        for n in all_nodes:
            if n["name"].strip().lower() in EXCLUDED_MACRO_NAMES:
                nodes_to_remove.add(n["uuid"])
                logger.info(f"【硬規則】直接過濾巨集觀國家/地理實體: {n['name']}")

        if dup_mapping or nodes_to_remove:
            # 建立不區分大小寫且去除空格的名稱對映
            name_to_node = {}
            for n in all_nodes:
                normalized_name = n["name"].strip().lower()
                name_to_node[normalized_name] = n
                
            uuid_redirect = {}
            
            for remove_name, keep_name in dup_mapping.items():
                r_node = name_to_node.get(remove_name.strip().lower())
                
                # A. 過濾巨集觀地理/無關實體
                if not keep_name or keep_name.strip() == "":
                    if r_node:
                        nodes_to_remove.add(r_node["uuid"])
                        logger.info(f"過濾巨集觀/無關實體: {r_node['name']} ({r_node['uuid']})")
                    continue
                    
                k_node = name_to_node.get(keep_name.strip().lower())
                
                # B. 合併重複實體
                if r_node and k_node:
                    if r_node["uuid"] != k_node["uuid"]:
                        nodes_to_remove.add(r_node["uuid"])
                        uuid_redirect[r_node["uuid"]] = k_node["uuid"]
                        logger.info(f"合併實體: {r_node['name']} ({r_node['uuid']}) -> {k_node['name']} ({k_node['uuid']})")
                
                # C. 英文實體翻譯重命名
                elif r_node and not k_node:
                    old_name = r_node["name"]
                    r_node["name"] = keep_name
                    # 同步將此重命名更新到 name_to_node 以供後續對照
                    normalized_new_name = keep_name.strip().lower()
                    name_to_node[normalized_new_name] = r_node
                    logger.info(f"重命名英文實體: {old_name} -> {keep_name}")
            
            # 從 nodes 列表中移除重複與過濾的實體
            all_nodes = [n for n in all_nodes if n["uuid"] not in nodes_to_remove]
            
            # 更新 edges 中的關聯並去重
            for edge in all_edges:
                if edge.get("source_node_uuid") in uuid_redirect:
                    edge["source_node_uuid"] = uuid_redirect[edge["source_node_uuid"]]
                if edge.get("target_node_uuid") in uuid_redirect:
                    edge["target_node_uuid"] = uuid_redirect[edge["target_node_uuid"]]
            
            # 邊去重
            unique_edges = []
            seen_edges = set()
            for edge in all_edges:
                edge_key = (edge.get("source_node_uuid"), edge.get("target_node_uuid"), edge.get("name"))
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    unique_edges.append(edge)
            all_edges = unique_edges

        total_count = len(all_nodes)
        node_map = {n["uuid"]: n for n in all_nodes}
        
        # 預先計算每個節點的關聯邊數
        # ==========================================
        # 2. 前綴與主體匹配自動補鏈 (方案 A 改良版) - 提前至過濾前執行
        # ==========================================
        from datetime import datetime
        import uuid
        parent_candidates = all_nodes
        KNOWN_SUFFIXES = {"總統", "政府", "軍隊", "外交部發言人", "外交部", "國防部", "軍", "官方", "領導人", "領導者", "總理", "軍區", "集團"}
        
        auto_edges = []
        for node_a in all_nodes:
            name_a = node_a["name"].strip()
            for node_b in parent_candidates:
                name_b = node_b["name"].strip()
                if name_a.startswith(name_b) and len(name_a) > len(name_b):
                    suffix = name_a[len(name_b):].strip()
                    if suffix in KNOWN_SUFFIXES:
                        # 檢查是否已存在這兩個節點之間的關係邊
                        edge_exists = False
                        for edge in all_edges:
                            s_uuid = edge.get("source_node_uuid")
                            t_uuid = edge.get("target_node_uuid")
                            edge_name = edge.get("name", "").upper()
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
                                "attributes": {},
                                "created_at": datetime.utcnow().isoformat(),
                                "valid_at": None,
                                "invalid_at": None,
                                "expired_at": None,
                                "episodes": [],
                            })
                            logger.info(f"【前綴自動補鏈】建立關係邊: {name_a} -[AFFILIATED_WITH]-> {name_b}")
        all_edges.extend(auto_edges)

        # 重新計算每個節點的關聯邊數 (已包含自動補鏈邊)
        node_edge_counts = {}
        for edge in all_edges:
            s_uuid = edge.get("source_node_uuid")
            t_uuid = edge.get("target_node_uuid")
            if s_uuid:
                node_edge_counts[s_uuid] = node_edge_counts.get(s_uuid, 0) + 1
            if t_uuid:
                node_edge_counts[t_uuid] = node_edge_counts.get(t_uuid, 0) + 1
        
        # 篩選符合條件的實體
        filtered_entities = []
        entity_types_found = set()
        
        person_org_keywords = [
            "person", "actor", "organization", "company", 
            "student", "alumni", "professor", "publicfigure", "expert", 
            "faculty", "official", "journalist", "activist", "university", 
            "governmentagency", "ngo", "mediaoutlet", "institution", "group", "community"
        ]
        
        # 排除非人物/非機構節點的名稱關鍵字（強制不作為人物/機構豁免，使其走邊數過濾）
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
        
        # 第一輪過濾：找出初步存活的節點與其 UUID 集合
        first_survived_nodes = []
        first_survived_uuids = set()
        
        for node in all_nodes:
            node_name_lower = node["name"].strip().lower()
            
            # 1. 檢查是否在嚴格過濾清單中（直接排除）
            if node_name_lower in STRICT_FILTER_KEYWORDS or any(kw in node_name_lower for kw in STRICT_FILTER_KEYWORDS):
                logger.info(f"無條件過濾無關器官/地理節點: {node['name']}")
                continue
                
            # 2. 檢查是否在非人物物品清單中
            is_non_person_by_name = False
            if node_name_lower in NON_PERSON_KEYWORDS or any(kw in node_name_lower for kw in ["house", "cabin", "forest", "flower", "tree", "plant", "hat", "cloak", "basket", "road", "bed", "pajamas"]):
                is_non_person_by_name = True
                
            labels = node.get("labels", [])
            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]
            
            # 只要擁有任何具體的自定義標籤（例如 Country, Location, MilitaryUnit 等），即視為重要核心主體，予以豁免首輪邊數 <= 1 過濾
            is_important_entity = len(custom_labels) > 0
            
            if is_non_person_by_name or not is_important_entity:
                edge_count = node_edge_counts.get(node["uuid"], 0)
                if edge_count <= 1:
                    logger.info(f"跳過低關聯非重要實體節點: {node['name']} (關聯邊數: {edge_count})")
                    continue
            
            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                # 豁免沒有 custom_labels 但度數 >= 2 的節點，使其能作為關聯節點存在
                if not matching_labels and len(custom_labels) > 0:
                    continue
            
            # 初步存活
            first_survived_nodes.append(node)
            first_survived_uuids.add(node["uuid"])

        # 第二輪過濾 (Double-pass filtering)：計算僅在存活節點間連線的有效邊
        valid_edges = [
            e for e in all_edges
            if e["source_node_uuid"] in first_survived_uuids
            and e["target_node_uuid"] in first_survived_uuids
        ]
        
        # 重新統計在有效邊中的節點出現次數
        second_edge_counts = {}
        for edge in valid_edges:
            s = edge["source_node_uuid"]
            t = edge["target_node_uuid"]
            second_edge_counts[s] = second_edge_counts.get(s, 0) + 1
            second_edge_counts[t] = second_edge_counts.get(t, 0) + 1
            
        # 篩選最終存活節點，僅過濾邊數為 0 的孤立節點
        final_survived_nodes = []
        final_survived_uuids = set()
        
        for node in first_survived_nodes:
            count = second_edge_counts.get(node["uuid"], 0)
            if count == 0:
                logger.info(f"【二次過濾】清除因關聯點被刪除而孤立的節點: {node['name']} (剩餘邊數: {count})")
                continue
                    
            final_survived_nodes.append(node)
            final_survived_uuids.add(node["uuid"])

        # 只保留與最終存活節點關聯的邊
        final_valid_edges = [
            e for e in valid_edges
            if e["source_node_uuid"] in final_survived_uuids
            and e["target_node_uuid"] in final_survived_uuids
        ]

        # 第三階段：組裝最終存活實體
        for node in final_survived_nodes:
            labels = node.get("labels", [])
            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]
            
            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                entity_type = matching_labels[0] if matching_labels else "Entity"
            else:
                entity_type = custom_labels[0] if custom_labels else "Entity"
            
            entity_types_found.add(entity_type)
            
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )
            
            if enrich_with_edges:
                related_edges = []
                related_node_uuids = set()
                
                for edge in final_valid_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])
                
                entity.related_edges = related_edges
                
                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append({
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        })
                
                entity.related_nodes = related_nodes
            
            filtered_entities.append(entity)
        
        logger.info(f"篩選完成: 總節點 {total_count}, 符合條件 {len(filtered_entities)}, "
                    f"實體型別: {entity_types_found}")
        
        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )
    
    def get_entity_with_context(
        self, 
        graph_id: str, 
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """
        獲取單個實體及其完整上下文（邊和關聯節點，帶重試機制）
        
        Args:
            graph_id: 圖譜ID
            entity_uuid: 實體UUID
            
        Returns:
            EntityNode或None
        """
        try:
            # 使用重試機制獲取節點
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=entity_uuid),
                operation_name=f"獲取節點詳情(uuid={entity_uuid[:8]}...)"
            )
            
            if not node:
                return None
            
            # 獲取節點的邊
            edges = self.get_node_edges(entity_uuid)
            
            # 獲取所有節點用於關聯查詢
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}
            
            # 處理相關邊和節點
            related_edges = []
            related_node_uuids = set()
            
            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])
            
            # 獲取關聯節點資訊
            related_nodes = []
            for related_uuid in related_node_uuids:
                if related_uuid in node_map:
                    related_node = node_map[related_uuid]
                    related_nodes.append({
                        "uuid": related_node["uuid"],
                        "name": related_node["name"],
                        "labels": related_node["labels"],
                        "summary": related_node.get("summary", ""),
                    })
            
            return EntityNode(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {},
                related_edges=related_edges,
                related_nodes=related_nodes,
            )
            
        except Exception as e:
            logger.error(f"獲取實體 {entity_uuid} 失敗: {str(e)}")
            return None
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """
        獲取指定型別的所有實體
        
        Args:
            graph_id: 圖譜ID
            entity_type: 實體型別（如 "Student", "PublicFigure" 等）
            enrich_with_edges: 是否獲取相關邊資訊
            
        Returns:
            實體列表
        """
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges
        )
        return result.entities



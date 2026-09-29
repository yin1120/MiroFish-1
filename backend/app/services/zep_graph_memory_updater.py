"""
Zep圖譜記憶更新服務
將模擬中的Agent活動動態更新到Zep圖譜中
"""

import os
import time
import threading
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from queue import Queue, Empty

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.locale import get_locale, set_locale

logger = get_logger('mirofish.zep_graph_memory_updater')


@dataclass
class AgentActivity:
    """Agent活動記錄"""
    platform: str           # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str        # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any]
    round_num: int
    timestamp: str
    
    def to_episode_text(self) -> str:
        """
        將活動轉換為可以傳送給Zep的文字描述
        
        採用自然語言描述格式，讓Zep能夠從中提取實體和關係
        不新增模擬相關的字首，避免誤導圖譜更新
        """
        # 根據不同的動作型別生成不同的描述
        action_descriptions = {
            "CREATE_POST": self._describe_create_post,
            "LIKE_POST": self._describe_like_post,
            "DISLIKE_POST": self._describe_dislike_post,
            "REPOST": self._describe_repost,
            "QUOTE_POST": self._describe_quote_post,
            "FOLLOW": self._describe_follow,
            "CREATE_COMMENT": self._describe_create_comment,
            "LIKE_COMMENT": self._describe_like_comment,
            "DISLIKE_COMMENT": self._describe_dislike_comment,
            "SEARCH_POSTS": self._describe_search,
            "SEARCH_USER": self._describe_search_user,
            "MUTE": self._describe_mute,
        }
        
        describe_func = action_descriptions.get(self.action_type, self._describe_generic)
        description = describe_func()
        
        # 返回 "【模擬第 X 輪】agent名稱於模擬推演第 X 輪中: 活動描述" 格式，使圖譜知識與 Zep 三元組天然具備明確時間輪次錨點
        r_str = f"第 {self.round_num} 輪" if hasattr(self, 'round_num') and self.round_num is not None else ""
        round_prefix = f"【模擬{r_str}】" if r_str else ""
        time_anchor = f"在社群模擬推演{r_str}中，" if r_str else ""
        return f"{round_prefix}{time_anchor}{self.agent_name}: {description}"
    
    def _describe_create_post(self) -> str:
        content = self.action_args.get("content", "")
        if content:
            return f"發表觀點表示：「{content}」。因為 {self.agent_name} 是代表其所屬主體的官方代表，此發言直接代表了其所屬國家或組織的立場。"
        return "發表了觀點"
    
    def _describe_like_post(self) -> str:
        """點贊帖子 - 包含帖子原文和作者資訊"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"點讚了{post_author}的帖子：「{post_content}」"
        elif post_content:
            return f"點讚了一條帖子：「{post_content}」"
        elif post_author:
            return f"點讚了{post_author}的一條帖子"
        return "點讚了一條帖子"
    
    def _describe_dislike_post(self) -> str:
        """踩帖子 - 包含帖子原文和作者資訊"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"踩了{post_author}的帖子：「{post_content}」"
        elif post_content:
            return f"踩了一條帖子：「{post_content}」"
        elif post_author:
            return f"踩了{post_author}的一條帖子"
        return "踩了一條帖子"
    
    def _describe_repost(self) -> str:
        """轉發帖子 - 包含原帖內容和作者資訊"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        
        if original_content and original_author:
            return f"轉發了{original_author}的帖子：「{original_content}」"
        elif original_content:
            return f"轉發了一條帖子：「{original_content}」"
        elif original_author:
            return f"轉發了{original_author}的一條帖子"
        return "轉發了一條帖子"
    
    def _describe_quote_post(self) -> str:
        """引用帖子 - 包含原帖內容、作者資訊和引用評論"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        quote_content = self.action_args.get("quote_content", "") or self.action_args.get("content", "")
        
        base = ""
        if original_content and original_author:
            base = f"引用了{original_author}的帖子「{original_content}」"
        elif original_content:
            base = f"引用了一條帖子「{original_content}」"
        elif original_author:
            base = f"引用了{original_author}的一條帖子"
        else:
            base = "引用了一條帖子"
        
        if quote_content:
            base += f"，並發表觀點表示：「{quote_content}」。因為 {self.agent_name} 是代表其所屬主體的官方代表，此觀點直接代表了其所屬國家或組織的立場。"
        return base
    
    def _describe_follow(self) -> str:
        """關注使用者 - 包含被關注使用者的名稱"""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"關注了使用者「{target_user_name}」"
        return "關注了一個使用者"
    
    def _describe_create_comment(self) -> str:
        """發表評論 - 包含評論內容和所評論的帖子資訊"""
        content = self.action_args.get("content", "")
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if content:
            if post_content and post_author:
                return f"在{post_author}的帖子「{post_content}」下發表觀點表示：「{content}」。因為 {self.agent_name} 是代表其所屬主體的官方代表，此觀點直接代表了其所屬國家或組織的立場。"
            elif post_content:
                return f"在帖子「{post_content}」下發表觀點表示：「{content}」。因為 {self.agent_name} 是代表其所屬主體的官方代表，此觀點直接代表了其所屬國家或組織的立場。"
            elif post_author:
                return f"在{post_author}的帖子下發表觀點表示：「{content}」。因為 {self.agent_name} 是代表其所屬主體的官方代表，此觀點直接代表了其所屬國家或組織的立場。"
            return f"發表觀點表示：「{content}」。因為 {self.agent_name} 是代表其所屬主體的官方代表，此觀點直接代表了其所屬國家或組織的立場。"
        return "發表了評論"
    
    def _describe_like_comment(self) -> str:
        """點贊評論 - 包含評論內容和作者資訊"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"點讚了{comment_author}的評論：「{comment_content}」"
        elif comment_content:
            return f"點讚了一條評論：「{comment_content}」"
        elif comment_author:
            return f"點讚了{comment_author}的一條評論"
        return "點讚了一條評論"
    
    def _describe_dislike_comment(self) -> str:
        """踩評論 - 包含評論內容和作者資訊"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"踩了{comment_author}的評論：「{comment_content}」"
        elif comment_content:
            return f"踩了一條評論：「{comment_content}」"
        elif comment_author:
            return f"踩了{comment_author}的一條評論"
        return "踩了一條評論"
    
    def _describe_search(self) -> str:
        """搜尋帖子 - 包含搜尋關鍵詞"""
        query = self.action_args.get("query", "") or self.action_args.get("keyword", "")
        return f"搜尋了「{query}」" if query else "進行了搜尋"
    
    def _describe_search_user(self) -> str:
        """搜尋使用者 - 包含搜尋關鍵詞"""
        query = self.action_args.get("query", "") or self.action_args.get("username", "")
        return f"搜尋了使用者「{query}」" if query else "搜尋了使用者"
    
    def _describe_mute(self) -> str:
        """遮蔽使用者 - 包含被遮蔽使用者的名稱"""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"遮蔽了使用者「{target_user_name}」"
        return "遮蔽了一個使用者"
    
    def _describe_generic(self) -> str:
        # 對於未知的動作型別，生成通用描述
        return f"執行了{self.action_type}操作"


class ZepGraphMemoryUpdater:
    """
    Zep圖譜記憶更新器
    
    監控模擬的actions日誌檔案，將新的agent活動實時更新到Zep圖譜中。
    按平臺分組，每累積BATCH_SIZE條活動後批次傳送到Zep。
    
    所有有意義的行為都會被更新到Zep，action_args中會包含完整的上下文資訊：
    - 點贊/踩的帖子原文
    - 轉發/引用的帖子原文
    - 關注/遮蔽的使用者名稱
    - 點贊/踩的評論原文
    """
    
    # 批次傳送大小（每個平臺累積多少條後傳送）
    BATCH_SIZE = 5
    
    # 平臺名稱對映（用於控制檯顯示）
    PLATFORM_DISPLAY_NAMES = {
        'twitter': '世界1',
        'reddit': '世界2',
    }
    
    # 傳送間隔（秒），避免請求過快
    SEND_INTERVAL = 0.5
    
    # 重試配置
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # 秒
    
    def __init__(self, graph_id: str, api_key: Optional[str] = None):
        """
        初始化更新器
        
        Args:
            graph_id: Zep圖譜ID
            api_key: Zep API Key（可選，預設從配置讀取）
        """
        self.graph_id = graph_id
        self.api_key = api_key or Config.ZEP_API_KEY
        
        if not self.api_key:
            raise ValueError("ZEP_API_KEY未配置")
        
        self.client = Zep(api_key=self.api_key)
        
        # 活動佇列
        self._activity_queue: Queue = Queue()
        
        # 按平臺分組的活動緩衝區（每個平臺各自累積到BATCH_SIZE後批次傳送）
        self._platform_buffers: Dict[str, List[AgentActivity]] = {
            'twitter': [],
            'reddit': [],
        }
        self._buffer_lock = threading.Lock()
        
        # 控制標誌
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        # 統計
        self._total_activities = 0  # 實際新增到佇列的活動數
        self._total_sent = 0        # 成功傳送到Zep的批次數
        self._total_items_sent = 0  # 成功傳送到Zep的活動條數
        self._failed_count = 0      # 傳送失敗的批次數
        self._skipped_count = 0     # 被過濾跳過的活動數（DO_NOTHING）
        
        logger.info(f"ZepGraphMemoryUpdater 初始化完成: graph_id={graph_id}, batch_size={self.BATCH_SIZE}")
    
    def _get_platform_display_name(self, platform: str) -> str:
        """獲取平臺的顯示名稱"""
        return self.PLATFORM_DISPLAY_NAMES.get(platform.lower(), platform)
    
    def start(self):
        """啟動後臺工作執行緒"""
        if self._running:
            return

        # Capture locale before spawning background thread
        current_locale = get_locale()

        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            args=(current_locale,),
            daemon=True,
            name=f"ZepMemoryUpdater-{self.graph_id[:8]}"
        )
        self._worker_thread.start()
        logger.info(f"ZepGraphMemoryUpdater 已啟動: graph_id={self.graph_id}")
    
    def stop(self):
        """停止後臺工作執行緒"""
        self._running = False
        
        # 傳送剩餘的活動
        self._flush_remaining()
        
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)
        
        logger.info(f"ZepGraphMemoryUpdater 已停止: graph_id={self.graph_id}, "
                   f"total_activities={self._total_activities}, "
                   f"batches_sent={self._total_sent}, "
                   f"items_sent={self._total_items_sent}, "
                   f"failed={self._failed_count}, "
                   f"skipped={self._skipped_count}")
    
    def add_activity(self, activity: AgentActivity):
        """
        新增一個agent活動到佇列
        
        所有有意義的行為都會被新增到佇列，包括：
        - CREATE_POST（發帖）
        - CREATE_COMMENT（評論）
        - QUOTE_POST（引用帖子）
        - SEARCH_POSTS（搜尋帖子）
        - SEARCH_USER（搜尋使用者）
        - LIKE_POST/DISLIKE_POST（點贊/踩帖子）
        - REPOST（轉發）
        - FOLLOW（關注）
        - MUTE（遮蔽）
        - LIKE_COMMENT/DISLIKE_COMMENT（點贊/踩評論）
        
        action_args中會包含完整的上下文資訊（如帖子原文、使用者名稱等）。
        
        Args:
            activity: Agent活動記錄
        """
        # 跳過DO_NOTHING型別的活動
        if activity.action_type == "DO_NOTHING":
            self._skipped_count += 1
            return
        
        self._activity_queue.put(activity)
        self._total_activities += 1
        logger.debug(f"新增活動到Zep佇列: {activity.agent_name} - {activity.action_type}")
    
    def add_activity_from_dict(self, data: Dict[str, Any], platform: str):
        """
        從字典資料新增活動
        
        Args:
            data: 從actions.jsonl解析的字典資料
            platform: 平臺名稱 (twitter/reddit)
        """
        # 跳過事件型別的條目
        if "event_type" in data:
            return
        
        activity = AgentActivity(
            platform=platform,
            agent_id=data.get("agent_id", 0),
            agent_name=data.get("agent_name", ""),
            action_type=data.get("action_type", ""),
            action_args=data.get("action_args", {}),
            round_num=data.get("round", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )
        
        self.add_activity(activity)
    
    def _worker_loop(self, locale: str = 'zh'):
        """後臺工作迴圈 - 按平臺批次傳送活動到Zep"""
        set_locale(locale)
        while self._running or not self._activity_queue.empty():
            try:
                # 嘗試從佇列獲取活動（超時1秒）
                try:
                    activity = self._activity_queue.get(timeout=1)
                    
                    # 將活動新增到對應平臺的緩衝區
                    platform = activity.platform.lower()
                    with self._buffer_lock:
                        if platform not in self._platform_buffers:
                            self._platform_buffers[platform] = []
                        self._platform_buffers[platform].append(activity)
                        
                        # 檢查該平臺是否達到批次大小
                        if len(self._platform_buffers[platform]) >= self.BATCH_SIZE:
                            batch = self._platform_buffers[platform][:self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[platform][self.BATCH_SIZE:]
                            # 釋放鎖後再傳送
                            self._send_batch_activities(batch, platform)
                            # 傳送間隔，避免請求過快
                            time.sleep(self.SEND_INTERVAL)
                    
                except Empty:
                    pass
                    
            except Exception as e:
                logger.error(f"工作迴圈異常: {e}")
                time.sleep(1)
    
    def _send_batch_activities(self, activities: List[AgentActivity], platform: str):
        """
        批次傳送活動到Zep圖譜（合併為一條文字）
        
        Args:
            activities: Agent活動列表
            platform: 平臺名稱
        """
        if not activities:
            return
        
        # 將多條活動合併為一條文字，用換行分隔
        episode_texts = [activity.to_episode_text() for activity in activities]
        combined_text = "\n".join(episode_texts)
        
        # 帶重試的傳送
        for attempt in range(self.MAX_RETRIES):
            try:
                self.client.graph.add(
                    graph_id=self.graph_id,
                    type="text",
                    data=combined_text
                )
                
                self._total_sent += 1
                self._total_items_sent += len(activities)
                display_name = self._get_platform_display_name(platform)
                logger.info(f"成功批次傳送 {len(activities)} 條{display_name}活動到圖譜 {self.graph_id}")
                logger.debug(f"批次內容預覽: {combined_text[:200]}...")
                return
                
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"批次傳送到Zep失敗 (嘗試 {attempt + 1}/{self.MAX_RETRIES}): {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"批次傳送到Zep失敗，已重試{self.MAX_RETRIES}次: {e}")
                    self._failed_count += 1
    
    def _flush_remaining(self):
        """傳送佇列和緩衝區中剩餘的活動"""
        # 首先處理佇列中剩餘的活動，新增到緩衝區
        while not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get_nowait()
                platform = activity.platform.lower()
                with self._buffer_lock:
                    if platform not in self._platform_buffers:
                        self._platform_buffers[platform] = []
                    self._platform_buffers[platform].append(activity)
            except Empty:
                break
        
        # 然後傳送各平臺緩衝區中剩餘的活動（即使不足BATCH_SIZE條）
        with self._buffer_lock:
            for platform, buffer in self._platform_buffers.items():
                if buffer:
                    display_name = self._get_platform_display_name(platform)
                    logger.info(f"傳送{display_name}平臺剩餘的 {len(buffer)} 條活動")
                    self._send_batch_activities(buffer, platform)
            # 清空所有緩衝區
            for platform in self._platform_buffers:
                self._platform_buffers[platform] = []
    
    def get_stats(self) -> Dict[str, Any]:
        """獲取統計資訊"""
        with self._buffer_lock:
            buffer_sizes = {p: len(b) for p, b in self._platform_buffers.items()}
        
        return {
            "graph_id": self.graph_id,
            "batch_size": self.BATCH_SIZE,
            "total_activities": self._total_activities,  # 新增到佇列的活動總數
            "batches_sent": self._total_sent,            # 成功傳送的批次數
            "items_sent": self._total_items_sent,        # 成功傳送的活動條數
            "failed_count": self._failed_count,          # 傳送失敗的批次數
            "skipped_count": self._skipped_count,        # 被過濾跳過的活動數（DO_NOTHING）
            "queue_size": self._activity_queue.qsize(),
            "buffer_sizes": buffer_sizes,                # 各平臺緩衝區大小
            "running": self._running,
        }


class ZepGraphMemoryManager:
    """
    管理多個模擬的Zep圖譜記憶更新器
    
    每個模擬可以有自己的更新器例項
    """
    
    _updaters: Dict[str, ZepGraphMemoryUpdater] = {}
    _lock = threading.Lock()
    
    @classmethod
    def create_updater(cls, simulation_id: str, graph_id: str) -> ZepGraphMemoryUpdater:
        """
        為模擬建立圖譜記憶更新器
        
        Args:
            simulation_id: 模擬ID
            graph_id: Zep圖譜ID
            
        Returns:
            ZepGraphMemoryUpdater例項
        """
        with cls._lock:
            # 如果已存在，先停止舊的
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
            
            updater = ZepGraphMemoryUpdater(graph_id)
            updater.start()
            cls._updaters[simulation_id] = updater
            
            logger.info(f"建立圖譜記憶更新器: simulation_id={simulation_id}, graph_id={graph_id}")
            return updater
    
    @classmethod
    def get_updater(cls, simulation_id: str) -> Optional[ZepGraphMemoryUpdater]:
        """獲取模擬的更新器"""
        return cls._updaters.get(simulation_id)
    
    @classmethod
    def stop_updater(cls, simulation_id: str):
        """停止並移除模擬的更新器"""
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
                del cls._updaters[simulation_id]
                logger.info(f"已停止圖譜記憶更新器: simulation_id={simulation_id}")
    
    # 防止 stop_all 重複呼叫的標誌
    _stop_all_done = False
    
    @classmethod
    def stop_all(cls):
        """停止所有更新器"""
        # 防止重複呼叫
        if cls._stop_all_done:
            return
        cls._stop_all_done = True
        
        with cls._lock:
            if cls._updaters:
                for simulation_id, updater in list(cls._updaters.items()):
                    try:
                        updater.stop()
                    except Exception as e:
                        logger.error(f"停止更新器失敗: simulation_id={simulation_id}, error={e}")
                cls._updaters.clear()
            logger.info("已停止所有圖譜記憶更新器")
    
    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        """獲取所有更新器的統計資訊"""
        return {
            sim_id: updater.get_stats() 
            for sim_id, updater in cls._updaters.items()
        }

"""
排程事件處理模組 (Scheduled Events Handler)
用於 OASIS 社群模擬中的劇本排程事件注入

功能特性:
1. 指定 Agent 行為 (Targeted Action): 指定 Agent 於特定輪次發布特定內容
2. 全域突發新聞 (Global Breaking News): 支援自訂發布角色名稱，並建立全網關注 (All-User Follow) 關聯，保證 100% 進入所有 Agent 的 Observation
3. 動作日誌元資料增強 (is_scheduled, description, event_type)
"""

import os
import json
import sqlite3
from typing import Dict, Any, List, Optional, Tuple

try:
    from oasis import ActionType, ManualAction
except ImportError:
    pass


def get_scheduled_events_for_round(
    config: Dict[str, Any],
    current_round: int,
    platform: str
) -> List[Dict[str, Any]]:
    """
    獲取指定輪次且匹配平台的排程事件清單
    
    Args:
        config: 模擬配置 (simulation_config.json)
        current_round: 當前輪次 (1-indexed)
        platform: 平台名稱 ("twitter" 或 "reddit")
        
    Returns:
        匹配的事件列表
    """
    event_config = config.get("event_config", {})
    all_events = event_config.get("scheduled_events", [])
    matching = []
    
    for evt in all_events:
        round_num = evt.get("round_num")
        try:
            round_num = int(round_num)
        except (ValueError, TypeError):
            continue
            
        if round_num == current_round:
            evt_platform = evt.get("platform", "all")
            if evt_platform in [platform, "all"]:
                matching.append(evt)
                
    return matching


def prepare_scheduled_actions(
    env,
    scheduled_events: List[Dict[str, Any]],
    db_path: str,
    agent_names: Dict[int, str],
    platform: str,
    log_func=print
) -> Tuple[Dict[Any, Any], Dict[int, Dict[str, Any]]]:
    """
    準備排程動作字典與元數據
    
    Args:
        env: OASIS 環境物件
        scheduled_events: 當前輪次要執行的排程事件清單
        db_path: 模擬 SQLite 資料庫路徑
        agent_names: agent_id -> agent_name 字典
        platform: 平台名稱
        log_func: 日誌輸出函式
        
    Returns:
        (manual_actions, scheduled_meta)
        - manual_actions: {agent_obj: ManualAction(...)}
        - scheduled_meta: {agent_id: {"is_scheduled": True, "description": ..., ...}}
    """
    manual_actions = {}
    scheduled_meta = {}
    
    if not scheduled_events:
        return manual_actions, scheduled_meta
        
    for evt in scheduled_events:
        event_type = evt.get("event_type", "targeted_action")
        content = evt.get("content", "").strip()
        description = evt.get("description", "")
        custom_author_name = evt.get("custom_author_name", "").strip()
        
        if not content:
            continue
            
        target_agent_id = evt.get("agent_id")
        try:
            target_agent_id = int(target_agent_id) if target_agent_id is not None else 0
        except (ValueError, TypeError):
            target_agent_id = 0
            
        # 獲取 Agent 物件
        agent = None
        try:
            if hasattr(env.agent_graph, "get_agent"):
                agent = env.agent_graph.get_agent(target_agent_id)
            elif isinstance(env.agent_graph, dict):
                agent = env.agent_graph.get(target_agent_id)
        except Exception:
            pass
            
        if agent is None:
            # 如果找不到該 ID 的 agent，回退至第一個可用的 agent
            try:
                if hasattr(env.agent_graph, "get_agents"):
                    agents_list = list(env.agent_graph.get_agents())
                    if agents_list:
                        target_agent_id, agent = agents_list[0]
                elif isinstance(env.agent_graph, dict) and env.agent_graph:
                    target_agent_id = next(iter(env.agent_graph))
                    agent = env.agent_graph[target_agent_id]
                else:
                    log_func(f"  警告: 無法獲取任何 Agent 執行排程事件")
                    continue
            except Exception as e:
                log_func(f"  警告: 獲取 Agent 失敗: {e}")
                continue

                
        actual_agent_id = target_agent_id
        
        # 處理自訂角色名稱
        if custom_author_name:
            agent_names[actual_agent_id] = custom_author_name
            _update_db_user_name(db_path, actual_agent_id, custom_author_name)
            
        # 全域突發新聞 或 自訂發布者：建立全網關注關聯，保證 100% 進入所有人的 Observation
        if event_type == "breaking_news" or custom_author_name:
            _ensure_global_broadcast_follow(db_path, actual_agent_id, log_func)
            
        # 建立 ManualAction (跳過 LLM 直接由環境發布貼文)
        manual_action = ManualAction(
            action_type=ActionType.CREATE_POST,
            action_args={"content": content}
        )
        
        manual_actions[agent] = manual_action
        scheduled_meta[actual_agent_id] = {
            "is_scheduled": True,
            "description": description,
            "event_type": event_type,
            "custom_author_name": custom_author_name or agent_names.get(actual_agent_id, f"Agent_{actual_agent_id}")
        }
        
        display_name = custom_author_name or agent_names.get(actual_agent_id, f"Agent_{actual_agent_id}")
        
        # 1. 方案 A：合成思維對話注入 (Synthetic Thought-Action Injection)
        try:
            from camel.messages import BaseMessage
            from camel.types import OpenAIBackendRole
            user_turn_prompt = (
                f"【重大戰略局勢 / 劇本決策指令】：\n"
                f"身為 {display_name}，當前國際與社群局勢發生重大變革（事件備註：{description or '官方重大立場轉折'}）。\n"
                f"最高決策層已正式下達指令，你必須立即就你的全新外交與戰略方針發布公開宣告，請做出決策並執行公開貼文。"
            )
            thought_data = {
                "thought": f"因應國際局勢劇變與核心戰略調整，我決定正式對外發布重大立場聲明：「{content}」。此宣告代表官方最新指引，往後所有言行必須嚴格維持一致。",
                "action_name": "create_post",
                "args": {"content": content}
            }
            user_msg = BaseMessage.make_user_message(role_name="User", content=user_turn_prompt)
            assistant_msg = BaseMessage.make_assistant_message(role_name="Assistant", content=json.dumps(thought_data, ensure_ascii=False))
            
            if hasattr(agent, 'update_memory'):
                agent.update_memory(user_msg, OpenAIBackendRole.USER)
                agent.update_memory(assistant_msg, OpenAIBackendRole.ASSISTANT)
                log_func(f"  [方案A記憶注入成功] 已為 {display_name} (Agent {actual_agent_id}) 寫入具備 Assistant 思考歷程的對話記憶")
        except Exception as e:
            log_func(f"  [方案A記憶注入警告] 無法寫入 ChatAgent Memory: {e}")

        # 2. 人設動態徹底覆寫 (Dynamic Persona Complete Purge & Overwrite)
        try:
            new_user_profile = (
                f"【官方最高核心立場與國家戰略方針（不可推翻）】：\n"
                f"身為 {display_name}，你的最高外交與軍事政策已發生決定性轉變——「{content}」"
                f"（重大背景：{description or '官方政策重大轉折'}）。\n"
                f"你在此前推演中的所有舊立場（包括任何舊有盟友關係、軍援承諾或歷史政策）已全部廢除並無效！\n"
                f"【行為與發言強制約束】：你的發言風格代表官方最高機構，正式、嚴肅且堅定不移。在後續推演的所有輪次中，"
                f"無論在社群上看到任何言論、爭辯或盟友質疑，你本人的所有發布、按讚、評論、轉發等一切行為，"
                f"都必須 100% 嚴格維護並推進此一全新立場，嚴禁自相矛盾或支持違背該方針的任何言論！"
            )

            # A. 徹底更新 user_info 內的 profile，清除舊立場文本
            if hasattr(agent, 'user_info') and agent.user_info:
                if not isinstance(agent.user_info.profile, dict):
                    agent.user_info.profile = {"other_info": {}}
                if "other_info" not in agent.user_info.profile or not isinstance(agent.user_info.profile["other_info"], dict):
                    agent.user_info.profile["other_info"] = {}
                agent.user_info.profile["other_info"]["user_profile"] = new_user_profile
                
                # B. 呼叫 user_info 原生方法重新編譯整個 system_message_content
                if hasattr(agent.user_info, 'to_system_message'):
                    new_system_content = agent.user_info.to_system_message()
                    if hasattr(agent, 'system_message') and agent.system_message:
                        agent.system_message.content = new_system_content
                        log_func(f"  [人設動態徹底覆寫成功] 已完全重置並剔除 {display_name} 的舊人設文本，替換為最新官方最高方針")
            elif hasattr(agent, 'system_message') and agent.system_message:
                agent.system_message.content = f"# OBJECTIVE\nYou are {display_name}.\n\n# SELF-DESCRIPTION\n{new_user_profile}\n\n# RESPONSE METHOD\nPlease perform actions by tool calling."
                log_func(f"  [人設動態徹底覆寫成功] 已重置 {display_name} 的 System Message 核心人設")
            
            # 同步更新 CAMEL memory 中的 system record，避免殘留舊紀錄造成雙重 System Message
            final_sys_content = agent.system_message.content if hasattr(agent, 'system_message') and agent.system_message else new_user_profile
            if hasattr(agent, 'memory') and hasattr(agent.memory, '_chat_history_block'):
                block = agent.memory._chat_history_block
                if hasattr(block, 'storage') and hasattr(block.storage, 'memory_list'):
                    for rec in block.storage.memory_list:
                        if isinstance(rec, dict) and rec.get('role_at_backend') == 'system':
                            if 'message' in rec and isinstance(rec['message'], dict):
                                rec['message']['content'] = final_sys_content
                
            # C. 資料庫 Bio 直接以最新最高方針為首要內容覆寫
            _update_db_user_bio(db_path, actual_agent_id, f"【官方最高方針】: {description or content[:40]}")
        except Exception as e:
            log_func(f"  [人設動態覆寫警告] 失敗: {e}")

        log_func(f"  [劇本排程觸發] {display_name} (Agent {actual_agent_id}): {content[:45]}... (備註: {description})")
        
    # 確保所有 agent 物件皆持有 db_path 屬性，供 Self-Action Memory 檢索
    if hasattr(env, 'agent_graph') and hasattr(env.agent_graph, 'agents'):
        for ag in env.agent_graph.agents.values():
            ag.db_path = db_path

    return manual_actions, scheduled_meta


def _update_db_user_bio(db_path: str, agent_id: int, new_bio: str):
    """更新資料庫中指定 agent 的 bio 資訊為最新方針"""
    if not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(user)")
        columns = [row[1] for row in cursor.fetchall()]
        if "bio" in columns:
            id_col = "agent_id" if "agent_id" in columns else "user_id"
            cursor.execute(f"UPDATE user SET bio = ? WHERE {id_col} = ?", (new_bio, agent_id))
            conn.commit()
        conn.close()
    except Exception:
        pass


def _update_db_user_name(db_path: str, agent_id: int, new_name: str):
    """更新資料庫中指定 agent 的姓名與使用者名稱"""
    if not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(user)")
        columns = [row[1] for row in cursor.fetchall()]
        if "agent_id" in columns:
            cursor.execute("""
                UPDATE user SET name = ?, user_name = ? WHERE agent_id = ? OR user_id = ?
            """, (new_name, new_name, agent_id, agent_id))
        else:
            cursor.execute("""
                UPDATE user SET name = ?, user_name = ? WHERE user_id = ?
            """, (new_name, new_name, agent_id))
        conn.commit()
        conn.close()
    except Exception:
        pass


def _ensure_global_broadcast_follow(db_path: str, poster_agent_id: int, log_func=print):
    """
    確保資料庫中所有其他活躍使用者都 follow 這個發布者
    使 OASIS 在查詢 Following 貼文時，此貼文 100% 進入所有人的 Observation
    """
    if not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(user)")
        columns = [row[1] for row in cursor.fetchall()]
        if "agent_id" in columns:
            cursor.execute("SELECT user_id FROM user WHERE agent_id = ? OR user_id = ?", (poster_agent_id, poster_agent_id))
        else:
            cursor.execute("SELECT user_id FROM user WHERE user_id = ?", (poster_agent_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return
            
        poster_user_id = row[0]
        cursor.execute("SELECT user_id FROM user WHERE user_id != ?", (poster_user_id,))
        other_user_ids = [r[0] for r in cursor.fetchall()]
        
        for uid in other_user_ids:
            cursor.execute("""
                INSERT OR IGNORE INTO follow (follower_id, followee_id, created_at)
                VALUES (?, ?, datetime('now'))
            """, (uid, poster_user_id))
            
        if "num_followers" in columns:
            cursor.execute("UPDATE user SET num_followers = ? WHERE user_id = ?", (len(other_user_ids), poster_user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        log_func(f"  建立全網關注關聯失敗: {e}")


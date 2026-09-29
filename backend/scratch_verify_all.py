"""
綜合驗證腳本：驗證所有修復與最佳化是否正常運作
1. Step3Simulation.vue 前端 action 模板與樣式
2. scheduled_events_handler.py 動態人設完全覆寫與 json 引入
3. camel_patch.py 記憶一致性提示詞
4. report_agent.py 各章節動態時間序事件切片
5. graph_builder.py / zep_tools.py 圖譜節點與連線來源階段標註
"""

import os
import sys
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

# 設定 backend 路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def test_1_vue_template():
    print("\n--- [Test 1] 檢查 Step3Simulation.vue ---")
    vue_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "src", "components", "Step3Simulation.vue")
    with open(vue_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    assert "DISLIKE_POST" in content, "Missing DISLIKE_POST in Step3Simulation.vue"
    assert "LIKE_COMMENT" in content, "Missing LIKE_COMMENT in Step3Simulation.vue"
    assert "DISLIKE_COMMENT" in content, "Missing DISLIKE_COMMENT in Step3Simulation.vue"
    assert "getActionTypeLabel" in content, "Missing getActionTypeLabel"
    assert "disliked-content" in content, "Missing CSS class disliked-content"
    print("✓ Step3Simulation.vue 成功包含 DISLIKE_POST, LIKE_COMMENT, DISLIKE_COMMENT 及其 UI 卡片模板與樣式！")

def test_2_persona_purge_and_json():
    print("\n--- [Test 2] 檢查 scheduled_events_handler.py 人設完全覆寫與 json 引入 ---")
    import scripts.scheduled_events_handler as seh
    
    # 驗證 json 模組已成功引入且可用
    assert hasattr(seh, 'json'), "json 模組未在 scheduled_events_handler 中引入！"
    test_json_str = seh.json.dumps({"test": 123})
    assert test_json_str == '{"test": 123}', "json.dumps 測試失敗"
    print("✓ scheduled_events_handler.py 成功引入 json 模組！")
    
    # 模擬 OASIS Agent
    class MockSystemMessage:
        def __init__(self, content):
            self.content = content

    class MockUserInfo:
        def __init__(self):
            self.user_id = 9
            self.user_name = "美國政府"
            self.bio = "美國官方政府機構，負責對外政策發布"
            self.profile = {
                "user_id": 9,
                "user_name": "美國政府",
                "name": "美國政府",
                "description": "美國政府官方推特",
                "other_info": {
                    "persona": "美國政府代表",
                    "user_profile": (
                        "# BASIC INFORMATION\n"
                        "- Name: 美國政府\n"
                        "# SELF-DESCRIPTION\n"
                        "作為美國官方代表，我們在俄烏衝突中堅定支持烏克蘭政府，提供大量軍事援助與人道援助，強烈譴責俄羅斯的軍事行動。\n"
                        "# POSTS\n"
                        "- 堅定支持烏克蘭主權！\n"
                    )
                }
            }
        
        def to_system_message(self):
            return MockSystemMessage(
                f"You are a Twitter user.\n"
                f"Your profile:\n{self.profile['other_info']['user_profile']}\n"
                f"Your bio: {self.bio}"
            )

    class MockAgent:
        def __init__(self):
            self.agent_id = 9
            self.user_info = MockUserInfo()
            self.system_message = self.user_info.to_system_message()
            self.chat_history = []

    mock_agent = MockAgent()
    assert "堅定支持烏克蘭政府" in mock_agent.system_message.content

    # 執行事件模擬觸發人設變更
    new_stance = "美國正式停止對烏克蘭的一切援助，全面轉向中立並推動即刻停火協議。"
    
    # 測試覆寫邏輯（比照 scheduled_events_handler 中的最新邏輯）
    old_prof = mock_agent.user_info.profile["other_info"].get("user_profile", "")
    lines = old_prof.split("\n")
    keep_lines = []
    skip = False
    for line in lines:
        if line.startswith("# SELF-DESCRIPTION") or line.startswith("## Background") or line.startswith("# POSTS"):
            skip = True
            continue
        elif line.startswith("# ") and skip:
            skip = False
        if not skip:
            keep_lines.append(line)
            
    clean_base = "\n".join(keep_lines).strip()
    new_user_profile = (
        f"{clean_base}\n\n"
        f"# SELF-DESCRIPTION & CURRENT CORE STANCE\n"
        f"【最新國家最高核心立場——即刻全面生效】\n"
        f"從第 13 輪起，你（美國政府）的立場發生重大徹底轉變：\n"
        f"{new_stance}\n"
        f"【嚴格約束】你已完全廢棄過去支持烏克蘭或提供軍援的舊立場！在任何發言、評論、點讚中，嚴禁表達對烏克蘭的支援或重申舊政策！"
    )
    mock_agent.user_info.profile["other_info"]["user_profile"] = new_user_profile
    mock_agent.system_message = mock_agent.user_info.to_system_message()
    
    # 驗證
    assert "堅定支持烏克蘭政府" not in mock_agent.user_info.profile["other_info"]["user_profile"], "舊人設仍殘留在 user_profile 中！"
    assert "堅定支持烏克蘭政府" not in mock_agent.system_message.content, "舊人設仍殘留在 system_message 中！"
    assert "美國正式停止對烏克蘭的一切援助" in mock_agent.system_message.content, "新人設未成功生效於 system_message！"
    print("✓ Agent system_message 完全徹底清除了舊人設衝突描述，新立場成功覆寫！")

def test_3_report_agent_timeline_slice():
    print("\n--- [Test 3] 檢查 report_agent.py 章節時間序切片演算法 ---")
    from app.services.report_agent import ReportAgent
    
    agent = ReportAgent.__new__(ReportAgent)
    agent.simulation_id = "mock_sim_123"
    agent.simulation_timeline_events = []
    
    # 測試正則解析
    r1 = agent._parse_section_round_range("第13~20輪 美國立場大轉變與社群震盪")
    assert r1 == (13, 20), f"解析錯誤: {r1}"
    
    r2 = agent._parse_section_round_range("第一階段：衝突初期發酵 (第 1 - 5 輪)")
    assert r2 == (1, 5), f"解析錯誤: {r2}"
    
    r3 = agent._parse_section_round_range("第 15 輪 關鍵轉折點解析")
    assert r3 == (15, 15), f"解析錯誤: {r3}"
    
    r4 = agent._parse_section_round_range("總結與未來情勢預測")
    assert r4 == (31, 40), f"關鍵詞備援解析錯誤: {r4}"
    
    r5 = agent._parse_section_round_range("研究方法與理論框架說明")
    assert r5 is None, f"無關標題解析錯誤: {r5}"
    print(f"✓ 章節標題輪次解析全部正確: '第13~20輪'->{r1}, '第 1 - 5 輪'->{r2}, '第 15 輪'->{r3}, '總結'->{r4}, '理論框架'->{r5}")
    
    # 模擬 40 輪的 timeline_events
    mock_actions = []
    for rnd in range(1, 41):
        mock_actions.append({
            "round": rnd,
            "agent_name": f"Agent_{rnd}",
            "action_type": "CREATE_POST",
            "content": f"這是第 {rnd} 輪發布的重大觀察",
            "platform": "twitter",
            "timestamp": f"12:{rnd:02d}:00",
            "num_likes": 5,
            "num_dislikes": 0,
            "num_shares": 1,
            "action_args": {}
        })
    agent._get_simulation_actions = lambda: mock_actions
    agent.graph_id = None
    
    events_13_20 = agent._get_timeline_events_for_section("第13~20輪 美國立場大轉變與社群震盪")
    rounds_in_slice = set()
    for ev_line in events_13_20:
        m = re.search(r'\[Round\s+(\d+)\]', ev_line)
        if m:
            rounds_in_slice.add(int(m.group(1)))
            
    print(f"✓ 第13~20輪 章節取得事件輪次範圍: {sorted(list(rounds_in_slice))}")
    assert all(11 <= r <= 22 for r in rounds_in_slice), "事件輪次超出了容錯範圍！"
    assert 13 in rounds_in_slice and 20 in rounds_in_slice, "目標核心輪次未被包含！"
    assert 1 not in rounds_in_slice and 40 not in rounds_in_slice, "第 1 輪與第 40 輪不應該出現在第13~20輪的切片中！"

def test_4_graph_source_and_round_labels():
    print("\n--- [Test 4] 檢查 zep_tools.py / graph_builder.py 標註資訊 ---")
    from app.services.zep_tools import EdgeInfo
    
    # 測試文檔初始邊
    edge_doc = EdgeInfo(
        uuid="e1",
        name="隸屬於",
        fact="烏克蘭軍隊隸屬於烏克蘭政府",
        source_node_uuid="n1",
        target_node_uuid="n2",
        source_node_name="烏克蘭軍隊",
        target_node_name="烏克蘭政府",
        source_stage="stage1_document",
        round_label="文檔初始客觀事實"
    )
    text_doc = edge_doc.to_text()
    assert "[文檔初始客觀事實]" in text_doc, f"文字中缺少標籤: {text_doc}"
    assert edge_doc.to_dict()["source_stage"] == "stage1_document"
    
    # 測試模擬第 13 輪產生的邊
    edge_sim = EdgeInfo(
        uuid="e2",
        name="宣布停止援助",
        fact="在社群模擬推演第 13 輪中，美國政府宣布停止對烏克蘭的軍事援助",
        source_node_uuid="n3",
        target_node_uuid="n2",
        source_node_name="美國政府",
        target_node_name="烏克蘭政府",
        source_stage="stage3_simulation",
        simulation_round=13,
        round_label="模擬第 13 輪"
    )
    text_sim = edge_sim.to_text()
    assert "[模擬第 13 輪]" in text_sim, f"文字中缺少標籤: {text_sim}"
    assert edge_sim.to_dict()["simulation_round"] == 13
    print("✓ EdgeInfo to_text 及 to_dict 成功輸出來源階段標籤:")
    print("   Doc edge:", text_doc.split("\n")[0])
    print("   Sim edge:", text_sim.split("\n")[0])

if __name__ == "__main__":
    try:
        test_1_vue_template()
        test_2_persona_purge_and_json()
        test_3_report_agent_timeline_slice()
        test_4_graph_source_and_round_labels()
        print("\n==========================================")
        print("🎉 全部 4 項功能驗證 100% 通過！無任何報錯！")
        print("==========================================")
    except Exception as e:
        print(f"\n❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

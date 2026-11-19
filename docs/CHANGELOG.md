# 通用劇本殺／桌遊多智能體模擬系統 — 討論決策、規格演進與程式碼變更紀錄 (CHANGELOG)

本文件用於完整追蹤專案從「架構與流程討論」、「規格書 ([`docs/FRD.md`](file:///c:/Users/user/MiroFish/docs/FRD.md) & [`docs/ARCHITECTURE.md`](file:///c:/Users/user/MiroFish/docs/ARCHITECTURE.md)) 修訂」到後續「後端 Python 與前端 React 程式碼實作更動」的所有歷史紀錄。

---

## 一、 核心架構討論與設計決策紀錄 (Design Discussions & Decisions)

### 1. 劇本結構規格、圖譜零污染與 `other` 擴充槽
- **討論議題**：如何確保單一劇本檔案 (`script.md`) 既能被確定性解析，又能支援未知特殊規則，且不讓秘密、真相或玩家個性污染 Zep 客觀知識圖譜（KG）？
- **拍板決策**：
  1. **三大板塊固定結構**：劇本嚴格分為 `(A) 關主部分`、`(B) 公開角色劇本`、`(C) 角色劇本秘密部分`，並於三大板塊各自增設 `other` 自定義擴充欄位，容納特殊機制與特例。
  2. **圖譜白名單與黑名單物理隔離**：
     - *白名單（允許入圖）*：僅限 `(A) 規模`、`(A) 故事 ➔ world_view`、`(B) 公開角色劇本`（`persona_and_intro`、`storyline`、`public_items_and_tasks`、`other`）。
     - *黑名單（嚴禁入圖）*：`(B) player_personality`（匯入即以 Regex 剝離）、`(C) 角色秘密部分` 全塊、`(A) 未解鎖線索與核心真相`、以及所有影響流程與題庫之規則條文。
     - *推演期間動態隔離*：僅 `visibility == 'public'` 的公開看板貼文可回寫 Zep 圖譜；私人看板、多人私聊、`GM_ONLY` 看板與心智筆記一律物理攔截。

---

### 2. 角色雙層鎖定與「手動輸入優先 ➔ AI 彌補完整」玩家個性生成
- **討論議題**：原生 [`oasis_profile_generator.py`](file:///c:/Users/user/MiroFish/backend/app/services/oasis_profile_generator.py) 會用 AI 腦補角色年齡、職業與背景，導致純編號角色（如「1號玩家」）或劇本原始設定被竄改；同時操控角色的「玩家遊玩個性」該放哪裡、如何決定？
- **拍板決策**：
  1. **第一層（角色劇本固定層 `immutable_role_canon`）**：100% 鎖死劇本 `(B)` 原文，強制繞過 AI 擴寫人設管線，零改寫。
  2. **第二層（玩家遊玩個性層 `player_playstyle`）**：於劇本 `(B) 公開角色劇本` 增設專屬欄位 `player_personality`（匯入時即刻抽取剝離，不進圖譜）。
  3. **生成順序**：採**「手動輸入優先 ➔ AI 彌補完整」**——先讀取劇本手動填寫的個性種子，再由 AI 針對簡略描述或留白角色補齊 5 大量化維度（勝負欲、誠實度、社交支配力、私聊熱情、邏輯細緻度），實現整桌打法生態平衡，統一存入 SQLite `player_meta_personas` 表。

---

### 3. LLM「功能與屬性聯合判斷」動態造版與廢除獨立 `gm_truths` 表
- **討論議題**：不應將看板鎖死在固定九宮格或「先功能後屬性」的死板切分，且 `GM_ONLY` 儲藏板與投票等機制不應寫死或重複建表。
- **拍板決策**：
  1. **LLM 功能與屬性聯合造版**：由 LLM 讀取劇本，同步評估「功能意圖」與「屬性邊界（全場公開 `public` / 多人私聊 `private_group` 2~N 人 / 單人私人 `private_single` 1-on-1 / 關主機密 `GM_ONLY`）」，針對每本劇本從零動態創造專屬看板群與 `BoardPolicy`。
  2. **6 大經典通用看板僅作 Few-Shot 範例參考**：包含 `gm_secret_vault` (`GM_ONLY`) 在內的 6 大原型僅作為 Prompt 格式示範，**絕不預先寫死必開**（例如純透明公開桌遊就不開 `gm_secret_vault`）。
  3. **徹底刪除 `gm_truths` 資料表，一律以開看板邏輯優先**：角色已知 `(C)` 秘密直接寫入其【個人專屬私人看板 (`1-on-1`)】；待解鎖線索與核心真相統一由動態開立之 `gm_secret_vault` (`GM_ONLY`) 看板存於 `posts` 表，使全域核心資料表收斂為 5 張。
  4. **凡有公開曝光疑慮之動作（含投票）一律走個人私人看板**：不為投票或暗中操作特化開發額外功能；只要任何動作直接在公開看板發布會有提前曝光或後手跟風疑慮，一律由玩家在【個人專屬私人看板 (`1-on-1`)】向關主發文執行，待全員完成後再由關主統一公布結果至【公開大廳】。

---

### 4. 最高機制核心：循序 `if` 關卡審查、主/附屬動作調度與動態私聊
- **討論議題**：通用五大物理法則如何轉化為程式邏輯？同輪內用道具與大廳發言如何穿插？對局中臨時拉群私聊如何運作？違規重試如何防死循環？
- **拍板決策**：
  1. **循序 `if` 關卡審查管線 (Sequential `if`-Gate Pipeline)**：
     - 事前守門：`if` 原則 1（權力資格/時序/失能/看板白名單）➔ `if` 原則 2（資產歸屬 `owners` JSON 精確比對/消耗/單輪代表使用限制）➔ `if` 原則 4（階段強制義務動作）➔ 通過後原子寫入 `posts`。
     - 事後結算：`if` 原則 3（兩段式線索觸發：先 Python 0 秒快篩，命中主題詞或搜查宣告再喚醒關主 LLM 語意比對並搬運線索）➔ `if` 動態私聊開房 ➔ `if` 原則 5（達成勝負條件立刻 `Break Loop` 進入復盤；`elif` 死鎖啟動補底）。
  2. **違規明確回饋 (`rejection_feedback`) 與依劇本規則兜底 (`MAX_ACTION_RETRY = 2`)**：
     - 每次被 `if` 關卡攔截退回時，必須附帶具體犯錯原因供 Agent 修正；
     - 最多重試 2 次，達上限時**僅在劇本規則允許 `PASS` 的前提下才可降級為 `PASS`**；若規則禁止 `PASS`，則從合法白名單與選項池強制執行合規保底動作。
  3. **主動作 (`MAIN_ACTION`) vs 自由／附屬動作 (`FREE_SUB_ACTION`，限 1 次，100% 以劇本為準)**：
     - 一切以劇本規則為主（若劇本規定本階段僅能大廳發言則不開放附屬動作）；
     - 當劇本允許同輪兼顧私下行動時，使用個人道具或申請私聊為 `FREE_SUB_ACTION`（每輪限 1 次），執行完後控制權留在同一位 Agent 手上，**並重新完整執行一次 7 步驟思考**以完成本輪 `MAIN_ACTION`。
  4. **回合與輪次狀態自動重置點 (`Lifecycle Reset Hooks`)**：
     - 單一玩家回合結束時重置 `sub_action_used_this_turn = False`；
     - 大輪次／階段切換時自動將 `agent_private_assets` 中 `status == 'used_in_turn'` 的道具批次重置回 `'in_hand'`。
  5. **對局中動態發起多人私聊**：
     - 私聊發起規則與是否可拒絕入房皆由劇本定義，且開局必寫清楚；若為私密發起，玩家於【個人專屬私人看板】向關主發 `REQUEST_WHISPER`（外人不可見）；
     - 審查通過後動態開房並將主線壓入堆疊（Stack）；**進房後的發言順序依劇本動態調整，未規定則預設按「進場順序（發起人先行）」輪流發文**。

---

### 5. 關主雙階段主持、Step 0 一次性對焦、7 步驟深度思考與防失憶心智筆記
- **討論議題**：如何避免初始貼文隨輪次拉長而失去影響力？如何引導 Agent 進行像人類玩桌遊一樣的深度猜忌、多方案評估與動態計畫修正？如何在限制讀取最近 50 筆對話以節省 Token 的同時，防止 Agent 對前期發生的事失憶？
- **拍板決策**：
  1. **關主雙階段主持與 `pinned_gm_opening` 永久常駐**：
     - 部分 A（開局全域主持宣讀）：寫入大廳首貼並同步持久化至 `game_sessions.pinned_gm_opening`；
     - 部分 B（每輪個人行動引導）：點名當前 Agent 並宣告 `available_boards` 與 `allowed_actions`。
  2. **單輪 7 步驟深度思考迴圈 (Step 0 ~ Step 6)**：
     - **Step 0（一次性統合對焦，讀過即過不重讀）**：在 Prompt 最頂層唯一一次注入「關主 100% 絕對真實公理 ＋ 對手互相猜忌公理 ＋ `pinned_gm_opening` 開局全文 ＋ 本輪行動引導」。
     - **Step 1（局勢掃描 ＋ 上輪情報結算 `Intel Yield` ＋ 計畫裁決）**：先將上輪不論成敗或意外所獲新情報與場上關鍵重點存入心智筆記【區塊 A】，再裁決舊計畫 `CONTINUE / ADAPT / ABORT & RE-SIMULATE`。
     - **Step 2（自我校準）**：對齊鎖死劇本人設、玩家個性與剩餘底牌，定調 `VICTORY_PUSH` 或 `INTEL_PROBE`。
     - **Step 3（深度猜忌與對手視角三連問）**：參考心智筆記【區塊 A】與 Zep KG，站在對手角度追問「他做了什麼？為什麼這樣做？手裡還留什麼牌與下步怎麼反制我？」。
     - **Step 4（多方案比較與 `IF/ELSE` 應變分支樹）**：擬定 2~3 方案，選出最優解並寫下本輪第一步與下輪 `IF/ELSE` 分支。
     - **Step 5（延遲更新雙區塊心智筆記 ＋ 表裡分離演技包裝）**：寫回 `player_meta_personas.mind_notes_json` 並追加至 `mind_notes_history_json`。
     - **Step 6（選台與提交合法動作）**：輸出 `target_board + action` 送交循序 `if` 關卡審查。
  3. **滑動視窗省 Token ＋ 心智筆記【區塊 A】記重點防失憶**：
     - 每次喚醒 Agent 思考時，公開與私聊對話流僅載入**最近 2～3 個大輪次（或最新 50 筆）的一字不漏原文**；
     - 為了不因 50 筆前的舊對話滑出視窗而失憶，Prompt 強制要求 Agent 模擬人類記憶習慣，在心智筆記【區塊 A】主動記錄**「全局關鍵事件、道具使用、出牌與線索摘要 (`key_event_and_item_memory`)」**與**「誰說了什麼話讓我懷疑」**；
     - 同時，從第 1 筆起的所有全量紀錄皆永久保存在 SQLite `posts` 表與 `actions.jsonl`，供第四階段 `ReportAgent` 生成完整復盤報告，以及第五階段 `InteractionView.tsx` 賽後一對一訪談調閱。

---

## 二、 規格文件變更紀錄 (Documentation Changelog)

| 日期 | 變更檔案 | 變更章節 / 模組 | 變更內容摘要 |
| :--- | :--- | :--- | :--- |
| 2026-11-11 | [`docs/FRD.md`](file:///c:/Users/user/MiroFish/docs/FRD.md)<br/>[`docs/ARCHITECTURE.md`](file:///c:/Users/user/MiroFish/docs/ARCHITECTURE.md) | `FRD-01`、`FRD-02`、`FRD-03`、`FRD-04`、`FRD-06`、`FRD-07`、Section 1~3 | • 劇本三大板塊新增 `other` 欄位，`(B)` 新增 `player_personality` 專屬欄位與白名單/黑名單圖譜隔離規範。<br/>• 機制審查改為循序 `if` 關卡管線。<br/>• 關主拆為雙階段主持，新增 `game_sessions.pinned_gm_opening`。<br/>• 造版改為「LLM 功能與屬性聯合判斷動態造版」，6 大經典看板改為 Few-Shot 範例（新增不寫死之 `gm_secret_vault`）。<br/>• 新增 Agent 單輪 7 步驟深度思考迴圈與雙區塊心智筆記。 |
| 2026-11-12 | [`docs/FRD.md`](file:///c:/Users/user/MiroFish/docs/FRD.md)<br/>[`docs/ARCHITECTURE.md`](file:///c:/Users/user/MiroFish/docs/ARCHITECTURE.md) | `FRD-02`、`FRD-05`、`FRD-08`、`FRD-09`、`FRD-10`、Section 1.1, 2.2, 3, 4 | • 區分主動作 (`MAIN_ACTION`) 與單次自由/附屬動作 (`FREE_SUB_ACTION`)，明訂 100% 以劇本為準且一律執行完整 7 步驟思考。<br/>• 新增對局中動態發起私聊規則（私密發起於個人關主板、房內發言順序依劇本或進場順序）。<br/>• 新增違規明確回饋 (`rejection_feedback`) 與重試上限 2 次（僅規則允許 `PASS` 時可降級 `PASS`）。<br/>• 徹底刪除 `gm_truths` 表（全域收斂為 5 張表），`player_meta_personas` 新增 `mind_notes_json` 與 `mind_notes_history_json`。<br/>• 定義原則 3 兩段式快篩與關主語意比對、React 前端架構、`run_larp_simulation.py` 執行器替換方案與第五階段賽後訪談。 |
| 2026-11-16 | [`docs/FRD.md`](file:///c:/Users/user/MiroFish/docs/FRD.md)<br/>[`docs/ARCHITECTURE.md`](file:///c:/Users/user/MiroFish/docs/ARCHITECTURE.md)<br/>[`docs/CHANGELOG.md`](file:///c:/Users/user/MiroFish/docs/CHANGELOG.md) | `FRD-02`、`FRD-03`、`FRD-07`、`FRD-08`、`FRD-09`、`FRD-10`、Section 2.2, 2.4, 2.5, 3.1, 3.4 | • 修正 `player_meta_personas` 為複合主鍵 `PRIMARY KEY (session_id, agent_id)`；`agent_private_assets` 新增 `session_id` 並將 `owners` 改為 JSON 陣列精確比對（修復 `LIKE '%Player_1%'` 誤判 `Player_10` 之 Bug）。<br/>• 新增回合/輪次切換之狀態重置點 (`Lifecycle Reset Hooks` 重置 `used_in_turn` 與 `sub_action_used`)。<br/>• 明訂「凡有公開曝光疑慮之動作（含投票）一律走個人私人看板向關主發文，再由關主公布到大廳」，不特化開發孤立投票功能。<br/>• 明訂 Agent 讀取最近 2~3 大輪次（或最新 50 筆）原文以控制 Token，並強制於心智筆記【區塊 A】記錄關鍵事件/道具/出牌/線索重點 (`key_event_and_item_memory`) 防止失憶，全量歷史則永久存於資料庫供第四階段復盤報告查閱。<br/>• 建立本 [`docs/CHANGELOG.md`](file:///c:/Users/user/MiroFish/docs/CHANGELOG.md) 追蹤檔案。 |
| 2026-11-18 | [`docs/FRD.md`](file:///c:/Users/user/MiroFish/docs/FRD.md)<br/>[`docs/ARCHITECTURE.md`](file:///c:/Users/user/MiroFish/docs/ARCHITECTURE.md)<br/>[`docs/CHANGELOG.md`](file:///c:/Users/user/MiroFish/docs/CHANGELOG.md) | `FRD-02`、`FRD-05`、`FRD-07`、Section 1, 1.1, 2.4, 3.2, 3.4 | • **移除向關主詢問規則機制，僅保留時機 B（個人私人看板內道具/技能宣告與關主互動）**：所有規則與本輪可用動作於 `pinned_gm_opening` 與 `GM Turn Guiding` 詳細解釋到 Agent 一次讀懂直接行動，不允許詢問規則延誤遊戲。<br/>• **取消硬性寫死之主動作/附屬動作 1 次上限與人工安全煞車閥**：改為「同位 Agent 連續動作迴圈」，每次思考輸出 1 個動作並由 Agent 自己依劇本規則在 JSON 填寫 `continue_turn`（`"需要"`/`true` 或 `"不需要"`/`false`）；機制核心僅負責於 `if` 關卡審查並駁回違規多動或未完成必做義務就想結束之情況。<br/>• **明訂 `PASS` 為劇本允許時之初始標準動作**：只要劇本允許過牌，Step 0 `allowed_actions` 一開始即包含 `"PASS"`。<br/>• **採用看板內訊息過濾方案 (`posts.visible_to`)**：對局中途不加開新看板，特定幾位 Agent 的私聊或定向訊息統一透過 `posts.visible_to` JSON 陣列過濾權限。<br/>• **新增雙 `post_id` 已讀游標 (`last_read_post_id` & `prev_read_post_id`)**：`posts.id` 採嚴格遞增整數，為每位 Agent 記錄上次與再上次讀到的 `post_id`，精準擷取「本局未讀新貼文 (`id > last_read_post_id`)」與「上一局貼文」，徹底解決單一 Agent 連續發多篇貼文時無法用人數算輪次之問題。<br/>• **精煉思考流程為「5 步驟零重複、以獲勝為最高前提之思考閉環 (`Step 0 ~ Step 4`)」**：消除重複查看對手貼文與重複抄寫心智筆記；在 Step 1 直接產出心智筆記【區塊 A】（未讀貼文掃描＋對手深度猜忌與獲勝威脅評估＋上輪情報結算），在 Step 2 直接產出心智筆記【區塊 B】（強制以「邁向獲勝」為最高前提，新增 `my_victory_condition_and_gap` 與 `how_this_plan_advances_victory`，將己方底牌與對手底牌綁在一起擬定左右局勢之多方案與 `IF/ELSE` 分支），Step 3 演技包裝，Step 4 輸出動作與 `continue_turn`。 |

---

## 三、 程式碼更動與實作追蹤表 (Codebase Changes & Implementation Tracker)

> **目前狀態**：📌 **架構討論與規格確認階段（依據指示，目前尚未修改任何專案程式碼）**。  
> 待確認進入開發階段後，所有新增或修改之 Python 後端與 React 前端檔案將即時記錄於下方表格：

| 階段 / 狀態 | 目標檔案路徑 (預計新增或修改) | 變更類型 | 預計實作 / 修改內容說明 |
| :--- | :--- | :--- | :--- |
| ⏳ 待開發 | `backend/app/services/script_parser.py` | 新增 | 嚴格 Regex 解析劇本三大板塊 `(A)/(B)/(C)` 與 `other`，物理剝離 `(B) player_personality`，切分 Zep 圖譜白名單文本。 |
| ⏳ 待開發 | `backend/app/services/graph_builder.py` | 修改 | 接軌 `script_parser.py` 白名單輸出，執行圖譜先行與角色人數 $N$ 雙向校驗，確保零秘密/零規則污染。 |
| ⏳ 待開發 | `backend/app/services/player_persona_generator.py` | 新增 | 實作雙層人設鎖定：固定鎖死 `immutable_role_canon`（繞過 [`oasis_profile_generator.py`](file:///c:/Users/user/MiroFish/backend/app/services/oasis_profile_generator.py) 腦補擴寫），並依「手動種子優先 ➔ AI 彌補完整」生成 5 大量化維度寫入 `player_meta_personas`。 |
| ⏳ 待開發 | `backend/app/services/board_orchestrator.py` | 新增 | 實作「LLM 功能與屬性聯合判斷動態造版」（以 6 大經典看板為 Few-Shot 參考），初始化 SQLite `simulation.db` 5 張核心表，將 `(C)` 秘密寫入個人私人看板、待解鎖線索與真相寫入 `GM_ONLY` 看板。 |
| ⏳ 待開發 | `backend/app/services/mechanism_engine.py` | 新增 | 實作最高機制核心：循序 `if` 關卡審查管線、違規錯誤原因回饋 (`rejection_feedback`)、重試上限與合規兜底、主/附屬動作調度、動態私聊房堆疊 (`Whisper Sub-Loop Stack`)、以及回合/輪次狀態自動重置 (`used_in_turn` 歸零)。 |
| ⏳ 待開發 | `backend/app/services/gm_host_agent.py` | 新增 | 實作關主雙階段主持（開局全域宣言寫入 `pinned_gm_opening` ＋ 每輪點名引導）與原則 3 兩段式線索觸發評估。 |
| ⏳ 待開發 | `backend/scripts/run_larp_simulation.py` | 新增 | 專屬回合制推演執行器，驅動 Agent 單輪 7 步驟深度思考迴圈（含近 50 筆/2~3 輪對話滑動視窗 ＋ 雙區塊心智筆記記錄關鍵道具/出牌/線索重點防失憶）。 |
| ⏳ 待開發 | [`backend/app/services/simulation_runner.py`](file:///c:/Users/user/MiroFish/backend/app/services/simulation_runner.py) | 修改 | 保持外部 `run_state.json` / `actions.jsonl` 介面相容，內部改呼叫 `run_larp_simulation.py`，並於送往 [`ZepGraphMemoryManager`](file:///c:/Users/user/MiroFish/backend/app/services/zep_graph_memory_updater.py) 前加上 `if visibility == 'public'` 過濾閥。 |
| ⏳ 待開發 | [`backend/app/services/report_agent.py`](file:///c:/Users/user/MiroFish/backend/app/services/report_agent.py) | 修改 | 第四階段終局復盤對接 `posts` 全量歷史、`GM_ONLY` 看板真相、`system_votes` 與 `mind_notes_history_json`；支援第五階段賽後一對一第一人稱復盤訪談。 |
| ⏳ 待開發 | `frontend/` (React `*.tsx`) | 新增/重構 | 使用 React 實作社群軟體頻道化動態看板容器 (`DynamicBoardContainer.tsx`)、雙區塊心智筆記卡片 (`MindNotesCard.tsx`)、復盤報告 (`SimulationReportView.tsx`) 與賽後訪談 (`InteractionView.tsx`)。 |


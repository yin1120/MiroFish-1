# 通用劇本殺多智能體模擬系統 (Generic LARP Multi-Agent System)
# 系統架構設計書 (System Architecture Document)

---

## 1. 系統總體架構概觀：最高權限機制核心體系 (System Architecture Overview)

```mermaid
graph TB
    subgraph Input_Sources["【機制核心之三維輸入源 (Mechanism Inputs)】"]
        direction TB
        Unified_Script["1. 單一劇本檔案 (Markdown)<br/>- 關主手冊 (機制指南 + 劇本自帶題庫)<br/>- 關主核心真相 (全局真相/僅 GM 可讀)<br/>- 角色客觀劇本庫 (公開區 vs 私密專區)"]
        Board_Lib["2. 後端通用看板能力庫 (Board Capabilities Library)<br/>- 對話板、手牌板、任務活動板、私聊室、暗投沙盒之能力定義"]
        GM_Meta_Prompt["3. 關主職責元規範 (GM Meta-Prompt Guidelines)<br/>- 主持人準則、裁判職責與 ManualAction 工具集"]
    end

    subgraph Supreme_Mechanism_Core["【最高權限遊戲機制核心 (The Arbiter Mechanism Engine)】"]
        direction TB
        Parser["劇本解析與人數校驗器 (script_parser.py)<br/>- 強制核對 Agent 數量與身分完全相符"]
        Contract_Orchestrator["本局契約編排器 (Session Contract Generator)<br/>- 綜合劇本、看板庫與GM規範，自主決定：<br/>  • 本局啟用之看板清單<br/>  • 本局關主主持與 ManualAction 規範 (物證混合驅動)<br/>  • 玩家合法動作約束矩陣 (失能禁言休眠)"]
        State_Machine["全局狀態機與守門員 (State Machine & Guardrail)<br/>- 掌握失能禁言休眠 (能看不能說，Zero Token)<br/>- 陣營分數累計與提前結束守衛 (Early Victory Guard)<br/>- 審查玩家發言、出牌、道具操作 (違規強制攔截)"]
    end

    subgraph Data_Storage_Layer["【資料與資產儲存層 (Storage Layer)】"]
        direction LR
        Clean_KG["純淨客觀知識圖譜 (Zep KG)<br/>- 僅存公開人設、生平、客觀關係、世界觀"]
        Unified_Asset_Store["單一私密資產資料表 (agent_private_assets)<br/>- 道具、秘密、任務存放於同一 SQLite 表<br/>- Key 區分: category, visibility (private/public)"]
        Truth_Store["關主真相庫 (GM Truth DB)<br/>- 僅 GM 可讀之作案真相"]
    end

    subgraph GM_Host_Layer["【關主主持人代行層 (GM Host Layer)】"]
        direction TB
        GM_Agent["關主主持人 (GM Host Agent)<br/>- 依據機制契約主持，從自帶題庫發題<br/>- 評估現場火候自主以 ManualAction 注入物證<br/>- 接收事件觸發後靈活生成即興戰況通報"]
    end

    subgraph Communication_Layer["【通訊與動態看板中心 (Communication & Fact Boards)】"]
        direction TB
        Scheduler["時序調度器 (Turn Scheduler)<br/>- 依狀態機排程：若 DISABLED 則【直接休眠跳過發言】"]
        Polling_API["REST 增量輪詢 API (/api/simulation/{id}/run-status/detail)<br/>- 前端每 2~3 秒定時拉取最新 Actions<br/>- 關主發題/報分/廣播均作為高權限 CREATE_POST 貼文"]
        
        subgraph Active_Boards["【本局由機制核心動態啟用之看板】"]
            Public_Stream["公共時間序對話看板 (Public Stream)"]
            Public_Card_Board["公共手牌/道具看板 (Public Card Board)"]
            Task_Board["任務活動與分數看板 (Task & Score Board)"]
            Whisper_Box["雙人微型私聊看板 (Whisper Sandbox)"]
            Secret_Ballot_Box["無記名暗投沙盒 (Secret Ballot Box)"]
        end
    end

    subgraph Agent_Mind["【Agent 第一人稱認知與決策閉環 (Cognitive Loop)】"]
        direction TB
        Perception["1. 感知環境事實 (Perception - 失能者仍接收)<br/>- 公共對話 + 任務題目 + 公共手牌<br/>- 本人 visibility=private 之道具/秘密/任務"]
        Cognitive_Notes["2. 半結構化純文字心智筆記 (Cognitive Notes)<br/>- 交叉比對全場事實，更新對每位玩家的第一人稱秘密日記"]
        Deliberation["3. 第一人稱決策行動 (Deliberation & Action)<br/>- 輸出 thought + speech + action (發言/出牌/答題/暗投)"]

        Perception --> Cognitive_Notes --> Deliberation
    end

    %% 連線交互
    Input_Sources --> Supreme_Mechanism_Core
    Parser --> Clean_KG
    Parser --> Unified_Asset_Store
    Parser --> Truth_Store

    Contract_Orchestrator -->|"派發本局主持契約"| GM_Agent
    Contract_Orchestrator -->|"動態掛載所選看板"| Active_Boards
    GM_Agent -->|"ManualAction CREATE_POST"| Polling_API
    Polling_API --> Active_Boards

    Scheduler -->|"輪次喚醒 (若非失能)"| Perception
    Clean_KG -.->|"客觀人設底色"| Perception
    Unified_Asset_Store -.->|"單表僅查本人 private"| Perception
    Active_Boards -.->|"拉取事實"| Perception

    Deliberation -->|"提交動作"| State_Machine
    State_Machine --"違規/失能"-->|"攔截駁回"| Deliberation
    State_Machine --"合法動作"--> Polling_API
    State_Machine -->|"事件上報"| GM_Agent
```

---

## 1.1 系統端到端總體運作流程圖 (End-to-End Operational Flow)

```mermaid
flowchart TD
    Start([0. 啟動系統並上傳劇本]) --> Phase0_Orchestrate

    subgraph Phase0_Orchestrate["【階段零：機制核心解析與本局編排】"]
        direction TB
        Input1["讀取單一劇本 (含自帶題庫)"]
        Input2["參考通用看板能力庫 (5大看板功能定義)"]
        Input3["參考關主職責元規範 (GM Meta-Prompt)"]
        Orchestrate["機制核心綜合評估與編排：<br/>1. 校驗 Agent 人數名單<br/>2. 自主決定本局開啟之看板清單<br/>3. 生成本局關主主持指南與物證注入時機<br/>4. 設定玩家動作權限與失能禁言規則"]

        Input1 ~~~ Input2 ~~~ Input3 --> Orchestrate
    end

    Phase0_Orchestrate --> Phase1_InitBoards

    subgraph Phase1_InitBoards["【階段一：環境掛載與關主開場】"]
        direction TB
        MountBoards["通訊層動態掛載所選看板 (前端 REST 輪詢同步)"]
        GMOpener["關主依機制指示執行開場 ManualAction (CREATE_POST)：<br/>宣讀世界觀、陣營任務與本局規則"]
        MountBoards --> GMOpener
    end

    Phase1_InitBoards --> Phase2_TurnLoop

    subgraph Phase2_TurnLoop["【階段二：機制嚴格約束下的輪次與博弈循環 (私聊與暗投穿插公聊)】"]
        direction TB
        CheckPerm{"機制發言權威審查：<br/>依本局規則與狀態機<br/>判定是否具備發言權?"}
        SkipSleep["【禁言休眠模式 (A方案)】<br/>• 機制裁決無發言權 (失能)<br/>• 跳過發言 / 0 Token / 背景接收事實"]
        MultiPerception["多維依據感知 (Perception)：<br/>1. 看板歷史紀錄 (對話流/題目/物證)<br/>2. 主觀認知表格 (純文字心智筆記)<br/>3. 私密手牌資產 (暗牌/秘密/目標)"]
        WriteNotes["撰寫/刷新第一人稱心智筆記"]
        DeliberateAction["輸出決策：thought + speech + action"]
        GuardCheck{"機制核心合法性審查 (Guardrail)"}
        RollbackAction["違規動作強制攔截並 Rollback"]
        InterleavedDispatch["動作分發與穿插公聊執行：<br/>• 常規公聊發言 (推進大廳主軸)<br/>• 穿插雙人私聊 (隔音2~3輪後返回大廳)<br/>• 穿插出牌/答題 (手牌板與任務板)<br/>• 穿插節點投票 (特定輪次暗投表決)"]

        CheckPerm --"無發言權 (失能禁言)"--> SkipSleep
        CheckPerm --"具發言權 (正常)"--> MultiPerception
        MultiPerception --> WriteNotes --> DeliberateAction --> GuardCheck
        GuardCheck --"違規"--> RollbackAction -.-> DeliberateAction
        GuardCheck --"合法"--> InterleavedDispatch
    end

    Phase2_TurnLoop --> Phase3_EventResponse

    subgraph Phase3_EventResponse["【階段三：動態事件觸發與提前結束判定】"]
        direction TB
        EventOccur["事件捕獲 (如: 答題成功/出牌/破壞)"]
        GMWake["喚醒關主 LLM 靈活處置：<br/>• 自主決定主持詞 (非硬編碼)<br/>• 調整陣營分數 / 發放道具"]
        CheckWin{"陣營分數達到 100 分<br/>或達成終止條件?"}
        EarlyVictory["【觸發提前結束！】<br/>中斷輪次循環，宣告勝利"]

        EventOccur --> GMWake --> CheckWin
        CheckWin --"是"--> EarlyVictory
        CheckWin --"否"--> NextTurn([進入下一輪])
    end

    ApplyAction --> EventOccur
    SkipSleep --> NextTurn
    NextTurn --> Phase2_TurnLoop
    EarlyVictory --> Phase4_Report([進入第四階段：生成復盤報告])
```

---

## 2. 核心時序流程 (Interaction Sequences)

### 2.1 機制編排、自主選板與關主開場時序 (Mechanism Orchestration Flow)
```mermaid
sequenceDiagram
    autonumber
    actor Admin as 研究員/系統啟動
    participant Mechanism as 最高機制核心 (The Arbiter)
    participant GM as 關主主持人 (GM Host Agent)
    participant Comm as 通訊看板中心
    participant Blackboard as 公共對話看板

    Admin->>Mechanism: 提交單一劇本檔案 (含自帶題庫)
    Mechanism->>Mechanism: 載入【通用看板能力庫】+【關主職責元規範】
    Mechanism->>Mechanism: 核對劇本 Agent 人數與清單 (若不符直接報錯中止)
    Note over Mechanism: 機制核心自主編排本局契約 (Session Contract):<br/>1. 決定啟用哪些看板<br/>2. 決定關主 ManualAction 規範 (物證注入混合驅動)<br/>3. 建立玩家法則審查表 (失能禁言能看不能說)
    Mechanism->>Comm: 動態掛載指定看板清單
    Mechanism->>GM: 注入本局關主主持指南與全局真相
    GM->>Blackboard: 執行開場 ManualAction (CREATE_POST): 宣讀世界觀背景、陣營目標與規則
    Mechanism->>Mechanism: 啟動輪次調度器
```

---

### 2.2 前後端通訊架構：MiroFish 原生定時輪詢時序 (Polling Interaction Flow)
```mermaid
sequenceDiagram
    autonumber
    actor Frontend as 前端 React 介面
    participant Backend_API as FastAPI 後端 (/api/simulation/...)
    participant DB as SQLite (simulation.db)
    actor GM as 關主 / 玩家 Agent

    GM->>DB: 發布新發言/線索物證/題目/戰況 (寫入 post / action 表)
    
    loop 每 2~3 秒定時輪詢 (Polling)
        Frontend->>Backend_API: GET /api/simulation/{id}/run-status/detail
        Backend_API->>DB: 查詢最新 all_actions (含 CREATE_POST, REVEAL_ITEM 等)
        Backend_API-->>Frontend: 回傳最新動作增量清單
        Frontend->>Frontend: 依 actionId 去重，即時更新對話流、手牌板與分數條
    end
```

---

## 3. 資料結構規範 (Data Schemas)

### 3.1 單一私密資產資料表 Schema (agent_private_assets)
所有玩家的道具、秘密、個人任務集中存放於單一 SQLite 資料表：
```sql
CREATE TABLE IF NOT EXISTS agent_private_assets (
    id TEXT PRIMARY KEY,                     -- 唯一識別碼 (如 "item_001", "sec_002")
    agent_id TEXT NOT NULL,                  -- 所屬玩家 ID (如 "Player_Li")
    category TEXT NOT NULL,                  -- 'item' (道具) | 'secret' (秘密) | 'objective' (個人任務)
    title TEXT NOT NULL,                     -- 名稱 (如 "泛黃借條", "我就是真凶", "陷害王掌櫃")
    content TEXT NOT NULL,                   -- 詳細內容 / 案件事實 / 勝利條件
    visibility TEXT DEFAULT 'private',       -- 'private' (私密) | 'public' (公開，亮牌後更新為此)
    status TEXT DEFAULT 'in_hand'            -- 'in_hand' (持有中) | 'revealed' (已公開) | 'completed' (已完成)
);
```

---

## 4. 模組部署與技術對齊 (Component Mapping)

| 模組名稱 | 負責後端元件 (Python) | 負責前端元件 (React) | 資料持久化與通訊方式 |
| :--- | :--- | :--- | :--- |
| **最高機制核心** | `mechanism_engine.py` (最高仲裁與編排中樞) | `GameEngineStatus.tsx` | 記憶體狀態機 + SQLite 審計日誌 |
| **單一劇本解析器** | `script_parser.py` (核對人數+分流) | `ScriptUploadView.tsx` | Markdown / Text 暫存 |
| **純淨圖譜生成** | `graph_builder.py` + `zep_tools.py` | `KnowledgeGraphView.tsx` | Zep 知識圖譜庫 (僅存公開區) |
| **單一私密資產庫** | `private_asset_service.py` (單表Key分流) | `PrivateAssetCard.tsx` (僅本人可見) | SQLite 表格 `agent_private_assets` |
| **Profile 玩家生成** | `player_persona_generator.py` (5大維度) | `PlayerPersonaCard.tsx` | SQLite 表格 `player_meta_personas` |
| **關主主持代行** | `gm_host_agent.py` (受機制驅動與約束) | `GMAdminPanel.tsx` (關主主持台) | GM 專用管道 + 貼文廣播隊列 |
| **通訊與動態看板** | `board_orchestrator.py` (原生輪詢) | `DynamicBoardContainer.tsx` | **原生定時輪詢 (每2~3秒拉取 detail)** |
| **第四階段報告** | `report_agent.py` (支援提前結束大綱) | `SimulationReportView.tsx` | Markdown 完整復盤報告 |

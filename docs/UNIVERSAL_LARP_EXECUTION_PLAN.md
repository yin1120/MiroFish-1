# 通用多智能體社交博弈模擬系統：架構流轉與機制決策流程檢測計劃書
# (Universal LARP Architecture Dataflow & Lifecycle Verification Plan)

> 💡 **視覺化互動檢視器**：系統已在工作區生成專屬的互動檢視網頁 [FLOWCHART_VIEWER.html](file:///c:/Users/user/MiroFish/docs/FLOWCHART_VIEWER.html)，您可以直接用瀏覽器開啟，自由切換分階段放大圖或全景總覽圖！

---

## 1. 系統端到端總體運作流程圖 (全景總覽圖)

本流程圖徹底摒棄針對單一桌遊的特化詞彙，全數採用**通用桌遊機制標準**：
1. **【步驟 4 玩家思考參考依據中樞】**：清晰刻畫玩家在決策行動前，必須調閱的**「個人主觀看板 (心智筆記)」、「個人看板歷史紀錄」、「公共看板歷史紀錄」與「客觀真理與圖譜」**，並進行內部深度思考 (thought)；
2. **【步驟 5 看板專屬機制審查】**：針對 5 大看板，以條列式清晰定義各自專屬的機制審查條件；在私聊房間中特別納入**「若規則需要有共識，但無共識則進入投票環節」**；
3. **【步驟 6 全域通用狀態掃描中樞】**：徹底拿掉特定桌遊勝負字眼，不解釋具體贏的條件為何，由機制在動作結算後**同時並行掃描 5 大通用狀態**（通用勝負終止、是否需要投票、是否觸發真相線索、全體發言權限更新、流程階段切換）；
4. **【關主主持職責】**：在各看板開場指引建立遊戲感，並在狀態掃描觸發事件時即時進行解說、敲鐘通報與終局復盤。

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'background': '#0a0a0a',
    'primaryColor': '#1e293b',
    'primaryTextColor': '#ffffff',
    'primaryBorderColor': '#38bdf8',
    'lineColor': '#38bdf8',
    'fontSize': '18px',
    'fontFamily': '"Fira Code", consolas, "Microsoft JhengHei", sans-serif'
  }
}}%%
flowchart TD
    %% ================= 階段 0：劇本三大標題分類來源 =================
    ScriptInput([載入單一劇本 script.md]) --> ScriptExtract[劇本結構化提取]

    subgraph ScriptSource["【劇本三大標題來源】"]
        direction TB
        GM_Script["【關主劇本】<br/>• 規模<br/>• 故事<br/>• 規則<br/>• 流程<br/>• 獲勝機制<br/>• 題庫"]
        Char_Public["【公開角色劇本】<br/>• 人設與人物介紹<br/>• 故事線<br/>• 公開道具與公開任務"]
        Char_Secret["【秘密角色劇本】<br/>• 秘密任務<br/>• 私密道具與技能<br/>• 作案行蹤與秘密<br/>• 對其他人的私下看法"]
    end

    ScriptExtract --> GM_Script
    ScriptExtract --> Char_Public
    ScriptExtract --> Char_Secret

    %% ================= 階段 1：直接對照看板表判定開板 =================
    GM_Script -->|"依據【規模】"| Step_CheckCount{"【步驟 1：人數名額核對】<br/>劇本記載人數 與 參賽名冊 是否相符?"}
    Step_CheckCount --"人數不符"--> AbortSession([報錯中止對局])
    Step_CheckCount --"人數相符"--> BoardDeductionEngine["【步驟 2：直接依【看板對照表】判定開板】"]

    GM_Script & Char_Secret --> BoardDeductionEngine

    subgraph OpenBoards["【開放之 5 大通用看板】"]
        direction TB
        Board_Public["1.【全場公開大廳】"]
        Board_Item["2.【個人道具視窗】"]
        Board_Card["3.【公共道具板】"]
        Board_Task["4.【任務分數看板】"]
        Board_Whisper["5.【多人私聊房間】"]
    end

    BoardDeductionEngine -->|"依據【故事】與【流程】 ➔ 全局主時序"| Board_Public
    BoardDeductionEngine -->|"依據【私密道具與技能】 ➔ 判定角色持有私密道具"| Board_Item
    BoardDeductionEngine -->|"依據【故事】與【規則】 ➔ 判定有公開道具或檯面操作"| Board_Card
    BoardDeductionEngine -->|"依據【題庫】與【獲勝機制】 ➔ 判定有題目與計分門檻"| Board_Task
    BoardDeductionEngine -->|"依據【流程】與【規則】 ➔ 判定規則允許私聊密會"| Board_Whisper

    %% ================= 階段 2：關主初始固定發言與信任確立 =================
    OpenBoards --> GMOpener["【步驟 3：關主初始固定發言與信任確立】<br/>1. 確立關主絕對信任：宣告超然客觀公證人身分，代表世界物理公理 (蓋真理戳記)<br/>2. 宣讀故事世界觀：時代環境、空間設定與開場劇情<br/>3. 說明遊戲流程階段：時序輪替、幕次推進、何時為公開討論與私聊時段<br/>4. 說明行動規則：發言順序、過牌規範、檯面操作規範、私聊禁直接用道具<br/>5. 宣告勝負目標與終止條件：陣營或個人獲勝門檻與終止判定，正式開局<br/>6. 各板點對點指引：道具視窗發放道具宣告共有者、公共道具板陳列公開道具、任務看板發布題目"]

    %% ================= 階段 3：輪到玩家行動 ➔ 思考參考依據與深度思考 =================
    GMOpener --> PlayerActionLoop["【步驟 4：輪到玩家行動輪次】"]

    PlayerActionLoop --> ThinkReferences

    subgraph ThinkReferences["【玩家行動前之多維思考參考依據】"]
        direction TB
        Ref_Subjective["1.【個人主觀看板 (心智筆記)】<br/>• 對其他玩家之主觀懷疑度與信用評級<br/>• 私密推理假設與隱密策略<br/>• 個人偽裝設定與自保話術規劃"]
        Ref_PrivateBoard["2.【個人看板歷史紀錄】<br/>• 個人道具視窗歷史 (持用狀態/共有者名單)<br/>• 專屬私聊房間歷史 (隔音商討紀錄/同盟承諾)<br/>• 秘密角色劇本 (秘密行蹤/私有獲勝目標)"]
        Ref_PublicBoard["3.【公共看板歷史紀錄】<br/>• 全場公開大廳歷史 (全體公開辯論與質詢紀錄)<br/>• 公共道具板歷史 (檯面公開道具與操作紀錄)<br/>• 任務分數看板現況 (題目解題進度與即時分數)"]
        Ref_TruthKG["4.【客觀真理與知識圖譜】<br/>• 關主官方真理公告 (規則/時序/死訊通報)<br/>• 客觀圖譜 (公開人設背景/世界物理底色)"]
    end

    ThinkReferences --> PlayerThinking["【玩家第一人稱深度思考 (Cognitive Deliberation)】<br/>• 交叉比對客觀事實與他人言論矛盾 (防詐欺/測謊)<br/>• 結合自身秘密與目標，擬定本輪博弈策略<br/>• 產出內部決策思考 (thought) 並決定行動"]

    PlayerThinking --> Action_Public["動作 A: 於【公開大廳】公開陳述發言或過牌"]
    PlayerThinking --> Action_Item["動作 B: 於【道具視窗】發文宣告使用隨身道具"]
    PlayerThinking --> Action_Card["動作 C: 於【公共道具板】公開操作或展示道具"]
    PlayerThinking --> Action_Task["動作 D: 於【任務看板】發文提交挑戰題目解答"]
    PlayerThinking --> Action_Whisper["動作 E: 於【私聊房間】進行多人隔音商討協商"]

    %% ================= 階段 4：動作連線匯入機制進行看板專屬審查 =================
    Action_Public -->|"連線匯入機制"| MechanismJudge
    Action_Item -->|"連線匯入機制"| MechanismJudge
    Action_Card -->|"連線匯入機制"| MechanismJudge
    Action_Task -->|"連線匯入機制"| MechanismJudge
    Action_Whisper -->|"連線匯入機制"| MechanismJudge

    subgraph MechanismJudge["【步驟 5：最高機制核心 (依看板分類專屬條列審查)】"]
        direction TB
        Judge_A["【全場公開大廳專屬審查】<br/>• 發言權限審查：審查發言者是否失能淘汰 (失能者直接禁言休眠，0 Token)<br/>• 發言排程審查：是否符合規則規定之發言順序或合法宣告過牌 (PASS)<br/>• 言論邊界審查：僅限公開陳述與辯論，嚴禁在此越權執行私密操作"]
        Judge_B["【個人道具視窗專屬審查】<br/>• 持有權限審查：動作發起者是否名列該道具/技能之持有人名單<br/>• 共有約束審查：共有道具本輪是否已被同伴使用 (限一人代表發動)<br/>• 消耗狀態審查：是否為一次性消耗品、是否處於冷卻或耗盡狀態"]
        Judge_C["【公共道具板專屬審查】<br/>• 操作時序審查：當前階段是否開放公開操作、時序是否輪到該玩家<br/>• 規則合規審查：操作動作是否符合劇本規定之檯面公開操作規則<br/>• 狀態流轉審查：私密道具公開化，更新為全場共享檯面狀態"]
        Judge_D["【任務分數看板專屬審查】<br/>• 作答資格審查：該任務挑戰是否開放、是否重複提交解答<br/>• 答案客觀審查：提交解答是否與劇本標準答案吻合<br/>• 數值核算審查：自動核算給分並實時累計至全域或陣營總進度條"]
        Judge_E["【多人私聊房間專屬審查】<br/>• 功能邊界審查：最高禁令：嚴禁在私聊房內直接使用道具 (違規阻斷)<br/>• 成員身分審查：發言者是否為該房間之合法受邀成員<br/>• 共識與時限審查：若規則需要共識但無共識、或達輪數上限 ➔ 強制進入投票環節"]
    end

    %% ================= 階段 5：機制審查結果與全域狀態掃描 =================
    MechanismJudge --"動作違規"--> RejectAction["【機制阻斷駁回】動作無效，退回重新思考與決策"] -.-> PlayerActionLoop

    MechanismJudge --"動作合規"--> ParallelCheck{"【步驟 6：全域機制通用狀態掃描中樞 (無差別並行掃描)】<br/>1. 通用勝負終止掃描：比對劇本勝負與終結判定邏輯 (不預設具體公式)<br/>2. 投票觸發節點掃描：檢查當前時序是否抵達預設之投票表決或指認節點<br/>3. 真相線索解鎖掃描：比對發言進展或動作是否滿足隱藏線索解鎖條件 (獨佔性鎖定)<br/>4. 發言權限更新掃描：檢查玩家狀態變更 (淘汰/出局/失能者即刻標記禁言休眠)<br/>5. 流程階段切換掃描：檢查當前階段各項進程條件，判定是否推進至下一階段"}

    %% ================= 階段 6：未達成勝負 (推進流程) =================
    ParallelCheck --"未達成勝負 (推進遊戲)"--> ActionApproved["【機制核准】動作正式生效，寫入公開或私密紀錄"]

    ActionApproved --> GMNarrate["【關主隨行解說與突發通報】<br/>• 獲得/發動道具即時解說<br/>• 人員失能淘汰於大廳敲鐘通報並啟動禁言休眠<br/>• 私聊無共識/超時主持房內投票，引導代表回道具視窗發動<br/>• 觸發隱藏線索多層級分發 (個人/小組/全場)<br/>• 階段切換敲鐘廣播<br/>• 到達投票節點啟動私密投票詢問與大廳計票公示"]

    GMNarrate --> NextTurn["輪次 + 1，調度下一位玩家"] --> PlayerActionLoop

    %% ================= 階段 7：達成勝負 (觸發終局) =================
    ParallelCheck --"達成勝負條件 (觸發終局)"--> BreakLoop["【機制立即中斷輪次循環】<br/>終止後續發言，進入終局復盤"]

    BreakLoop --> GMEarlyWin["【關主發布提前獲勝插播廣播】<br/>於全場大廳插播宣告勝利陣營/玩家"]

    GMEarlyWin --> FinalReview["【步驟 7：終局真相宣讀與復盤評分】<br/>1. 機制統計投票表決與個人秘密目標達成狀況<br/>2. 關主對照核心真相庫宣讀真實真相與因果<br/>3. 產出完整復盤報告與玩家推理評分榜"] --> End([推演完成])
```

---

## 2. 分階段高清晰放大流程圖 (超大字體・細節無損)

為避免完整長圖在部分螢幕上文字縮小，以下將系統流程拆解為三大高清晰大圖：

### 2.1 【階段一：開局準備與開板判定 (步驟 1 ~ 3)】

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'background': '#0a0a0a',
    'primaryColor': '#1e293b',
    'primaryTextColor': '#ffffff',
    'primaryBorderColor': '#38bdf8',
    'lineColor': '#38bdf8',
    'fontSize': '22px',
    'fontFamily': '"Fira Code", consolas, "Microsoft JhengHei", sans-serif'
  }
}}%%
flowchart TD
    ScriptInput([載入單一劇本 script.md]) --> ScriptExtract[劇本結構化提取]

    subgraph ScriptSource["【劇本三大標題來源】"]
        direction TB
        GM_Script["【關主劇本】<br/>• 規模<br/>• 故事<br/>• 規則<br/>• 流程<br/>• 獲勝機制<br/>• 題庫"]
        Char_Public["【公開角色劇本】<br/>• 人設與人物介紹<br/>• 故事線<br/>• 公開道具與公開任務"]
        Char_Secret["【秘密角色劇本】<br/>• 秘密任務<br/>• 私密道具與技能<br/>• 作案行蹤與秘密<br/>• 對其他人的私下看法"]
    end

    ScriptExtract --> GM_Script
    ScriptExtract --> Char_Public
    ScriptExtract --> Char_Secret

    GM_Script -->|"依據【規模】"| Step_CheckCount{"【步驟 1：人數名額核對】<br/>劇本記載人數 與 參賽名冊 是否相符?"}
    Step_CheckCount --"人數不符"--> AbortSession([報錯中止對局])
    Step_CheckCount --"人數相符"--> BoardDeductionEngine["【步驟 2：直接依【看板對照表】判定開板】"]

    GM_Script & Char_Secret --> BoardDeductionEngine

    subgraph OpenBoards["【開放之 5 大通用看板】"]
        direction TB
        Board_Public["1.【全場公開大廳】"]
        Board_Item["2.【個人道具視窗】"]
        Board_Card["3.【公共道具板】"]
        Board_Task["4.【任務分數看板】"]
        Board_Whisper["5.【多人私聊房間】"]
    end

    BoardDeductionEngine -->|"依據【故事】與【流程】 ➔ 全局主時序"| Board_Public
    BoardDeductionEngine -->|"依據【私密道具與技能】 ➔ 判定角色持有私密道具"| Board_Item
    BoardDeductionEngine -->|"依據【故事】與【規則】 ➔ 判定有公開道具或檯面操作"| Board_Card
    BoardDeductionEngine -->|"依據【題庫】與【獲勝機制】 ➔ 判定有題目與計分門檻"| Board_Task
    BoardDeductionEngine -->|"依據【流程】與【規則】 ➔ 判定規則允許私聊密會"| Board_Whisper

    OpenBoards --> GMOpener["【步驟 3：關主初始固定發言與信任確立】<br/>1. 確立關主絕對信任：宣告超然客觀公證人身分，代表世界物理公理 (蓋真理戳記)<br/>2. 宣讀故事世界觀：時代環境、空間設定與開場劇情<br/>3. 說明遊戲流程階段：時序輪替、幕次推進、公開討論與私聊時段<br/>4. 說明行動規則：發言順序、過牌規範、檯面操作規範、私聊禁直接用道具<br/>5. 宣告勝負目標與終止條件：陣營或個人獲勝門檻與終止判定，正式開局<br/>6. 各板點對點指引：道具視窗發放道具宣告共有者、公共道具板陳列公開道具、任務看板發布題目"]

    GMOpener --> NextStep([進入步驟 4：輪到玩家行動輪次])
```

---

### 2.2 【階段二：玩家思考參考依據與輪次決策行動 (步驟 4)】

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'background': '#0a0a0a',
    'primaryColor': '#1e293b',
    'primaryTextColor': '#ffffff',
    'primaryBorderColor': '#38bdf8',
    'lineColor': '#38bdf8',
    'fontSize': '22px',
    'fontFamily': '"Fira Code", consolas, "Microsoft JhengHei", sans-serif'
  }
}}%%
flowchart TD
    PlayerActionLoop["【步驟 4：輪到玩家行動輪次】"] --> ThinkReferences

    subgraph ThinkReferences["【玩家行動前之多維思考參考依據】"]
        direction TB
        Ref_Subjective["1.【個人主觀看板 (心智筆記)】<br/>• 對其他玩家之主觀懷疑度與信用評級<br/>• 私密推理假設與隱密策略<br/>• 個人偽裝設定與自保話術規劃"]
        Ref_PrivateBoard["2.【個人看板歷史紀錄】<br/>• 個人道具視窗歷史 (持用狀態/共有者名單)<br/>• 專屬私聊房間歷史 (隔音商討紀錄/同盟承諾)<br/>• 秘密角色劇本 (秘密行蹤/私有獲勝目標)"]
        Ref_PublicBoard["3.【公共看板歷史紀錄】<br/>• 全場公開大廳歷史 (全體公開辯論與質詢紀錄)<br/>• 公共道具板歷史 (檯面公開道具與操作紀錄)<br/>• 任務分數看板現況 (題目解題進度與即時分數)"]
        Ref_TruthKG["4.【客觀真理與知識圖譜】<br/>• 關主官方真理公告 (規則/時序/死訊通報)<br/>• 客觀圖譜 (公開人設背景/世界物理底色)"]
    end

    ThinkReferences --> PlayerThinking["【玩家第一人稱深度思考 (Cognitive Deliberation)】<br/>• 交叉比對客觀事實與他人言論矛盾 (防詐欺/測謊)<br/>• 結合自身秘密與目標，擬定本輪博弈策略<br/>• 產出內部決策思考 (thought) 並決定行動"]

    PlayerThinking --> Action_Public["動作 A: 於【公開大廳】公開陳述發言或過牌"]
    PlayerThinking --> Action_Item["動作 B: 於【道具視窗】發文宣告使用隨身道具"]
    PlayerThinking --> Action_Card["動作 C: 於【公共道具板】公開操作或展示道具"]
    PlayerThinking --> Action_Task["動作 D: 於【任務看板】發文提交挑戰題目解答"]
    PlayerThinking --> Action_Whisper["動作 E: 於【私聊房間】進行多人隔音商討協商"]

    Action_Public & Action_Item & Action_Card & Action_Task & Action_Whisper --> NextStep([連線匯入步驟 5 機制專屬審查])
```

---

### 2.3 【階段三：中心機制審查、全域狀態掃描與終局流轉 (步驟 5 ~ 7)】

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'background': '#0a0a0a',
    'primaryColor': '#1e293b',
    'primaryTextColor': '#ffffff',
    'primaryBorderColor': '#38bdf8',
    'lineColor': '#38bdf8',
    'fontSize': '20px',
    'fontFamily': '"Fira Code", consolas, "Microsoft JhengHei", sans-serif'
  }
}}%%
flowchart TD
    ActionsInput([接收玩家看板動作 A ~ E]) --> MechanismJudge

    subgraph MechanismJudge["【步驟 5：最高機制核心 (依看板分類專屬條列審查)】"]
        direction TB
        Judge_A["【全場公開大廳專屬審查】<br/>• 發言權限審查：審查發言者是否失能淘汰 (失能者直接禁言休眠，0 Token)<br/>• 發言排程審查：是否符合規則規定之發言順序或合法宣告過牌 (PASS)<br/>• 言論邊界審查：僅限公開陳述與辯論，嚴禁在此越權執行私密操作"]
        Judge_B["【個人道具視窗專屬審查】<br/>• 持有權限審查：動作發起者是否名列該道具/技能之持有人名單<br/>• 共有約束審查：共有道具本輪是否已被同伴使用 (限一人代表發動)<br/>• 消耗狀態審查：是否為一次性消耗品、是否處於冷卻或耗盡狀態"]
        Judge_C["【公共道具板專屬審查】<br/>• 操作時序審查：當前階段是否開放公開操作、時序是否輪到該玩家<br/>• 規則合規審查：操作動作是否符合劇本規定之檯面公開操作規則<br/>• 狀態流轉審查：私密道具公開化，更新為全場共享檯面狀態"]
        Judge_D["【任務分數看板專屬審查】<br/>• 作答資格審查：該任務挑戰是否開放、是否重複提交解答<br/>• 答案客觀審查：提交解答是否與劇本標準答案吻合<br/>• 數值核算審查：自動核算給分並實時累計至全域或陣營總進度條"]
        Judge_E["【多人私聊房間專屬審查】<br/>• 功能邊界審查：最高禁令：嚴禁在私聊房內直接使用道具 (違規阻斷)<br/>• 成員身分審查：發言者是否為該房間之合法受邀成員<br/>• 共識與時限審查：若規則需要共識但無共識、或達輪數上限 ➔ 強制進入投票環節"]
    end

    MechanismJudge --"動作違規"--> RejectAction["【機制阻斷駁回】動作無效，退回重新思考與決策"]

    MechanismJudge --"動作合規"--> ParallelCheck{"【步驟 6：全域機制通用狀態掃描中樞 (無差別並行掃描)】<br/>1. 通用勝負終止掃描：比對劇本勝負與終結判定邏輯 (不預設具體公式)<br/>2. 投票觸發節點掃描：檢查當前時序是否抵達預設之投票表決或指認節點<br/>3. 真相線索解鎖掃描：比對發言進展或動作是否滿足隱藏線索解鎖條件 (獨佔性鎖定)<br/>4. 發言權限更新掃描：檢查玩家狀態變更 (淘汰/出局/失能者即刻標記禁言休眠)<br/>5. 流程階段切換掃描：檢查當前階段各項進程條件，判定是否推進至下一階段"}

    ParallelCheck --"未達成勝負 (推進遊戲)"--> ActionApproved["【機制核准】動作正式生效，寫入公開或私密紀錄"]

    ActionApproved --> GMNarrate["【關主隨行解說與突發通報】<br/>• 獲得/發動道具即時解說<br/>• 人員失能淘汰於大廳敲鐘通報並啟動禁言休眠<br/>• 私聊無共識/超時主持房內投票，引導代表回道具視窗發動<br/>• 觸發隱藏線索多層級分發 (個人/小組/全場)<br/>• 階段切換敲鐘廣播<br/>• 到達投票節點啟動私密投票詢問與大廳計票公示"]

    GMNarrate --> NextTurn["輪次 + 1，調度下一位玩家"]

    ParallelCheck --"達成勝負條件 (觸發終局)"--> BreakLoop["【機制立即中斷輪次循環】<br/>終止後續發言，進入終局復盤"]

    BreakLoop --> GMEarlyWin["【關主發布提前獲勝插播廣播】<br/>於全場大廳插播宣告勝利陣營/玩家"]

    GMEarlyWin --> FinalReview["【步驟 7：終局真相宣讀與復盤評分】<br/>1. 機制統計投票表決與個人秘密目標達成狀況<br/>2. 關主對照核心真相庫宣讀真實真相與因果<br/>3. 產出完整復盤報告與玩家推理評分榜"] --> End([推演完成])
```

---

## 3. 核心架構流轉與判斷依據文字詳解

### 3.1 步驟 4：玩家行動前之多維思考參考依據詳解

在步驟 4 輪到玩家行動時，玩家 Agent 透過以下四大參考維度進行深度思考：
1. **【個人主觀看板 (心智筆記卡片)】**：記錄對其他玩家之主觀懷疑度、私密推理假設、自保話術與偽裝風格；
2. **【個人看板歷史紀錄】**：個人道具視窗歷史（持用狀態/共有名單/使用結算）、專屬私聊隔音歷史（情報約定/房內微投票結果）、秘密角色劇本（秘密行蹤/私有獲勝目標）；
3. **【公共看板歷史紀錄】**：全場公開大廳歷史對話流、公共道具板檯面操作紀錄、任務分數看板進度現況；
4. **【客觀真理與知識圖譜】**：關主官方公告 (`SYSTEM_GROUND_TRUTH` 規則/時序/死訊通報)、純淨客觀圖譜 (公開人設與世界物理常識)；
5. **【延遲心智更新 (Lazy Cognitive Updating)】**：僅輪到行動時才喚醒思考引擎，調用上述四大參考依據完成交叉比對，產出決策思考 (`thought`)，再分發為具體看板動作。

### 3.2 步驟 5：5 大看板專屬機制審查條列詳解

1. **【全場公開大廳】**：審查存活與發言權限（失能禁言休眠 0 Token）、發言時序排程（順時針輪流或合法過牌）、言論邊界（嚴禁執行私密操作）。
2. **【個人道具視窗】**：審查道具持有權限、共有道具單輪限一人發動約束、單次消耗與冷卻狀態。
3. **【公共道具板】**：審查操作時序權限、檯面公開操作規則合規性、道具狀態公開化流轉。
4. **【任務分數看板】**：審查作答資格與重複作答、解答客觀吻合度、數值核算與進度累計。
5. **【多人私聊房間】**：
   - 嚴禁直接在房內使用道具（違規強制阻斷）；
   - 審查成員合法身分；
   - **共識要求與無共識投票審查**：若規則需共識但無共識、或達輪數上限（預設 4 輪）➔ 機制強制在房內發起微投票表決，定案後關閉房間。

### 3.3 步驟 6：全域機制通用狀態掃描中樞 (五大並行審查詳解)

不預設任何具體贏的公式，無差別並行執行以下 5 大通用狀態判定：
1. **通用勝負終止條件掃描**：比對劇本勝負判定邏輯（不預設特定公式）。滿足即中斷輪次循環，插播提前獲勝。
2. **是否需要觸發投票環節掃描**：檢查當前時序是否抵達預設之投票表決或指認節點。抵達即啟動投票程序。
3. **是否觸發真相與隱藏線索掃描**：比對發言進展或動作是否滿足解鎖條件，並執行獨佔性鎖定，定向多層級分發。
4. **全體玩家發言權限與狀態更新掃描**：檢查本次動作是否導致玩家狀態變更（淘汰/出局/失能），即時標記禁言休眠模式。
5. **流程階段切換判斷掃描**：檢查當前階段各項進程條件，判定是否推進至下一流程階段並驅動關主廣播。

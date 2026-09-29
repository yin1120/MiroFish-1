"""
本體生成服務
介面1：分析文字內容，生成適合社會模擬的實體和關係型別定義
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional
from ..utils.llm_client import LLMClient
from ..utils.locale import get_language_instruction

logger = logging.getLogger(__name__)


def _to_pascal_case(name: str) -> str:
    """將任意格式的名稱轉換為 PascalCase（如 'works_for' -> 'WorksFor', 'person' -> 'Person'）"""
    # 按非字母數字字元分割
    parts = re.split(r'[^a-zA-Z0-9]+', name)
    # 再按 camelCase 邊界分割（如 'camelCase' -> ['camel', 'Case']）
    words = []
    for part in parts:
        words.extend(re.sub(r'([a-z])([A-Z])', r'\1_\2', part).split('_'))
    # 每個詞首字母大寫，過濾空串
    result = ''.join(word.capitalize() for word in words if word)
    return result if result else 'Unknown'


# 本體生成的系統提示詞
ONTOLOGY_SYSTEM_PROMPT = """你是一個專業的知識圖譜本體設計專家。你的任務是分析給定的文字內容和模擬需求，設計適合**社交媒體輿論模擬**的實體型別和關係型別。

**重要：你必須輸出有效的JSON格式資料，不要輸出任何其他內容。**

## 核心任務背景

我們正在構建一個**社交媒體輿論模擬系統**。在這個系統中：
- 每個實體裝飾著一個可以在社交媒體上發聲、互動、傳播資訊的"賬號"或"主體"
- 實體之間會相互影響、轉發、評論、回應
- 我們需要模擬輿論事件中各方的反應和資訊傳播路徑

因此，**實體必須是現實中真實存在的、可以在社媒上發聲和互動的主體**：

**可以是**：
- 具體的個人（公眾人物、當事人、意見領袖、專家學者、普通人）
- 公司、企業（包括其官方賬號）
- 組織機構（大學、協會、NGO、工會等）
- 政府部門、監管機構
- 媒體機構（報紙、電視臺、自媒體、網站）
- 社交媒體平臺本身
- 特定群體代表（如校友會、粉絲團、維權群體等）

**不可以是**：
- 抽象概念（如"輿論"、"情緒"、"趨勢"）
- 主題/話題（如"學術誠信"、"教育改革"）
- 觀點/態度（如"支援方"、"反對方"）

## 輸出格式

請輸出JSON格式，包含以下結構：

```json
{
    "entity_types": [
        {
            "name": "實體型別名稱（英文，PascalCase）",
            "description": "簡短描述（英文，不超過100字元）",
            "attributes": [
                {
                    "name": "屬性名（英文，snake_case）",
                    "type": "text",
                    "description": "屬性描述"
                }
            ],
            "examples": ["示例實體1", "示例實體2"]
        }
    ],
    "edge_types": [
        {
            "name": "關係型別名稱（英文，UPPER_SNAKE_CASE）",
            "description": "簡短描述（英文，不超過100字元）",
            "source_targets": [
                {"source": "源實體型別", "target": "目標實體型別"}
            ],
            "attributes": []
        }
    ],
    "analysis_summary": "對文字內容的簡要分析說明"
}
```

## 設計指南（極其重要！）

【重要警告：不要盲目複製範例實體】
你必須仔細分析輸入的文本內容。如果文本與學校、學生、教授無關，你的實體列表中絕對不能出現 `Student`、`Professor`、`University`。如果文本與商業、CEO無關，你的列表中絕對不能出現 `Executive` 等無關型別。請務必為當前文本所屬領域（如地緣政治、軍事戰爭）設計高度相關的具體型別！
例如：如果涉及戰爭與衝突，你必須定義 `Country` (或 `GeopoliticalEntity`，代表國家)、`MilitaryLeaderPerson` (軍事領袖)、`Location` (交戰地點/行政區劃，注意：地點型別名稱中絕對不可包含 Person/Organization/Company/Group 等後綴) 等，並確保關係的 `source_targets` 支援這些實體。

### 1. 實體型別設計 - 必須嚴格遵守

**數量要求：必須正好10個實體型別**

**層次結構要求（必須同時包含具體型別和兜底型別）**：

你的10個實體型別必須包含以下層次：

A. **兜底型別（必須包含，放在列表最後2個）**：
   - `Person`: 任何自然人個體的兜底型別。當一個人不屬於其他更具體的人物型別時，歸入此類。
   - `Organization`: 任何組織機構的兜底型別。當一個組織不屬於其他更具體的組織型別時，歸入此類。

B. **具體型別（8個，根據文字內容與所屬領域精確設計，絕對禁止照抄無關範例）**：
   - 針對文字中出現的主要角色，設計更具體的型別。你必須根據文字所屬領域進行客觀分析。
   - **禁止照抄原則**：下面的「學術事件」和「商業事件」僅為示範參考，如果文本是有關**軍事、地緣政治、國際衝突**的，你必須生成例如 `Country`、`GeopoliticalEntity`、`MilitaryForceOrganization`、`Location`（非發言類）等型別，**絕對禁止**在軍事衝突文本中生成 `Student`、`Professor`、`University` 等與文本無關的型別！
   - 例如：如果文字涉及學術事件，可以有 `Student`, `Professor`, `University`
   - 例如：如果文字涉及商業事件，可以有 `Company`, `CEO`, `Employee`

**為什麼需要兜底型別**：
- 文字中會出現各種人物，如"中小學教師"、"路人甲"、"某位網友"
- 如果沒有專門的型別匹配，他們應該被歸入 `Person`
- 同理，小型組織、臨時團體等應該歸入 `Organization`

**具體型別的設計原則**：
- 從文字中識別出高頻出現或關鍵的角色型別
- 每個具體型別應該有明確的邊界，避免重疊
- description 必須清晰說明這個型別和兜底型別的區別

**實體型別名稱的規範化命名規則與通用設計（極重要）**：
- **禁止硬編碼特定國家、人物或專有名詞**：實體型別名稱必須是「通用且抽象」的（例如：【絕對不要】設計 `UkrainianGovernmentPerson`、`RussianGovernmentPerson`，而應該設計為通用的 `GovernmentOfficialPerson` 或 `PoliticalLeaderPerson`；【絕對不要】設計 `WagnerOrganization`，而應該設計為通用的 `MilitaryOrganization`）。
- **使用 `country` 屬性區分歸屬**：對於不同角色的國家或政治體系歸屬，請**一律放入 `country` 屬性（Attribute）**中（例如：讓烏克蘭政府和俄羅斯政府實體均屬於 `GovernmentOfficialPerson` 或 `Organization`，並由其 `country` 屬性值如 `"Ukraine"` 或 `"Russia"` 分別區分）。這樣做可以將複雜的規則簡化，使 `source_targets` 配對規則大幅收攏（如只需定義 `[GovernmentOfficialPerson -> Organization]` 一種配對），從而徹底避免超出 Zep API 的 10 個關係限制！
- **發言角色（人物與組織）字尾規範**：為了讓系統能夠正確辨識哪些是「可發言的 Agent」並防止在後處理中被誤殺，請務必在自訂的人物與組織/團體/公司型別名稱中，包含對應的關鍵字作為後綴：
  - 人物類型的後綴請使用 `Person`（例如：用 `PoliticianPerson` 代替 `PoliticianEntity`，用 `MilitaryLeaderPerson` 代替 `MilitaryLeaderEntity`，用 `JournalistPerson` 代替 `Journalist` 等）。
  - 組織/團體/公司類型的後綴請使用 `Organization` 或 `Company` 或 `Group`（例如：用 `MilitaryUnitOrganization` 代替 `MilitaryUnitEntity`，用 `NgoOrganization` 代替 `Ngo`）。
- **非發言角色（如道具、地點、植物、物品等背景事物）**：絕對禁止在名稱中包含 `Person`、`Organization`、`Company`、`Group` 等發言實體關鍵字。請維持一般後綴（例如 `Location` 或 `Item`，如 `CabinLocation`、`BreadItem`），以防止系統將其誤認成能發言的 Agent 帳號。

### 2. 關係型別設計

- 數量：6-10個
- **緊扣文件主題設計核心行為與事件關係（極重要）**：
  - 關係型別應該深刻反映**文件主體中的核心動態行為、事件與聯絡**，而不僅限於靜態的社會關係。
  - **如果文件是關於戰爭、軍事或衝突**：請務必包含具體的動態戰事動作，例如：`ATTACKED`（攻擊）、`RECAPTURED`（收復）、`OCCUPIED`（佔領）、`WITHDREW_FROM`（撤退/撤出）、`SANCTIONED`（制裁）、`MILITARY_AID`（提供軍援）、`DESTROYED`（摧毀）、`FOUGHT_IN`（交戰於）等關係。
  - **如果文件是關於商業/經濟**：請包含如 `ACQUIRED`（收購）、`INVESTED_IN`（投資）、`SUED`（起訴）等。
  - 同時也應包含社媒互動中的真實聯絡（如：`SUPPORTS`（支持）、`OPPOSES`（反對）、`COMMENTED_ON`（評論）等）。
- 確保關係的 source_targets 涵蓋你定義的實體型別
- **放寬關係型別的 source_targets 限制（極重要）**：在定義邊關係的 `source_targets` 時，應儘量將 `source` 和 `target` 指向更寬泛的兜底型別（如 `Person` 和 `Organization` 等），或涵蓋多種可能發生的角色對應組合。**避免將來源與目標限制得過於具體**（例如：絕對不要限制 `SUPPORTS` 只能由個人指向政治人物，這會導致組織支持政治人物、個人支持其他個人或組織等關係在圖譜中無法被提取。應至少涵蓋 `Person -> Person`、`Person -> Organization`、`Organization -> Person` 等多種合理情況；同理，`ATTACKED` 等關係的 source/target 也可以為 `Organization` 或 `Location`，代表軍隊、國家或交戰地點）。

### 3. 屬性設計

- 每個實體型別可以有適當數量的關鍵屬性
- **注意**：屬性名不能使用 `name`、`uuid`、`group_id`、`created_at`、`summary`（這些是系統保留字）
- **動態角色屬性要求**：請分析文件內容，若發現人物有具體描述「性別」、「年齡」或「國家」，請將這些屬性加入 attributes，**並且務必在 description 欄位寫下詳細的英文萃取指示，並包含中文關鍵字提示，幫助後續引擎準確對齊抓取**。例如：
  - `age`: "The exact age of the person. Look for keywords like '年齡', '歲' (e.g., 58)"
  - `gender`: "The gender of the person. Look for keywords like '性別', 'Male', 'Female'"
  - `country`: "Country of residence or origin. Look for keywords like '國家', 'Taiwan'"
- 推薦使用：`full_name`, `title`, `role`, `position`, `location`, `description` 等
- **限制（極重要）**：絕對禁止將個人屬性（如 '性別/gender'、'年齡/age'、'國家/country'）定義為獨立的實體型別（entity_types）或邊關係。請務必將它們作為人物實體型別（如 `Person` 以及其他具體人物型別）的 attributes 進行定義。

## 實體型別參考

**個人類（具體）**：
- Student: 學生
- Professor: 教授/學者
- Journalist: 記者
- Celebrity: 明星/網紅
- Executive: 高管
- Official: 政府官員
- Lawyer: 律師
- Doctor: 醫生

**個人類（兜底）**：
- Person: 任何自然人（不屬於上述具體型別時使用）

**組織類（具體）**：
- University: 高校
- Company: 公司企業
- GovernmentAgency: 政府機構
- MediaOutlet: 媒體機構
- Hospital: 醫院
- School: 中小學
- NGO: 非政府組織

**組織類（兜底）**：
- Organization: 任何組織機構（不屬於上述具體型別時使用）

## 關係型別參考

- WORKS_FOR: 工作於
- STUDIES_AT: 就讀於
- AFFILIATED_WITH: 隸屬於
- REPRESENTS: 代表
- REGULATES: 監管
- REPORTS_ON: 報道
- COMMENTS_ON: 評論
- RESPONDS_TO: 回應
- SUPPORTS: 支援
- OPPOSES: 反對
- COLLABORATES_WITH: 合作
- COMPETES_WITH: 競爭
"""


class OntologyGenerator:
    """
    本體生成器
    分析文字內容，生成實體和關係型別定義
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
    
    def generate(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成本體定義
        
        Args:
            document_texts: 檔案文字列表
            simulation_requirement: 模擬需求描述
            additional_context: 額外上下文
            
        Returns:
            本體定義（entity_types, edge_types等）
        """
        # 構建使用者訊息
        user_message = self._build_user_message(
            document_texts, 
            simulation_requirement,
            additional_context
        )
        
        lang_instruction = get_language_instruction()
        system_prompt = (
            f"{ONTOLOGY_SYSTEM_PROMPT}\n\n{lang_instruction}\n"
            "【關鍵輸出限制】\n"
            "1. 嚴格輸出標準純 JSON 物件（包含 entity_types 與 edge_types），不要輸出任何多餘的文字說明或前言。\n"
            "2. 嚴格遵守本體設計規範：必須正好定義 10 個實體型別（前 8 個為針對文本領域精確分析之具體型別，最後 2 個為 Person 與 Organization 兜底型別）。\n"
            "3. 關係型別 (edge_types) 請精準定義 8 到 10 個核心關係型別。\n"
            "4. Entity type names MUST be in English PascalCase (e.g., 'Person', 'MediaOrganization'). "
            "Relationship type names MUST be in English UPPER_SNAKE_CASE (e.g., 'WORKS_FOR'). "
            "Attribute names MUST be in English snake_case.\n"
            "5. 【嚴格格式安全】：description 或 examples 字串內部【絕對嚴禁使用英文雙引號 (\")】，若需引用專有名詞一律使用單引號 (') 或書名號《》，嚴防破壞 JSON 語法！"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        # 呼叫LLM（上限設為 4096 tokens，確保複雜本體定義完整生成，並關閉思考模式以達到秒級極速回應）
        result = self.llm_client.chat_json(
            messages=messages,
            temperature=0.2,
            max_tokens=4096,
            enable_thinking=False
        )
        
        # 驗證和後處理
        result = self._validate_and_process(result)
        
        return result
    
    # 傳給 LLM 的文字最大長度（5萬字）
    MAX_TEXT_LENGTH_FOR_LLM = 50000
    
    def _build_user_message(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str]
    ) -> str:
        """構建使用者訊息"""
        
        # 合併文字
        combined_text = "\n\n---\n\n".join(document_texts)
        original_length = len(combined_text)
        
        # 如果文字超過5萬字，截斷（僅影響傳給LLM的內容，不影響圖譜構建）
        if len(combined_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            combined_text = combined_text[:self.MAX_TEXT_LENGTH_FOR_LLM]
            combined_text += f"\n\n...(原文共{original_length}字，已擷取前{self.MAX_TEXT_LENGTH_FOR_LLM}字用於本體分析)..."
        
        message = f"""## 模擬需求

{simulation_requirement}

## 檔案內容

{combined_text}
"""
        
        if additional_context:
            message += f"""
## 額外說明

{additional_context}
"""
        
        message += """
請根據以上內容，設計適合社會輿論模擬的實體型別和關係型別。

**必須遵守的規則**：
1. 必須正好輸出10個實體型別
2. 最後2個必須是兜底型別：Person（個人兜底）和 Organization（組織兜底）
3. 前8個是根據文字內容設計的具體型別
4. 所有實體型別必須是現實中可以發聲的主體，不能是抽象概念
5. 屬性名不能使用 name、uuid、group_id 等保留字，用 full_name、org_name 等替代
6. 絕對禁止將年齡、性別、國家等個人屬性特徵設計為獨立的實體型別。它們必須只作為 Person 或其他個人實體的屬性 (attributes)。

============================================================
【重要輸出規範】
請直接輸出標準純 JSON 本體定義物件，根節點包含 entity_types 與 edge_types。
不要輸出任何 Markdown 標題或前置說明文字。
============================================================
"""
        
        return message
    
    def _validate_and_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """驗證和後處理結果"""
        
        # 確保必要欄位存在
        if "entity_types" not in result:
            result["entity_types"] = []
        if "edge_types" not in result:
            result["edge_types"] = []
        if "analysis_summary" not in result:
            result["analysis_summary"] = ""
        
        # 透過小模型批次自動將「非通用」的實體名稱進行歸一化清理，不硬編碼國家清單，適用於任何 geopolitical/專有名詞
        normalization_map = self._normalize_entity_names_batch(result["entity_types"])
        
        # 驗證實體型別
        # 記錄原始名稱到 PascalCase/Cleaned名稱 的對映，用於後續修正 edge 的 source_targets 引用
        entity_name_map = {}
        for entity in result["entity_types"]:
            # 強制將 entity name 轉為 PascalCase（Zep API 要求）
            if "name" in entity:
                original_name = entity["name"]
                name = _to_pascal_case(original_name)
                
                # 套用 LLM 自動歸一化映射
                if name in normalization_map:
                    cleaned_name = normalization_map[name]
                    if cleaned_name != name:
                        logger.warning(f"實體類型 '{name}' 經 LLM 自動歸一化為通用的 '{cleaned_name}'")
                        name = cleaned_name
                
                entity["name"] = name
                if entity["name"] != original_name:
                    logger.warning(f"Entity type name '{original_name}' auto-converted to '{entity['name']}'")
                entity_name_map[original_name] = entity["name"]
                
                # 確保被歸一化後的實體類型擁有 country 屬性以區分歸屬
                if original_name != name:
                    has_country_attr = any(attr.get("name") == "country" for attr in entity.get("attributes", []))
                    if not has_country_attr:
                        if "attributes" not in entity:
                            entity["attributes"] = []
                        entity["attributes"].append({
                            "name": "country",
                            "type": "text",
                            "description": "Country of origin or affiliation. E.g., Ukraine, Russia, USA."
                        })
            if "attributes" not in entity:
                entity["attributes"] = []
            if "examples" not in entity:
                entity["examples"] = []
            # 確保description不超過100字元
            if len(entity.get("description", "")) > 100:
                entity["description"] = entity["description"][:97] + "..."
        
        # 驗證關係型別
        for edge in result["edge_types"]:
            # 強制將 edge name 轉為 SCREAMING_SNAKE_CASE（Zep API 要求）
            if "name" in edge:
                original_name = edge["name"]
                edge["name"] = original_name.upper()
                if edge["name"] != original_name:
                    logger.warning(f"Edge type name '{original_name}' auto-converted to '{edge['name']}'")
            # 修正 source_targets 中的實體名稱引用，與轉換後的 PascalCase 保持一致
            for st in edge.get("source_targets", []):
                if st.get("source") in entity_name_map:
                    st["source"] = entity_name_map[st["source"]]
                if st.get("target") in entity_name_map:
                    st["target"] = entity_name_map[st["target"]]
            if "source_targets" not in edge:
                edge["source_targets"] = []
            if "attributes" not in edge:
                edge["attributes"] = []
            if len(edge.get("description", "")) > 100:
                edge["description"] = edge["description"][:97] + "..."
        
        # Zep API 限制：最多 10 個自定義實體型別，最多 10 個自定義邊型別
        MAX_ENTITY_TYPES = 10
        MAX_EDGE_TYPES = 10

        # 去重：按 name 去重，保留首次出現的
        seen_names = set()
        deduped = []
        for entity in result["entity_types"]:
            name = entity.get("name", "")
            if name and name not in seen_names:
                seen_names.add(name)
                deduped.append(entity)
            elif name in seen_names:
                logger.warning(f"Duplicate entity type '{name}' removed during validation")
        result["entity_types"] = deduped

        # 兜底型別定義
        person_fallback = {
            "name": "Person",
            "description": "Any individual person not fitting other specific person types.",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name of the person"},
                {"name": "role", "type": "text", "description": "Role or occupation"}
            ],
            "examples": ["ordinary citizen", "anonymous netizen"]
        }
        
        organization_fallback = {
            "name": "Organization",
            "description": "Any organization not fitting other specific organization types.",
            "attributes": [
                {"name": "org_name", "type": "text", "description": "Name of the organization"},
                {"name": "org_type", "type": "text", "description": "Type of organization"}
            ],
            "examples": ["small business", "community group"]
        }
        
        # 檢查是否已有兜底型別
        entity_names = {e["name"] for e in result["entity_types"]}
        has_person = "Person" in entity_names
        has_organization = "Organization" in entity_names
        
        # 需要新增的兜底型別
        fallbacks_to_add = []
        if not has_person:
            fallbacks_to_add.append(person_fallback)
        if not has_organization:
            fallbacks_to_add.append(organization_fallback)
        
        if fallbacks_to_add:
            current_count = len(result["entity_types"])
            needed_slots = len(fallbacks_to_add)
            
            # 如果新增後會超過 10 個，需要移除一些現有型別
            if current_count + needed_slots > MAX_ENTITY_TYPES:
                # 計算需要移除多少個
                to_remove = current_count + needed_slots - MAX_ENTITY_TYPES
                # 從末尾移除（保留前面更重要的具體型別）
                result["entity_types"] = result["entity_types"][:-to_remove]
            
            # 新增兜底型別
            result["entity_types"].extend(fallbacks_to_add)
        
        # 最終確保不超過限制（防禦性程式設計）
        if len(result["entity_types"]) > MAX_ENTITY_TYPES:
            result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]
        
        # 獲取最終確定後的實體型別名稱集合，用於校驗關係的 source_targets
        entity_names = {e["name"] for e in result["entity_types"]}
        
        for edge in result["edge_types"]:
            if "source_targets" not in edge:
                edge["source_targets"] = []
                
            unique_sts = []
            seen_pairs = set()
            for st in edge["source_targets"]:
                src = st.get("source", "Entity")
                tgt = st.get("target", "Entity")
                
                # 確保 source 和 target 在最終實體名稱列表中，否則降級為 "Entity"
                if src not in entity_names and src != "Entity":
                    src = "Entity"
                if tgt not in entity_names and tgt != "Entity":
                    tgt = "Entity"
                    
                pair = (src, tgt)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    unique_sts.append({"source": src, "target": tgt})
            
            # Zep API 限制每個關係的 source_targets 最多 10 個
            if len(unique_sts) > 10:
                logger.warning(f"Edge type '{edge.get('name')}' has {len(unique_sts)} source_targets, truncating to 10 (Zep API limit)")
                unique_sts = unique_sts[:10]
            
            edge["source_targets"] = unique_sts
        
        if len(result["edge_types"]) > MAX_EDGE_TYPES:
            result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]
        
        return result

    def _normalize_entity_names_batch(self, entity_types: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        批次使用 LLM 將所有非通用的型別名稱歸一化，返回 {舊名稱: 新通用名稱} 的對照字典。
        """
        names_to_clean = [et["name"] for et in entity_types if et and "name" in et and et["name"] not in ("Person", "Organization", "Entity")]
        if not names_to_clean:
            return {}
            
        system_prompt = (
            "You are an ontology normalization assistant. Your task is to clean a list of entity type names "
            "by removing specific country names, nationalities, regional designations, proper nouns, or specific organization names, "
            "converting them into a generic, abstract category name in PascalCase.\n"
            "Examples:\n"
            "- 'UkrainianGovernmentOfficialPerson' -> 'GovernmentOfficialPerson'\n"
            "- 'RussianMilitaryLeaderPerson' -> 'MilitaryLeaderPerson'\n"
            "- 'HarvardUniversity' -> 'University'\n"
            "- 'WagnerOrganization' -> 'MilitaryOrganization'\n"
            "- 'GovernmentOfficialPerson' -> 'GovernmentOfficialPerson' (already generic, keep as is)\n"
            "Output must be a valid JSON object mapping the original name to the cleaned generic name.\n"
            "Example Output: {\"UkrainianGovernmentOfficialPerson\": \"GovernmentOfficialPerson\", \"RussianMilitaryLeaderPerson\": \"MilitaryLeaderPerson\"}\n"
            "Rule: Return ONLY the raw JSON object. Do not output markdown code blocks, explanation or extra text."
        )
        
        user_content = f"Clean these entity type names: {json.dumps(names_to_clean)}"
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
            response_text = self.llm_client.chat(messages=messages, temperature=0.1).strip()
            # 移除可能夾帶的 markdown 語法
            if response_text.startswith("```"):
                start = response_text.find("{")
                end = response_text.rfind("}")
                if start != -1 and end != -1:
                    response_text = response_text[start:end+1]
            
            mapping = json.loads(response_text)
            if isinstance(mapping, dict):
                # 確保所有 key 和 value 都是乾淨的 PascalCase
                cleaned_mapping = {}
                for k, v in mapping.items():
                    v_clean = re.sub(r'[^a-zA-Z0-9]', '', v)
                    if v_clean:
                        cleaned_mapping[k] = v_clean
                return cleaned_mapping
        except Exception as e:
            logger.error(f"批次 LLM 歸一化型別名稱失敗: {e}")
        return {}
        
        # 驗證關係型別
        for edge in result["edge_types"]:
            # 強制將 edge name 轉為 SCREAMING_SNAKE_CASE（Zep API 要求）
            if "name" in edge:
                original_name = edge["name"]
                edge["name"] = original_name.upper()
                if edge["name"] != original_name:
                    logger.warning(f"Edge type name '{original_name}' auto-converted to '{edge['name']}'")
            # 修正 source_targets 中的實體名稱引用，與轉換後的 PascalCase 保持一致
            for st in edge.get("source_targets", []):
                if st.get("source") in entity_name_map:
                    st["source"] = entity_name_map[st["source"]]
                if st.get("target") in entity_name_map:
                    st["target"] = entity_name_map[st["target"]]
            if "source_targets" not in edge:
                edge["source_targets"] = []
            if "attributes" not in edge:
                edge["attributes"] = []
            if len(edge.get("description", "")) > 100:
                edge["description"] = edge["description"][:97] + "..."
        
        # Zep API 限制：最多 10 個自定義實體型別，最多 10 個自定義邊型別
        MAX_ENTITY_TYPES = 10
        MAX_EDGE_TYPES = 10

        # 去重：按 name 去重，保留首次出現的
        seen_names = set()
        deduped = []
        for entity in result["entity_types"]:
            name = entity.get("name", "")
            if name and name not in seen_names:
                seen_names.add(name)
                deduped.append(entity)
            elif name in seen_names:
                logger.warning(f"Duplicate entity type '{name}' removed during validation")
        result["entity_types"] = deduped

        # 兜底型別定義
        person_fallback = {
            "name": "Person",
            "description": "Any individual person not fitting other specific person types.",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name of the person"},
                {"name": "role", "type": "text", "description": "Role or occupation"}
            ],
            "examples": ["ordinary citizen", "anonymous netizen"]
        }
        
        organization_fallback = {
            "name": "Organization",
            "description": "Any organization not fitting other specific organization types.",
            "attributes": [
                {"name": "org_name", "type": "text", "description": "Name of the organization"},
                {"name": "org_type", "type": "text", "description": "Type of organization"}
            ],
            "examples": ["small business", "community group"]
        }
        
        # 檢查是否已有兜底型別
        entity_names = {e["name"] for e in result["entity_types"]}
        has_person = "Person" in entity_names
        has_organization = "Organization" in entity_names
        
        # 需要新增的兜底型別
        fallbacks_to_add = []
        if not has_person:
            fallbacks_to_add.append(person_fallback)
        if not has_organization:
            fallbacks_to_add.append(organization_fallback)
        
        if fallbacks_to_add:
            current_count = len(result["entity_types"])
            needed_slots = len(fallbacks_to_add)
            
            # 如果新增後會超過 10 個，需要移除一些現有型別
            if current_count + needed_slots > MAX_ENTITY_TYPES:
                # 計算需要移除多少個
                to_remove = current_count + needed_slots - MAX_ENTITY_TYPES
                # 從末尾移除（保留前面更重要的具體型別）
                result["entity_types"] = result["entity_types"][:-to_remove]
            
            # 新增兜底型別
            result["entity_types"].extend(fallbacks_to_add)
        
        # 最終確保不超過限制（防禦性程式設計）
        if len(result["entity_types"]) > MAX_ENTITY_TYPES:
            result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]
        
        # 獲取最終確定後的實體型別名稱集合，用於校驗關係的 source_targets
        entity_names = {e["name"] for e in result["entity_types"]}
        
        for edge in result["edge_types"]:
            if "source_targets" not in edge:
                edge["source_targets"] = []
                
            unique_sts = []
            seen_pairs = set()
            for st in edge["source_targets"]:
                src = st.get("source", "Entity")
                tgt = st.get("target", "Entity")
                
                # 確保 source 和 target 在最終實體名稱列表中，否則降級為 "Entity"
                if src not in entity_names and src != "Entity":
                    src = "Entity"
                if tgt not in entity_names and tgt != "Entity":
                    tgt = "Entity"
                    
                pair = (src, tgt)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    unique_sts.append({"source": src, "target": tgt})
            
            # Zep API 限制每個關係的 source_targets 最多 10 個
            if len(unique_sts) > 10:
                logger.warning(f"Edge type '{edge.get('name')}' has {len(unique_sts)} source_targets, truncating to 10 (Zep API limit)")
                unique_sts = unique_sts[:10]
            
            edge["source_targets"] = unique_sts
        
        if len(result["edge_types"]) > MAX_EDGE_TYPES:
            result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]
        
        return result
    
    def generate_python_code(self, ontology: Dict[str, Any]) -> str:
        """
        將本體定義轉換為Python程式碼（類似ontology.py）
        
        Args:
            ontology: 本體定義
            
        Returns:
            Python程式碼字串
        """
        code_lines = [
            '"""',
            '自定義實體型別定義',
            '由MiroFish自動生成，用於社會輿論模擬',
            '"""',
            '',
            'from pydantic import Field',
            'from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel',
            '',
            '',
            '# ============== 實體型別定義 ==============',
            '',
        ]
        
        # 生成實體型別
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            desc = entity.get("description", f"A {name} entity.")
            
            code_lines.append(f'class {name}(EntityModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = entity.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        code_lines.append('# ============== 關係型別定義 ==============')
        code_lines.append('')
        
        # 生成關係型別
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            # 轉換為PascalCase類名
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            desc = edge.get("description", f"A {name} relationship.")
            
            code_lines.append(f'class {class_name}(EdgeModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = edge.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        # 生成型別字典
        code_lines.append('# ============== 型別配置 ==============')
        code_lines.append('')
        code_lines.append('ENTITY_TYPES = {')
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            code_lines.append(f'    "{name}": {name},')
        code_lines.append('}')
        code_lines.append('')
        code_lines.append('EDGE_TYPES = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            code_lines.append(f'    "{name}": {class_name},')
        code_lines.append('}')
        code_lines.append('')
        
        # 生成邊的source_targets對映
        code_lines.append('EDGE_SOURCE_TARGETS = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            source_targets = edge.get("source_targets", [])
            if source_targets:
                st_list = ', '.join([
                    f'{{"source": "{st.get("source", "Entity")}", "target": "{st.get("target", "Entity")}"}}'
                    for st in source_targets
                ])
                code_lines.append(f'    "{name}": [{st_list}],')
        code_lines.append('}')
        
        return '\n'.join(code_lines)


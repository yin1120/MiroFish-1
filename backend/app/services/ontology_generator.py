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
- 每個實體都是一個可以在社交媒體上發聲、互動、傳播資訊的"賬號"或"主體"
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

### 1. 實體型別設計 - 必須嚴格遵守

**數量要求：必須正好10個實體型別**

**層次結構要求（必須同時包含具體型別和兜底型別）**：

你的10個實體型別必須包含以下層次：

A. **兜底型別（必須包含，放在列表最後2個）**：
   - `Person`: 任何自然人個體的兜底型別。當一個人不屬於其他更具體的人物型別時，歸入此類。
   - `Organization`: 任何組織機構的兜底型別。當一個組織不屬於其他更具體的組織型別時，歸入此類。

B. **具體型別（8個，根據文字內容設計）**：
   - 針對文字中出現的主要角色，設計更具體的型別
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

### 2. 關係型別設計

- 數量：6-10個
- 關係應該反映社媒互動中的真實聯絡
- 確保關係的 source_targets 涵蓋你定義的實體型別

### 3. 屬性設計

- 每個實體型別可以有適當數量的關鍵屬性
- **注意**：屬性名不能使用 `name`、`uuid`、`group_id`、`created_at`、`summary`（這些是系統保留字）
- **動態角色屬性要求**：請分析文件內容，若發現人物有具體描述「性別」、「年齡」、「國家」或「MBTI」，請將這些屬性加入 attributes，**並且務必在 description 欄位寫下詳細的英文萃取指示，並包含中文關鍵字提示，幫助後續引擎準確對齊抓取**。例如：
  - `age`: "The exact age of the person. Look for keywords like '年齡', '歲' (e.g., 58)"
  - `gender`: "The gender of the person. Look for keywords like '性別', 'Male', 'Female'"
  - `country`: "Country of residence or origin. Look for keywords like '國家', 'Taiwan'"
  - `mbti`: "MBTI personality type. Look for keywords like 'MBTI', 'ISTJ', 'ENTJ'"
- 推薦使用：`full_name`, `title`, `role`, `position`, `location`, `description` 等
- **限制（極重要）**：絕對禁止將個人屬性（如 'MBTI/性格'、'性別/gender'、'年齡/age'、'國家/country'）定義為獨立的實體型別（entity_types）或邊關係。請務必將它們作為人物實體型別（如 `Person` 以及其他具體人物型別）的 attributes 進行定義。

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
        system_prompt = f"{ONTOLOGY_SYSTEM_PROMPT}\n\n{lang_instruction}\nIMPORTANT: Entity type names MUST be in English PascalCase (e.g., 'PersonEntity', 'MediaOrganization'). Relationship type names MUST be in English UPPER_SNAKE_CASE (e.g., 'WORKS_FOR'). Attribute names MUST be in English snake_case. Only description fields and analysis_summary should use the specified language above."
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        # 呼叫LLM
        result = self.llm_client.chat_json(
            messages=messages,
            temperature=0.3,
            max_tokens=4096
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
6. 絕對禁止將 MBTI、年齡、性別、國家等個人屬性特徵設計為獨立的實體型別。它們必須只作為 Person 或其他個人實體的屬性 (attributes)。
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
        
        # 驗證實體型別
        # 記錄原始名稱到 PascalCase 的對映，用於後續修正 edge 的 source_targets 引用
        entity_name_map = {}
        for entity in result["entity_types"]:
            # 強制將 entity name 轉為 PascalCase（Zep API 要求）
            if "name" in entity:
                original_name = entity["name"]
                entity["name"] = _to_pascal_case(original_name)
                if entity["name"] != original_name:
                    logger.warning(f"Entity type name '{original_name}' auto-converted to '{entity['name']}'")
                entity_name_map[original_name] = entity["name"]
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


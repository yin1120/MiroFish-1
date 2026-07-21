"""
LLM客戶端封裝
統一使用OpenAI格式呼叫
"""

import json
import re
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config


class LLMClient:
    """LLM客戶端"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=1800.0
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        傳送聊天請求
        
        Args:
            messages: 訊息列表
            temperature: 溫度引數
            max_tokens: 最大token數
            response_format: 響應格式（如JSON模式）
            
        Returns:
            模型響應文字
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if response_format:
            kwargs["response_format"] = response_format
        
        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        # 部分模型（如MiniMax M2.5）會在content中包含<think>思考內容，需要移除
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        傳送聊天請求並返回JSON
        
        Args:
            messages: 訊息列表
            temperature: 溫度引數
            max_tokens: 最大token數
            max_retries: 最大重試次數
            
        Returns:
            解析後的JSON物件
        """
        import logging
        logger = logging.getLogger(__name__)
        
        last_error = None
        for attempt in range(max_retries):
            try:
                response = self.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"}
                )
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}: LLM call failed or doesn't support json_object format: {e}. Retrying without response_format...")
                response = self.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            
            # 清理markdown程式碼塊標記
            cleaned_response = response.strip()
            cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response, flags=re.IGNORECASE)
            cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)
            cleaned_response = cleaned_response.strip()

            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError as e:
                last_error = f"LLM返回的JSON格式無效: {cleaned_response}"
                logger.warning(f"JSON parsing failed on attempt {attempt + 1}: {e}")
                
        raise ValueError(last_error)


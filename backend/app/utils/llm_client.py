"""
LLM客戶端封裝
統一使用OpenAI格式呼叫，支援獨立視窗連線監控、心跳耗時、截斷自動修復與詳細日誌記錄
"""

import os
import json
import re
import time
import threading
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config
from .logger import get_logger

logger = get_logger("mirofish.llm")

# 算力連線即時傳輸檔案路徑（由第二個 CMD 視窗 monitor_llm.py 即時讀取）
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")
STREAM_LOG_FILE = os.path.join(LOG_DIR, "llm_stream.log")


def _write_stream_log(msg: str):
    """即時寫入算力連線日誌，由第二個 CMD 視窗同步顯示"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(STREAM_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
            f.flush()
    except Exception:
        pass


def _repair_truncated_json(text: str) -> str:
    """自動嘗試修復被截斷的 JSON（補齊未閉合的雙引號、括號等）"""
    text = text.strip()
    if not text:
        return text
    
    in_string = False
    escape = False
    stack = []
    
    for char in text:
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            if char in '{[':
                stack.append(char)
            elif char in '}]':
                if stack:
                    stack.pop()
                    
    if in_string:
        text += '"'
        
    while stack:
        open_bracket = stack.pop()
        if open_bracket == '{':
            text += '}'
        elif open_bracket == '[':
            text += ']'
            
    return text


class LLMClient:
    """LLM客戶端，支援獨立算力視窗即時監控與狀態追蹤"""
    
    _request_counter = 0
    _counter_lock = threading.Lock()
    
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
            timeout=1200.0
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
        enable_thinking: Optional[bool] = False,
        extra_body: Optional[Dict] = None
    ) -> str:
        """
        傳送聊天請求
        
        Args:
            messages: 訊息列表
            temperature: 溫度引數
            max_tokens: 最大token數
            response_format: 響應格式（如JSON模式）
            enable_thinking: 是否啟用深度思考模式（預設 False 免思考極速回應）
            extra_body: 額外 OpenAI 請求參數
            
        Returns:
            模型響應文字
        """
        with LLMClient._counter_lock:
            req_id = LLMClient._request_counter
            LLMClient._request_counter += 1
            
        prompt_chars = sum(len(m.get("content", "")) for m in messages if isinstance(m.get("content"), str))
        start_time = time.time()
        
        # 1. 在算力監控視窗印出請求啟動
        monitor_header = (
            f"======================================================================\n"
            f"🚀 [LLM Request #{req_id}] 透過 API KEY 發起推論請求！\n"
            f"  🤖 指定模型: {self.model}\n"
            f"  🌐 算力端點: {self.base_url}\n"
            f"  📝 Prompt 大小: {prompt_chars:,} 字元 | max_tokens: {max_tokens} | 溫度: {temperature} | 思考模式: {'開啟' if enable_thinking else '關閉'}\n"
            f"----------------------------------------------------------------------"
        )
        _write_stream_log(monitor_header)
        logger.info(f"[LLM Request #{req_id}] 發送請求: model={self.model}, prompt_chars={prompt_chars}, max_tokens={max_tokens}")
        
        # 在後端終端印出簡短提醒，保持後端視窗整潔
        print(f"\n[MiroFish Backend] -> 正在發送 [LLM Request #{req_id}] 至算力中心... (連線詳細動態請見「算力連線資訊」視窗)", flush=True)
        
        # 2. 啟動心跳計時器（每 10 秒輸出一次到算力監控視窗）
        stop_heartbeat = threading.Event()
        def _heartbeat():
            elapsed = 0
            while not stop_heartbeat.wait(10.0):
                elapsed += 10
                _write_stream_log(f"  ⏳ [LLM Request #{req_id}] 算力推論中... 已連線等待 {elapsed} 秒 ⚡")
                if elapsed % 30 == 0:
                    logger.debug(f"[LLM Request #{req_id}] 仍在推論中，已耗時 {elapsed} 秒...")
                    
        hb_thread = threading.Thread(target=_heartbeat, daemon=True)
        hb_thread.start()
        
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            
            if response_format:
                kwargs["response_format"] = response_format

            extra = dict(extra_body or {})
            if enable_thinking is not None and "3.5" in str(self.model):
                extra["enable_thinking"] = enable_thinking
            if extra:
                kwargs["extra_body"] = extra
            
            response = self.client.chat.completions.create(**kwargs)
            duration = time.time() - start_time
            stop_heartbeat.set()
            
            content = response.choices[0].message.content or ""
            tokens = getattr(response.usage, "completion_tokens", 0) if response.usage else 0
            tps = tokens / duration if duration > 0 and tokens > 0 else 0
            
            # 偵測是否含有思考模式 / 思考歷程
            has_think_tag = bool(re.search(r'<think>[\s\S]*?</think>', content, re.IGNORECASE))
            has_thinking_process = bool(re.search(r'Thinking Process:[\s\S]*?(?=\{)', content, re.IGNORECASE))
            raw_preview = content.strip()[:80].replace("\n", " ")
            
            thinking_msg = ""
            if has_think_tag:
                match = re.search(r'<think>([\s\S]*?)</think>', content, re.IGNORECASE)
                t_chars = len(match.group(1)) if match else 0
                thinking_msg = f"  ⚠️ [思考歷程偵測] 模型使用了 <think> 標籤思考 (耗費約 {t_chars:,} 字元)，已自動過濾！\n"
            elif has_thinking_process:
                match = re.search(r'(Thinking Process:[\s\S]*?)(?=\{)', content, re.IGNORECASE)
                t_chars = len(match.group(1)) if match else 0
                thinking_msg = f"  ⚠️ [思考歷程偵測] 模型輸出了 Thinking Process (耗費約 {t_chars:,} 字元)，已自動過濾！\n"
            else:
                thinking_msg = f"  ✨ [思考模式監測] ✅ 模型未輸出思考歷程，直接輸出標準內容！\n"
                
            preview_msg = f"  📄 [輸出開頭預覽] {raw_preview}...\n"
            
            success_msg = (
                f"----------------------------------------------------------------------\n"
                f"✅ [LLM Request #{req_id}] 推論成功完成！\n"
                f"  ⏱️ 連線耗時: {duration:.2f} 秒\n"
                f"  📝 生成 Tokens: {tokens:,}\n"
                f"  ⚡ 實際速度: {tps:.2f} tokens/sec\n"
                f"{thinking_msg}"
                f"{preview_msg}"
                f"======================================================================\n"
            )
            _write_stream_log(success_msg)
            print(f"[MiroFish Backend] <- [LLM Request #{req_id}] 推論成功完成！耗時: {duration:.2f}s, Tokens: {tokens}", flush=True)
            logger.info(f"[LLM Request #{req_id}] 成功完成: duration={duration:.2f}s, tokens={tokens}, tps={tps:.2f}")
            
            # 清除 <think> 標籤
            content = re.sub(r'<think>[\s\S]*?</think>', '', content, flags=re.IGNORECASE).strip()
            # 如果有殘留的 </think> 結束標籤，切除前面的所有思考內容
            if "</think>" in content:
                content = content.split("</think>", 1)[1].strip()
            return content
            
        except Exception as e:
            stop_heartbeat.set()
            err_str = str(e)
            
            # ── 智能自愈機制：若遇到遠端 500 (OOM 顯存溢出) 且對話較長，自動修剪並重試 ──
            if ("500" in err_str or "Internal Server Error" in err_str or "out of memory" in err_str.lower()) and len(messages) > 1:
                logger.warning(f"[LLM Request #{req_id}] 偵測到遠端算力中心 500/OOM 異常，啟動上下文精簡自愈重試機制...")
                _write_stream_log(
                    f"  ⚠️ [LLM Request #{req_id}] 偵測到算力中心顯存負載極限 (500 Error)！\n"
                    f"  🔄 正在自動精簡歷史對話與工具觀測數據，啟動緊急降級重試..."
                )
                print(f"\n[MiroFish Backend] ⚠️ [LLM Request #{req_id}] 遇到遠端 500 (顯存吃緊)，自動精簡上下文並重試...", flush=True)
                
                # 修剪 messages 中過長的使用者/工具觀測訊息
                pruned_messages = []
                for m in messages:
                    c = m.get("content", "")
                    if isinstance(c, str) and len(c) > 1500 and m.get("role") != "system":
                        c = c[:1200] + "\n\n... (為避免 GPU 顯存溢出，已自動精簡歷史事實) ..."
                    pruned_messages.append({"role": m.get("role"), "content": c})
                
                try:
                    retry_start = time.time()
                    kwargs["messages"] = pruned_messages
                    retry_resp = self.client.chat.completions.create(**kwargs)
                    retry_duration = time.time() - retry_start
                    retry_content = retry_resp.choices[0].message.content or ""
                    
                    # 清除思考標籤
                    retry_content = re.sub(r'<think>[\s\S]*?</think>', '', retry_content, flags=re.IGNORECASE).strip()
                    if "</think>" in retry_content:
                        retry_content = retry_content.split("</think>", 1)[1].strip()
                        
                    _write_stream_log(
                        f"  ✅ [LLM Request #{req_id}] 自動自愈重試成功！耗時: {retry_duration:.2f} 秒\n"
                        f"======================================================================\n"
                    )
                    logger.info(f"[LLM Request #{req_id}] 自愈重試成功完成: duration={retry_duration:.2f}s")
                    print(f"[MiroFish Backend] <- [LLM Request #{req_id}] 自愈重試成功！耗時: {retry_duration:.2f}s", flush=True)
                    return retry_content
                except Exception as retry_err:
                    logger.error(f"[LLM Request #{req_id}] 自愈重試依然失敗: {retry_err}")

            duration = time.time() - start_time
            err_msg = (
                f"----------------------------------------------------------------------\n"
                f"❌ [LLM Request #{req_id}] 算力連線異常！耗時: {duration:.2f} 秒\n"
                f"  錯誤型別: {type(e).__name__}\n"
                f"  詳細訊息: {str(e)}\n"
                f"======================================================================\n"
            )
            _write_stream_log(err_msg)
            print(f"\n[MiroFish Backend] ❌ [LLM Request #{req_id}] 發生異常: {str(e)}", flush=True)
            logger.error(f"[LLM Request #{req_id}] 發生異常: {str(e)}", exc_info=True)
            raise e
    
    @staticmethod
    def _extract_json_candidate(text: str) -> str:
        """從混雜文字或思考歷程中，精準定位真實的 JSON 物件，絕不誤抓思考段落中的括號"""
        text = text.strip()
        if "</think>" in text:
            text = text.split("</think>", 1)[1].strip()
            
        # 1. 優先提取 ```json { ... } ``` 程式碼區塊（最標準且最常出現）
        code_blocks = re.findall(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
        for b in code_blocks:
            if re.search(r'\{\s*"[a-zA-Z0-9_]+"\s*:', b):
                return b.strip()
                
        # 2. 匹配以 {"key": 開頭並以 } 結尾的最外層完整 JSON 物件
        match_full = re.search(r'(\{\s*"[a-zA-Z0-9_]+"\s*:[\s\S]*\})', text)
        if match_full:
            return match_full.group(1).strip()
            
        # 3. 匹配以 {"key": 開頭的截斷 JSON（保留用於後續 _repair_truncated_json 補全括號）
        match_start = re.search(r'(\{\s*"[a-zA-Z0-9_]+"\s*:[\s\S]*)', text)
        if match_start:
            return match_start.group(1).strip()
            
        # 4. 陣列格式匹配
        match_arr = re.search(r'(\[[\s\S]*\])', text)
        if match_arr:
            return match_arr.group(1).strip()
            
        # 5. 兜底提取任何 { ... }
        match_fallback = re.search(r'(\{[\s\S]*\})', text)
        if match_fallback:
            return match_fallback.group(1).strip()
            
        return text

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        enable_thinking: Optional[bool] = False,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        傳送聊天請求並返回JSON（具備截斷自動修復功能）
        
        Args:
            messages: 訊息列表
            temperature: 溫度引數
            max_tokens: 最大token數（預設 4096，穩定且避免死循環霸佔顯存）
            enable_thinking: 是否啟用思考歷程（預設 False 免思考極速回應）
            max_retries: 最大重試次數
            
        Returns:
            解析後的JSON物件
        """
        last_error = None
        for attempt in range(max_retries):
            try:
                # 優先嘗試加入 response_format 抑制思考前綴；若伺服器不支援則自動降級為標準呼叫
                try:
                    response = self.chat(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        enable_thinking=enable_thinking,
                        response_format={"type": "json_object"}
                    )
                except Exception as ex:
                    if "response_format" in str(ex).lower() or "400" in str(ex):
                        response = self.chat(
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            enable_thinking=enable_thinking
                        )
                    else:
                        raise ex
            except Exception as e:
                logger.warning(f"嘗試第 {attempt + 1} 次: LLM 呼叫失敗: {e}")
                if attempt == max_retries - 1:
                    raise e
                time.sleep(2)
                continue
            
            # 精準提取真實 JSON 區塊，排除思考過程中的註解或字串雜訊
            cleaned_response = self._extract_json_candidate(response)

            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError as e:
                # 1. 優先嘗試專業 json_repair 引擎（專門秒級修復未轉義引號、缺失/多餘逗號、控制字元）
                try:
                    from json_repair import repair_json
                    repaired_str = repair_json(cleaned_response)
                    repaired_data = json.loads(repaired_str)
                    logger.info(f"第 {attempt + 1} 次: 成功透過 json_repair 引擎修復 JSON 語法瑕疵！")
                    _write_stream_log("  ✨ [JSON 智慧修復] 成功修復大模型 JSON 格式瑕疵（未轉義引號/逗號）！")
                    return repaired_data
                except Exception:
                    pass

                # 2. 嘗試傳統括號補全修復被截斷的 JSON
                repaired = _repair_truncated_json(cleaned_response)
                try:
                    repaired_data = json.loads(repaired)
                    logger.info(f"第 {attempt + 1} 次: 成功透過括號補全自動修復截斷的 JSON！")
                    _write_stream_log("  ℹ️ [JSON 修復] 成功自動補全被截斷之 JSON 結尾！")
                    return repaired_data
                except Exception:
                    pass
                
                last_error = f"LLM返回的JSON格式無效: {cleaned_response[:200]}"
                logger.warning(f"第 {attempt + 1} 次 JSON 解析失敗: {e}")
                _write_stream_log(f"  ⚠️ [警告] 第 {attempt + 1} 次 JSON 解析失敗，即將重試...")
                
        raise ValueError(last_error)

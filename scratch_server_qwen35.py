"""
內層核心推論服務 (server_qwen35.py)
運行於本地 127.0.0.1:8001 (對外隱蔽，由網關代理)
支援 Qwen3.5-27B 在 4 張 Tesla V100 上的原生多模態圖文推論與打字機 SSE 串流
"""

import os
import sys
import time
import json
import uuid
import threading
import asyncio
from typing import List, Optional, Dict, Any, Union
from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from transformers import (
    Qwen3_5ForConditionalGeneration,
    AutoProcessor,
    TextIteratorStreamer,
    StoppingCriteria,
    StoppingCriteriaList
)
from qwen_vl_utils import process_vision_info
from PIL import ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True


class AbortStoppingCriteria(StoppingCriteria):
    """自訂中止器：當連線中斷或取消事件觸發時，通知 HuggingFace 於下一個 Token 即刻煞車"""
    def __init__(self, stop_event: threading.Event):
        self.stop_event = stop_event

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs) -> bool:
        return self.stop_event.is_set()

# 確保輸出支援 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL_PATH = os.getenv("MODEL_PATH", "/mnt/r70640/models/Qwen3.5-27B")
MODEL_NAME = "Qwen3.5-27B"

# 全域模型、Processor 與 Tokenizer 實例
model = None
processor = None
tokenizer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, processor, tokenizer
    print("==================================================")
    print(f">>> [推論引擎] 正在載入 AutoProcessor: {MODEL_PATH}")
    print("==================================================")
    processor = AutoProcessor.from_pretrained(MODEL_PATH, trust_remote_code=True)
    tokenizer = processor.tokenizer

    print(f">>> [推論引擎] 正在將 Qwen3.5-27B 多模態模型均分加載至 4 張 V100 (FP16)...")
    t0 = time.time()
    model = Qwen3_5ForConditionalGeneration.from_pretrained(
        MODEL_PATH,
        device_map="balanced",
        torch_dtype=torch.float16,
        trust_remote_code=True
    )
    model.eval()
    print(f">>> [推論引擎] 模型加載成功！耗時: {time.time() - t0:.2f} 秒")
    print(f">>> [推論引擎] 顯存分配分佈: {getattr(model, 'hf_device_map', 'auto')}")
    print("==================================================")
    yield
    print(">>> [推論引擎] 正在卸載模型並釋放顯存...")
    del model
    del processor
    del tokenizer
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


app = FastAPI(title="Qwen3.5-27B Multimodal Native Inference Server", lifespan=lifespan)


# --- 資料結構定義 (相容 OpenAI 規範) ---
class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]], Any]


class ChatCompletionRequest(BaseModel):
    model: str = MODEL_NAME
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    max_tokens: Optional[int] = 2048
    stream: Optional[bool] = False
    enable_thinking: Optional[bool] = False  # 預設關閉思考歷程（免思考極速模式）
    chat_template_kwargs: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"


# --- 路由 1：探測可用模型 (GET /v1/models) ---
@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_NAME,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "lab"
            }
        ]
    }


# --- 路由 2：健康檢查 (GET /health) ---
@app.get("/health")
async def health_check():
    is_ready = (model is not None and processor is not None)
    gpu_mem = []
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            used = torch.cuda.memory_allocated(i) / (1024 ** 2)
            total = torch.cuda.get_device_properties(i).total_memory / (1024 ** 2)
            gpu_mem.append({"device": f"cuda:{i}", "used_mb": round(used, 1), "total_mb": round(total, 1)})
    return {
        "status": "healthy" if is_ready else "loading",
        "model": MODEL_NAME,
        "multimodal": True,
        "gpus": gpu_mem
    }


# --- 路由 3：對話生成 (POST /v1/chat/completions) ---
@app.post("/v1/chat/completions")
async def create_chat_completion(req: ChatCompletionRequest, raw_request: Request):
    if model is None or processor is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="模型尚未就緒，請稍後重試")

    req_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created_ts = int(time.time())

    # 1. 整理對話格式並適配 OpenAI 多模態格式至 Qwen-VL 規範
    has_image = False
    formatted_messages = []

    for m in req.messages:
        if isinstance(m.content, list):
            new_content = []
            for item in m.content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == "text":
                    new_content.append({"type": "text", "text": item.get("text", "")})
                elif item_type == "image_url":
                    # 轉換 OpenAI image_url 為 Qwen-VL 識別之 image
                    has_image = True
                    img_data = item.get("image_url", {})
                    url = img_data.get("url", "") if isinstance(img_data, dict) else str(img_data)
                    new_content.append({"type": "image", "image": url})
                elif item_type == "image":
                    has_image = True
                    new_content.append(item)
            formatted_messages.append({"role": m.role, "content": new_content})
        else:
            formatted_messages.append({"role": m.role, "content": str(m.content)})

    # 判斷思考模式開關（預設關閉以加速推論，亦支援客戶端傳入覆蓋）
    enable_thinking = req.enable_thinking
    if req.chat_template_kwargs:
        if "thinking" in req.chat_template_kwargs:
            enable_thinking = bool(req.chat_template_kwargs["thinking"])
        elif "enable_thinking" in req.chat_template_kwargs:
            enable_thinking = bool(req.chat_template_kwargs["enable_thinking"])

    # 套用 Jinja 聊天模板
    text_prompt = processor.apply_chat_template(
        formatted_messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=enable_thinking
    )

    # 2. 構建輸入張量 (若含圖片則透過 qwen_vl_utils 提取視覺張量)
    if has_image:
        try:
            image_inputs, video_inputs = process_vision_info(formatted_messages)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"圖像解析失敗，請確認圖片格式或 Base64 資料是否完整: {e}")
        inputs = processor(
            text=[text_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt"
        )
    else:
        inputs = processor(
            text=[text_prompt],
            padding=True,
            return_tensors="pt"
        )

    # 移至目標設備 (多卡 balanced 下將輸入張量傳入主卡 cuda:0)
    target_device = "cuda:0" if torch.cuda.is_available() else "cpu"
    inputs = {k: v.to(target_device) if hasattr(v, "to") else v for k, v in inputs.items()}

    # 初始化斷線停止控制器
    stop_event = threading.Event()
    stopping_criteria = StoppingCriteriaList([AbortStoppingCriteria(stop_event)])

    gen_kwargs = {
        **inputs,
        "max_new_tokens": req.max_tokens or 2048,
        "temperature": max(req.temperature or 0.7, 0.01),
        "top_p": req.top_p or 0.9,
        "do_sample": True,
        "pad_token_id": tokenizer.eos_token_id,
        "stopping_criteria": stopping_criteria
    }

    # 啟動非同步斷線監控協程
    async def _monitor_disconnect():
        try:
            while not stop_event.is_set():
                if await raw_request.is_disconnected():
                    print(f">>> [連線中斷] 偵測到客戶端斷開 ({req_id})，立即停止 GPU 推論！", flush=True)
                    stop_event.set()
                    break
                await asyncio.sleep(0.5)
        except Exception:
            pass

    # 3. 串流模式 (SSE Streaming)
    if req.stream:
        monitor_task = asyncio.create_task(_monitor_disconnect())
        streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
        gen_kwargs["streamer"] = streamer

        # 背景執行緒執行生成
        thread = threading.Thread(target=model.generate, kwargs=gen_kwargs)
        thread.start()

        async def event_generator():
            try:
                # 首個空 chunk 送出角色標記
                first_chunk = {
                    "id": req_id,
                    "object": "chat.completion.chunk",
                    "created": created_ts,
                    "model": MODEL_NAME,
                    "choices": [
                        {"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}
                    ]
                }
                yield f"data: {json.dumps(first_chunk, ensure_ascii=False)}\n\n"

                # 透過 asyncio.to_thread 非同步拉取 Token，避免阻塞 FastAPI 事件循環
                def get_next_token():
                    try:
                        return next(streamer)
                    except StopIteration:
                        return None

                while not stop_event.is_set():
                    text_chunk = await asyncio.to_thread(get_next_token)
                    if text_chunk is None:
                        break
                    if text_chunk:
                        chunk = {
                            "id": req_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": MODEL_NAME,
                            "choices": [
                                {"index": 0, "delta": {"content": text_chunk}, "finish_reason": None}
                            ]
                        }
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

                # 若未被強制中斷，正常送出結束標記
                if not stop_event.is_set():
                    finish_chunk = {
                        "id": req_id,
                        "object": "chat.completion.chunk",
                        "created": created_ts,
                        "model": MODEL_NAME,
                        "choices": [
                            {"index": 0, "delta": {}, "finish_reason": "stop"}
                        ]
                    }
                    yield f"data: {json.dumps(finish_chunk, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
            finally:
                stop_event.set()
                monitor_task.cancel()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    # 4. 非串流模式 (一次性回傳，移至獨立工作執行緒以解放事件循環)
    else:
        monitor_task = asyncio.create_task(_monitor_disconnect())

        def _do_generate():
            with torch.no_grad():
                return model.generate(**gen_kwargs)

        try:
            outputs = await asyncio.to_thread(_do_generate)
        finally:
            stop_event.set()
            monitor_task.cancel()

        if await raw_request.is_disconnected():
            if 'outputs' in locals():
                del outputs
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            raise HTTPException(status_code=499, detail="客戶端已斷線，已終止生成")

        prompt_len = inputs["input_ids"].shape[1]
        new_tokens = outputs[0][prompt_len:]
        reply_content = tokenizer.decode(new_tokens, skip_special_tokens=True)

        return {
            "id": req_id,
            "object": "chat.completion",
            "created": created_ts,
            "model": MODEL_NAME,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": reply_content},
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": prompt_len,
                "completion_tokens": len(new_tokens),
                "total_tokens": prompt_len + len(new_tokens)
            }
        }


if __name__ == "__main__":
    import uvicorn
    # 本地內部監聽 127.0.0.1:8001
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")

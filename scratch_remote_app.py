"""
外層守門網關 (FastAPI Gateway - app.py)
監聽 0.0.0.0:8000 (對外公開)
功能：
1. 身份認證 (Bearer Token，熱重載 keys.json)
2. 速率限制 (預設 30 RPM 滑動窗口)
3. 併發限制 (單一 Key 最多 2 個進行中推論)
4. 反向代理轉發至本地 127.0.0.1:8001 (長連線 SSE 串流)
5. 模型探測 (GET /v1/models) 與健康檢查 (GET /health)
"""

import os
import sys
import json
import time
from collections import defaultdict
from typing import Dict, List, Optional, Any

import httpx
import asyncio
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# 確保輸出支援 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_FILE = os.path.join(BASE_DIR, "keys.json")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001")
MODEL_NAME = "Qwen3.5-27B"

app = FastAPI(title="Lab LLM Gateway", version="1.0.0")

# 配置 CORS 跨域支援
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 狀態追蹤 (記憶體快取) ---
# key -> List[float] (請求時間戳)
rpm_records = defaultdict(list)
# key -> int (當前在線推論請求數)
active_concurrency = defaultdict(int)

# 快取金鑰資料與檔案最後修改時間
keys_cache: Dict[str, Any] = {}
keys_last_mtime: float = 0.0

# 全域核心推論排隊等候信號量 (嚴格放行 1 個推論任務獨享 GPU 全部算力與顯存頻寬，其餘請求非同步排隊交棒)
INFERENCE_SEMAPHORE = asyncio.Semaphore(1)


def get_keys() -> Dict[str, Any]:
    """熱重載讀取 keys.json，檔案異動即刻生效，無需重啟網關"""
    global keys_cache, keys_last_mtime
    try:
        if os.path.exists(KEYS_FILE):
            mtime = os.path.getmtime(KEYS_FILE)
            if mtime != keys_last_mtime:
                with open(KEYS_FILE, "r", encoding="utf-8") as f:
                    keys_cache = json.load(f)
                keys_last_mtime = mtime
        else:
            # 檔案不存在時預設空字典
            keys_cache = {}
    except Exception as e:
        print(f"⚠️ [網關警告] 讀取 keys.json 失敗: {e}")
    return keys_cache


def verify_api_key(request: Request) -> tuple[str, Dict[str, Any]]:
    """驗證請求攜帶之 API Key 是否合法與有效"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "message": "缺少 Authorization 標頭或格式錯誤，請使用 'Bearer <YOUR_API_KEY>'",
                    "type": "invalid_request_error",
                    "code": "unauthorized"
                }
            }
        )

    api_key = auth_header.replace("Bearer ", "").strip()
    all_keys = get_keys()

    if api_key not in all_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "message": "提供的 API Key 無效或不存在，請聯絡實驗室管理者申請。",
                    "type": "invalid_request_error",
                    "code": "invalid_api_key"
                }
            }
        )

    key_info = all_keys[api_key]
    if not key_info.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "message": "此 API Key 已被停用，請聯絡實驗室管理者復權。",
                    "type": "permission_error",
                    "code": "key_revoked"
                }
            }
        )

    return api_key, key_info


def check_rate_and_concurrency_limit(api_key: str, key_info: Dict[str, Any]):
    """檢查速率限制 (RPM) 與併發限制 (Concurrency)"""
    rpm_limit = key_info.get("rpm_limit", 30)
    concurrency_limit = key_info.get("concurrency_limit", 2)
    now = time.time()

    # 1. 檢查速率限制 (0 代表無限制)
    if rpm_limit > 0:
        # 清理 60 秒之前的舊紀錄
        timestamps = [t for t in rpm_records[api_key] if now - t < 60.0]
        rpm_records[api_key] = timestamps

        if len(timestamps) >= rpm_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": {
                        "message": f"已達每分鐘請求速率上限 ({rpm_limit} RPM)，請稍候再試。",
                        "type": "rate_limit_error",
                        "code": "rate_limit_exceeded"
                    }
                }
            )
        rpm_records[api_key].append(now)

    # 2. 檢查併發限制 (0 代表無限制)
    if concurrency_limit > 0:
        current_active = active_concurrency[api_key]
        if current_active >= concurrency_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": {
                        "message": f"已達單一金鑰最大併發推論上限 ({concurrency_limit} 個在線請求)，請等待前次生成完成。",
                        "type": "concurrency_limit_error",
                        "code": "concurrency_limit_exceeded"
                    }
                }
            )


# --- 路由 1：模型清單探測 (GET /v1/models) ---
@app.get("/v1/models")
async def get_models(request: Request):
    # 支援透過驗證或免驗證探測，確保 LM Studio / Continue 能即刻選取
    try:
        verify_api_key(request)
    except HTTPException:
        pass  # 允許預覽探測以提升客戶端相容性

    # 嘗試向本地 8001 查詢，若本地短暫重啟中則返回預設值
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{BACKEND_URL}/v1/models")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass

    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_NAME,
                "object": "model",
                "created": 1725696000,
                "owned_by": "lab"
            }
        ]
    }


# --- 路由 2：服務健康檢查 (GET /health) ---
@app.get("/health")
async def health_check():
    backend_status = "offline"
    backend_details = {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{BACKEND_URL}/health")
            if resp.status_code == 200:
                backend_status = "online"
                backend_details = resp.json()
    except httpx.TimeoutException:
        backend_status = "busy (推論運算中，等待回應逾時)"
    except Exception as e:
        err_msg = str(e) or type(e).__name__
        backend_status = f"unreachable ({err_msg})"

    return {
        "gateway": "healthy",
        "backend_url": BACKEND_URL,
        "backend_status": backend_status,
        "active_keys_count": len(get_keys()),
        "backend_details": backend_details
    }


# --- 路由 3：對話補全轉發 (POST /v1/chat/completions) ---
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    # 1. 身分驗證與限流防護
    api_key, key_info = verify_api_key(request)
    check_rate_and_concurrency_limit(api_key, key_info)

    # 2. 解析 Request Body
    try:
        req_body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="無效的 JSON 格式"
        )

    # 標記併發計數增加
    active_concurrency[api_key] += 1
    is_stream = req_body.get("stream", False)

    # 3. 獲取全域推論排隊權（若已有 2 個推論進行中，此請求將在此非同步排隊等候）
    await INFERENCE_SEMAPHORE.acquire()
    semaphore_released = False

    def release_semaphore():
        nonlocal semaphore_released
        if not semaphore_released:
            semaphore_released = True
            INFERENCE_SEMAPHORE.release()

    # 4. 反向代理轉發至本地 8001 推論服務
    client = httpx.AsyncClient(timeout=None)  # 長連線無超時，防止長文本斷線

    try:
        # A. 串流模式 (SSE Streaming)
        if is_stream:
            # 建立上游串流連線
            upstream_req = client.build_request(
                method="POST",
                url=f"{BACKEND_URL}/v1/chat/completions",
                json=req_body,
                headers={"Content-Type": "application/json"}
            )
            upstream_resp = await client.send(upstream_req, stream=True)

            if upstream_resp.status_code != 200:
                await upstream_resp.aread()
                active_concurrency[api_key] = max(0, active_concurrency[api_key] - 1)
                release_semaphore()
                await client.aclose()
                raise HTTPException(
                    status_code=upstream_resp.status_code,
                    detail=f"推論後端回傳錯誤: {upstream_resp.text}"
                )

            async def stream_generator():
                try:
                    async for chunk in upstream_resp.aiter_bytes():
                        # 即時偵測客戶端連線狀態，斷線則立刻跳出
                        if await request.is_disconnected():
                            print(f">>> [網關斷線偵測] 串流客戶端中斷連線，立即切斷 upstream 連線以觸發 GPU 煞車！", flush=True)
                            break
                        yield chunk
                finally:
                    # 串流結束或中斷，歸還併發計數與信號量，交棒給排隊中的下一個請求
                    active_concurrency[api_key] = max(0, active_concurrency[api_key] - 1)
                    release_semaphore()
                    await upstream_resp.aclose()
                    await client.aclose()

            return StreamingResponse(
                stream_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )

        # B. 非串流模式 (一次性回傳)
        else:
            # 啟動斷線監控協程：若使用者端關閉連線，主動切斷向 8001 的轉發以觸發 GPU 煞車
            stop_watcher = asyncio.Event()

            async def _watch_disconnect():
                try:
                    while not stop_watcher.is_set():
                        if await request.is_disconnected():
                            print(f">>> [網關斷線偵測] 非串流客戶端中斷連線，立即關閉對 8001 的連線以觸發 GPU 煞車！", flush=True)
                            await client.aclose()
                            break
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

            watcher_task = asyncio.create_task(_watch_disconnect())
            try:
                resp = await client.post(
                    f"{BACKEND_URL}/v1/chat/completions",
                    json=req_body,
                    headers={"Content-Type": "application/json"}
                )
                if resp.status_code != 200:
                    raise HTTPException(
                        status_code=resp.status_code,
                        detail=f"推論後端回傳錯誤: {resp.text}"
                    )
                return resp.json()
            finally:
                stop_watcher.set()
                watcher_task.cancel()
                active_concurrency[api_key] = max(0, active_concurrency[api_key] - 1)
                release_semaphore()
                await client.aclose()

    except HTTPException:
        active_concurrency[api_key] = max(0, active_concurrency[api_key] - 1)
        release_semaphore()
        await client.aclose()
        raise
    except Exception as e:
        active_concurrency[api_key] = max(0, active_concurrency[api_key] - 1)
        release_semaphore()
        await client.aclose()
        # 若是斷線引起的關閉，不視為錯誤
        if await request.is_disconnected():
            raise HTTPException(status_code=499, detail="客戶端已中斷請求")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"無法連線至本地核心推論服務 (127.0.0.1:8001): {e}"
        )


if __name__ == "__main__":
    import uvicorn
    # 對外監聽 0.0.0.0:8000
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

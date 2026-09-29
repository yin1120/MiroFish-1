@echo off
cd /d "%~dp0"
echo ======================================================================
echo    MiroFish SSH 隧道連線助手 (將遠端 8002 映射至本地 8000)
echo ======================================================================
echo.
echo [提示 1] 連上伺服器後，若尚未啟動 14B 模型，請於伺服器終端貼上以下指令：
echo.
echo   source /mnt/r70640/vllm_env/bin/activate
echo   CUDA_VISIBLE_DEVICES=0,2 python3 -m vllm.entrypoints.openai.api_server \
echo       --model Qwen/Qwen2.5-14B-Instruct \
echo       --download-dir /mnt/r70640/models \
echo       --port 8002 \
echo       --max-model-len 32768 \
echo       --gpu-memory-utilization 0.9 \
echo       --dtype float16 \
echo       --tensor-parallel-size 2 \
echo       --enforce-eager
echo.
echo [提示 2] 結束推演後，在終端按下 Ctrl+C 即可釋放 GPU 給其他同學！
echo ======================================================================
echo.
echo 正在建立 SSH 隧道至 140.138.175.53 (Local 8000 -^> Remote 8002)...
ssh -L 8000:localhost:8002 r70640@140.138.175.53
pause

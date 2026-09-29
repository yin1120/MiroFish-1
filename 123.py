import base64
import requests
import os

API_URL = "http://localhost:8000/v1/chat/completions"

def encode_image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def test_image_understanding(image_source: str, prompt_text: str):
    if image_source.startswith("http://") or image_source.startswith("https://"):
        image_payload = image_source
    else:
        if not os.path.exists(image_source):
            print(f"❌ 找不到本地圖片檔案: {image_source}")
            return
        base64_image = encode_image_to_base64(image_source)
        image_payload = f"data:image/jpeg;base64,{base64_image}"

    payload = {
        "model": "Qwen/Qwen2.5-VL-7B-Instruct",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_payload}
                    },
                    {
                        "type": "text",
                        "text": prompt_text
                    }
                ]
            }
        ],
        "max_tokens": 1024,
        "temperature": 0.2
    }

    print(f"📡 正在傳送圖片與請求至: {API_URL} (等待推論中，首次運行可能需要 1~2 分鐘)...")
    try:
        # 將 timeout 調大至 300 秒
        response = requests.post(API_URL, json=payload, timeout=300)
        response.raise_for_status()
        
        result = response.json()
        reply = result["choices"][0]["message"]["content"]
        
        print("\n" + "=" * 20 + " 模型辨識結果 " + "=" * 20)
        print(reply)
        print("=" * 54 + "\n")
        
    except requests.exceptions.Timeout:
        print("❌ 請求逾時：伺服器推論時間超過 300 秒。")
    except requests.exceptions.RequestException as e:
        print(f"❌ 請求失敗: {e}")

if __name__ == "__main__":
    # 建議先測試本地小圖或網路圖片
    test_url = "C:\\Users\\user\\Desktop\\用來辨識的照片\\用來辨識的照片\\face05.jpg"
    test_prompt = "請用繁體中文詳細描述這張圖片的內容。"
    
    test_image_understanding(test_url, test_prompt)


# import torch
# import uvicorn
# from fastapi import FastAPI, Request
# from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
# from qwen_vl_utils import process_vision_info

# # 強制關閉 cuDNN 卷積以相容 V100
# torch.backends.cudnn.enabled = False

# app = FastAPI()
# model_id = "Qwen/Qwen2.5-VL-7B-Instruct"

# print(f"正在載入模型: {model_id} ...")
# processor = AutoProcessor.from_pretrained(
#     model_id,
#     cache_dir="/mnt/r70640/models",
#     trust_remote_code=True
# )
# model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
#     model_id,
#     cache_dir="/mnt/r70640/models",
#     torch_dtype=torch.float16,
#     device_map="auto",
#     trust_remote_code=True
# )
# print("模型載入完成，API 伺服器就緒！")

# def convert_openai_to_qwen_format(messages):
#     """將 OpenAI 的 image_url 結構轉換為 Qwen-VL 支援的格式"""
#     converted_messages = []
#     for msg in messages:
#         role = msg.get("role", "user")
#         content = msg.get("content")

#         if isinstance(content, list):
#             new_content = []
#             for item in content:
#                 if isinstance(item, dict):
#                     if item.get("type") == "image_url":
#                         img_url_data = item.get("image_url", {})
#                         url = img_url_data.get("url") if isinstance(img_url_data, dict) else img_url_data
#                         new_content.append({"type": "image", "image": url})
#                     elif item.get("type") == "image":
#                         new_content.append(item)
#                     elif item.get("type") == "text":
#                         new_content.append(item)
#                     else:
#                         new_content.append(item)
#                 else:
#                     new_content.append(item)
#             converted_messages.append({"role": role, "content": new_content})
#         else:
#             converted_messages.append(msg)
#     return converted_messages

# @app.post("/v1/chat/completions")
# async def chat_completions(request: Request):
#     data = await request.json()
#     raw_messages = data.get("messages", [])
#     max_tokens = data.get("max_tokens", 4096)
#     temperature = data.get("temperature", 0.7)

#     # 格式轉換
#     messages = convert_openai_to_qwen_format(raw_messages)

#     text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
#     image_inputs, video_inputs = process_vision_info(messages)
#     inputs = processor(
#         text=[text],
#         images=image_inputs,
#         videos=video_inputs,
#         padding=True,
#         return_tensors="pt"
#     ).to("cuda")

#     with torch.inference_mode():
#         generated_ids = model.generate(
#             **inputs,
#             max_new_tokens=max_tokens,
#             temperature=temperature,
#             do_sample=(temperature > 0)
#         )

#     trimmed_ids = [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)]
#     output_text = processor.batch_decode(
#         trimmed_ids,
#         skip_special_tokens=True,
#         clean_up_tokenization_spaces=False
#     )[0]

#     return {
#         "id": "chatcmpl-vl",
#         "object": "chat.completion",
#         "choices": [{
#             "index": 0,
#             "message": {"role": "assistant", "content": output_text},
#             "finish_reason": "stop"
#         }]
#     }

# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=8000)
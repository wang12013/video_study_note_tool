# -*- coding: utf-8 -*-
import base64
import json
import pathlib

import httpx

from video_notes.core.config import Store

store = Store()
key = store.get_secret("dashscope_api_key")
headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}

frames = sorted(pathlib.Path(".devdata/frames").glob("f_*.jpg"))
picks = [frames[i] for i in range(0, len(frames), max(1, len(frames) // 10))][:10]

PROMPT = (
    "你是视频课件分析器。判断这张视频帧属于哪一类，并提取信息。只输出 JSON，不要解释。\n"
    "type 取值：slide=整页课件/PPT/PDF/思维导图/架构图；demo=软件操作界面/代码编辑器/终端/浏览器演示；"
    "person=人像/摄像头画面；other=其他（转场、黑屏、加载页）。\n"
    "若 type=slide，填写 page_title（页面标题）和 text（页面上全部文字，保留层级换行）；否则 text 留空。\n"
    '输出格式：{"type":"...","page_title":"...","text":"...","layout":"title_bullets|diagram|table|code|image|mixed","confidence":0.0}'
)

results = []
for path in picks:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "model": "qwen3-vl-plus",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
        "temperature": 0.1,
    }
    try:
        r = httpx.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
        if r.status_code != 200:
            results.append({"frame": path.name, "error": r.status_code, "body": r.text[:300]})
            continue
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        results.append({"frame": path.name, "content": content, "usage": usage})
    except Exception as exc:
        results.append({"frame": path.name, "error": repr(exc)})

pathlib.Path("m0_vlm.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
for item in results:
    print("==", item["frame"])
    if "error" in item:
        print("ERROR", item["error"], item.get("body", ""))
    else:
        print(item["content"][:400].replace("\n", " "))
        print("usage:", item.get("usage"))

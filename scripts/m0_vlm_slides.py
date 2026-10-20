# -*- coding: utf-8 -*-
import base64
import json
import pathlib

import httpx

from video_notes.core.config import Store

store = Store()
key = store.get_secret("dashscope_api_key")
headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}

PROMPT = (
    "你是视频课件分析器。判断这张视频帧属于哪一类，并提取信息。只输出 JSON，不要解释。\n"
    "type 取值：slide=整页课件/PPT/PDF/思维导图/架构图；demo=软件操作界面/代码编辑器/终端/浏览器演示；"
    "person=人像/摄像头画面；other=其他。\n"
    "若 type=slide，填写 page_title 和 text（页面上全部文字，保留层级换行）；否则 text 留空。\n"
    '输出格式：{"type":"...","page_title":"...","text":"...","layout":"title_bullets|diagram|table|code|image|mixed","confidence":0.0}'
)

def analyze(path: pathlib.Path) -> dict:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "model": "qwen3-vl-plus",
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
            {"type": "text", "text": PROMPT},
        ]}],
        "temperature": 0.1,
    }
    r = httpx.post("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", headers=headers, json=payload, timeout=120)
    if r.status_code != 200:
        return {"frame": path.name, "error": r.status_code, "body": r.text[:200]}
    data = r.json()
    return {"frame": path.name, "content": data["choices"][0]["message"]["content"], "usage": data.get("usage")}

all_results = {}
for name in ["short1", "short2"]:
    frames = sorted(pathlib.Path(f".devdata/frames_{name}").glob("f_*.jpg"))
    if not frames:
        continue
    picks = [frames[i] for i in range(0, len(frames), max(1, len(frames) // 8))][:8]
    results = [analyze(p) for p in picks]
    all_results[name] = results
    print("=====", name, "frames:", len(frames))
    for item in results:
        if "error" in item:
            print(item["frame"], "ERROR", item["error"], item.get("body", "")[:120])
        else:
            print(item["frame"], item["content"][:260].replace("\n", " "))

pathlib.Path("m0_vlm_slides.json").write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")

# -*- coding: utf-8 -*-
import json

import httpx

from video_notes.core.config import Store

store = Store()
key = store.get_secret("deepseek_api_key")
base = store.get("deepseek_base_url")
model = store.get("deepseek_model")
section_text = open(r"D:\notes_ai_generate\想找一款真正合心意的待办事项 App，我的需求是这样的\sections.json", encoding="utf-8").read()
print(section_text[:300])

system = "你是一位中文技术博主...（占位）"
user = "把下面这段口述整理成教程文章的一节，只输出 JSON：{\"title\": \"...\", \"markdown\": \"...\"}\n\n" + section_text

for extra in [
    {"response_format": {"type": "json_object"}},
    {"response_format": {"type": "json_object"}, "thinking": {"type": "disabled"}},
    {"max_tokens": 4000},
]:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.4,
        "max_tokens": 2400,
        **extra,
    }
    r = httpx.post(base + "/chat/completions", headers={"Authorization": "Bearer " + key}, json=payload, timeout=180)
    print("=== extra:", extra, "status:", r.status_code)
    if r.status_code != 200:
        print(r.text[:500])
        continue
    data = r.json()
    choice = data["choices"][0]
    msg = choice["message"]
    print("finish_reason:", choice.get("finish_reason"))
    print("usage:", data.get("usage"))
    print("has reasoning:", bool(msg.get("reasoning_content")))
    print("content head:", (msg.get("content") or "")[:400])
    print("content len:", len(msg.get("content") or ""))

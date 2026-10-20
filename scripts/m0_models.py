# -*- coding: utf-8 -*-
import base64
import json
import pathlib

import httpx

from video_notes.core.config import Store

store = Store()
dash_key = store.get_secret("dashscope_api_key")
ds_key = store.get_secret("deepseek_api_key")
headers = {"Authorization": "Bearer " + dash_key}

out = {}

r = httpx.get("https://dashscope.aliyuncs.com/compatible-mode/v1/models", headers=headers, timeout=30)
ids = [m.get("id") for m in r.json().get("data", [])]
out["count"] = len(ids)
for kw in ["asr", "audio", "vl", "ocr", "omni", "vision"]:
    out[kw] = [i for i in ids if kw in i.lower()]

# deepseek chat test
r2 = httpx.post(
    "https://api.deepseek.com/chat/completions",
    headers={"Authorization": "Bearer " + ds_key},
    json={"model": "deepseek-flash", "messages": [{"role": "user", "content": "回复两个字：收到"}], "max_tokens": 20},
    timeout=60,
)
out["deepseek_chat"] = [r2.status_code, r2.text[:400]]

audio = pathlib.Path(".devdata/dl/audio.wav").read_bytes()
b64 = base64.b64encode(audio).decode("ascii")
for model in ["qwen-audio-3.0-asr-flash", "fun-asr-flash-2026-06-15"]:
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": "data:audio/wav;base64," + b64, "format": "wav"}}]}
        ],
        "stream": False,
    }
    try:
        r3 = httpx.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
            timeout=180,
        )
        out[model] = [r3.status_code, r3.text[:1500]]
    except Exception as exc:
        out[model] = ["ERR", repr(exc)]

pathlib.Path("m0_models.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1)[:7000])

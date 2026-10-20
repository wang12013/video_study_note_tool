# -*- coding: utf-8 -*-
import base64
import json
import pathlib

import httpx

from video_notes.core.config import Store

store = Store()
ds_key = store.get_secret("deepseek_api_key")
dash_key = store.get_secret("dashscope_api_key")
ds_base = (store.get("deepseek_base_url") or "https://api.deepseek.com").rstrip("/")
ds_model = store.get("deepseek_model") or "deepseek-chat"

print("deepseek key:", ("set len=%d" % len(ds_key)) if ds_key else "MISSING")
print("dashscope key:", ("set len=%d" % len(dash_key)) if dash_key else "MISSING")

out = {"deepseek": {}, "dashscope": {}, "asr": {}}

if ds_key:
    try:
        r = httpx.get(ds_base + "/models", headers={"Authorization": "Bearer " + ds_key}, timeout=30)
        out["deepseek"]["models"] = [r.status_code, r.text[:600]]
    except Exception as exc:
        out["deepseek"]["models"] = ["ERR", repr(exc)]

if dash_key:
    try:
        r = httpx.get(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
            headers={"Authorization": "Bearer " + dash_key},
            timeout=30,
        )
        data = r.json() if r.status_code == 200 else None
        ids = [m.get("id") for m in (data or {}).get("data", [])]
        out["dashscope"]["models"] = [r.status_code, ids[:60] if ids else r.text[:400]]
    except Exception as exc:
        out["dashscope"]["models"] = ["ERR", repr(exc)]

    audio = pathlib.Path(".devdata/dl/audio.wav").read_bytes()
    b64 = base64.b64encode(audio).decode("ascii")
    for model in ["qwen3-asr-flash", "qwen-asr-flash", "paraformer-realtime-v2"]:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": "data:audio/wav;base64," + b64, "format": "wav"},
                        }
                    ],
                }
            ],
            "stream": False,
        }
        try:
            r = httpx.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={"Authorization": "Bearer " + dash_key, "Content-Type": "application/json"},
                json=payload,
                timeout=120,
            )
            out["asr"][model] = [r.status_code, r.text[:900]]
        except Exception as exc:
            out["asr"][model] = ["ERR", repr(exc)]

pathlib.Path("m0_api_check.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])

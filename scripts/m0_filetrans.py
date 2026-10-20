# -*- coding: utf-8 -*-
import json
import pathlib
import time

import httpx
from dashscope.utils.oss_utils import OssUtils

from video_notes.core.config import Store

store = Store()
key = store.get_secret("dashscope_api_key")
model = store.get("asr_model") or "qwen-audio-3.0-asr-flash-filetrans"
audio = pathlib.Path(".devdata/dl/audio.wav").resolve()

print("model:", model, "file:", audio, audio.stat().st_size)
t0 = time.time()
oss_url, cert = OssUtils.upload(model=model, file_path=str(audio), api_key=key)
print("uploaded:", oss_url, "in", round(time.time() - t0, 2), "s")

headers = {
    "Authorization": "Bearer " + key,
    "Content-Type": "application/json",
    "X-DashScope-Async": "enable",
    "X-DashScope-OssResourceResolve": "enable",
}
body = {
    "model": model,
    "input": {"file_urls": [oss_url]},
    "parameters": {"language": "zh", "channel_id": [0]},
}
r = httpx.post("https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription", headers=headers, json=body, timeout=60)
print("submit:", r.status_code, r.text[:400])
payload = r.json()
task_id = (payload.get("output") or {}).get("task_id")
if not task_id:
    raise SystemExit(1)

poll_headers = {"Authorization": "Bearer " + key, "X-DashScope-OssResourceResolve": "enable"}
tr = None
for i in range(120):
    time.sleep(3)
    tr = httpx.get(f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}", headers=poll_headers, timeout=60).json()
    status = (tr.get("output") or {}).get("task_status")
    print(f"poll {i}: {status}", flush=True)
    if status in ("SUCCEEDED", "FAILED"):
        break
out = (tr or {}).get("output") or {}
pathlib.Path("m0_filetrans_task.json").write_text(json.dumps(tr, ensure_ascii=False, indent=2), encoding="utf-8")
results = out.get("results") or []
if results and results[0].get("transcription_url"):
    url = results[0]["transcription_url"]
    data = httpx.get(url, timeout=60).text
    pathlib.Path("m0_filetrans_result.json").write_text(data, encoding="utf-8")
    parsed = json.loads(data)
    transcripts = parsed.get("transcripts") or []
    sentences = (transcripts[0].get("sentences") if transcripts else []) or []
    print("sentences:", len(sentences))
    for s in sentences[:8]:
        print(s.get("begin_time"), s.get("end_time"), str(s.get("text"))[:60])
    print("transcript keys:", list(transcripts[0].keys()) if transcripts else None)
else:
    print("no transcription_url")
    print(json.dumps(out, ensure_ascii=False)[:1000])

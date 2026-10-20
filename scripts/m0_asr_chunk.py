# -*- coding: utf-8 -*-
import base64
import json
import pathlib
import subprocess
import time

import httpx

from video_notes.core.config import Store

store = Store()
key = store.get_secret("dashscope_api_key")
headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}

work = pathlib.Path(".devdata/asr_chunks")
work.mkdir(parents=True, exist_ok=True)
for old in work.glob("*.wav"):
    old.unlink()

audio = pathlib.Path(".devdata/dl/audio.wav")
chunk_seconds = 30
out = []
index = 0
start = 0.0
while True:
    target = work / f"c{index:03d}.wav"
    cmd = [
        "runtime/ffmpeg.exe", "-y", "-ss", str(start), "-t", str(chunk_seconds),
        "-i", str(audio), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target),
    ]
    subprocess.run(cmd, capture_output=True)
    if not target.exists() or target.stat().st_size < 2000:
        break
    b64 = base64.b64encode(target.read_bytes()).decode("ascii")
    payload = {
        "model": "qwen3-asr-flash",
        "messages": [
            {"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": "data:audio/wav;base64," + b64, "format": "wav"}}]}
        ],
        "stream": False,
    }
    t0 = time.time()
    r = httpx.post(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        headers=headers, json=payload, timeout=180,
    )
    cost = time.time() - t0
    if r.status_code != 200:
        out.append({"index": index, "start": start, "error": r.status_code, "body": r.text[:300], "latency": round(cost, 2)})
        break
    data = r.json()
    text = data["choices"][0]["message"]["content"]
    out.append({
        "index": index,
        "start": round(start, 2),
        "end": round(start + chunk_seconds, 2),
        "text": text,
        "latency": round(cost, 2),
        "audio_tokens": data.get("usage", {}).get("prompt_tokens_details", {}).get("audio_tokens"),
    })
    index += 1
    start += chunk_seconds

pathlib.Path("m0_asr_chunks.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
for item in out:
    print(item.get("index"), item.get("start"), "->", item.get("end"), "latency", item.get("latency"))
    if "text" in item:
        print("  ", item["text"][:160])
    else:
        print("  ERROR", item.get("error"), item.get("body"))
print("total latency:", round(sum(i.get("latency", 0) for i in out), 2))

from __future__ import annotations

import base64
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from ..core.config import Store
from ..core import paths
from . import media


class AsrError(RuntimeError):
    pass


@dataclass
class Segment:
    t0: float
    t1: float
    text: str


@dataclass
class Transcript:
    source: str
    language: str
    duration: float
    segments: list[Segment]

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "language": self.language,
            "duration": round(self.duration, 2),
            "segments": [
                {"t0": round(s.t0, 2), "t1": round(s.t1, 2), "text": s.text}
                for s in self.segments
            ],
        }


DASHSCOPE = "https://dashscope.aliyuncs.com"
Progress = Callable[[str], None]


def _noop(message: str) -> None:
    pass


def transcribe(audio: Path, store: Store, progress: Progress = _noop) -> Transcript:
    key = store.get_secret("dashscope_api_key")
    if not key:
        raise AsrError("未配置 DashScope API Key，请在设置页填写")
    model = store.get("asr_model") or "qwen-audio-3.0-asr-flash-filetrans"
    duration = media.probe_duration(audio)
    progress(f"转写中（{model}，音频 {duration:.0f} 秒）")

    if "filetrans" in model:
        try:
            return _filetrans(audio, model, key, duration, progress)
        except Exception as exc:  # noqa: BLE001
            progress(f"文件转写失败，改用分片识别：{exc}")
            return _chunked(audio, key, duration, progress)
    return _chunked(audio, key, duration, progress)


# ---------------------------------------------------------------------------
# Primary: recorded-file transcription (sentence timestamps)
# ---------------------------------------------------------------------------
def _filetrans(audio: Path, model: str, key: str, duration: float, progress: Progress) -> Transcript:
    from dashscope.utils.oss_utils import OssUtils

    progress("上传音频到 DashScope 临时存储")
    oss_url, _cert = OssUtils.upload(model=model, file_path=str(audio.resolve()), api_key=key)
    if not oss_url:
        raise AsrError("上传失败")

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
    response = httpx.post(
        DASHSCOPE + "/api/v1/services/audio/asr/transcription",
        headers=headers,
        json=body,
        timeout=60,
    )
    payload = response.json()
    task_id = (payload.get("output") or {}).get("task_id")
    if response.status_code != 200 or not task_id:
        raise AsrError(f"提交转写任务失败: {response.text[:300]}")

    poll_headers = {"Authorization": "Bearer " + key, "X-DashScope-OssResourceResolve": "enable"}
    deadline = time.time() + 900
    result: dict = {}
    while time.time() < deadline:
        time.sleep(3)
        result = httpx.get(
            f"{DASHSCOPE}/api/v1/tasks/{task_id}", headers=poll_headers, timeout=60
        ).json()
        status = (result.get("output") or {}).get("task_status")
        if status == "SUCCEEDED":
            break
        if status == "FAILED":
            output = result.get("output") or {}
            raise AsrError(f"转写失败: {output.get('code')} {output.get('message')}")

    output = result.get("output") or {}
    results = output.get("results") or []
    if not results or not results[0].get("transcription_url"):
        raise AsrError("转写任务没有返回结果地址")
    data = httpx.get(results[0]["transcription_url"], timeout=120).json()

    segments: list[Segment] = []
    for transcript in data.get("transcripts") or []:
        for sentence in transcript.get("sentences") or []:
            text = str(sentence.get("text") or "").strip()
            if not text:
                continue
            segments.append(
                Segment(
                    t0=float(sentence.get("begin_time") or 0) / 1000.0,
                    t1=float(sentence.get("end_time") or 0) / 1000.0,
                    text=text,
                )
            )
    if not segments:
        raise AsrError("转写结果为空")
    progress(f"转写完成，共 {len(segments)} 句")
    return Transcript(source="filetrans", language="zh", duration=duration, segments=segments)


# ---------------------------------------------------------------------------
# Fallback: chunked OpenAI-compatible ASR (no timestamps, chunk offsets)
# ---------------------------------------------------------------------------
def _chunked(audio: Path, key: str, duration: float, progress: Progress, chunk: int = 30) -> Transcript:
    work = audio.parent / "asr_chunks"
    work.mkdir(parents=True, exist_ok=True)
    segments: list[Segment] = []
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    start = 0.0
    index = 0
    while start < duration - 0.5:
        target = work / f"c{index:03d}.wav"
        subprocess.run(
            [
                paths.ffmpeg_path(),
                "-y",
                "-ss",
                str(start),
                "-t",
                str(chunk),
                "-i",
                str(audio),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(target),
            ],
            capture_output=True,
        )
        if not target.exists() or target.stat().st_size < 2000:
            break
        payload = {
            "model": "qwen3-asr-flash",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": "data:audio/wav;base64,"
                                + base64.b64encode(target.read_bytes()).decode("ascii"),
                                "format": "wav",
                            },
                        }
                    ],
                }
            ],
            "stream": False,
        }
        response = httpx.post(
            DASHSCOPE + "/compatible-mode/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=180,
        )
        if response.status_code != 200:
            raise AsrError(f"分片识别失败: {response.text[:300]}")
        text = response.json()["choices"][0]["message"]["content"].strip()
        if text:
            segments.append(Segment(t0=start, t1=min(start + chunk, duration), text=text))
        progress(f"分片识别 {index + 1}，累计 {len(segments)} 段")
        index += 1
        start += chunk
    if not segments:
        raise AsrError("分片识别结果为空")
    return Transcript(source="chunked", language="zh", duration=duration, segments=segments)

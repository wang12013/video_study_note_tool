from __future__ import annotations

import base64
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable

import httpx
from PIL import Image

from ..core.config import Store
from . import media

VLM_PROMPT = (
    "你是视频课件分析器。判断这张视频帧属于哪一类，并提取信息。只输出 JSON，不要解释。\n"
    "type 取值：\n"
    "- slide：整页课件，如全屏展示的 PPT/PDF 页、思维导图、架构图、白板讲解页。画面应当只有页面内容本身，"
    "看不到浏览器标签页与地址栏、软件菜单栏、窗口标题栏、桌面图标、任务栏等界面元素。\n"
    "- demo：屏幕录制或软件操作，包括浏览器（能看到标签页/地址栏）、代码编辑器、终端、PPT 编辑界面、桌面操作。"
    "**即使演示画面中间是大段文字或文档，只要能看到浏览器或软件界面元素，就判为 demo。**\n"
    "- person：人像/摄像头画面；other：转场、黑屏、加载页。\n"
    "若 type=slide：page_title 填页面标题（没有就写空字符串），text 填页面上的全部文字，保留换行与层级。"
    "页面底部若有烧录的视频字幕，提取 text 时忽略字幕文字。\n"
    "若 type=demo 或 person，text 留空。\n"
    '输出格式：{"type":"...","page_title":"...","text":"...","layout":"title_bullets|diagram|table|code|image|mixed","confidence":0.0}'
)

DASHSCOPE = "https://dashscope.aliyuncs.com"

FrameProgress = Callable[[str], None]


@dataclass
class Slide:
    index: int
    t_start: float
    t_end: float
    image: str
    title: str
    text: str
    layout: str
    confidence: float

    def to_dict(self) -> dict:
        return asdict(self)


def _noop(message: str) -> None:
    pass


# ---------------------------------------------------------------------------
# frame hashing and clustering
# ---------------------------------------------------------------------------
def _dhash(path: Path, size: int = 8) -> int:
    with Image.open(path) as image:
        gray = image.convert("L").resize((size + 1, size), Image.LANCZOS)
        pixels = list(gray.getdata())
    bits = 0
    for row in range(size):
        offset = row * (size + 1)
        for col in range(size):
            bits = (bits << 1) | (1 if pixels[offset + col] > pixels[offset + col + 1] else 0)
    return bits


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _cluster(hashes: list[int], threshold: int = 8) -> list[list[int]]:
    if not hashes:
        return []
    clusters: list[list[int]] = [[0]]
    for index in range(1, len(hashes)):
        if _hamming(hashes[index], hashes[index - 1]) <= threshold:
            clusters[-1].append(index)
        else:
            clusters.append([index])
    return clusters


# ---------------------------------------------------------------------------
# VLM classification
# ---------------------------------------------------------------------------
def _analyze_frame(frame: Path, key: str) -> dict:
    payload = {
        "model": "qwen3-vl-plus",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/jpeg;base64," + base64.b64encode(frame.read_bytes()).decode("ascii")
                        },
                    },
                    {"type": "text", "text": VLM_PROMPT},
                ],
            }
        ],
        "temperature": 0.1,
    }
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    last = ""
    for _ in range(2):
        try:
            response = httpx.post(
                DASHSCOPE + "/compatible-mode/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                start, end = content.find("{"), content.rfind("}")
                if start != -1 and end != -1:
                    return json.loads(content[start : end + 1])
                last = "no json"
            else:
                last = response.text[:200]
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)
    return {"type": "other", "error": last}


def _merge_candidates(candidates: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for candidate in candidates:
        if not merged:
            merged.append(candidate)
            continue
        prev = merged[-1]
        same_title = bool(candidate["title"]) and candidate["title"] == prev["title"]
        text_a, text_b = set(prev["text"]), set(candidate["text"])
        containment = 0.0
        if text_a and text_b:
            containment = len(text_a & text_b) / min(len(text_a), len(text_b))
        if (same_title or containment >= 0.6) and candidate["t_start"] - prev["t_end"] < 40:
            prev["t_end"] = candidate["t_end"]
            prev["rep_t"] = candidate["rep_t"]
            if len(candidate["text"]) > len(prev["text"]):
                prev["text"] = candidate["text"]
            if not prev["title"]:
                prev["title"] = candidate["title"]
        else:
            merged.append(candidate)
    return merged


# ---------------------------------------------------------------------------
# public
# ---------------------------------------------------------------------------
def detect_slides(video: Path, workdir: Path, store: Store, progress: FrameProgress = _noop) -> list[Slide]:
    key = store.get_secret("dashscope_api_key")
    if not key:
        return []

    frames = media.extract_frames(video, workdir / "frames", fps=1.0, width=480)
    if not frames:
        return []
    progress(f"抽帧完成，共 {len(frames)} 帧")

    hashes = [_dhash(path) for path in frames]
    clusters = _cluster(hashes)
    min_len = 3
    stable = [cluster for cluster in clusters if len(cluster) >= min_len]
    progress(f"画面聚类：{len(clusters)} 段，其中稳定 {len(stable)} 段")

    max_slides = int(store.get("max_slides") or 150)
    cap = max(40, max_slides * 2)
    if len(stable) > cap:
        step = len(stable) / cap
        stable = [stable[int(i * step)] for i in range(cap)]
        progress(f"候选过多，均匀采样到 {len(stable)} 段")

    candidates = []
    for cluster in stable:
        start = float(cluster[0])
        end = float(cluster[-1] + 1)
        rep = max(cluster[0], cluster[-1] - 1)
        candidates.append({"t_start": start, "t_end": end, "rep_t": float(rep), "frame": frames[rep]})

    progress(f"识别课件页（{len(candidates)} 个候选，Qwen-VL）")
    results: list[dict] = [{} for _ in candidates]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_analyze_frame, item["frame"], key): index for index, item in enumerate(candidates)}
        done = 0
        for future in futures:
            index = futures[future]
            results[index] = future.result()
            done += 1
            if done % 20 == 0:
                progress(f"  已识别 {done}/{len(candidates)}")

    slides_raw = []
    for item, result in zip(candidates, results):
        if result.get("type") != "slide":
            continue
        slides_raw.append(
            {
                "t_start": item["t_start"],
                "t_end": item["t_end"],
                "rep_t": item["rep_t"],
                "title": str(result.get("page_title") or "").strip(),
                "text": str(result.get("text") or "").strip(),
                "layout": str(result.get("layout") or ""),
                "confidence": float(result.get("confidence") or 0),
            }
        )
    progress(f"课件页：{len(slides_raw)} 张")
    if not slides_raw:
        return []

    slides_raw = _merge_candidates(slides_raw)
    if len(slides_raw) > max_slides:
        step = len(slides_raw) / max_slides
        slides_raw = [slides_raw[int(i * step)] for i in range(max_slides)]
        progress(f"超过上限，保留 {len(slides_raw)} 张")

    slides_dir = workdir / "slides"
    slides_dir.mkdir(parents=True, exist_ok=True)
    for old in slides_dir.glob("*.png"):
        old.unlink()

    slides: list[Slide] = []
    for index, item in enumerate(slides_raw):
        image_path = slides_dir / f"slide_{index + 1:04d}.png"
        try:
            media.extract_frame_at(video, item["rep_t"], image_path)
        except media.MediaError:
            continue
        slides.append(
            Slide(
                index=index,
                t_start=item["t_start"],
                t_end=item["t_end"],
                image=str(image_path),
                title=item["title"],
                text=item["text"],
                layout=item["layout"],
                confidence=item["confidence"],
            )
        )
    progress(f"截图完成：{len(slides)} 张")
    return slides
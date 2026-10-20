from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..core import paths
from ..core.config import Store
from ..ingest.bilibili import BilibiliClient, VideoRef
from . import asr, download, media, notes, sections, slides

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(text: str, fallback: str = "未命名") -> str:
    cleaned = _UNSAFE.sub("_", text).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:80] or fallback


def _time_tag(seconds: float) -> str:
    total = int(max(0, seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}h{minutes:02d}m{secs:02d}s"


@dataclass
class BuildOptions:
    out_root: Path | None = None
    index: int = 0
    keep_video: bool = False
    title: str | None = None
    force: bool = False
    folder_name: str | None = None


@dataclass
class BuildResult:
    notes_path: Path
    transcript_path: Path
    sections_path: Path
    slides_path: Path | None
    workdir: Path
    title: str
    image_count: int
    warnings: list[str]


def _resolve_source(source: str, store: Store, options: BuildOptions, progress):
    path = Path(source)
    if path.exists() and path.is_file():
        return {
            "kind": "local",
            "video": path,
            "title": options.title or path.stem,
            "video_id": "local_" + safe_name(path.stem, "video"),
            "duration": media.probe_duration(path),
            "source": str(path),
        }

    progress("解析 B 站链接")
    client = BilibiliClient(cookie=store.get_secret("bilibili_cookie") or "")
    try:
        season, refs = client.enumerate(source)
    finally:
        client.close()
    if not refs:
        raise RuntimeError("没有解析到视频")
    if options.index >= len(refs):
        raise RuntimeError(f"序号超出范围：共 {len(refs)} 个视频")
    ref: VideoRef = refs[options.index]
    title = options.title or ref.title or ref.bvid
    return {
        "kind": "bilibili",
        "ref": ref,
        "title": title,
        "video_id": safe_name(ref.bvid + (f"_p{ref.page}" if ref.page > 1 else "")),
        "duration": float(ref.duration or 0),
        "source": ref.url,
    }


def _load_cached_slides(path: Path) -> list[slides.Slide]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        slides.Slide(
            index=int(item["index"]),
            t_start=float(item["t_start"]),
            t_end=float(item["t_end"]),
            image=str(item["image"]),
            title=str(item.get("title") or ""),
            text=str(item.get("text") or ""),
            layout=str(item.get("layout") or ""),
            confidence=float(item.get("confidence") or 0),
        )
        for item in data
    ]


def build(source: str, store: Store, options: BuildOptions | None = None, progress=print) -> BuildResult:
    options = options or BuildOptions()
    info = _resolve_source(source, store, options, progress)
    title = str(info["title"]).strip() or "未命名视频"

    workdir = paths.cache_dir() / "videos" / info["video_id"]
    workdir.mkdir(parents=True, exist_ok=True)
    meta_path = workdir / "meta.json"
    meta = {
        "title": title,
        "source": info["source"],
        "kind": info["kind"],
        "duration": info.get("duration"),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    video_path = info.get("video")
    if info["kind"] == "bilibili":
        cached = [p for p in workdir.glob("video.*") if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".flv")]
        if cached and not options.force:
            video_path = cached[0]
            progress("复用已下载的视频")
        else:
            video_path = download.download_video(info["ref"], workdir, store, progress=progress)
        meta["duration"] = media.probe_duration(video_path)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(f"视频：{title}（{float(meta.get('duration') or 0):.0f} 秒）")

    transcript_path = workdir / "transcript.json"
    if transcript_path.exists() and not options.force:
        progress("复用已有转写")
        cached_data = json.loads(transcript_path.read_text(encoding="utf-8"))
        transcript = asr.Transcript(
            source=cached_data.get("source", "cache"),
            language=cached_data.get("language", "zh"),
            duration=float(cached_data.get("duration") or 0),
            segments=[
                asr.Segment(t0=float(s["t0"]), t1=float(s["t1"]), text=s["text"])
                for s in cached_data.get("segments", [])
            ],
        )
    else:
        audio_path = media.extract_audio(video_path, workdir / "audio.wav")
        transcript = asr.transcribe(audio_path, store, progress=progress)
        transcript_path.write_text(
            json.dumps(transcript.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    slides_path = workdir / "slides.json"
    if slides_path.exists() and not options.force:
        progress("复用已有课件页")
        slide_list = _load_cached_slides(slides_path)
    else:
        progress("检测课件页")
        slide_list = slides.detect_slides(video_path, workdir, store, progress=progress)
        slides_path.write_text(
            json.dumps([s.to_dict() for s in slide_list], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    progress(f"课件页：{len(slide_list)} 张")

    progress("切分小节")
    section_list = sections.build_sections(transcript.segments, slides=slide_list)
    if not section_list:
        raise RuntimeError("转写结果为空，无法生成笔记")
    sections_path = workdir / "sections.json"
    sections.save_sections(sections_path, section_list)

    slide_map = {}
    for section in section_list:
        for slide_id in section.slide_ids:
            if 0 <= slide_id < len(slide_list):
                slide_map[section.index] = slide_list[slide_id]
                break

    note_sections, final_title, intro = notes.compose_note(
        title,
        float(meta.get("duration") or transcript.duration),
        section_list,
        slide_map,
        store,
        progress=progress,
    )

    out_root = options.out_root or Path(store.get("output_dir") or paths.default_library_dir())
    folder = safe_name(options.folder_name) if options.folder_name else safe_name(final_title)
    target_dir = out_root / folder
    if target_dir.exists():
        suffix = 2
        while (out_root / f"{folder}_{suffix}").exists():
            suffix += 1
        target_dir = out_root / f"{folder}_{suffix}"
    target_dir.mkdir(parents=True, exist_ok=True)

    images: dict[int, dict] = {}
    image_paths: list[str] = []
    if slide_map:
        assets_dir = target_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        for section_index, slide in slide_map.items():
            name = f"slide-{slide.index + 1:03d}-{_time_tag(slide.t_start)}.png"
            shutil.copy2(slide.image, assets_dir / name)
            images[section_index] = {
                "path": f"assets/{name}",
                "alt": slide.title or "课件截图",
            }
            image_paths.append(f"assets/{name}")

    markdown = notes.render_markdown(final_title, intro, note_sections, images)
    warnings = notes.quality_check(markdown, image_paths)

    notes_path = target_dir / "notes.md"
    notes_path.write_text(markdown, encoding="utf-8")
    shutil.copy2(transcript_path, target_dir / "transcript.json")
    shutil.copy2(sections_path, target_dir / "sections.json")
    shutil.copy2(meta_path, target_dir / "meta.json")
    if slides_path.exists():
        shutil.copy2(slides_path, target_dir / "slides.json")

    if not options.keep_video:
        cleanup_paths = [workdir / "audio.wav"]
        if info["kind"] == "bilibili":
            cleanup_paths.append(Path(video_path))
        for path in cleanup_paths:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass
        shutil.rmtree(workdir / "asr_chunks", ignore_errors=True)
        shutil.rmtree(workdir / "frames", ignore_errors=True)

    return BuildResult(
        notes_path=notes_path,
        transcript_path=target_dir / "transcript.json",
        sections_path=target_dir / "sections.json",
        slides_path=(target_dir / "slides.json") if slides_path.exists() else None,
        workdir=workdir,
        title=final_title,
        image_count=len(image_paths),
        warnings=warnings,
    )
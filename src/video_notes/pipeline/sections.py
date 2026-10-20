from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .asr import Segment


@dataclass
class Section:
    index: int
    t0: float
    t1: float
    text: str
    slide_ids: list[int] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.t1 - self.t0)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "t0": round(self.t0, 2),
            "t1": round(self.t1, 2),
            "slide_ids": self.slide_ids,
            "text": self.text,
        }


def _slide_at(slides, seconds: float):
    for slide in slides:
        if slide.t_start <= seconds < slide.t_end:
            return slide
    return None


def _dominant_slide(slides, t0: float, t1: float):
    best = None
    best_overlap = 0.0
    for slide in slides:
        overlap = min(t1, slide.t_end) - max(t0, slide.t_start)
        if overlap > best_overlap:
            best_overlap = overlap
            best = slide
    return best


def build_sections(
    segments: Iterable[Segment],
    slides=None,
    target_seconds: float = 150.0,
    min_seconds: float = 40.0,
    max_seconds: float = 240.0,
    gap_seconds: float = 1.2,
    slide_span: float = 18.0,
) -> list[Section]:
    """Group sentences into sections, splitting on slide changes and length."""
    sentences = [s for s in segments if s.text.strip()]
    if not sentences:
        return []
    slides = slides or []

    sections: list[Section] = []
    current: list[Segment] = []

    def flush() -> None:
        if not current:
            return
        t0, t1 = current[0].t0, current[-1].t1
        slide = _dominant_slide(slides, t0, t1) if slides else None
        sections.append(
            Section(
                index=len(sections),
                t0=t0,
                t1=t1,
                text="".join(s.text for s in current).strip(),
                slide_ids=[slide.index] if slide is not None else [],
            )
        )
        current.clear()

    for sentence in sentences:
        if current:
            span = sentence.t1 - current[0].t0
            gap = sentence.t0 - current[-1].t1
            active = _slide_at(slides, sentence.t0) if slides else None
            previous = _slide_at(slides, current[-1].t0) if slides else None
            slide_changed = active is not None and active is not previous
            if (
                span >= max_seconds
                or (slide_changed and span >= slide_span)
                or (span >= target_seconds and gap >= gap_seconds)
            ):
                flush()
        current.append(sentence)

    flush()

    merge_limit = 15.0 if slides else 20.0
    merged: list[Section] = []
    for section in sections:
        if merged and (section.duration < merge_limit or merged[-1].duration < merge_limit):
            prev = merged[-1]
            merged[-1] = Section(
                index=prev.index,
                t0=prev.t0,
                t1=section.t1,
                text=prev.text + section.text,
                slide_ids=prev.slide_ids or section.slide_ids,
            )
        else:
            merged.append(section)
    for index, section in enumerate(merged):
        section.index = index
    return merged


def save_sections(path: Path, sections: list[Section]) -> None:
    path.write_text(
        json.dumps([s.to_dict() for s in sections], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

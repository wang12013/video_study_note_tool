from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx

from ..core.config import Store
from .sections import Section

STYLE_SYSTEM = """你是一位中文技术博主，擅长把视频课程的口述内容和课件整理成结构清晰、可直接阅读的教程文章。

写作要求：
1. 只使用提供的讲稿与课件内容。不要补充里面没有的事实、数据、命令或结论；没讲清楚的地方写"（视频未展开）"。
2. 口吻像技术博客：先抛出问题再解释，段落之间自然承接，不要写成干巴巴的要点罗列。
3. 关键结论、设问用 **加粗**；只有并列项才用列表；补充说明可以用 > 引用。
4. 不写练习题、不写"本章小结 / 课后习题 / 总结与思考"这类模板段落。
5. 不出现时间戳，不出现"本视频 / UP 主 / 本期节目"这类元叙述，也不写"如果你也……不妨往下看"这类拉拢读者的话。
6. 正文不要出现任何 Markdown 标题符号（#），标题由外层统一生成；也不要重复本节标题。
7. 以段落叙述为主，列表最多用 1 处；不要把内容拆成一串要点。
8. 长度与讲稿匹配：每 1 分钟讲稿约 150~250 字。"""


class LLMError(RuntimeError):
    pass


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"无法解析 JSON: {text[:200]}")
    return json.loads(cleaned[start : end + 1])


def chat_json(
    store: Store,
    system: str,
    user: str,
    max_tokens: int = 2400,
    temperature: float = 0.45,
) -> dict:
    key = store.get_secret("deepseek_api_key")
    if not key:
        raise LLMError("未配置 DeepSeek API Key，请在设置页填写")
    base = (store.get("deepseek_base_url") or "https://api.deepseek.com").rstrip("/")
    model = store.get("deepseek_model") or "deepseek-flash"
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    base_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    variants = [
        {**base_payload, "response_format": {"type": "json_object"}, "thinking": {"type": "disabled"}},
        {**base_payload, "response_format": {"type": "json_object"}},
        base_payload,
    ]
    response = None
    for payload in variants:
        response = httpx.post(base + "/chat/completions", headers=headers, json=payload, timeout=180)
        if response.status_code == 200:
            break
    assert response is not None
    if response.status_code != 200:
        raise LLMError(f"模型调用失败 {response.status_code}: {response.text[:300]}")
    content = response.json()["choices"][0]["message"]["content"]
    try:
        return _parse_json(content)
    except (ValueError, json.JSONDecodeError) as exc:
        raise LLMError(f"模型输出不是合法 JSON: {exc}") from exc


@dataclass
class NoteSection:
    title: str
    markdown: str


def _section_prompt(
    video_title: str,
    duration: float,
    index: int,
    total: int,
    section: Section,
    prev_title: str,
    slide,
) -> str:
    parts = [
        f"视频标题：{video_title}",
        f"视频总时长：{duration / 60:.0f} 分钟",
        f"本节：第 {index + 1} 节（共 {total} 节）",
        f"上一节标题：{prev_title or '（无，这是第一节）'}",
    ]
    if slide is not None:
        parts.append("【本节课件页】")
        parts.append(f"页面标题：{slide.title or '（无标题）'}")
        parts.append("课件文字：")
        parts.append(slide.text or "（无）")
    parts.append("【本节讲稿】")
    parts.append(section.text)
    parts.append("")
    if slide is not None:
        parts.append(
            "本节配有一张课件截图。请在正文合适位置插入占位符 {img:1}（只出现一次），"
            "一般放在引出这一页内容的段落之后；不要写“如下图”之类的说明，也不要用其他图片标记。"
        )
    parts.append(
        '请把本节整理成教程文章中的一节。只输出 JSON：{"title": "本节标题（不超过 20 字，不加序号）", '
        '"markdown": "本节正文（3~8 段，段落之间空行，可用 **加粗** 和 > 引用）"}'
    )
    return "\n".join(parts)


def _global_prompt(video_title: str, duration: float, titles: list[str], excerpts: list[str]) -> str:
    lines = []
    for index, (title, excerpt) in enumerate(zip(titles, excerpts), 1):
        lines.append(f"{index}. {title}：{excerpt[:100]}")
    return f"""视频标题：{video_title}
视频总时长：{duration / 60:.0f} 分钟
各节标题与内容摘要：
{chr(10).join(lines)}

请为整篇文章生成总标题和导语。只输出 JSON：
{{"title": "文章标题（不超过 24 字，用陈述句，不要问句或感叹句）", "intro": "2 段导语：这篇文章讲什么、解决什么问题，直接进入主题"}}"""


def compose_note(
    video_title: str,
    duration: float,
    sections: list[Section],
    slide_map: dict[int, object],
    store: Store,
    progress=print,
) -> tuple[list[NoteSection], str, str]:
    notes: list[NoteSection] = []
    prev_title = ""
    total = len(sections)
    for index, section in enumerate(sections):
        slide = slide_map.get(section.index)
        progress(f"生成笔记 {index + 1}/{total}" + ("（含课件页）" if slide is not None else ""))
        user = _section_prompt(video_title, duration, index, total, section, prev_title, slide)
        try:
            data = chat_json(store, STYLE_SYSTEM, user)
            title = str(data.get("title") or f"第 {index + 1} 节").strip()
            markdown = str(data.get("markdown") or "").strip()
        except LLMError as exc:
            progress(f"第 {index + 1} 节生成失败：{exc}")
            title = f"第 {index + 1} 节"
            markdown = section.text
        notes.append(NoteSection(title=title, markdown=markdown))
        prev_title = title

    progress("生成总标题与导语")
    final_title = video_title
    intro = ""
    for attempt in range(2):
        try:
            data = chat_json(
                store,
                STYLE_SYSTEM if attempt == 0 else "你是中文技术编辑。只输出合法 JSON，不要输出任何解释。",
                _global_prompt(video_title, duration, [n.title for n in notes], [s.text for s in sections]),
                max_tokens=1200,
                temperature=0.3 if attempt == 0 else 0.15,
            )
            final_title = str(data.get("title") or video_title).strip()
            intro = str(data.get("intro") or "").strip()
            break
        except LLMError as exc:
            progress(f"总标题生成失败（第 {attempt + 1} 次）：{exc}")
    return notes, final_title, intro


def render_markdown(
    title: str,
    intro: str,
    sections: list[NoteSection],
    images: dict[int, dict],
) -> str:
    parts = [f"### {title}", ""]
    if intro:
        parts += [intro.strip(), ""]
    for index, section in enumerate(sections):
        body = section.markdown.strip()
        body = re.sub(r"\n*（视频未展开）\s*$", "", body)
        body = re.sub(r"(?m)^#{1,6}\s*(.+)$", r"**\1**", body)
        first_line, _, rest = body.partition("\n")
        if first_line.strip().strip("*").strip() == section.title.strip():
            body = rest.strip()

        info = images.get(index)
        token = "{img:1}"
        if info:
            image_md = f"![{info.get('alt') or '课件截图'}]({info.get('path')})"
            if token in body:
                body = body.replace(token, image_md, 1)
            else:
                paragraphs = body.split("\n\n")
                position = 1 if len(paragraphs) > 1 else len(paragraphs)
                paragraphs.insert(position, image_md)
                body = "\n\n".join(paragraphs)
        body = body.replace(token, "").replace("{img}", "")
        parts += [f"#### {section.title}", "", body.strip(), ""]
    return "\n".join(parts).strip() + "\n"


def quality_check(markdown: str, image_paths: list[str]) -> list[str]:
    warnings: list[str] = []
    if re.search(r"\[\d{1,2}:\d{2}", markdown):
        warnings.append("正文里出现了时间戳")
    for word in ("练习题", "课后习题", "本章小结", "作为AI", "作为 AI"):
        if word in markdown:
            warnings.append(f"出现禁用词：{word}")
    for path in image_paths:
        if path not in markdown:
            warnings.append(f"图片未插入：{path}")
    if markdown.count("#### ") < 1:
        warnings.append("没有分节")
    return warnings

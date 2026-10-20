from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from urllib.parse import parse_qs, urlsplit

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

API = "https://api.bilibili.com"
VIDEO_URL = "https://www.bilibili.com/video/{bvid}"


class BiliError(RuntimeError):
    def __init__(self, code: int, message: str, url: str = "") -> None:
        self.code = code
        self.message = message
        self.url = url
        super().__init__(f"[{code}] {message}")


@dataclass
class SeasonInfo:
    season_id: int
    mid: int
    title: str = ""
    intro: str = ""
    cover: str = ""
    url: str = ""


@dataclass
class VideoRef:
    bvid: str
    cid: int
    page: int
    title: str
    duration: int
    cover: str = ""
    desc: str = ""
    url: str = ""
    season_id: int = 0
    multi_page: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Target:
    kind: str  # season | video | fav
    url: str
    mid: int = 0
    season_id: int = 0
    bvid: str = ""
    page: int = 1
    media_id: int = 0


class BilibiliClient:
    def __init__(self, cookie: str = "", timeout: float = 20.0, delay: float = 0.25) -> None:
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
        }
        if cookie:
            headers["Cookie"] = cookie
        self.cookie = cookie
        self.delay = delay
        self.client = httpx.Client(headers=headers, timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    # low level -------------------------------------------------------
    def _get(self, path: str, **params) -> dict:
        url = f"{API}{path}"
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                time.sleep(1.0 * (attempt + 1))
                continue
            code = payload.get("code")
            if code != 0:
                raise BiliError(int(code or -1), str(payload.get("message") or "unknown"), url)
            return payload.get("data") or {}
        raise BiliError(-1, f"request failed: {last_error}", url)

    # resolution ------------------------------------------------------
    def resolve(self, raw: str) -> Target:
        url = (raw or "").strip()
        if not url:
            raise ValueError("empty url")
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url
        if "b23.tv" in url or "bili2233.cn" in url:
            url = self._expand_short(url)

        parts = urlsplit(url)
        host = (parts.netloc or "").lower()
        path = parts.path or ""
        query = parse_qs(parts.query)

        match = re.search(r"/video/(BV[0-9A-Za-z]+)", path, re.I)
        if match:
            page = int((query.get("p") or ["1"])[0])
            return Target(kind="video", url=url, bvid=match.group(1), page=page)
        match = re.search(r"/video/av(\d+)", path, re.I)
        if match:
            page = int((query.get("p") or ["1"])[0])
            return Target(kind="video", url=url, bvid=f"av{match.group(1)}", page=page)

        match = re.search(r"/(\d+)/lists/(\d+)", path)
        if match:
            return Target(
                kind="season", url=url, mid=int(match.group(1)), season_id=int(match.group(2))
            )
        match = re.search(r"/(\d+)/channel/collectiondetail", path)
        if match and query.get("sid"):
            return Target(
                kind="season",
                url=url,
                mid=int(match.group(1)),
                season_id=int(query["sid"][0]),
            )
        match = re.search(r"/medialist/(?:play|detail)/ml(\d+)", path)
        if match:
            return Target(kind="fav", url=url, media_id=int(match.group(1)))

        raise ValueError(f"无法识别的链接: {url}")

    def _expand_short(self, url: str) -> str:
        try:
            response = self.client.get(url)
            return str(response.url)
        except httpx.HTTPError as exc:
            raise BiliError(-1, f"短链解析失败: {exc}", url) from exc

    # data ------------------------------------------------------------
    def video_detail(self, bvid: str) -> dict:
        return self._get("/x/web-interface/view", bvid=bvid)

    def season_archives(self, mid: int, season_id: int) -> list[dict]:
        items: list[dict] = []
        page = 1
        while True:
            data = self._get(
                "/x/polymer/web-space/seasons_archives_list",
                mid=mid,
                season_id=season_id,
                sort_reverse="false",
                page_num=page,
                page_size=30,
            )
            archives = data.get("archives") or []
            items.extend(archives)
            page_info = data.get("page") or {}
            total = int(page_info.get("total") or len(items))
            if not archives or len(items) >= total:
                break
            page += 1
            time.sleep(self.delay)
        return items

    def fav_archives(self, media_id: int) -> list[dict]:
        items: list[dict] = []
        page = 1
        while True:
            data = self._get(
                "/x/v3/fav/resource/list",
                media_id=media_id,
                pn=page,
                ps=20,
                platform="web",
            )
            medias = data.get("medias") or []
            items.extend(medias)
            if not data.get("has_more") or not medias:
                break
            page += 1
            time.sleep(self.delay)
        return items

    def _refs_from_detail(
        self, bvid: str, season_id: int = 0, page_filter: int | None = None
    ) -> list[VideoRef]:
        detail = self.video_detail(bvid)
        pages = detail.get("pages") or []
        if not pages:
            pages = [
                {
                    "cid": detail.get("cid"),
                    "page": 1,
                    "part": detail.get("title", ""),
                    "duration": detail.get("duration", 0),
                }
            ]
        multi = len(pages) > 1
        refs: list[VideoRef] = []
        for page in pages:
            number = int(page.get("page") or 1)
            if page_filter is not None and number != page_filter:
                continue
            title = str(page.get("part") or detail.get("title") or "")
            if multi:
                title = f"P{number} {title}"
            url = VIDEO_URL.format(bvid=bvid) + (f"?p={number}" if multi else "")
            refs.append(
                VideoRef(
                    bvid=bvid,
                    cid=int(page.get("cid") or 0),
                    page=number,
                    title=title,
                    duration=int(page.get("duration") or 0),
                    cover=str(detail.get("pic") or ""),
                    desc=str(detail.get("desc") or ""),
                    url=url,
                    season_id=int(detail.get("season_id") or season_id or 0),
                    multi_page=multi,
                )
            )
        return refs

    # public ----------------------------------------------------------
    def enumerate(self, url: str) -> tuple[SeasonInfo | None, list[VideoRef]]:
        target = self.resolve(url)
        if target.kind == "season":
            archives = self.season_archives(target.mid, target.season_id)
            refs: list[VideoRef] = []
            season: SeasonInfo | None = None
            for index, archive in enumerate(archives):
                bvid = str(archive.get("bvid") or "")
                if not bvid:
                    continue
                detail = self.video_detail(bvid)
                if season is None:
                    raw = detail.get("ugc_season") or {}
                    season = SeasonInfo(
                        season_id=target.season_id,
                        mid=target.mid,
                        title=str(raw.get("title") or ""),
                        intro=str(raw.get("intro") or ""),
                        cover=str(raw.get("cover") or ""),
                        url=url,
                    )
                refs.extend(self._refs_from_detail_from(detail, bvid, target.season_id))
                if index + 1 < len(archives):
                    time.sleep(self.delay)
            return season, refs

        if target.kind == "video":
            detail = self.video_detail(target.bvid)
            refs = self._refs_from_detail_from(detail, target.bvid, 0)
            if target.page and len(refs) > 1:
                refs = [ref for ref in refs if ref.page == target.page]
            raw = detail.get("ugc_season") or {}
            season = None
            if raw.get("id"):
                season = SeasonInfo(
                    season_id=int(raw["id"]),
                    mid=int(raw.get("mid") or 0),
                    title=str(raw.get("title") or ""),
                    intro=str(raw.get("intro") or ""),
                    cover=str(raw.get("cover") or ""),
                    url=url,
                )
            return season, refs

        if target.kind == "fav":
            medias = self.fav_archives(target.media_id)
            refs = []
            for index, media in enumerate(medias):
                bvid = str(media.get("bvid") or "")
                if not bvid:
                    continue
                detail = self.video_detail(bvid)
                refs.extend(self._refs_from_detail_from(detail, bvid, 0))
                if index + 1 < len(medias):
                    time.sleep(self.delay)
            return None, refs

        raise ValueError(f"unsupported target: {target.kind}")

    def _refs_from_detail_from(self, detail: dict, bvid: str, season_id: int) -> list[VideoRef]:
        pages = detail.get("pages") or []
        if not pages:
            pages = [
                {
                    "cid": detail.get("cid"),
                    "page": 1,
                    "part": detail.get("title", ""),
                    "duration": detail.get("duration", 0),
                }
            ]
        multi = len(pages) > 1
        refs: list[VideoRef] = []
        for page in pages:
            number = int(page.get("page") or 1)
            title = str(page.get("part") or detail.get("title") or "")
            if multi:
                title = f"P{number} {title}"
            ref_url = VIDEO_URL.format(bvid=bvid) + (f"?p={number}" if multi else "")
            refs.append(
                VideoRef(
                    bvid=bvid,
                    cid=int(page.get("cid") or 0),
                    page=number,
                    title=title,
                    duration=int(page.get("duration") or 0),
                    cover=str(detail.get("pic") or ""),
                    desc=str(detail.get("desc") or ""),
                    url=ref_url,
                    season_id=int(detail.get("season_id") or season_id or 0),
                    multi_page=multi,
                )
            )
        return refs

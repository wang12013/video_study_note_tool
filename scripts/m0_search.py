# -*- coding: utf-8 -*-
import json
import re
import subprocess

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
h = {"User-Agent": UA, "Referer": "https://www.bilibili.com/"}

ids = ["115105778043488", "117437039183785", "115342957354884", "1652476819", "742735570", "407136059", "82996604", "117337097246380"]
rows = []
for aid in ids:
    try:
        r = httpx.get("https://api.bilibili.com/x/web-interface/view", headers=h, params={"aid": aid}, timeout=20)
        d = r.json().get("data") or {}
        rows.append({"aid": aid, "bvid": d.get("bvid"), "title": d.get("title"), "duration": d.get("duration"), "desc": (d.get("desc") or "")[:80]})
    except Exception as exc:
        rows.append({"aid": aid, "error": repr(exc)})

for row in rows:
    print(row)

json.dump(rows, open("m0_search.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

#!/usr/bin/env python3
"""Avisa a Bing/Yandex/Seznam (IndexNow) de todas las URLs del sitemap. Correr después de cada publicación.
Uso: python3 scripts/indexnow.py"""
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import config as C  # noqa: E402

sitemap = (Path(__file__).resolve().parent.parent / "dist" / "sitemap.xml").read_text(encoding="utf-8")
urls = re.findall(r"<loc>(.*?)</loc>", sitemap)
host = C.SITE_URL.split("//")[1]
body = json.dumps({"host": host, "key": C.INDEXNOW_KEY, "keyLocation": f"{C.SITE_URL}/{C.INDEXNOW_KEY}.txt", "urlList": urls}).encode()
req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body, headers={"Content-Type": "application/json; charset=utf-8"})
with urllib.request.urlopen(req, timeout=30) as r:
    print("IndexNow:", r.status, f"({len(urls)} URLs)")

import json, re, sys, glob, os, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

JST = timezone(timedelta(hours=9))
# (表示名, 運営会社, RSSのURL) 同じ運営会社は媒体数で1つと数える
FEEDS = [
    ("ITmedia AI+", "ITmedia", "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml"),
    ("GIGAZINE", "GIGAZINE", "https://gigazine.net/news/rss_2.0/"),
    ("INTERNET Watch", "Impress", "https://internet.watch.impress.co.jp/data/rss/1.0/iw/feed.rdf"),
    ("Impress Watch", "Impress", "https://www.watch.impress.co.jp/data/rss/1.0/ipw/feed.rdf"),
]
HOURS = 36        # 何時間前までの記事を対象にするか
SIMILAR = 0.35    # 同じ話題とみなすタイトルの類似度
AI = re.compile(r"(?<![A-Za-z])AI(?![a-z])|人工知能|機械学習|LLM|ChatGPT|Claude|Gemini|OpenAI|大規模言語|ディープラーニング", re.I)
DARK = re.compile("漏洩|流出|脆弱性|不正|詐欺|ハッキング|攻撃|訴訟|提訴|ディープフェイク|悪用|事故|規制|逮捕|障害|侵害|懸念|リスク")
BRIGHT = re.compile("発表|公開|開始|登場|新機能|開発|搭載|導入|向上|実現|リリース|強化|支援|活用|対応")


def local(tag):
    return tag.split("}")[-1]


def child(e, name):
    for c in e:
        if local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def parse_date(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    return d if d.tzinfo else d.replace(tzinfo=JST)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ai-news-app/1.0"})
    return urllib.request.urlopen(req, timeout=30).read()


def classify(text):
    d, b = bool(DARK.search(text)), bool(BRIGHT.search(text))
    return "dark" if d and not b else "bright" if b and not d else "neutral"


def bigrams(t):
    t = re.sub(r"\s|[「」『』、。!?:()（）]", "", t)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def similar(a, b):
    x, y = bigrams(a), bigrams(b)
    return bool(x and y) and len(x & y) / len(x | y) >= SIMILAR


def main():
    now = datetime.now(JST)
    items, seen, status = [], set(), []
    for name, company, url in FEEDS:
        try:
            root = ET.fromstring(fetch(url))
            n = 0
            for e in root.iter():
                if local(e.tag) != "item":
                    continue
                title, link = child(e, "title"), child(e, "link")
                desc = re.sub(r"<[^>]+>", "", child(e, "description")).strip()[:120]
                when = parse_date(child(e, "pubDate") or child(e, "date"))
                if not title or not link or link in seen:
                    continue
                if when and now - when > timedelta(hours=HOURS):
                    continue
                if not AI.search(title + " " + desc):
                    continue
                seen.add(link)
                n += 1
                items.append({"title": title, "summary": desc, "link": link, "source": name,
                              "company": company, "category": classify(title + " " + desc)})
            status.append({"name": name, "ok": True, "items": n})
        except Exception as ex:
            status.append({"name": name, "ok": False, "error": str(ex)[:100]})
    for s in status:
        print(s)

    groups = []
    for it in items:
        for g in groups:
            if similar(g["title"], it["title"]):
                g["members"].append(it)
                break
        else:
            groups.append({"title": it["title"], "members": [it]})
    out = []
    for g in groups:
        rep = g["members"][0]
        out.append({"title": rep["title"], "summary": rep["summary"], "link": rep["link"],
                    "source": rep["source"], "category": rep["category"],
                    "count": len({m["company"] for m in g["members"]}),
                    "others": [{"source": m["source"], "link": m["link"]} for m in g["members"][1:]]})
    out.sort(key=lambda g: -g["count"])

    os.makedirs("data", exist_ok=True)
    today = now.strftime("%Y-%m-%d")
    with open(f"data/{today}.json", "w", encoding="utf-8") as f:
        json.dump({"date": today, "groups": out}, f, ensure_ascii=False, indent=1)
    dates = sorted((os.path.basename(p)[:-5] for p in glob.glob("data/20*.json")), reverse=True)
    with open("data/index.json", "w", encoding="utf-8") as f:
        json.dump(dates, f)
    with open("data/status.json", "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=1)
    if not any(s["ok"] for s in status):
        sys.exit(1)


if __name__ == "__main__":
    main()

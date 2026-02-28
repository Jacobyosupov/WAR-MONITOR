"""
שליפת חדשות מ-RSS של מקורות ישראליים + NewsAPI
עם דירוג דחיפות אוטומטי
"""

import asyncio
import httpx
import feedparser
import re
from datetime import datetime, timezone
from typing import Optional

# ── מקורות RSS ישראליים ─────────────────────────────

RSS_SOURCES = [
    {"name": "ynet",        "url": "https://www.ynet.co.il/Integration/StoryRss2.xml",          "lang": "he"},
    {"name": "N12",         "url": "https://www.mako.co.il/rss/31750a2610f26110VgnVCM1000005201000aRCRD.xml", "lang": "he"},
    {"name": "Walla",       "url": "https://rss.walla.co.il/feed/1",                             "lang": "he"},
    {"name": "הארץ",        "url": "https://www.haaretz.co.il/cmlink/1.1647970",                 "lang": "he"},
    {"name": "Times of Israel", "url": "https://www.timesofisrael.com/feed/",                    "lang": "en"},
    {"name": "Jerusalem Post",  "url": "https://www.jpost.com/rss/rssfeedsfrontpage.aspx",       "lang": "en"},
    {"name": "Reuters MidEast", "url": "https://feeds.reuters.com/Reuters/worldNews",            "lang": "en"},
]

# ── מילות מפתח לפי דחיפות ───────────────────────────

LEVEL_3_KEYWORDS = [  # 🔴 קריטי
    "אזעקה", "טיל", "פצצה", "התקפה", "פיגוע", "הפצצה",
    "missile", "attack", "explosion", "rocket", "alert", "strike",
    "nuclear", "גרעין", "נשק", "כיפת ברזל"
]

LEVEL_2_KEYWORDS = [  # 🟠 דחוף
    "איראן", "iran", "חיזבאללה", "hezbollah", "חמאס", "hamas",
    "צבא", "military", "idf", "צה\"ל", "לחימה", "combat",
    "חרבות ברזל", "מלחמה", "war", "sanctions", "סנקציות"
]

LEVEL_1_KEYWORDS = [  # 🟡 רגיל
    "ישראל", "israel", "מזרח תיכון", "middle east",
    "דיפלומטיה", "diplomatic", "ביידן", "biden", "נתניהו",
    "נשק", "weapons", "הסכם", "deal", "משא ומתן"
]

REGION_KEYWORDS = {
    "north":  ["צפון", "חיפה", "גליל", "לבנון", "north", "haifa", "galilee"],
    "south":  ["דרום", "עזה", "באר שבע", "south", "gaza", "beer sheva"],
    "center": ["תל אביב", "מרכז", "tel aviv", "center", "jerusalem", "ירושלים"],
    "all":    [],
}


def detect_level(text: str) -> int:
    text_lower = text.lower()
    if any(k.lower() in text_lower for k in LEVEL_3_KEYWORDS):
        return 3
    if any(k.lower() in text_lower for k in LEVEL_2_KEYWORDS):
        return 2
    if any(k.lower() in text_lower for k in LEVEL_1_KEYWORDS):
        return 1
    return 0


def detect_region(text: str) -> str:
    text_lower = text.lower()
    for region, keywords in REGION_KEYWORDS.items():
        if region == "all":
            continue
        if any(k.lower() in text_lower for k in keywords):
            return region
    return "all"


def level_emoji(level: int) -> str:
    return {3: "🔴", 2: "🟠", 1: "🟡", 0: "⚪"}.get(level, "⚪")


def level_label(level: int) -> str:
    return {3: "קריטי", 2: "דחוף", 1: "רגיל", 0: "כללי"}.get(level, "כללי")


# ── שליפת RSS ────────────────────────────────────────

async def fetch_rss(source: dict) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            r = await client.get(source["url"])
            feed = feedparser.parse(r.text)
            articles = []
            for entry in feed.entries[:10]:
                title = entry.get("title", "")
                desc = entry.get("summary", entry.get("description", ""))
                url = entry.get("link", "")
                published = entry.get("published", "")

                combined = f"{title} {desc}"
                level = detect_level(combined)
                if level == 0:
                    continue  # לא רלוונטי

                articles.append({
                    "title": title,
                    "description": re.sub(r"<[^>]+>", "", desc)[:200],
                    "url": url,
                    "source": source["name"],
                    "lang": source["lang"],
                    "level": level,
                    "region": detect_region(combined),
                    "published": published,
                })
            return articles
    except Exception as e:
        return []


async def fetch_all_rss() -> list[dict]:
    tasks = [fetch_rss(src) for src in RSS_SOURCES]
    results = await asyncio.gather(*tasks)
    articles = []
    for result in results:
        articles.extend(result)
    # מיון לפי דחיפות
    articles.sort(key=lambda x: x["level"], reverse=True)
    return articles


# ── NewsAPI ──────────────────────────────────────────

async def fetch_newsapi(query: str, api_key: str, lang: str = "en", page_size: int = 5) -> list[dict]:
    if not api_key or api_key == "YOUR_NEWS_KEY":
        return []
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query, "language": lang,
        "sortBy": "publishedAt", "pageSize": page_size,
        "apiKey": api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            data = r.json()
            articles = []
            for a in data.get("articles", []):
                combined = f"{a.get('title','')} {a.get('description','')}"
                level = detect_level(combined)
                articles.append({
                    "title": a.get("title", ""),
                    "description": (a.get("description") or "")[:200],
                    "url": a.get("url", ""),
                    "source": a.get("source", {}).get("name", ""),
                    "lang": lang,
                    "level": level,
                    "region": detect_region(combined),
                    "published": a.get("publishedAt", ""),
                })
            return articles
    except Exception:
        return []


# ── פורמט הודעה ──────────────────────────────────────

def format_article(article: dict) -> str:
    emoji = level_emoji(article["level"])
    label = level_label(article["level"])
    title = article.get("title", "")
    source = article.get("source", "")
    desc = article.get("description", "")
    url = article.get("url", "")
    region_tag = f"📍 {article['region']}" if article.get("region") and article["region"] != "all" else ""

    return (
        f"{emoji} *[{label}]* {title}\n"
        f"🗞 {source} {region_tag}\n"
        f"{desc}\n"
        f"🔗 [קרא עוד]({url})"
    )

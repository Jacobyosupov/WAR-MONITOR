"""
War Monitor – Flask Backend API
מגיש חדשות מ-RSS ו-NewsAPI לאתר
"""

import os
import asyncio
import time
from threading import Thread
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

from database import init_db, was_sent, mark_sent, cleanup_old_articles
from fetcher import fetch_all_rss, fetch_newsapi, detect_level, detect_region

# ── הגדרות ──────────────────────────────────────────
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "300"))  # שניות

app = Flask(__name__, static_folder="static")
CORS(app)

# ── Cache ────────────────────────────────────────────
cache = {
    "articles": [],
    "last_fetch": 0,
    "stats": {"critical": 0, "urgent": 0, "regular": 0, "total": 0}
}


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(coro)
    loop.close()
    return result


async def fetch_fresh():
    """שלוף חדשות טריות מכל המקורות"""
    articles = await fetch_all_rss()
    if NEWS_API_KEY:
        api_en = await fetch_newsapi("Iran Israel attack war military", NEWS_API_KEY, "en", 8)
        api_he = await fetch_newsapi("איראן ישראל מלחמה צבא", NEWS_API_KEY, "he", 5)
        articles += api_en + api_he

    # מיין לפי דחיפות
    articles.sort(key=lambda x: x.get("level", 0), reverse=True)

    # הגבל ל-50
    return articles[:50]


def refresh_cache():
    """רענן cache ברקע"""
    while True:
        try:
            articles = run_async(fetch_fresh())
            stats = {
                "critical": sum(1 for a in articles if a.get("level") == 3),
                "urgent":   sum(1 for a in articles if a.get("level") == 2),
                "regular":  sum(1 for a in articles if a.get("level") == 1),
                "total":    len(articles)
            }
            cache["articles"] = articles
            cache["stats"] = stats
            cache["last_fetch"] = time.time()
            print(f"✅ Cache refreshed: {len(articles)} articles")
        except Exception as e:
            print(f"❌ Cache refresh error: {e}")
        time.sleep(REFRESH_INTERVAL)


# ── API Routes ───────────────────────────────────────

@app.route("/api/news")
def get_news():
    """
    GET /api/news
    ?level=1,2,3   – סינון לפי דחיפות
    ?lang=he,en     – סינון לפי שפה
    ?region=north   – סינון לפי אזור
    ?q=...          – חיפוש חופשי
    ?limit=20       – הגבלת תוצאות
    """
    articles = list(cache["articles"])

    # פילטרים
    level_filter = request.args.get("level")
    lang_filter  = request.args.get("lang")
    region_filter = request.args.get("region")
    query        = request.args.get("q", "").strip().lower()
    limit        = int(request.args.get("limit", 30))

    if level_filter:
        levels = [int(l) for l in level_filter.split(",")]
        articles = [a for a in articles if a.get("level") in levels]

    if lang_filter:
        articles = [a for a in articles if a.get("lang") == lang_filter]

    if region_filter and region_filter != "all":
        articles = [a for a in articles if a.get("region") in [region_filter, "all"]]

    if query:
        articles = [
            a for a in articles
            if query in (a.get("title","") + " " + a.get("description","")).lower()
        ]

    return jsonify({
        "articles": articles[:limit],
        "count": len(articles),
        "cached_at": cache["last_fetch"],
        "stats": cache["stats"]
    })


@app.route("/api/stats")
def get_stats():
    return jsonify({
        "stats": cache["stats"],
        "cached_at": cache["last_fetch"],
        "refresh_interval": REFRESH_INTERVAL
    })


@app.route("/api/search")
def search():
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify({"articles": [], "count": 0})

    results = [
        a for a in cache["articles"]
        if q in (a.get("title","") + " " + a.get("description","")).lower()
    ]
    return jsonify({"articles": results, "count": len(results), "query": q})


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "articles": len(cache["articles"]),
        "last_fetch": cache["last_fetch"],
        "news_api": bool(NEWS_API_KEY)
    })


# ── Static files ─────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("static", path)


# ── Startup ──────────────────────────────────────────

def start():
    init_db()

    # טען cache ראשוני
    try:
        articles = run_async(fetch_fresh())
        cache["articles"] = articles
        cache["last_fetch"] = time.time()
        cache["stats"] = {
            "critical": sum(1 for a in articles if a.get("level") == 3),
            "urgent":   sum(1 for a in articles if a.get("level") == 2),
            "regular":  sum(1 for a in articles if a.get("level") == 1),
            "total":    len(articles)
        }
        print(f"✅ Initial fetch: {len(articles)} articles")
    except Exception as e:
        print(f"⚠️ Initial fetch failed: {e}")

    # הפעל רענון ברקע
    t = Thread(target=refresh_cache, daemon=True)
    t.start()

    port = int(os.getenv("PORT", 5000))
    print(f"🌐 Server running on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    start()

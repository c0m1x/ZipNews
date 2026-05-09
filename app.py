#!/usr/bin/env python3
"""
World Signal: a key-free global news map.

Run with:
    python3 app.py
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

import csv
import hashlib
import html
import io
import json
import os
import re
import time
import unicodedata
import xml.etree.ElementTree as ET


PORT = int(os.environ.get("PORT", "8000"))
NEWS_CACHE_SECONDS = int(os.environ.get("NEWS_CACHE_SECONDS", "600"))
MARKET_CACHE_SECONDS = int(os.environ.get("MARKET_CACHE_SECONDS", "120"))
FEED_TIMEOUT_SECONDS = int(os.environ.get("FEED_TIMEOUT_SECONDS", "8"))
MAX_ITEMS_PER_SOURCE = int(os.environ.get("MAX_ITEMS_PER_SOURCE", "16"))
USER_AGENT = (
    "WorldSignal/0.1 (+local personal dashboard; RSS aggregation; "
    "contact: local-user)"
)


CATEGORIES = {
    "news": {"label": "News", "color": "#2f6fed"},
    "economy": {"label": "Economy", "color": "#0f9f8f"},
    "politics": {"label": "Politics", "color": "#d05a3b"},
    "sport": {"label": "Sport", "color": "#7b56d9"},
    "cyber": {"label": "Cybersecurity", "color": "#d69b16"},
}


SOURCES = [
    {
        "name": "BBC World",
        "category": "news",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "region": "Europe",
        "country": "United Kingdom",
        "lat": 51.5072,
        "lon": -0.1276,
    },
    {
        "name": "The Guardian World",
        "category": "news",
        "url": "https://www.theguardian.com/world/rss",
        "region": "Europe",
        "country": "United Kingdom",
        "lat": 51.5072,
        "lon": -0.1276,
    },
    {
        "name": "Al Jazeera",
        "category": "news",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "region": "Middle East",
        "country": "Qatar",
        "lat": 25.2854,
        "lon": 51.5310,
    },
    {
        "name": "Google News Portugal",
        "category": "news",
        "url": "https://news.google.com/rss?hl=pt-PT&gl=PT&ceid=PT:pt",
        "region": "Europe",
        "country": "Portugal",
        "lat": 38.7223,
        "lon": -9.1393,
    },
    {
        "name": "Google News Brazil",
        "category": "news",
        "url": "https://news.google.com/rss?hl=pt-BR&gl=BR&ceid=BR:pt-419",
        "region": "South America",
        "country": "Brazil",
        "lat": -15.7939,
        "lon": -47.8828,
    },
    {
        "name": "Google News India",
        "category": "news",
        "url": "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
        "region": "Asia-Pacific",
        "country": "India",
        "lat": 28.6139,
        "lon": 77.2090,
    },
    {
        "name": "Google News Australia",
        "category": "news",
        "url": "https://news.google.com/rss?hl=en-AU&gl=AU&ceid=AU:en",
        "region": "Oceania",
        "country": "Australia",
        "lat": -35.2809,
        "lon": 149.1300,
    },
    {
        "name": "Google News South Africa",
        "category": "news",
        "url": "https://news.google.com/rss?hl=en-ZA&gl=ZA&ceid=ZA:en",
        "region": "Africa",
        "country": "South Africa",
        "lat": -25.7479,
        "lon": 28.2293,
    },
    {
        "name": "Google News Canada",
        "category": "news",
        "url": "https://news.google.com/rss?hl=en-CA&gl=CA&ceid=CA:en",
        "region": "North America",
        "country": "Canada",
        "lat": 45.4215,
        "lon": -75.6972,
    },
    {
        "name": "Google News UAE",
        "category": "news",
        "url": "https://news.google.com/rss?hl=en-AE&gl=AE&ceid=AE:en",
        "region": "Middle East",
        "country": "United Arab Emirates",
        "lat": 24.4539,
        "lon": 54.3773,
    },
    {
        "name": "BBC Business",
        "category": "economy",
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "region": "Europe",
        "country": "United Kingdom",
        "lat": 51.5072,
        "lon": -0.1276,
    },
    {
        "name": "NPR Business",
        "category": "economy",
        "url": "https://feeds.npr.org/1006/rss.xml",
        "region": "North America",
        "country": "United States",
        "lat": 38.9072,
        "lon": -77.0369,
    },
    {
        "name": "CNBC Economy",
        "category": "economy",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147",
        "region": "North America",
        "country": "United States",
        "lat": 40.7128,
        "lon": -74.0060,
    },
    {
        "name": "MarketWatch",
        "category": "economy",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "region": "North America",
        "country": "United States",
        "lat": 40.7128,
        "lon": -74.0060,
    },
    {
        "name": "Yahoo Finance",
        "category": "economy",
        "url": "https://finance.yahoo.com/news/rssindex",
        "region": "North America",
        "country": "United States",
        "lat": 40.7128,
        "lon": -74.0060,
    },
    {
        "name": "NPR Politics",
        "category": "politics",
        "url": "https://feeds.npr.org/1014/rss.xml",
        "region": "North America",
        "country": "United States",
        "lat": 38.9072,
        "lon": -77.0369,
    },
    {
        "name": "Politico",
        "category": "politics",
        "url": "https://rss.politico.com/politics-news.xml",
        "region": "North America",
        "country": "United States",
        "lat": 38.9072,
        "lon": -77.0369,
    },
    {
        "name": "BBC Politics",
        "category": "politics",
        "url": "https://feeds.bbci.co.uk/news/politics/rss.xml",
        "region": "Europe",
        "country": "United Kingdom",
        "lat": 51.5072,
        "lon": -0.1276,
    },
    {
        "name": "The Guardian Politics",
        "category": "politics",
        "url": "https://www.theguardian.com/politics/rss",
        "region": "Europe",
        "country": "United Kingdom",
        "lat": 51.5072,
        "lon": -0.1276,
    },
    {
        "name": "BBC Sport",
        "category": "sport",
        "url": "https://feeds.bbci.co.uk/sport/rss.xml?edition=uk",
        "region": "Europe",
        "country": "United Kingdom",
        "lat": 51.5072,
        "lon": -0.1276,
    },
    {
        "name": "ESPN",
        "category": "sport",
        "url": "https://www.espn.com/espn/rss/news",
        "region": "North America",
        "country": "United States",
        "lat": 41.6718,
        "lon": -72.9493,
    },
    {
        "name": "The Guardian Sport",
        "category": "sport",
        "url": "https://www.theguardian.com/sport/rss",
        "region": "Europe",
        "country": "United Kingdom",
        "lat": 51.5072,
        "lon": -0.1276,
    },
    {
        "name": "The Hacker News",
        "category": "cyber",
        "url": "https://feeds.feedburner.com/TheHackersNews",
        "region": "Global",
        "country": "Global",
        "lat": 20.0,
        "lon": 0.0,
    },
    {
        "name": "BleepingComputer",
        "category": "cyber",
        "url": "https://www.bleepingcomputer.com/feed/",
        "region": "Global",
        "country": "Global",
        "lat": 20.0,
        "lon": 0.0,
    },
    {
        "name": "Krebs on Security",
        "category": "cyber",
        "url": "https://krebsonsecurity.com/feed/",
        "region": "North America",
        "country": "United States",
        "lat": 38.9072,
        "lon": -77.0369,
    },
]


LOCATIONS = [
    ("Global", "Global", "Global", 20.0, 0.0, ["global", "worldwide", "international"]),
    ("Portugal", "Europe", "Portugal", 38.7223, -9.1393, ["portugal", "portuguese", "lisbon", "lisboa", "porto"]),
    ("Spain", "Europe", "Spain", 40.4168, -3.7038, ["spain", "spanish", "madrid", "barcelona", "catalonia"]),
    ("France", "Europe", "France", 48.8566, 2.3522, ["france", "french", "paris"]),
    ("Germany", "Europe", "Germany", 52.5200, 13.4050, ["germany", "german", "berlin", "munich"]),
    ("United Kingdom", "Europe", "United Kingdom", 51.5072, -0.1276, ["united kingdom", "britain", "british", "england", "london", "uk"]),
    ("Ireland", "Europe", "Ireland", 53.3498, -6.2603, ["ireland", "irish", "dublin"]),
    ("Italy", "Europe", "Italy", 41.9028, 12.4964, ["italy", "italian", "rome", "milan"]),
    ("Netherlands", "Europe", "Netherlands", 52.3676, 4.9041, ["netherlands", "dutch", "amsterdam"]),
    ("Belgium", "Europe", "Belgium", 50.8503, 4.3517, ["belgium", "brussels"]),
    ("Poland", "Europe", "Poland", 52.2297, 21.0122, ["poland", "polish", "warsaw"]),
    ("Ukraine", "Europe", "Ukraine", 50.4501, 30.5234, ["ukraine", "ukrainian", "kyiv", "kiev"]),
    ("Russia", "Europe", "Russia", 55.7558, 37.6173, ["russia", "russian", "moscow"]),
    ("Turkey", "Middle East", "Turkey", 39.9334, 32.8597, ["turkey", "turkish", "istanbul", "ankara"]),
    ("United States", "North America", "United States", 38.9072, -77.0369, ["united states", "usa", "u.s.", "washington", "new york", "california", "texas", "florida"]),
    ("Canada", "North America", "Canada", 45.4215, -75.6972, ["canada", "canadian", "ottawa", "toronto", "vancouver"]),
    ("Mexico", "North America", "Mexico", 19.4326, -99.1332, ["mexico", "mexican", "mexico city"]),
    ("Brazil", "South America", "Brazil", -15.7939, -47.8828, ["brazil", "brazilian", "brasil", "brasilia", "sao paulo", "são paulo", "rio de janeiro"]),
    ("Argentina", "South America", "Argentina", -34.6037, -58.3816, ["argentina", "argentine", "buenos aires"]),
    ("Chile", "South America", "Chile", -33.4489, -70.6693, ["chile", "chilean", "santiago"]),
    ("Colombia", "South America", "Colombia", 4.7110, -74.0721, ["colombia", "colombian", "bogota", "bogotá"]),
    ("South Africa", "Africa", "South Africa", -25.7479, 28.2293, ["south africa", "johannesburg", "cape town", "pretoria"]),
    ("Nigeria", "Africa", "Nigeria", 9.0765, 7.3986, ["nigeria", "nigerian", "lagos", "abuja"]),
    ("Egypt", "Africa", "Egypt", 30.0444, 31.2357, ["egypt", "egyptian", "cairo"]),
    ("Kenya", "Africa", "Kenya", -1.2921, 36.8219, ["kenya", "kenyan", "nairobi"]),
    ("Morocco", "Africa", "Morocco", 34.0209, -6.8416, ["morocco", "moroccan", "rabat", "casablanca"]),
    ("Ethiopia", "Africa", "Ethiopia", 9.0300, 38.7400, ["ethiopia", "ethiopian", "addis ababa"]),
    ("Ghana", "Africa", "Ghana", 5.6037, -0.1870, ["ghana", "ghanaian", "accra"]),
    ("Israel", "Middle East", "Israel", 31.7683, 35.2137, ["israel", "israeli", "jerusalem", "tel aviv"]),
    ("Palestine", "Middle East", "Palestine", 31.5017, 34.4668, ["palestine", "palestinian", "gaza", "west bank"]),
    ("Iran", "Middle East", "Iran", 35.6892, 51.3890, ["iran", "iranian", "tehran"]),
    ("Saudi Arabia", "Middle East", "Saudi Arabia", 24.7136, 46.6753, ["saudi arabia", "saudi", "riyadh"]),
    ("United Arab Emirates", "Middle East", "United Arab Emirates", 24.4539, 54.3773, ["united arab emirates", "uae", "emirates", "dubai", "abu dhabi"]),
    ("Qatar", "Middle East", "Qatar", 25.2854, 51.5310, ["qatar", "qatari", "doha"]),
    ("Lebanon", "Middle East", "Lebanon", 33.8938, 35.5018, ["lebanon", "lebanese", "beirut"]),
    ("Syria", "Middle East", "Syria", 33.5138, 36.2765, ["syria", "syrian", "damascus"]),
    ("Iraq", "Middle East", "Iraq", 33.3152, 44.3661, ["iraq", "iraqi", "baghdad"]),
    ("China", "Asia-Pacific", "China", 39.9042, 116.4074, ["china", "chinese", "beijing", "shanghai"]),
    ("Hong Kong", "Asia-Pacific", "Hong Kong", 22.3193, 114.1694, ["hong kong"]),
    ("Taiwan", "Asia-Pacific", "Taiwan", 25.0330, 121.5654, ["taiwan", "taiwanese", "taipei"]),
    ("Japan", "Asia-Pacific", "Japan", 35.6762, 139.6503, ["japan", "japanese", "tokyo"]),
    ("South Korea", "Asia-Pacific", "South Korea", 37.5665, 126.9780, ["south korea", "korea", "korean", "seoul"]),
    ("North Korea", "Asia-Pacific", "North Korea", 39.0392, 125.7625, ["north korea", "pyongyang"]),
    ("India", "Asia-Pacific", "India", 28.6139, 77.2090, ["india", "indian", "delhi", "new delhi", "mumbai"]),
    ("Pakistan", "Asia-Pacific", "Pakistan", 33.6844, 73.0479, ["pakistan", "pakistani", "islamabad", "karachi"]),
    ("Bangladesh", "Asia-Pacific", "Bangladesh", 23.8103, 90.4125, ["bangladesh", "bangladeshi", "dhaka"]),
    ("Singapore", "Asia-Pacific", "Singapore", 1.3521, 103.8198, ["singapore"]),
    ("Indonesia", "Asia-Pacific", "Indonesia", -6.2088, 106.8456, ["indonesia", "indonesian", "jakarta"]),
    ("Philippines", "Asia-Pacific", "Philippines", 14.5995, 120.9842, ["philippines", "filipino", "manila"]),
    ("Thailand", "Asia-Pacific", "Thailand", 13.7563, 100.5018, ["thailand", "thai", "bangkok"]),
    ("Vietnam", "Asia-Pacific", "Vietnam", 21.0278, 105.8342, ["vietnam", "vietnamese", "hanoi"]),
    ("Malaysia", "Asia-Pacific", "Malaysia", 3.1390, 101.6869, ["malaysia", "malaysian", "kuala lumpur"]),
    ("Australia", "Oceania", "Australia", -35.2809, 149.1300, ["australia", "australian", "canberra", "sydney", "melbourne"]),
    ("New Zealand", "Oceania", "New Zealand", -41.2865, 174.7762, ["new zealand", "auckland", "wellington"]),
]


MARKET_SYMBOLS = [
    ("^SPX", "S&P 500"),
    ("^NDQ", "Nasdaq"),
    ("^DJI", "Dow"),
    ("EURUSD", "EUR/USD"),
    ("BTCUSD", "Bitcoin"),
    ("XAUUSD", "Gold"),
]


_cache = {
    "news": {"expires": 0, "payload": None},
    "markets": {"expires": 0, "payload": None},
}


def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat()


def strip_accents(value):
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_for_match(value):
    return strip_accents(normalize_text(value).lower())


def local_name(tag):
    return tag.split("}", 1)[-1].lower()


def child_text(node, *names):
    wanted = {name.lower() for name in names}
    for child in list(node):
        if local_name(child.tag) in wanted and child.text:
            return normalize_text(child.text)
    return ""


def child_attr(node, child_name, attr_name):
    for child in list(node):
        if local_name(child.tag) == child_name and child.attrib.get(attr_name):
            return child.attrib.get(attr_name)
    return ""


def parse_datetime(value):
    value = normalize_text(value)
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def stable_id(*parts):
    base = "|".join(part or "" for part in parts)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def location_from_source(source):
    return {
        "name": source.get("country") or source["name"],
        "region": source.get("region", "Global"),
        "country": source.get("country", "Global"),
        "lat": source.get("lat", 20.0),
        "lon": source.get("lon", 0.0),
    }


_LOCATION_PATTERNS = []
for loc_name, region, country, lat, lon, aliases in LOCATIONS:
    for alias in sorted(aliases, key=len, reverse=True):
        normalized_alias = strip_accents(alias.lower())
        if len(normalized_alias) < 3:
            continue
        pattern = re.compile(r"(?<![a-z0-9])" + re.escape(normalized_alias) + r"(?![a-z0-9])")
        _LOCATION_PATTERNS.append(
            (
                len(normalized_alias),
                pattern,
                {
                    "name": loc_name,
                    "region": region,
                    "country": country,
                    "lat": lat,
                    "lon": lon,
                },
            )
        )
_LOCATION_PATTERNS.sort(key=lambda item: item[0], reverse=True)


def detect_location(text, source):
    haystack = normalize_for_match(text)
    for _, pattern, location in _LOCATION_PATTERNS:
        if pattern.search(haystack):
            return dict(location)
    return location_from_source(source)


def summarize(description, title):
    description = normalize_text(description)
    title = normalize_text(title)
    if not description or description.lower() == title.lower():
        return title
    sentences = re.split(r"(?<=[.!?])\s+", description)
    summary = sentences[0] if sentences else description
    if len(summary) > 220:
        summary = summary[:217].rsplit(" ", 1)[0] + "..."
    return summary


def source_from_item(item, fallback):
    for child in list(item):
        if local_name(child.tag) == "source" and child.text:
            return normalize_text(child.text)
    return fallback


def extract_feed_items(root):
    items = [node for node in root.iter() if local_name(node.tag) == "item"]
    if items:
        return items
    return [node for node in root.iter() if local_name(node.tag) == "entry"]


def parse_feed(source, raw):
    root = ET.fromstring(raw)
    feed_items = extract_feed_items(root)
    articles = []
    for item in feed_items[:MAX_ITEMS_PER_SOURCE]:
        title = child_text(item, "title")
        if not title:
            continue

        link = child_text(item, "link")
        if not link:
            link = child_attr(item, "link", "href")
        guid = child_text(item, "guid", "id")
        description = child_text(item, "description", "summary", "encoded")
        pub_value = child_text(item, "pubDate", "published", "updated", "date")
        published_at = parse_datetime(pub_value)
        now = utc_now()
        if published_at and published_at.timestamp() > now.timestamp() + 600:
            published_at = now
        timestamp = published_at.timestamp() if published_at else 0

        source_name = source_from_item(item, source["name"])
        joined = f"{title}. {description}. {source_name}"
        location = detect_location(joined, source)
        article_id = stable_id(link or guid, title, source_name)
        age_hours = max(0, ((now.timestamp() - timestamp) / 3600.0)) if timestamp else 72
        impact = score_article(title, description, source["category"], age_hours)

        articles.append(
            {
                "id": article_id,
                "title": title,
                "summary": summarize(description, title),
                "url": link,
                "source": source_name,
                "feed": source["name"],
                "category": source["category"],
                "categoryLabel": CATEGORIES[source["category"]]["label"],
                "color": CATEGORIES[source["category"]]["color"],
                "publishedAt": published_at.isoformat() if published_at else None,
                "timestamp": timestamp,
                "region": location["region"],
                "country": location["country"],
                "location": location["name"],
                "lat": location["lat"],
                "lon": location["lon"],
                "impact": impact,
            }
        )
    return articles


def score_article(title, description, category, age_hours):
    text = f"{title} {description}".lower()
    score = 4
    if age_hours <= 6:
        score += 3
    elif age_hours <= 24:
        score += 2
    elif age_hours <= 72:
        score += 1
    if category in {"economy", "politics", "cyber"}:
        score += 1
    for keyword in (
        "breaking",
        "election",
        "war",
        "attack",
        "inflation",
        "rates",
        "central bank",
        "breach",
        "ransomware",
        "champions",
        "world cup",
    ):
        if keyword in text:
            score += 1
    return max(3, min(10, score))


def fetch_feed(source):
    started = time.time()
    status = {
        "name": source["name"],
        "category": source["category"],
        "ok": False,
        "items": 0,
        "durationMs": 0,
        "error": "",
    }
    try:
        request = Request(source["url"], headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8"})
        with urlopen(request, timeout=FEED_TIMEOUT_SECONDS) as response:
            raw = response.read(2_500_000)
        articles = parse_feed(source, raw)
        status["ok"] = True
        status["items"] = len(articles)
        return articles, status
    except HTTPError as exc:
        status["error"] = f"HTTP {exc.code}"
    except URLError as exc:
        status["error"] = str(exc.reason)
    except ET.ParseError as exc:
        status["error"] = f"XML parse error: {exc}"
    except Exception as exc:  # noqa: BLE001 - API should survive one bad feed.
        status["error"] = type(exc).__name__
    finally:
        status["durationMs"] = int((time.time() - started) * 1000)
    return [], status


def aggregate_news(force=False):
    cached = _cache["news"]
    if not force and cached["payload"] and cached["expires"] > time.time():
        return cached["payload"]

    articles = []
    statuses = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_feed, source) for source in SOURCES]
        for future in as_completed(futures):
            feed_articles, status = future.result()
            articles.extend(feed_articles)
            statuses.append(status)

    deduped = {}
    for article in articles:
        key = normalize_for_match(article["title"])
        if key not in deduped or article["timestamp"] > deduped[key]["timestamp"]:
            deduped[key] = article

    final_articles = sorted(deduped.values(), key=lambda article: article["timestamp"], reverse=True)
    payload = {
        "generatedAt": iso_now(),
        "cacheSeconds": NEWS_CACHE_SECONDS,
        "articles": final_articles,
        "sources": sorted(statuses, key=lambda status: status["name"]),
        "categories": CATEGORIES,
        "stats": build_stats(final_articles, statuses),
    }
    cached["payload"] = payload
    cached["expires"] = time.time() + NEWS_CACHE_SECONDS
    return payload


def build_stats(articles, statuses):
    category_counts = {}
    region_counts = {}
    country_counts = {}
    for article in articles:
        category_counts[article["category"]] = category_counts.get(article["category"], 0) + 1
        region_counts[article["region"]] = region_counts.get(article["region"], 0) + 1
        country_counts[article["country"]] = country_counts.get(article["country"], 0) + 1
    return {
        "articleCount": len(articles),
        "sourceCount": len(statuses),
        "healthySources": sum(1 for status in statuses if status["ok"]),
        "categoryCounts": category_counts,
        "regionCounts": region_counts,
        "countryCounts": dict(sorted(country_counts.items(), key=lambda item: item[1], reverse=True)[:12]),
    }


def filter_news(payload, query):
    category = query.get("category", ["all"])[0]
    region = query.get("region", ["all"])[0]
    search = normalize_for_match(query.get("q", [""])[0])
    try:
        limit = int(query.get("limit", ["300"])[0])
    except ValueError:
        limit = 300

    articles = payload["articles"]
    if category != "all":
        articles = [article for article in articles if article["category"] == category]
    if region != "all":
        articles = [article for article in articles if article["region"] == region or article["country"] == region]
    if search:
        articles = [
            article
            for article in articles
            if search
            in normalize_for_match(
                f"{article['title']} {article['summary']} {article['source']} {article['location']} {article['country']}"
            )
        ]

    result = dict(payload)
    result["articles"] = articles[: max(1, min(limit, 500))]
    result["filteredStats"] = build_stats(result["articles"], payload["sources"])
    return result


def build_briefing(force=False):
    payload = aggregate_news(force=force)
    articles = payload["articles"]
    stats = payload["stats"]
    lines = []

    if not articles:
        lines.append("No live feeds responded yet. Try refresh in a moment.")
    else:
        lead_pool = [
            article
            for article in articles
            if article["category"] in {"news", "economy", "politics"}
        ] or articles
        lead = max(lead_pool, key=lambda article: (article["impact"], article["timestamp"]))
        lines.append(
            f"Global lead: {lead['title']} ({lead['source']}, {lead['location']})."
        )

    for category, meta in CATEGORIES.items():
        picks = [article for article in articles if article["category"] == category][:2]
        if not picks:
            continue
        locations = ", ".join(sorted({pick["location"] for pick in picks})[:3])
        headline = "; ".join(pick["title"] for pick in picks)
        lines.append(f"{meta['label']}: {headline}. Watch: {locations}.")

    portugal_items = [
        article
        for article in articles
        if article["country"] == "Portugal" or "portugal" in article["feed"].lower()
    ][:2]
    if portugal_items:
        headline = "; ".join(article["title"] for article in portugal_items)
        lines.append(f"Portugal watch: {headline}.")

    top_regions = sorted(stats["regionCounts"].items(), key=lambda item: item[1], reverse=True)[:4]
    if top_regions:
        region_line = ", ".join(f"{region} {count}" for region, count in top_regions)
        lines.append(f"Coverage density: {region_line}.")

    return {
        "generatedAt": payload["generatedAt"],
        "headline": "Atlas briefing",
        "script": " ".join(lines),
        "lines": lines,
        "stats": stats,
    }


def fetch_markets(force=False):
    cached = _cache["markets"]
    if not force and cached["payload"] and cached["expires"] > time.time():
        return cached["payload"]

    symbols = "+".join(symbol for symbol, _ in MARKET_SYMBOLS)
    url = f"https://stooq.com/q/l/?s={symbols}&f=sd2t2ohlcv&h&e=csv"
    items = []
    status = {"ok": False, "error": ""}
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=FEED_TIMEOUT_SECONDS) as response:
            raw = response.read(200_000).decode("utf-8", errors="replace")
        rows = list(csv.DictReader(io.StringIO(raw)))
        labels = {symbol: label for symbol, label in MARKET_SYMBOLS}
        for row in rows:
            symbol = row.get("Symbol", "")
            if symbol not in labels:
                continue
            close = parse_float(row.get("Close"))
            open_price = parse_float(row.get("Open"))
            change_pct = None
            if close is not None and open_price not in (None, 0):
                change_pct = ((close - open_price) / open_price) * 100
            items.append(
                {
                    "symbol": symbol,
                    "label": labels[symbol],
                    "value": close,
                    "changePct": change_pct,
                    "date": row.get("Date"),
                    "time": row.get("Time"),
                }
            )
        status["ok"] = True
    except Exception as exc:  # noqa: BLE001 - market snapshot is optional.
        status["error"] = type(exc).__name__

    payload = {"generatedAt": iso_now(), "items": items, "status": status}
    cached["payload"] = payload
    cached["expires"] = time.time() + MARKET_CACHE_SECONDS
    return payload


def parse_float(value):
    try:
        if value in (None, "", "N/D"):
            return None
        return float(value)
    except ValueError:
        return None


def respond_json(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except BrokenPipeError:
        pass


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.join(os.getcwd(), "static"), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        force = query.get("refresh", ["0"])[0] == "1"

        if parsed.path == "/api/news":
            payload = aggregate_news(force=force)
            respond_json(self, filter_news(payload, query))
            return
        if parsed.path == "/api/briefing":
            respond_json(self, build_briefing(force=force))
            return
        if parsed.path == "/api/markets":
            respond_json(self, fetch_markets(force=force))
            return
        if parsed.path == "/api/health":
            respond_json(
                self,
                {
                    "ok": True,
                    "time": iso_now(),
                    "sources": len(SOURCES),
                    "categories": list(CATEGORIES.keys()),
                },
            )
            return

        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def log_message(self, format, *args):  # noqa: A002 - stdlib method signature.
        print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), format % args))


class AppServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main():
    try:
        server = AppServer(("0.0.0.0", PORT), AppHandler)
    except OSError as exc:
        if exc.errno == 98:
            print(f"Port {PORT} is already in use.")
            print("Stop the existing server with Ctrl+C, or run on another port:")
            print(f"    PORT=8001 python3 app.py")
            return
        raise
    print(f"World Signal running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

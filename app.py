#!/usr/bin/env python3
"""
World Signal: a key-free global news map.

Run with:
    python3 app.py
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

import csv
import hashlib
import html
import io
import json
import os
import re
import socket
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
        "name": "DW World",
        "category": "news",
        "url": "https://rss.dw.com/rdf/rss-en-world",
        "region": "Europe",
        "country": "Germany",
        "lat": 52.5200,
        "lon": 13.4050,
    },
    {
        "name": "France 24 World",
        "category": "news",
        "url": "https://www.france24.com/en/rss",
        "region": "Europe",
        "country": "France",
        "lat": 48.8566,
        "lon": 2.3522,
    },
    {
        "name": "Euronews",
        "category": "news",
        "url": "https://www.euronews.com/rss?level=theme&name=news",
        "region": "Europe",
        "country": "France",
        "lat": 45.7640,
        "lon": 4.8357,
    },
    {
        "name": "Sky News World",
        "category": "news",
        "url": "https://feeds.skynews.com/feeds/rss/world.xml",
        "region": "Europe",
        "country": "United Kingdom",
        "lat": 51.5072,
        "lon": -0.1276,
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
        "name": "DW Business",
        "category": "economy",
        "url": "https://rss.dw.com/rdf/rss-en-bus",
        "region": "Europe",
        "country": "Germany",
        "lat": 52.5200,
        "lon": 13.4050,
    },
    {
        "name": "France 24 Business",
        "category": "economy",
        "url": "https://www.france24.com/en/business/rss",
        "region": "Europe",
        "country": "France",
        "lat": 48.8566,
        "lon": 2.3522,
    },
    {
        "name": "Euronews Business",
        "category": "economy",
        "url": "https://www.euronews.com/rss?level=theme&name=business",
        "region": "Europe",
        "country": "France",
        "lat": 45.7640,
        "lon": 4.8357,
    },
    {
        "name": "Sky News Business",
        "category": "economy",
        "url": "https://feeds.skynews.com/feeds/rss/business.xml",
        "region": "Europe",
        "country": "United Kingdom",
        "lat": 51.5072,
        "lon": -0.1276,
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
        "name": "PBS Politics",
        "category": "politics",
        "url": "https://www.pbs.org/newshour/feeds/rss/politics",
        "region": "North America",
        "country": "United States",
        "lat": 38.9072,
        "lon": -77.0369,
    },
    {
        "name": "The Hill",
        "category": "politics",
        "url": "https://thehill.com/feed/",
        "region": "North America",
        "country": "United States",
        "lat": 38.9072,
        "lon": -77.0369,
    },
    {
        "name": "Sky News Politics",
        "category": "politics",
        "url": "https://feeds.skynews.com/feeds/rss/politics.xml",
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
        "name": "DW Sports",
        "category": "sport",
        "url": "https://rss.dw.com/rdf/rss-en-sports",
        "region": "Europe",
        "country": "Germany",
        "lat": 52.5200,
        "lon": 13.4050,
    },
    {
        "name": "France 24 Sport",
        "category": "sport",
        "url": "https://www.france24.com/en/sport/rss",
        "region": "Europe",
        "country": "France",
        "lat": 48.8566,
        "lon": 2.3522,
    },
    {
        "name": "Sky Sports News",
        "category": "sport",
        "url": "https://www.skysports.com/rss/12040",
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
    {
        "name": "The Register Security",
        "category": "cyber",
        "url": "https://api.theregister.com/api/v1/article?limit=25&orderBy=published&query=tag%3Asecurity&remapper=rss&site_id=2",
        "region": "Europe",
        "country": "United Kingdom",
        "lat": 51.5072,
        "lon": -0.1276,
    },
    {
        "name": "CyberScoop",
        "category": "cyber",
        "url": "https://cyberscoop.com/feed/",
        "region": "North America",
        "country": "United States",
        "lat": 38.9072,
        "lon": -77.0369,
    },
    {
        "name": "SecurityWeek",
        "category": "cyber",
        "url": "https://www.securityweek.com/feed/",
        "region": "Global",
        "country": "Global",
        "lat": 20.0,
        "lon": 0.0,
    },
    {
        "name": "Dark Reading",
        "category": "cyber",
        "url": "https://www.darkreading.com/rss.xml",
        "region": "Global",
        "country": "Global",
        "lat": 20.0,
        "lon": 0.0,
    },
    {
        "name": "CERT-EU",
        "category": "cyber",
        "url": "https://cert.europa.eu/publications/security-advisories-rss",
        "region": "Europe",
        "country": "Belgium",
        "lat": 50.8503,
        "lon": 4.3517,
    },
    {
        "name": "Schneier on Security",
        "category": "cyber",
        "url": "https://www.schneier.com/feed/atom/",
        "region": "North America",
        "country": "United States",
        "lat": 42.3601,
        "lon": -71.0589,
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


MARKET_GROUPS = {
    "indices": "Indices",
    "etfs": "ETFs",
    "bonds": "Country Bonds",
    "fx": "FX",
    "crypto": "Crypto",
    "commodities": "Commodities",
}


MARKET_INSTRUMENTS = [
    {
        "symbol": "^SPX",
        "displaySymbol": "SPX",
        "label": "S&P 500",
        "assetClass": "indices",
        "yahoo": "^GSPC",
        "strip": True,
    },
    {
        "symbol": "^NDQ",
        "displaySymbol": "NDQ",
        "label": "Nasdaq",
        "assetClass": "indices",
        "yahoo": "^IXIC",
        "strip": True,
    },
    {
        "symbol": "^DJI",
        "displaySymbol": "DJI",
        "label": "Dow",
        "assetClass": "indices",
        "yahoo": "^DJI",
        "strip": True,
    },
    {
        "symbol": "EURUSD",
        "displaySymbol": "EUR/USD",
        "label": "EUR/USD",
        "assetClass": "fx",
        "yahoo": "EURUSD=X",
        "strip": True,
    },
    {
        "symbol": "BTCUSD",
        "displaySymbol": "BTC/USD",
        "label": "Bitcoin",
        "assetClass": "crypto",
        "yahoo": "BTC-USD",
        "strip": True,
    },
    {
        "symbol": "XAUUSD",
        "displaySymbol": "XAU/USD",
        "label": "Gold",
        "assetClass": "commodities",
        "yahoo": "GC=F",
        "strip": True,
    },
    {"symbol": "^RUT", "displaySymbol": "RUT", "label": "Russell 2000", "assetClass": "indices", "yahoo": "^RUT"},
    {"symbol": "^GDAXI", "displaySymbol": "DAX", "label": "DAX", "assetClass": "indices", "yahoo": "^GDAXI"},
    {"symbol": "^FTSE", "displaySymbol": "FTSE", "label": "FTSE 100", "assetClass": "indices", "yahoo": "^FTSE"},
    {"symbol": "^N225", "displaySymbol": "N225", "label": "Nikkei 225", "assetClass": "indices", "yahoo": "^N225"},
    {"symbol": "^HSI", "displaySymbol": "HSI", "label": "Hang Seng", "assetClass": "indices", "yahoo": "^HSI"},
    {"symbol": "^STOXX50E", "displaySymbol": "SX5E", "label": "Euro Stoxx 50", "assetClass": "indices", "yahoo": "^STOXX50E"},
    {"symbol": "^VIX", "displaySymbol": "VIX", "label": "CBOE Volatility", "assetClass": "indices", "yahoo": "^VIX"},
    {"symbol": "SPY.US", "displaySymbol": "SPY", "label": "SPDR S&P 500 ETF", "assetClass": "etfs", "yahoo": "SPY"},
    {"symbol": "QQQ.US", "displaySymbol": "QQQ", "label": "Invesco QQQ", "assetClass": "etfs", "yahoo": "QQQ"},
    {"symbol": "VT.US", "displaySymbol": "VT", "label": "Vanguard Total World", "assetClass": "etfs", "yahoo": "VT"},
    {"symbol": "ACWI.US", "displaySymbol": "ACWI", "label": "iShares MSCI ACWI", "assetClass": "etfs", "yahoo": "ACWI"},
    {"symbol": "URTH.US", "displaySymbol": "URTH", "label": "iShares MSCI World", "assetClass": "etfs", "yahoo": "URTH"},
    {"symbol": "VEA.US", "displaySymbol": "VEA", "label": "Vanguard Developed Markets", "assetClass": "etfs", "yahoo": "VEA"},
    {"symbol": "EEM.US", "displaySymbol": "EEM", "label": "iShares Emerging Markets", "assetClass": "etfs", "yahoo": "EEM"},
    {"symbol": "GLD.US", "displaySymbol": "GLD", "label": "SPDR Gold Shares", "assetClass": "etfs", "yahoo": "GLD"},
    {"symbol": "SLV.US", "displaySymbol": "SLV", "label": "iShares Silver Trust", "assetClass": "etfs", "yahoo": "SLV"},
    {"symbol": "BND.US", "displaySymbol": "BND", "label": "Vanguard Total Bond", "assetClass": "etfs", "yahoo": "BND"},
    {"symbol": "BNDX.US", "displaySymbol": "BNDX", "label": "Vanguard Total Intl Bond", "assetClass": "etfs", "yahoo": "BNDX"},
    {"symbol": "GOVT.US", "displaySymbol": "GOVT", "label": "iShares U.S. Treasury Bond", "assetClass": "etfs", "yahoo": "GOVT"},
    {"symbol": "IEF.US", "displaySymbol": "IEF", "label": "iShares 7-10Y Treasury", "assetClass": "etfs", "yahoo": "IEF"},
    {"symbol": "TLT.US", "displaySymbol": "TLT", "label": "iShares 20+ Year Treasury", "assetClass": "etfs", "yahoo": "TLT"},
    {"symbol": "LQD.US", "displaySymbol": "LQD", "label": "iShares IG Corporate Bond", "assetClass": "etfs", "yahoo": "LQD"},
    {"symbol": "HYG.US", "displaySymbol": "HYG", "label": "iShares High Yield Corp", "assetClass": "etfs", "yahoo": "HYG"},
    {"symbol": "BWX.US", "displaySymbol": "BWX", "label": "SPDR Intl Treasury Bond", "assetClass": "etfs", "yahoo": "BWX"},
    {"symbol": "EMB.US", "displaySymbol": "EMB", "label": "iShares EM USD Bond", "assetClass": "etfs", "yahoo": "EMB"},
    {"symbol": "US02Y", "displaySymbol": "US 2Y", "label": "United States 2Y", "assetClass": "bonds", "tradingView": "TVC:US02Y"},
    {"symbol": "US05Y", "displaySymbol": "US 5Y", "label": "United States 5Y", "assetClass": "bonds", "tradingView": "TVC:US05Y"},
    {"symbol": "US10Y", "displaySymbol": "US 10Y", "label": "United States 10Y", "assetClass": "bonds", "tradingView": "TVC:US10Y"},
    {"symbol": "US30Y", "displaySymbol": "US 30Y", "label": "United States 30Y", "assetClass": "bonds", "tradingView": "TVC:US30Y"},
    {"symbol": "DE10Y", "displaySymbol": "DE 10Y", "label": "Germany 10Y", "assetClass": "bonds", "tradingView": "TVC:DE10Y"},
    {"symbol": "GB10Y", "displaySymbol": "UK 10Y", "label": "United Kingdom 10Y", "assetClass": "bonds", "tradingView": "TVC:GB10Y"},
    {"symbol": "JP10Y", "displaySymbol": "JP 10Y", "label": "Japan 10Y", "assetClass": "bonds", "tradingView": "TVC:JP10Y"},
    {"symbol": "FR10Y", "displaySymbol": "FR 10Y", "label": "France 10Y", "assetClass": "bonds", "tradingView": "TVC:FR10Y"},
    {"symbol": "IT10Y", "displaySymbol": "IT 10Y", "label": "Italy 10Y", "assetClass": "bonds", "tradingView": "TVC:IT10Y"},
    {"symbol": "ES10Y", "displaySymbol": "ES 10Y", "label": "Spain 10Y", "assetClass": "bonds", "tradingView": "TVC:ES10Y"},
    {"symbol": "PT10Y", "displaySymbol": "PT 10Y", "label": "Portugal 10Y", "assetClass": "bonds", "tradingView": "TVC:PT10Y"},
    {"symbol": "CA10Y", "displaySymbol": "CA 10Y", "label": "Canada 10Y", "assetClass": "bonds", "tradingView": "TVC:CA10Y"},
    {"symbol": "AU10Y", "displaySymbol": "AU 10Y", "label": "Australia 10Y", "assetClass": "bonds", "tradingView": "TVC:AU10Y"},
    {"symbol": "BR10Y", "displaySymbol": "BR 10Y", "label": "Brazil 10Y", "assetClass": "bonds", "tradingView": "TVC:BR10Y"},
    {"symbol": "IN10Y", "displaySymbol": "IN 10Y", "label": "India 10Y", "assetClass": "bonds", "tradingView": "TVC:IN10Y"},
    {"symbol": "CN10Y", "displaySymbol": "CN 10Y", "label": "China 10Y", "assetClass": "bonds", "tradingView": "TVC:CN10Y"},
    {"symbol": "EU10Y", "displaySymbol": "EU 10Y", "label": "Euro Area 10Y", "assetClass": "bonds", "tradingView": "TVC:EU10Y"},
    {"symbol": "CL.F", "displaySymbol": "CL", "label": "Crude Oil", "assetClass": "commodities", "yahoo": "CL=F"},
    {"symbol": "BZ.F", "displaySymbol": "BZ", "label": "Brent Crude", "assetClass": "commodities", "yahoo": "BZ=F"},
    {"symbol": "NG.F", "displaySymbol": "NG", "label": "Natural Gas", "assetClass": "commodities", "yahoo": "NG=F"},
    {"symbol": "HG.F", "displaySymbol": "HG", "label": "Copper", "assetClass": "commodities", "yahoo": "HG=F", "stooqScale": 0.01},
    {"symbol": "SI.F", "displaySymbol": "SI", "label": "Silver", "assetClass": "commodities", "yahoo": "SI=F", "stooqScale": 0.01},
    {"symbol": "PL.F", "displaySymbol": "PL", "label": "Platinum", "assetClass": "commodities", "yahoo": "PL=F"},
    {"symbol": "ZC.F", "displaySymbol": "ZC", "label": "Corn", "assetClass": "commodities", "yahoo": "ZC=F"},
    {"symbol": "ZW.F", "displaySymbol": "ZW", "label": "Wheat", "assetClass": "commodities", "yahoo": "ZW=F"},
    {"symbol": "GBPUSD", "displaySymbol": "GBP/USD", "label": "GBP/USD", "assetClass": "fx", "yahoo": "GBPUSD=X"},
    {"symbol": "USDJPY", "displaySymbol": "USD/JPY", "label": "USD/JPY", "assetClass": "fx", "yahoo": "USDJPY=X"},
    {"symbol": "USDBRL", "displaySymbol": "USD/BRL", "label": "USD/BRL", "assetClass": "fx", "yahoo": "USDBRL=X"},
    {"symbol": "USDCHF", "displaySymbol": "USD/CHF", "label": "USD/CHF", "assetClass": "fx", "yahoo": "USDCHF=X"},
    {"symbol": "AUDUSD", "displaySymbol": "AUD/USD", "label": "AUD/USD", "assetClass": "fx", "yahoo": "AUDUSD=X"},
    {"symbol": "EURGBP", "displaySymbol": "EUR/GBP", "label": "EUR/GBP", "assetClass": "fx", "yahoo": "EURGBP=X"},
    {"symbol": "USDCNY", "displaySymbol": "USD/CNY", "label": "USD/CNY", "assetClass": "fx", "yahoo": "CNY=X"},
    {"symbol": "ETHUSD", "displaySymbol": "ETH/USD", "label": "Ethereum", "assetClass": "crypto", "yahoo": "ETH-USD"},
    {"symbol": "BNBUSD", "displaySymbol": "BNB/USD", "label": "BNB", "assetClass": "crypto", "yahoo": "BNB-USD"},
    {"symbol": "SOLUSD", "displaySymbol": "SOL/USD", "label": "Solana", "assetClass": "crypto", "yahoo": "SOL-USD"},
    {"symbol": "XRPUSD", "displaySymbol": "XRP/USD", "label": "XRP", "assetClass": "crypto", "yahoo": "XRP-USD"},
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
        limit = int(query.get("limit", ["500"])[0])
    except ValueError:
        limit = 500

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


def fetch_stooq_market_rows():
    symbols = "+".join(instrument["symbol"] for instrument in MARKET_INSTRUMENTS)
    url = f"https://stooq.com/q/l/?s={symbols}&f=sd2t2ohlcvpn&h&e=csv"
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=FEED_TIMEOUT_SECONDS) as response:
        raw = response.read(500_000).decode("utf-8", errors="replace")
    rows = list(csv.DictReader(io.StringIO(raw)))
    return {row.get("Symbol", "").upper(): row for row in rows if row.get("Symbol")}


def fetch_yahoo_market_history(instrument):
    yahoo_symbol = instrument.get("yahoo")
    if not yahoo_symbol:
        return {}
    encoded = quote(yahoo_symbol, safe="")
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{encoded}?range=1y&interval=1d"
    )
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urlopen(request, timeout=FEED_TIMEOUT_SECONDS) as response:
        data = json.loads(response.read(1_500_000).decode("utf-8", errors="replace"))

    result = ((data.get("chart") or {}).get("result") or [{}])[0]
    meta = result.get("meta") or {}
    quote_block = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    timestamps = result.get("timestamp") or []
    closes = quote_block.get("close") or []
    highs = quote_block.get("high") or []
    lows = quote_block.get("low") or []
    volumes = quote_block.get("volume") or []

    history = []
    high_values = []
    low_values = []
    for index, timestamp in enumerate(timestamps):
        close = parse_float(closes[index] if index < len(closes) else None)
        if close is None:
            continue
        high = parse_float(highs[index] if index < len(highs) else None)
        low = parse_float(lows[index] if index < len(lows) else None)
        volume = parse_int(volumes[index] if index < len(volumes) else None)
        if high is not None:
            high_values.append(high)
        if low is not None:
            low_values.append(low)
        history.append(
            {
                "date": datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat(),
                "close": close,
                "high": high,
                "low": low,
                "volume": volume,
            }
        )

    range_low = parse_float(meta.get("fiftyTwoWeekLow"))
    range_high = parse_float(meta.get("fiftyTwoWeekHigh"))
    if range_low is None and low_values:
        range_low = min(low_values)
    if range_high is None and high_values:
        range_high = max(high_values)

    previous_close = parse_float(meta.get("previousClose"))
    if previous_close is None and len(history) >= 2:
        previous_close = history[-2]["close"]
    if previous_close is None:
        previous_close = parse_float(meta.get("chartPreviousClose"))

    return {
        "currency": meta.get("currency"),
        "regularMarketPrice": parse_float(meta.get("regularMarketPrice")),
        "regularMarketOpen": parse_float(meta.get("regularMarketOpen")),
        "previousClose": previous_close,
        "dayHigh": parse_float(meta.get("regularMarketDayHigh")),
        "dayLow": parse_float(meta.get("regularMarketDayLow")),
        "volume": parse_int(meta.get("regularMarketVolume")),
        "range52w": {"low": range_low, "high": range_high},
        "history": history[-64:],
    }


def fetch_tradingview_bond_rows():
    columns = ["name", "description", "close", "change", "change_abs", "open", "high", "low"]
    tickers = [instrument["tradingView"] for instrument in MARKET_INSTRUMENTS if instrument.get("tradingView")]
    if not tickers:
        return {}

    payload = {
        "symbols": {"tickers": tickers, "query": {"types": []}},
        "columns": columns,
    }
    request = Request(
        "https://scanner.tradingview.com/bonds/scan",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=FEED_TIMEOUT_SECONDS) as response:
        data = json.loads(response.read(300_000).decode("utf-8", errors="replace"))

    rows = {}
    for row in data.get("data", []):
        values = dict(zip(columns, row.get("d") or []))
        symbol = row.get("s")
        if symbol:
            rows[symbol.upper()] = values
    return rows


def build_session_history(item):
    open_price = item.get("open")
    high = item.get("high")
    low = item.get("low")
    close = item.get("close")
    if not all(value is not None for value in (open_price, high, low, close)):
        return []
    date = item.get("date") or utc_now().date().isoformat()
    if close >= open_price:
        values = [open_price, low, high, close]
    else:
        values = [open_price, high, low, close]
    return [{"date": date, "close": value} for value in values]


def align_history_close(history, close):
    if not history or close is None:
        return history or []
    aligned = [dict(point) for point in history]
    aligned[-1]["close"] = close
    return aligned


def build_market_item(instrument, stooq_row, yahoo_data, tradingview_data=None):
    scale = instrument.get("stooqScale", 1)
    tradingview_data = tradingview_data or {}

    def scaled_row_value(field):
        value = parse_float(stooq_row.get(field) if stooq_row else None)
        return value * scale if value is not None else None

    def first_available(*values):
        for value in values:
            if value is not None:
                return value
        return None

    stooq_close = scaled_row_value("Close")
    stooq_open = scaled_row_value("Open")
    stooq_high = scaled_row_value("High")
    stooq_low = scaled_row_value("Low")
    stooq_previous = scaled_row_value("Prev")
    stooq_volume = parse_int(stooq_row.get("Volume") if stooq_row else None)
    yahoo_close = yahoo_data.get("regularMarketPrice")
    yahoo_open = yahoo_data.get("regularMarketOpen")
    yahoo_previous = yahoo_data.get("previousClose")
    yahoo_high = yahoo_data.get("dayHigh")
    yahoo_low = yahoo_data.get("dayLow")
    yahoo_volume = yahoo_data.get("volume")
    tv_close = parse_float(tradingview_data.get("close"))
    tv_open = parse_float(tradingview_data.get("open"))
    tv_high = parse_float(tradingview_data.get("high"))
    tv_low = parse_float(tradingview_data.get("low"))
    tv_change_pct = parse_float(tradingview_data.get("change"))
    tv_change_abs = parse_float(tradingview_data.get("change_abs"))

    quote_source = "unavailable"
    if yahoo_close is not None:
        quote_source = "yahoo"
        close = yahoo_close
        open_price = first_available(yahoo_open, stooq_open, tv_open)
        previous = first_available(yahoo_previous, stooq_previous)
        high = first_available(yahoo_high, stooq_high)
        low = first_available(yahoo_low, stooq_low)
        volume = first_available(yahoo_volume, stooq_volume)
    elif stooq_close is not None:
        quote_source = "stooq"
        close = stooq_close
        open_price = first_available(stooq_open, yahoo_open, tv_open)
        previous = first_available(stooq_previous, yahoo_previous)
        high = first_available(stooq_high, yahoo_high)
        low = first_available(stooq_low, yahoo_low)
        volume = first_available(stooq_volume, yahoo_volume)
    else:
        quote_source = "tradingview" if tv_close is not None else quote_source
        close = tv_close
        open_price = first_available(tv_open, stooq_open, yahoo_open)
        previous = first_available(yahoo_previous, stooq_previous)
        high = first_available(tv_high, stooq_high, yahoo_high)
        low = first_available(tv_low, stooq_low, yahoo_low)
        volume = first_available(stooq_volume, yahoo_volume)

    if previous is None and close is not None and tv_change_abs is not None:
        previous = close - tv_change_abs
    if close is not None and high is not None:
        high = max(high, close)
    if close is not None and low is not None:
        low = min(low, close)

    change_pct = None
    if quote_source == "tradingview" and tv_change_pct is not None:
        change_pct = tv_change_pct
    elif close is not None and previous not in (None, 0):
        change_pct = ((close - previous) / previous) * 100
    elif close is not None and open_price not in (None, 0):
        change_pct = ((close - open_price) / open_price) * 100

    item = {
        "symbol": instrument["symbol"],
        "displaySymbol": instrument.get("displaySymbol", instrument["symbol"]),
        "label": instrument["label"],
        "assetClass": instrument["assetClass"],
        "assetClassLabel": MARKET_GROUPS.get(instrument["assetClass"], instrument["assetClass"].title()),
        "currency": instrument.get("currency") or yahoo_data.get("currency"),
        "value": close,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "previousClose": previous,
        "changePct": change_pct,
        "volume": volume,
        "range52w": yahoo_data.get("range52w") or {"low": None, "high": None},
        "history": align_history_close(yahoo_data.get("history") or [], close),
        "historySource": "yahoo" if yahoo_data.get("history") else "session",
        "quoteSource": quote_source,
        "date": stooq_row.get("Date") if stooq_row else None,
        "time": stooq_row.get("Time") if stooq_row else None,
        "strip": bool(instrument.get("strip")),
    }
    if not item["history"]:
        item["history"] = build_session_history(item)
    return item


def fetch_markets(force=False):
    cached = _cache["markets"]
    if not force and cached["payload"] and cached["expires"] > time.time():
        return cached["payload"]

    status = {
        "ok": False,
        "error": "",
        "sources": {"stooq": False, "yahoo": False, "tradingView": False},
        "quoteSources": {},
        "historyErrors": 0,
    }
    stooq_rows = {}
    try:
        stooq_rows = fetch_stooq_market_rows()
        status["sources"]["stooq"] = True
    except Exception as exc:  # noqa: BLE001 - markets should survive source outages.
        status["error"] = f"Stooq: {type(exc).__name__}"

    tradingview_rows = {}
    try:
        tradingview_rows = fetch_tradingview_bond_rows()
        status["sources"]["tradingView"] = bool(tradingview_rows)
    except Exception as exc:  # noqa: BLE001 - bond yields should not break markets.
        status["error"] = f"{status['error']}; TradingView: {type(exc).__name__}".strip("; ")

    yahoo_data = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(fetch_yahoo_market_history, instrument): instrument
            for instrument in MARKET_INSTRUMENTS
        }
        for future in as_completed(futures):
            instrument = futures[future]
            try:
                result = future.result()
                yahoo_data[instrument["symbol"].upper()] = result
                if result.get("history"):
                    status["sources"]["yahoo"] = True
            except Exception:  # noqa: BLE001 - one chart should not break the page.
                yahoo_data[instrument["symbol"].upper()] = {}
                status["historyErrors"] += 1

    items = []
    for instrument in MARKET_INSTRUMENTS:
        symbol_key = instrument["symbol"].upper()
        item = build_market_item(
            instrument,
            stooq_rows.get(symbol_key),
            yahoo_data.get(symbol_key, {}),
            tradingview_rows.get((instrument.get("tradingView") or "").upper()),
        )
        items.append(item)

    for item in items:
        quote_source = item.get("quoteSource") or "unavailable"
        status["quoteSources"][quote_source] = status["quoteSources"].get(quote_source, 0) + 1

    status["ok"] = any(item["value"] is not None for item in items)
    payload = {
        "generatedAt": iso_now(),
        "cacheSeconds": MARKET_CACHE_SECONDS,
        "items": items,
        "groups": MARKET_GROUPS,
        "status": status,
    }
    cached["payload"] = payload
    cached["expires"] = time.time() + MARKET_CACHE_SECONDS
    return payload


def parse_float(value):
    try:
        if value in (None, "", "N/D"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int(value):
    parsed = parse_float(value)
    if parsed is None:
        return None
    return int(parsed)


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
        elif parsed.path in {"/markets", "/markets/"}:
            self.path = "/markets.html"
        return super().do_GET()

    def do_HEAD(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.path = "/index.html"
        elif parsed.path in {"/markets", "/markets/"}:
            self.path = "/markets.html"
        return super().do_HEAD()

    def log_message(self, format, *args):  # noqa: A002 - stdlib method signature.
        print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), format % args))


class AppServer(ThreadingHTTPServer):
    allow_reuse_address = True


def local_network_url(port):
    host = ""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            host = probe.getsockname()[0]
    except OSError:
        try:
            host = socket.gethostbyname(socket.gethostname())
        except OSError:
            host = ""
    if host and not host.startswith("127."):
        return f"http://{host}:{port}"
    return ""


def public_service_url():
    explicit_url = os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    if explicit_url:
        return explicit_url

    fly_app_name = os.environ.get("FLY_APP_NAME")
    if fly_app_name:
        return f"https://{fly_app_name}.fly.dev"

    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    if railway_domain:
        return f"https://{railway_domain}"

    return ""


def is_cloud_runtime():
    cloud_markers = (
        "FLY_APP_NAME",
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_PUBLIC_DOMAIN",
        "RENDER",
        "RENDER_SERVICE_ID",
        "RENDER_EXTERNAL_URL",
    )
    return any(os.environ.get(marker) for marker in cloud_markers)


def is_container_runtime():
    return os.path.exists("/.dockerenv")


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
    public_url = public_service_url()
    mobile_url = (
        ""
        if public_url or is_cloud_runtime() or is_container_runtime()
        else local_network_url(PORT)
    )
    if public_url:
        print(f"Public URL: {public_url}")
    elif mobile_url:
        print(f"Open on your phone at {mobile_url} while on the same Wi-Fi.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

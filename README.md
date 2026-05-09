# World Signal

A key-free prototype for a global news intelligence dashboard. It aggregates public RSS feeds for world news, economics, politics, sport, Portugal, and cybersecurity, pins stories to a world map using lightweight place detection, adds a market snapshot, and generates a narrated briefing in the browser.

## Run

```bash
python3 app.py
```

Open `http://localhost:8000`.

## What It Does

- Pulls public RSS feeds from BBC, Guardian, Al Jazeera, Google News regional feeds, NPR, CNBC, MarketWatch, Yahoo Finance, Politico, ESPN, The Hacker News, BleepingComputer, and Krebs on Security.
- Maps stories to regions and countries with a built-in gazetteer.
- Shows category filters for news, economy, politics, sport, and cybersecurity.
- Adds quick map views for World, Europe, Portugal, and the current visible story set.
- Refreshes automatically every 10 minutes when the Auto toggle is on.
- Includes a source health panel so failed or slow feeds are visible.
- Adds a Stooq-based market strip for major indexes, EUR/USD, Bitcoin, and gold.
- Produces an Atlas briefing and can read it aloud using the browser Speech Synthesis API.

## Architecture

- `app.py`: Python standard-library HTTP server, RSS aggregation, caching, summarization, geolocation, market data, JSON API.
- `static/index.html`: dashboard shell.
- `static/styles.css`: responsive map-first interface.
- `static/app.js`: Leaflet map, filters, markers, feed rendering, briefing narration.

## API

- `GET /api/news`: all stories.
- `GET /api/news?category=economy&region=Europe&q=ECB`: filtered stories.
- `GET /api/news?refresh=1`: force feed refresh.
- `GET /api/briefing`: generated briefing.
- `GET /api/markets`: market snapshot.
- `GET /api/health`: server status.

## Next Upgrades

- Replace heuristic place detection with entity extraction and geocoding.
- Store stories in PostGIS for spatial history, clustering, and trend queries.
- Add user-configured source packs for Portugal, trading, cybersecurity, and sports leagues.
- Add LLM summarization with citations and per-topic daily digests.
- Add CesiumJS or MapLibre terrain for a true 3D globe view.

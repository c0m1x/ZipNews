# World Signal

A key-free prototype for a global news intelligence dashboard. It aggregates public RSS feeds for world news, economics, politics, sport, Portugal, and cybersecurity, pins stories to a world map using lightweight place detection, adds a market snapshot, and generates a narrated briefing in the browser.

## Run

```bash
python3 app.py
```

Open `http://localhost:8000`.

For a phone on the same Wi-Fi, use the LAN URL printed by the server, for example
`http://192.168.1.23:8000`.

## Deploy

The app is ready for a public Docker deploy. The simplest path is Render:

1. Push this project to a GitHub/GitLab/Bitbucket repository.
2. In Render, create a new Blueprint from that repository, or create a new Web Service and choose Docker.
3. Keep the default Dockerfile path as `./Dockerfile`.
4. Set the health check path to `/api/health` if you are not using the included `render.yaml`.
5. Deploy. Render will give you a public URL like `https://world-signal.onrender.com`.

The included `render.yaml` config uses the free instance type. Free services can sleep after inactivity, so the first phone load may be slow. Switch the plan in Render if you want it always warm.

For any Docker host:

```bash
docker build -t world-signal .
docker run --rm -p 8080:8080 -e PORT=8080 world-signal
```

## What It Does

- Pulls public RSS feeds from BBC, Guardian, Al Jazeera, DW, France 24, Euronews, Sky, Google News regional feeds, NPR, CNBC, MarketWatch, Yahoo Finance, Politico, PBS, The Hill, ESPN, The Register, CyberScoop, SecurityWeek, Dark Reading, CERT-EU, Schneier, The Hacker News, BleepingComputer, and Krebs on Security.
- Maps stories to regions and countries with a built-in gazetteer.
- Shows category filters for news, economy, politics, sport, and cybersecurity.
- Adds quick map views for World, Europe, Portugal, and the current visible story set.
- Refreshes automatically every 10 minutes when the Auto toggle is on.
- Includes a source health panel so failed or slow feeds are visible.
- Adds a Stooq-based market strip for major indexes, EUR/USD, Bitcoin, and gold.
- Adds a full markets dashboard at `/markets` with sortable asset groups, OHLC data, volume, 52-week ranges, country bond yields, sparklines, and independent refresh.
- Produces an Atlas briefing and can read it aloud using the browser Speech Synthesis API.

## Architecture

- `app.py`: Python standard-library HTTP server, RSS aggregation, caching, summarization, geolocation, market data, JSON API.
- `static/index.html`: dashboard shell.
- `static/markets.html`: full-screen markets page shell.
- `static/styles.css`: responsive map-first interface.
- `static/app.js`: Leaflet map, filters, markers, feed rendering, briefing narration.
- `static/markets.js`: sortable markets table, collapsible groups, sparklines, and page refresh loop.

## API

- `GET /api/news`: all stories.
- `GET /api/news?category=economy&region=Europe&q=ECB`: filtered stories.
- `GET /api/news?refresh=1`: force feed refresh.
- `GET /api/briefing`: generated briefing.
- `GET /api/markets`: expanded market snapshot with OHLC, volume, 52-week range, and chart history.
- `GET /api/health`: server status.

## Next Upgrades

- Replace heuristic place detection with entity extraction and geocoding.
- Store stories in PostGIS for spatial history, clustering, and trend queries.
- Add user-configured source packs for Portugal, trading, cybersecurity, and sports leagues.
- Add LLM summarization with citations and per-topic daily digests.
- Add CesiumJS or MapLibre terrain for a true 3D globe view.

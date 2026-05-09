# World Signal — Task List

## Epic 1 — Map: Replace the canvas map with a fast, interactive renderer

- [ ] **Swap canvas renderer for Leaflet.js (or MapLibre)**
  Remove the current hand-drawn canvas map. Integrate Leaflet.js with a free tile provider (OpenStreetMap, CartoDB Light/Dark). MapLibre is an alternative if vector tiles or 3D terrain is wanted later.
  `frontend` `app.js` `index.html`

- [ ] **Migrate story markers to native map layer**
  Re-implement the existing story pins using Leaflet markers or GeoJSON layer. Each pin should open a popup with headline, source, and category tag on click. Preserve colour-coding by category (news, economy, politics, sport, cyber).
  `frontend` `app.js`

- [ ] **Keep all existing filter & view controls**
  Category filters (news, economy, politics, sport, cyber) and quick-view buttons (World, Europe, Portugal, visible set) must still work after the migration — they now call `map.flyTo()` or update the GeoJSON layer instead of redrawing a canvas.
  `frontend` `app.js`

- [ ] **Match tile theme to dashboard colour scheme** *(nice-to-have)*
  Use a muted tile style (e.g. CartoDB Positron or Voyager) so the map doesn't visually clash with the rest of the dashboard. Ideally switch tile URL when the UI is in dark mode.
  `styles.css`

---

## Epic 2 — Markets page: Full-screen markets dashboard at `/markets`

- [ ] **Create a `/markets` route and page shell**
  Add a new route in `app.py` that serves a dedicated markets page. Add a nav link from the main dashboard. The page should share the same header/footer shell but have its own layout.
  `backend` `frontend` `app.py`

- [ ] **Expand `/api/markets` with a wider instrument list**
  Add more tickers to the Stooq fetcher: major ETFs (SPY, QQQ, VEA, EEM, GLD, SLV, TLT), commodities (crude oil, natural gas, copper), FX pairs beyond EUR/USD (GBP/USD, USD/JPY, USD/BRL), and crypto (ETH, BNB). Return OHLC + volume where available, not just the last price.
  `backend` `app.py`

- [ ] **Add sparkline / mini-chart for each instrument**
  Fetch intraday or last-N-days history per ticker and render a small trend line next to each row. A subtle green/red colour indicates direction. Can use a lightweight canvas chart (Chart.js or uPlot) per cell.
  `frontend` `markets.js`

- [ ] **Build the instrument table with sortable columns**
  Show: name, ticker, last price, change %, day high/low, volume, 52-week range, and sparkline. Allow column-header sorting. Group rows by asset class (indices, ETFs, FX, crypto, commodities) with collapsible sections.
  `frontend` `markets.js`

- [ ] **Keep the existing market strip on the main dashboard** *(no regression)*
  The current top-bar ticker strip (major indexes, EUR/USD, BTC, gold) stays on the home page unchanged. Add a "View all markets →" link that navigates to the new page.
  `app.js`

- [ ] **Auto-refresh markets page independently** *(nice-to-have)*
  The markets page should poll `/api/markets` on its own interval (suggested: 60s, with visual countdown). Independent of the news auto-refresh toggle on the home page.
  `markets.js`
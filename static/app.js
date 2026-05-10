const state = {
  map: null,
  markerLayer: null,
  canvasRenderer: null,
  markers: new Map(),
  payload: null,
  articles: [],
  briefing: null,
  activeCategories: new Set(),
  activeRegion: "all",
  search: "",
  activeId: null,
  previousFocus: null,
  refreshId: 0,
  lastFilterKey: "",
  autoRefreshTimer: null,
  scrollTicking: false,
};

const els = {};

document.addEventListener("DOMContentLoaded", () => {
  cacheElements();
  initMap();
  bindEvents();
  refreshAll();
});

function cacheElements() {
  els.map = document.querySelector("#map");
  els.statusLine = document.querySelector("#statusLine");
  els.marketStrip = document.querySelector("#marketStrip");
  els.refreshButton = document.querySelector("#refreshButton");
  els.autoRefreshToggle = document.querySelector("#autoRefreshToggle");
  els.fitStoriesButton = document.querySelector("#fitStoriesButton");
  els.clearFiltersButton = document.querySelector("#clearFiltersButton");
  els.mapViewButtons = document.querySelectorAll("[data-map-view]");
  els.categoryFilters = document.querySelector("#categoryFilters");
  els.regionSelect = document.querySelector("#regionSelect");
  els.searchInput = document.querySelector("#searchInput");
  els.articleCount = document.querySelector("#articleCount");
  els.sourceMetric = document.querySelector("#sourceMetric");
  els.regionMetric = document.querySelector("#regionMetric");
  els.countryMetric = document.querySelector("#countryMetric");
  els.sourceList = document.querySelector("#sourceList");
  els.briefingButton = document.querySelector("#briefingButton");
  els.briefingSummary = document.querySelector("#briefingSummary");
  els.briefingOverlay = document.querySelector("#briefingOverlay");
  els.briefingLines = document.querySelector("#briefingLines");
  els.closeBriefingButton = document.querySelector("#closeBriefingButton");
  els.activeStory = document.querySelector("#activeStory");
  els.feedCount = document.querySelector("#feedCount");
  els.storyFeed = document.querySelector("#storyFeed");
}

function initMap() {
  if (typeof L === "undefined") {
    setMapFallback("Map unavailable");
    return;
  }

  try {
    state.map = L.map("map", {
      zoomControl: false,
      preferCanvas: true,
      worldCopyJump: false,
      zoomSnap: 0.25,
      zoomDelta: 0.5,
      wheelPxPerZoomLevel: 90,
      minZoom: 1.5,
      maxZoom: 12,
      dragging: true,
      scrollWheelZoom: true,
      touchZoom: true,
      doubleClickZoom: true,
      keyboard: true,
    }).setView([20, 0], 2.15);

    L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
      attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
      subdomains: "abcd",
      maxZoom: 19,
      detectRetina: true,
      keepBuffer: 5,
      updateWhenIdle: false,
      updateWhenZooming: false,
      crossOrigin: true,
    }).addTo(state.map);

    L.control.zoom({ position: "bottomleft" }).addTo(state.map);
    state.canvasRenderer = L.canvas({ padding: 0.5 });
    state.markerLayer = L.layerGroup().addTo(state.map);
    setTimeout(() => state.map.invalidateSize(), 0);
  } catch (error) {
    console.error("Map failed to initialize", error);
    state.map = null;
    state.markerLayer = null;
    state.canvasRenderer = null;
    setMapFallback("Map unavailable");
  }
}

function setMapFallback(message) {
  if (!els.map) {
    return;
  }
  els.map.classList.add("map-fallback");
  els.map.textContent = message;
  els.map.setAttribute("aria-label", message);
}

function bindEvents() {
  els.refreshButton.addEventListener("click", () => refreshAll(true));
  els.fitStoriesButton.addEventListener("click", () => fitVisibleStories());
  els.clearFiltersButton.addEventListener("click", clearFilters);
  els.autoRefreshToggle.addEventListener("change", configureAutoRefresh);
  els.mapViewButtons.forEach((button) => {
    button.addEventListener("click", () => focusMapView(button.dataset.mapView));
  });
  els.regionSelect.addEventListener("change", () => {
    state.activeRegion = els.regionSelect.value;
    render();
  });
  els.searchInput.addEventListener("input", debounce(() => {
    state.search = els.searchInput.value.trim().toLowerCase();
    render();
  }, 160));
  els.briefingButton.addEventListener("click", openBriefing);
  els.closeBriefingButton.addEventListener("click", closeBriefing);
  els.briefingOverlay.addEventListener("click", (event) => {
    if (event.target === els.briefingOverlay) {
      closeBriefing();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !els.briefingOverlay.hidden) {
      closeBriefing();
    }
  });
  window.addEventListener("scroll", scheduleTopbarState, { passive: true });
  window.addEventListener("resize", scheduleTopbarState);
  scheduleTopbarState();
  configureAutoRefresh();
}

function scheduleTopbarState() {
  if (state.scrollTicking) {
    return;
  }
  state.scrollTicking = true;
  requestAnimationFrame(() => {
    state.scrollTicking = false;
    syncTopbarState();
  });
}

function syncTopbarState() {
  const isMobile = window.matchMedia("(max-width: 820px)").matches;
  document.body.classList.toggle("mobile-topbar-collapsed", isMobile && window.scrollY > 72);
}

async function refreshAll(force = false) {
  setLoading(true);
  const refreshId = ++state.refreshId;
  const suffix = force ? "?refresh=1" : "";
  state.briefing = null;
  renderBriefing();
  loadBriefing(suffix, refreshId);
  loadMarkets(suffix, refreshId);

  try {
    const news = await fetchJSON(`/api/news${suffix}`);
    if (refreshId !== state.refreshId) {
      return;
    }
    state.payload = news;
    state.articles = news.articles || [];
    if (!state.activeId && state.articles.length) {
      state.activeId = state.articles[0].id;
    }
    renderCategories();
    renderRegions();
    render();
    els.statusLine.textContent = statusText(news);
  } catch (error) {
    if (refreshId === state.refreshId) {
      state.briefing = { lines: [error.message || "Unable to load feeds."], script: "" };
      renderBriefing();
      els.statusLine.textContent = "Feed refresh failed";
    }
  } finally {
    if (refreshId === state.refreshId) {
      setLoading(false);
    }
  }
}

function loadBriefing(suffix, refreshId) {
  fetchJSON(`/api/briefing${suffix}`)
    .then((briefing) => {
      if (refreshId !== state.refreshId) {
        return;
      }
      state.briefing = briefing;
      renderBriefing();
    })
    .catch((error) => {
      if (refreshId !== state.refreshId) {
        return;
      }
      state.briefing = { lines: [error.message || "Unable to load briefing."], script: "" };
      renderBriefing();
    });
}

function loadMarkets(suffix, refreshId) {
  fetchJSON(`/api/markets${suffix}`)
    .then((markets) => {
      if (refreshId !== state.refreshId) {
        return;
      }
      renderMarkets(markets);
    })
    .catch((error) => {
      if (refreshId !== state.refreshId) {
        return;
      }
      console.warn("Markets unavailable", error);
      renderMarkets(null);
    });
}

function configureAutoRefresh() {
  if (state.autoRefreshTimer) {
    clearInterval(state.autoRefreshTimer);
    state.autoRefreshTimer = null;
  }
  if (els.autoRefreshToggle.checked) {
    state.autoRefreshTimer = setInterval(() => refreshAll(false), 10 * 60 * 1000);
  }
}

function focusMapView(view) {
  const views = {
    world: { center: [20, 0], zoom: 2.15 },
    europe: { center: [50, 12], zoom: 4 },
    portugal: { center: [39.6, -8.1], zoom: 6.25 },
  };
  const target = views[view] || views.world;
  els.mapViewButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.mapView === view);
  });
  if (!state.map) {
    return;
  }
  state.map.flyTo(target.center, target.zoom, { duration: 0.65 });
}

function fitVisibleStories() {
  if (!state.map) {
    focusMapView("world");
    return;
  }
  const bounds = filteredArticles()
    .filter((article) => Number.isFinite(article.lat) && Number.isFinite(article.lon))
    .map((article) => [article.lat, article.lon]);
  if (!bounds.length) {
    focusMapView("world");
    return;
  }
  state.map.fitBounds(bounds, { padding: [56, 56], maxZoom: 6 });
  els.mapViewButtons.forEach((button) => button.classList.remove("is-active"));
}

function clearFilters() {
  state.activeCategories.clear();
  state.activeRegion = "all";
  state.search = "";
  state.activeId = state.articles.length ? state.articles[0].id : null;
  state.lastFilterKey = "";
  els.searchInput.value = "";
  els.regionSelect.value = "all";
  renderCategories();
  render();
  focusMapView("world");
}

async function fetchJSON(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function setLoading(isLoading) {
  els.refreshButton.disabled = isLoading;
  els.refreshButton.textContent = isLoading ? "Refreshing" : "Refresh";
  document.body.classList.toggle("loading", isLoading);
}

function render() {
  const filtered = filteredArticles();
  syncActiveArticle(filtered);
  const filterKey = `${activeCategoryKey()}|${state.activeRegion}|${state.search}`;
  renderMetrics(filtered);
  renderMap(filtered, filterKey);
  renderBriefing();
  renderActiveStory(filtered);
  renderFeed(filtered);
}

function renderCategories() {
  const categories = (state.payload && state.payload.categories) || {};
  const counts = (state.payload && state.payload.stats && state.payload.stats.categoryCounts) || {};
  const buttons = [
    { key: "all", label: "All", color: "#111827", count: state.articles.length },
    ...Object.entries(categories).map(([key, meta]) => ({
      key,
      label: meta.label,
      color: meta.color,
      count: counts[key] || 0,
    })),
  ];

  els.categoryFilters.innerHTML = buttons
    .map((item) => {
      const active = isCategoryActive(item.key);
      return `
        <button class="segment-button ${active ? "is-active" : ""}"
          type="button" data-category="${item.key}" title="${escapeHTML(item.label)}"
          aria-pressed="${active ? "true" : "false"}">
          <span><span class="dot" style="background:${item.color}"></span> ${escapeHTML(item.label)}</span>
          <strong>${item.count}</strong>
        </button>`;
    })
    .join("");

  els.categoryFilters.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      toggleCategory(button.dataset.category);
    });
  });
}

function isCategoryActive(category) {
  return category === "all" ? state.activeCategories.size === 0 : state.activeCategories.has(category);
}

function toggleCategory(category) {
  if (category === "all") {
    state.activeCategories.clear();
  } else if (state.activeCategories.has(category)) {
    state.activeCategories.delete(category);
  } else {
    state.activeCategories.add(category);
  }
  state.lastFilterKey = "";
  renderCategories();
  render();
}

function activeCategoryKey() {
  if (!state.activeCategories.size) {
    return "all";
  }
  return [...state.activeCategories].sort().join(",");
}

function renderRegions() {
  const current = els.regionSelect.value || state.activeRegion;
  const regions = unique(
    state.articles.flatMap((article) => [article.region, article.country]).filter(Boolean)
  ).sort((a, b) => a.localeCompare(b));
  els.regionSelect.innerHTML = [
    `<option value="all">All regions</option>`,
    ...regions.map((region) => `<option value="${escapeAttr(region)}">${escapeHTML(region)}</option>`),
  ].join("");
  els.regionSelect.value = regions.includes(current) ? current : "all";
  state.activeRegion = els.regionSelect.value;
}

function renderMarkets(markets) {
  const items = (markets && markets.items) || [];
  const linkTile = `
    <a class="market-tile market-link" href="/markets">
      <span>Markets</span>
      <strong>View all</strong>
      <small>Full board</small>
    </a>`;
  const signalTile = `
    <a class="market-tile market-link signal-strip-link" href="/signals">
      <span>Signals</span>
      <strong>Trade/War</strong>
      <small>Intel board</small>
    </a>`;
  if (!items.length) {
    els.marketStrip.innerHTML = `<div class="market-tile"><span>Markets</span><strong>Unavailable</strong><small>Snapshot</small></div>${linkTile}${signalTile}`;
    return;
  }
  const stripItems = items.filter((item) => item.strip).slice(0, 6);
  els.marketStrip.innerHTML = stripItems
    .slice(0, 6)
    .map((item) => {
      const value = formatMarketValue(item);
      const change = typeof item.changePct === "number" ? item.changePct : null;
      const className = change === null ? "" : change >= 0 ? "up" : "down";
      const changeText = change === null ? "flat" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`;
      return `
        <div class="market-tile">
          <span>${escapeHTML(item.label)}</span>
          <strong>${value}</strong>
          <small class="${className}">${changeText}</small>
        </div>`;
    })
    .join("") + linkTile + signalTile;
}

function renderMetrics(articles) {
  const stats = (state.payload && state.payload.stats) || {};
  els.articleCount.textContent = articles.length;
  els.sourceMetric.textContent = `${stats.healthySources || 0}/${stats.sourceCount || 0}`;
  els.regionMetric.textContent = unique(articles.map((article) => article.region)).length;
  els.countryMetric.textContent = unique(articles.map((article) => article.country)).length;
  renderSources();
}

function renderSources() {
  const sources = (state.payload && state.payload.sources) || [];
  els.sourceList.innerHTML = sources
    .map(
      (source) => `
        <div class="source-row ${source.ok ? "" : "is-down"}" title="${escapeAttr(source.error || "ok")}">
          <span class="health-dot"></span>
          <strong>${escapeHTML(source.name)}</strong>
          <span>${source.ok ? source.items : "down"}</span>
        </div>`
    )
    .join("");
}

function renderMap(articles, filterKey) {
  if (!state.map || !state.markerLayer) {
    state.lastFilterKey = filterKey;
    return;
  }

  state.markerLayer.clearLayers();
  state.markers.clear();

  const visibleArticles = prioritizeMapArticles(articles);
  const bounds = [];
  visibleArticles.forEach((article) => {
    if (!Number.isFinite(article.lat) || !Number.isFinite(article.lon)) {
      return;
    }
    const offset = jitter(article.id);
    const marker = L.circleMarker([article.lat + offset.lat, article.lon + offset.lon], {
      renderer: state.canvasRenderer,
      radius: article.id === state.activeId ? 11 : 4 + article.impact * 0.65,
      weight: article.id === state.activeId ? 3 : 1.4,
      color: article.id === state.activeId ? "#111827" : article.color,
      fillColor: article.color,
      fillOpacity: article.id === state.activeId ? 0.82 : 0.58,
      opacity: 0.95,
      className: article.id === state.activeId ? "pulse-marker" : "",
    });
    marker.bindPopup(popupHTML(article), { className: "map-popup" });
    marker.on("click", () => setActive(article.id, true));
    marker.addTo(state.markerLayer);
    state.markers.set(article.id, marker);
    bounds.push([article.lat, article.lon]);
  });

  if (state.activeId && state.markers.has(state.activeId)) {
    state.markers.get(state.activeId).bringToFront();
  }

  if (bounds.length && filterKey !== state.lastFilterKey && articles.length < state.articles.length) {
    state.map.fitBounds(bounds, { padding: [42, 42], maxZoom: 5 });
  }
  state.lastFilterKey = filterKey;
  state.map.invalidateSize();
}

function renderBriefing() {
  const lines = (state.briefing && state.briefing.lines) || [];
  const displayLines = lines.length ? lines : ["Building briefing."];
  els.briefingSummary.textContent = displayLines[0];
  els.briefingLines.innerHTML = displayLines.map((line) => `<p>${escapeHTML(line)}</p>`).join("");
}

function openBriefing() {
  state.previousFocus = document.activeElement;
  els.briefingOverlay.hidden = false;
  els.briefingButton.setAttribute("aria-expanded", "true");
  document.body.classList.add("briefing-open");
  els.closeBriefingButton.focus();
}

function closeBriefing() {
  if (els.briefingOverlay.hidden) {
    return;
  }
  els.briefingOverlay.hidden = true;
  els.briefingButton.setAttribute("aria-expanded", "false");
  document.body.classList.remove("briefing-open");
  if (state.previousFocus && typeof state.previousFocus.focus === "function") {
    state.previousFocus.focus();
  }
}

function renderActiveStory(articles) {
  const article = articles.find((item) => item.id === state.activeId) || articles[0];
  if (!article) {
    els.activeStory.innerHTML = "";
    return;
  }
  state.activeId = article.id;
  els.activeStory.innerHTML = `
    <div class="active-story-inner">
      <div class="story-meta">
        <span class="category-pill" style="background:${article.color}">${escapeHTML(article.categoryLabel)}</span>
        <span>${escapeHTML(relativeTime(article.publishedAt))}</span>
        <span>${escapeHTML(article.location)}</span>
      </div>
      <h3>${escapeHTML(article.title)}</h3>
      <p>${escapeHTML(article.summary)}</p>
      <div class="story-footer">
        <span>${escapeHTML(article.source)}</span>
        ${article.url ? `<a class="story-link" href="${escapeAttr(article.url)}" target="_blank" rel="noreferrer">Open story</a>` : ""}
      </div>
    </div>`;
}

function renderFeed(articles) {
  els.feedCount.textContent = articles.length;
  els.storyFeed.innerHTML = articles
    .slice(0, 140)
    .map(
      (article) => `
        <button class="story-item ${article.id === state.activeId ? "is-active" : ""}" type="button" data-id="${article.id}">
          <div class="story-meta">
            <span class="category-pill" style="background:${article.color}">${escapeHTML(article.categoryLabel)}</span>
            <span>${escapeHTML(relativeTime(article.publishedAt))}</span>
            <span>${escapeHTML(article.location)}</span>
          </div>
          <h3>${escapeHTML(article.title)}</h3>
          <p>${escapeHTML(article.summary)}</p>
          <div class="story-footer">
            <span>${escapeHTML(article.source)}</span>
            <span>${escapeHTML(article.region)}</span>
          </div>
        </button>`
    )
    .join("");

  els.storyFeed.querySelectorAll(".story-item").forEach((item) => {
    item.addEventListener("click", () => setActive(item.dataset.id, true));
  });
}

function setActive(id, panMap = false) {
  state.activeId = id;
  const article = state.articles.find((item) => item.id === id);
  if (article && panMap && state.map && Number.isFinite(article.lat) && Number.isFinite(article.lon)) {
    state.map.flyTo([article.lat, article.lon], Math.max(state.map.getZoom(), 4), {
      duration: 0.65,
    });
    const marker = state.markers.get(id);
    if (marker) {
      marker.openPopup();
    }
  }
  render();
}

function filteredArticles() {
  return state.articles.filter((article) => {
    const categoryMatch =
      state.activeCategories.size === 0 || state.activeCategories.has(article.category);
    const regionMatch =
      state.activeRegion === "all" ||
      article.region === state.activeRegion ||
      article.country === state.activeRegion;
    const query = state.search;
    const textMatch =
      !query ||
      `${article.title} ${article.summary} ${article.source} ${article.location} ${article.country}`
        .toLowerCase()
        .includes(query);
    return categoryMatch && regionMatch && textMatch;
  });
}

function syncActiveArticle(articles) {
  if (articles.some((article) => article.id === state.activeId)) {
    return;
  }
  state.activeId = articles.length ? articles[0].id : null;
}

function prioritizeMapArticles(articles) {
  const maxMarkers = 260;
  if (articles.length <= maxMarkers) {
    return articles;
  }
  const active = articles.find((article) => article.id === state.activeId);
  const ranked = articles
    .slice()
    .sort((a, b) => b.impact - a.impact || b.timestamp - a.timestamp)
    .slice(0, maxMarkers);
  if (active && !ranked.some((article) => article.id === active.id)) {
    ranked[ranked.length - 1] = active;
  }
  return ranked.sort((a, b) => b.timestamp - a.timestamp);
}

function popupHTML(article) {
  return `
    <div>
      <span class="category-pill" style="background:${article.color}">${escapeHTML(article.categoryLabel)}</span>
      <strong>${escapeHTML(article.title)}</strong>
      <p>${escapeHTML(article.summary)}</p>
      <div class="story-footer">
        <span>${escapeHTML(article.source)}</span>
        ${article.url ? `<a href="${escapeAttr(article.url)}" target="_blank" rel="noreferrer">Open</a>` : ""}
      </div>
    </div>`;
}

function statusText(payload) {
  const generated = payload && payload.generatedAt ? new Date(payload.generatedAt) : new Date();
  const stats = (payload && payload.stats) || {};
  return `${stats.articleCount || 0} stories across ${Object.keys(stats.regionCounts || {}).length} regions · ${generated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

function relativeTime(value) {
  if (!value) {
    return "recent";
  }
  const then = new Date(value).getTime();
  const diff = Math.max(0, Date.now() - then);
  const minutes = Math.max(1, Math.round(diff / 60000));
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 48) {
    return `${hours}h`;
  }
  const days = Math.round(hours / 24);
  return `${days}d`;
}

function formatMarketValue(item) {
  if (typeof item.value !== "number") {
    return "N/A";
  }
  if (item.symbol.includes("USD") && item.value < 10) {
    return item.value.toFixed(4);
  }
  if (item.symbol === "BTCUSD" || item.symbol === "XAUUSD") {
    return item.value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  return item.value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function jitter(id) {
  const raw = parseInt(id.slice(0, 6), 16);
  const lat = ((raw % 19) - 9) * 0.08;
  const lon = (((raw >> 4) % 19) - 9) * 0.08;
  return { lat, lon };
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function escapeHTML(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeAttr(value) {
  return escapeHTML(value);
}

function debounce(fn, wait) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

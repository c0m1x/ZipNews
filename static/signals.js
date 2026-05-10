const SIGNAL_REFRESH_SECONDS = 300;
const SIGNAL_MARKER_LIMIT = 260;

const signalState = {
  map: null,
  markerLayer: null,
  canvasRenderer: null,
  markers: new Map(),
  items: [],
  categories: {},
  collapsed: new Set(),
  activeCategories: new Set(),
  activeRegion: "all",
  activeId: null,
  search: "",
  lastMapKey: "",
  nextRefreshAt: Date.now() + SIGNAL_REFRESH_SECONDS * 1000,
  timer: null,
  loading: false,
};

const signalEls = {};

document.addEventListener("DOMContentLoaded", () => {
  cacheSignalElements();
  initSignalMap();
  bindSignalEvents();
  refreshSignals(false);
  signalState.timer = setInterval(tickSignals, 1000);
});

function cacheSignalElements() {
  signalEls.status = document.querySelector("#signalsStatus");
  signalEls.refreshButton = document.querySelector("#signalsRefreshButton");
  signalEls.count = document.querySelector("#signalsCount");
  signalEls.conflict = document.querySelector("#signalsConflict");
  signalEls.transport = document.querySelector("#signalsTransport");
  signalEls.trade = document.querySelector("#signalsTrade");
  signalEls.mapCount = document.querySelector("#signalsMapCount");
  signalEls.countdown = document.querySelector("#signalsCountdown");
  signalEls.search = document.querySelector("#signalsSearch");
  signalEls.regionSelect = document.querySelector("#signalsRegionSelect");
  signalEls.categoryFilters = document.querySelector("#signalsCategoryFilters");
  signalEls.clearButton = document.querySelector("#signalsClearButton");
  signalEls.board = document.querySelector("#signalsBoard");
  signalEls.source = document.querySelector("#signalsSource");
  signalEls.map = document.querySelector("#signalsMap");
  signalEls.active = document.querySelector("#signalsActive");
  signalEls.fitButton = document.querySelector("#signalsFitButton");
  signalEls.mapViewButtons = document.querySelectorAll("[data-signal-view]");
}

function initSignalMap() {
  if (typeof L === "undefined") {
    setSignalMapFallback("Map unavailable");
    return;
  }

  try {
    signalState.map = L.map("signalsMap", {
      zoomControl: false,
      preferCanvas: true,
      worldCopyJump: false,
      zoomSnap: 0.25,
      zoomDelta: 0.5,
      wheelPxPerZoomLevel: 90,
      minZoom: 1.5,
      maxZoom: 12,
    }).setView([20, 0], 2.1);

    L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
      attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
      subdomains: "abcd",
      maxZoom: 19,
      detectRetina: true,
      keepBuffer: 5,
      crossOrigin: true,
    }).addTo(signalState.map);

    L.control.zoom({ position: "bottomright" }).addTo(signalState.map);
    signalState.canvasRenderer = L.canvas({ padding: 0.5 });
    signalState.markerLayer = L.layerGroup().addTo(signalState.map);
    setTimeout(() => signalState.map.invalidateSize(), 0);
  } catch (error) {
    console.error("Signals map failed to initialize", error);
    signalState.map = null;
    signalState.markerLayer = null;
    signalState.canvasRenderer = null;
    setSignalMapFallback("Map unavailable");
  }
}

function setSignalMapFallback(message) {
  if (!signalEls.map) {
    return;
  }
  signalEls.map.classList.add("map-fallback");
  signalEls.map.textContent = message;
  signalEls.map.setAttribute("aria-label", message);
}

function bindSignalEvents() {
  signalEls.refreshButton.addEventListener("click", () => refreshSignals(true));
  signalEls.search.addEventListener("input", debounce(() => {
    signalState.search = signalEls.search.value.trim().toLowerCase();
    signalState.lastMapKey = "";
    renderSignalsPage();
  }, 120));
  signalEls.regionSelect.addEventListener("change", () => {
    signalState.activeRegion = signalEls.regionSelect.value;
    signalState.lastMapKey = "";
    renderSignalsPage();
  });
  signalEls.clearButton.addEventListener("click", clearSignalFilters);
  signalEls.categoryFilters.addEventListener("click", (event) => {
    const button = event.target.closest("[data-category]");
    if (button) {
      toggleSignalCategory(button.dataset.category);
    }
  });
  signalEls.fitButton.addEventListener("click", () => fitSignalsMap(filteredSignalItems()));
  signalEls.mapViewButtons.forEach((button) => {
    button.addEventListener("click", () => focusSignalMapView(button.dataset.signalView));
  });
  signalEls.board.addEventListener("click", (event) => {
    const groupButton = event.target.closest("[data-group-toggle]");
    if (groupButton) {
      toggleSignalGroup(groupButton.dataset.groupToggle);
      return;
    }
    const card = event.target.closest("[data-signal-card]");
    if (card && !event.target.closest("a")) {
      setActiveSignal(card.dataset.signalCard, true);
    }
  });
  signalEls.board.addEventListener("keydown", (event) => {
    if (!["Enter", " "].includes(event.key)) {
      return;
    }
    const card = event.target.closest("[data-signal-card]");
    if (!card) {
      return;
    }
    event.preventDefault();
    setActiveSignal(card.dataset.signalCard, true);
  });
}

async function refreshSignals(force) {
  if (signalState.loading) {
    return;
  }
  signalState.loading = true;
  signalEls.refreshButton.disabled = true;
  signalEls.refreshButton.textContent = "Refreshing";
  try {
    const payload = await fetchJSON(`/api/signals${force ? "?refresh=1" : ""}`);
    signalState.items = payload.articles || [];
    signalState.categories = payload.categories || {};
    signalState.lastMapKey = "";
    renderSignalFilters();
    renderSignalsPage();
    const generated = payload.generatedAt ? new Date(payload.generatedAt) : new Date();
    const contacts = countMappableItems(signalState.items);
    signalEls.status.textContent = `Signals updated ${generated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} - ${contacts} radar contacts`;
    signalEls.source.textContent = sourceText(payload.sources || []);
  } catch (error) {
    signalEls.status.textContent = "Signals unavailable";
    signalEls.active.innerHTML = `<div class="signal-empty-focus">${escapeHTML(error.message || "Unable to load signals.")}</div>`;
    signalEls.board.innerHTML = `<div class="market-empty">${escapeHTML(error.message || "Unable to load signals.")}</div>`;
  } finally {
    signalState.loading = false;
    signalEls.refreshButton.disabled = false;
    signalEls.refreshButton.textContent = "Refresh";
    signalState.nextRefreshAt = Date.now() + SIGNAL_REFRESH_SECONDS * 1000;
    updateSignalCountdown();
  }
}

function tickSignals() {
  updateSignalCountdown();
  if (!signalState.loading && Date.now() >= signalState.nextRefreshAt) {
    refreshSignals(false);
  }
}

function updateSignalCountdown() {
  const seconds = Math.max(0, Math.ceil((signalState.nextRefreshAt - Date.now()) / 1000));
  signalEls.countdown.textContent = `${seconds}s`;
}

function renderSignalsPage() {
  const items = filteredSignalItems();
  syncActiveSignal(items);
  renderSignalMetrics(items);
  renderSignalMap(items);
  renderActiveSignal(items);

  if (!items.length) {
    signalEls.board.innerHTML = `<div class="market-empty">No matching signals.</div>`;
    return;
  }

  const groups = groupSignalItems(items);
  signalEls.board.innerHTML = Object.entries(groups)
    .map(([groupKey, groupItems]) => signalGroupHTML(groupKey, groupItems))
    .join("");
}

function renderSignalMetrics(items) {
  const mappedCount = countMappableItems(items);
  signalEls.count.textContent = items.length;
  signalEls.mapCount.textContent = mappedCount;
  signalEls.conflict.textContent = items.filter((item) => ["conflict", "posture"].includes(item.category)).length;
  signalEls.transport.textContent = items.filter((item) => ["maritime", "aviation"].includes(item.category)).length;
  signalEls.trade.textContent = items.filter((item) => item.category === "trade").length;
}

function renderSignalFilters() {
  const categoryCounts = {};
  signalState.items.forEach((item) => {
    categoryCounts[item.category] = (categoryCounts[item.category] || 0) + 1;
  });
  const buttons = [
    { key: "all", label: "All", color: "#111827", count: signalState.items.length },
    ...Object.entries(signalState.categories).map(([key, meta]) => ({
      key,
      label: meta.label,
      color: meta.color,
      count: categoryCounts[key] || 0,
    })),
  ];

  signalEls.categoryFilters.innerHTML = buttons
    .map((item) => {
      const active = isSignalCategoryActive(item.key);
      return `
        <button class="segment-button ${active ? "is-active" : ""}"
          type="button" data-category="${escapeAttr(item.key)}" title="${escapeAttr(item.label)}"
          aria-pressed="${active ? "true" : "false"}">
          <span><span class="dot" style="background:${escapeAttr(item.color)}"></span> ${escapeHTML(item.label)}</span>
          <strong>${item.count}</strong>
        </button>`;
    })
    .join("");

  const current = signalState.activeRegion;
  const regions = unique(
    signalState.items
      .flatMap((item) => [item.region, item.country])
      .filter(Boolean)
  ).sort((a, b) => a.localeCompare(b));
  signalEls.regionSelect.innerHTML = [
    `<option value="all">All regions</option>`,
    ...regions.map((region) => `<option value="${escapeAttr(region)}">${escapeHTML(region)}</option>`),
  ].join("");
  signalEls.regionSelect.value = regions.includes(current) ? current : "all";
  signalState.activeRegion = signalEls.regionSelect.value;
}

function filteredSignalItems() {
  const query = signalState.search;
  const items = signalState.items.filter((item) => {
    const categoryMatch =
      signalState.activeCategories.size === 0 || signalState.activeCategories.has(item.category);
    const regionMatch =
      signalState.activeRegion === "all" ||
      item.region === signalState.activeRegion ||
      item.country === signalState.activeRegion;
    const textMatch =
      !query ||
      `${item.title} ${item.summary} ${item.source} ${item.feed} ${item.location} ${item.country} ${item.region} ${item.categoryLabel}`
        .toLowerCase()
        .includes(query);
    return categoryMatch && regionMatch && textMatch;
  });
  return items.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
}

function groupSignalItems(items) {
  const groups = {};
  Object.keys(signalState.categories).forEach((key) => {
    groups[key] = [];
  });
  items.forEach((item) => {
    const key = item.category || "other";
    if (!groups[key]) {
      groups[key] = [];
    }
    groups[key].push(item);
  });
  return Object.fromEntries(Object.entries(groups).filter(([, groupItems]) => groupItems.length));
}

function signalGroupHTML(groupKey, groupItems) {
  const collapsed = signalState.collapsed.has(groupKey);
  const meta = signalState.categories[groupKey] || { label: groupKey, color: "#637083" };
  const latest = groupItems[0] ? relativeTime(groupItems[0].publishedAt) : "recent";
  return `
    <section class="market-group signal-group ${collapsed ? "is-collapsed" : ""}">
      <button class="market-group-header signal-group-header" type="button" data-group-toggle="${escapeAttr(groupKey)}">
        <span><span class="dot" style="background:${escapeAttr(meta.color)}"></span>${escapeHTML(meta.label)}</span>
        <strong>${groupItems.length}</strong>
        <small>Latest ${escapeHTML(latest)}</small>
      </button>
      <div class="signal-list">
        ${groupItems.slice(0, 24).map((item) => signalCardHTML(item)).join("")}
      </div>
    </section>`;
}

function signalCardHTML(item) {
  const isActive = item.id === signalState.activeId;
  const isMapped = isMappable(item);
  return `
    <article class="signal-card ${isActive ? "is-active" : ""} ${isMapped ? "" : "is-unmapped"}" data-signal-card="${escapeAttr(item.id)}" role="button" tabindex="0" aria-pressed="${isActive ? "true" : "false"}">
      <div class="signal-card-top">
        <span class="category-pill" style="background:${escapeAttr(item.color)}">${escapeHTML(item.categoryLabel)}</span>
        <span>${escapeHTML(relativeTime(item.publishedAt))}</span>
        <span class="${isMapped ? "" : "signal-pending"}">${escapeHTML(signalLocationLabel(item))}</span>
      </div>
      <h3>
        ${item.url ? `<a href="${escapeAttr(item.url)}" target="_blank" rel="noreferrer">${escapeHTML(item.title)}</a>` : escapeHTML(item.title)}
      </h3>
      <p>${escapeHTML(item.summary)}</p>
      <div class="signal-footer">
        <span>${escapeHTML(item.source)}</span>
        <span>${escapeHTML(item.feed)}</span>
      </div>
    </article>`;
}

function renderActiveSignal(items) {
  const item = items.find((candidate) => candidate.id === signalState.activeId);
  if (!item) {
    signalEls.active.innerHTML = `<div class="signal-empty-focus">No matching signals.</div>`;
    return;
  }

  signalEls.active.innerHTML = `
    <div class="signal-active-card ${isMappable(item) ? "" : "is-unmapped"}">
      <div class="signal-card-top">
        <span class="category-pill" style="background:${escapeAttr(item.color)}">${escapeHTML(item.categoryLabel)}</span>
        <span>${escapeHTML(relativeTime(item.publishedAt))}</span>
        <span class="${isMappable(item) ? "" : "signal-pending"}">${escapeHTML(signalLocationLabel(item))}</span>
      </div>
      <h3>${escapeHTML(item.title)}</h3>
      <p>${escapeHTML(item.summary)}</p>
      <dl class="signal-details">
        <div>
          <dt>Radar fix</dt>
          <dd>${escapeHTML(signalLocationLabel(item))}</dd>
        </div>
        <div>
          <dt>Precision</dt>
          <dd>${escapeHTML(signalPrecisionLabel(item))}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>${escapeHTML(item.source)}</dd>
        </div>
      </dl>
      ${item.url ? `<a class="signal-open-link" href="${escapeAttr(item.url)}" target="_blank" rel="noreferrer">Open story</a>` : ""}
    </div>`;
}

function renderSignalMap(items) {
  if (!signalState.map || !signalState.markerLayer) {
    return;
  }

  signalState.markerLayer.clearLayers();
  signalState.markers.clear();

  const mappableItems = items.filter(isMappable);
  const visibleItems = prioritizeSignalMapItems(mappableItems);
  const bounds = [];
  visibleItems.forEach((item) => {
    const offset = jitter(item.id);
    const isActive = item.id === signalState.activeId;
    const marker = L.circleMarker([item.lat + offset.lat, item.lon + offset.lon], {
      renderer: signalState.canvasRenderer,
      radius: isActive ? 11 : 5 + Math.min(item.impact || 4, 10) * 0.55,
      weight: isActive ? 3 : 1.4,
      color: isActive ? "#111827" : item.color,
      fillColor: item.color,
      fillOpacity: isActive ? 0.86 : 0.62,
      opacity: 0.95,
      className: isActive ? "pulse-marker" : "",
    });
    marker.bindPopup(signalPopupHTML(item), { className: "map-popup" });
    marker.on("click", () => setActiveSignal(item.id, true));
    marker.addTo(signalState.markerLayer);
    signalState.markers.set(item.id, marker);
    bounds.push([item.lat, item.lon]);
  });

  if (signalState.activeId && signalState.markers.has(signalState.activeId)) {
    signalState.markers.get(signalState.activeId).bringToFront();
  }

  const mapKey = `${activeSignalCategoryKey()}|${signalState.activeRegion}|${signalState.search}`;
  if (bounds.length && mapKey !== signalState.lastMapKey) {
    fitSignalsMap(mappableItems, true);
  }
  signalState.lastMapKey = mapKey;
  signalState.map.invalidateSize();
}

function signalPopupHTML(item) {
  return `
    <div>
      <span class="category-pill" style="background:${escapeAttr(item.color)}">${escapeHTML(item.categoryLabel)}</span>
      <strong>${escapeHTML(item.title)}</strong>
      <p>${escapeHTML(item.summary)}</p>
      <div class="story-footer">
        <span>${escapeHTML(signalLocationLabel(item))}</span>
        <span>${escapeHTML(item.source)}</span>
        ${item.url ? `<a href="${escapeAttr(item.url)}" target="_blank" rel="noreferrer">Open</a>` : ""}
      </div>
    </div>`;
}

function setActiveSignal(id, panMap = false) {
  signalState.activeId = id;
  renderSignalsPage();
  const item = signalState.items.find((candidate) => candidate.id === id);
  if (!item || !panMap || !signalState.map || !Number.isFinite(item.lat) || !Number.isFinite(item.lon)) {
    return;
  }
  signalState.map.flyTo([item.lat, item.lon], Math.max(signalState.map.getZoom(), 4), { duration: 0.6 });
  const marker = signalState.markers.get(id);
  if (marker) {
    setTimeout(() => marker.openPopup(), 120);
  }
}

function syncActiveSignal(items) {
  if (items.some((item) => item.id === signalState.activeId)) {
    return;
  }
  const mapped = items.find(isMappable);
  signalState.activeId = mapped ? mapped.id : items.length ? items[0].id : null;
}

function prioritizeSignalMapItems(items) {
  if (items.length <= SIGNAL_MARKER_LIMIT) {
    return items;
  }
  const active = items.find((item) => item.id === signalState.activeId);
  const ranked = items
    .slice()
    .sort((a, b) => (b.impact || 0) - (a.impact || 0) || (b.timestamp || 0) - (a.timestamp || 0))
    .slice(0, SIGNAL_MARKER_LIMIT);
  if (active && !ranked.some((item) => item.id === active.id)) {
    ranked[ranked.length - 1] = active;
  }
  return ranked.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
}

function fitSignalsMap(items, quiet = false) {
  if (!signalState.map) {
    return;
  }
  const bounds = items
    .filter(isMappable)
    .map((item) => [item.lat, item.lon]);
  if (!bounds.length) {
    focusSignalMapView("world");
    return;
  }
  signalState.map.fitBounds(bounds, { padding: [44, 44], maxZoom: quiet ? 5 : 6 });
  if (!quiet) {
    signalEls.mapViewButtons.forEach((button) => button.classList.remove("is-active"));
  }
}

function focusSignalMapView(view) {
  const views = {
    world: { center: [20, 0], zoom: 2.1 },
    europe: { center: [50, 12], zoom: 4 },
    "middle-east": { center: [29, 42], zoom: 4 },
    "indo-pacific": { center: [11, 105], zoom: 3.45 },
  };
  const target = views[view] || views.world;
  signalEls.mapViewButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.signalView === view);
  });
  if (signalState.map) {
    signalState.map.flyTo(target.center, target.zoom, { duration: 0.65 });
  }
}

function toggleSignalCategory(category) {
  if (category === "all") {
    signalState.activeCategories.clear();
  } else if (signalState.activeCategories.has(category)) {
    signalState.activeCategories.delete(category);
  } else {
    signalState.activeCategories.add(category);
  }
  signalState.lastMapKey = "";
  renderSignalFilters();
  renderSignalsPage();
}

function toggleSignalGroup(key) {
  if (signalState.collapsed.has(key)) {
    signalState.collapsed.delete(key);
  } else {
    signalState.collapsed.add(key);
  }
  renderSignalsPage();
}

function clearSignalFilters() {
  signalState.activeCategories.clear();
  signalState.activeRegion = "all";
  signalState.search = "";
  signalState.lastMapKey = "";
  signalEls.search.value = "";
  renderSignalFilters();
  renderSignalsPage();
  focusSignalMapView("world");
}

function isSignalCategoryActive(category) {
  return category === "all" ? signalState.activeCategories.size === 0 : signalState.activeCategories.has(category);
}

function activeSignalCategoryKey() {
  if (!signalState.activeCategories.size) {
    return "all";
  }
  return [...signalState.activeCategories].sort().join(",");
}

async function fetchJSON(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function sourceText(sources) {
  const healthy = sources.filter((source) => source.ok).length;
  if (!sources.length) {
    return "Signal sources unavailable.";
  }
  return `${healthy}/${sources.length} topic feeds live. Ship and air feeds only plot concrete ports, routes, airports, and cargo hubs.`;
}

function isMappable(item) {
  return Number.isFinite(item.lat) && Number.isFinite(item.lon);
}

function countMappableItems(items) {
  return items.filter(isMappable).length;
}

function signalLocationLabel(item) {
  if (isMappable(item)) {
    return item.location || item.country || "Mapped contact";
  }
  return item.location || "Radar fix pending";
}

function signalPrecisionLabel(item) {
  if (item.locationPrecision === "radar") {
    return "Transport radar point";
  }
  if (item.locationPrecision === "unmapped") {
    if (item.category === "posture") {
      return "No broad public strategic zone detected";
    }
    return "No concrete port, route, airport, or cargo hub detected";
  }
  if (item.locationPrecision === "strategic-zone") {
    return "Broad public defense zone";
  }
  return "General news location";
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

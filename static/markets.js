const MARKET_REFRESH_SECONDS = 60;

const marketState = {
  items: [],
  groups: {},
  sortKey: "label",
  sortDirection: "asc",
  collapsed: new Set(),
  search: "",
  nextRefreshAt: Date.now() + MARKET_REFRESH_SECONDS * 1000,
  timer: null,
  loading: false,
};

const marketEls = {};

document.addEventListener("DOMContentLoaded", () => {
  cacheMarketElements();
  bindMarketEvents();
  refreshMarkets(false);
  marketState.timer = setInterval(tickMarkets, 1000);
});

function cacheMarketElements() {
  marketEls.status = document.querySelector("#marketsStatus");
  marketEls.refreshButton = document.querySelector("#marketsRefreshButton");
  marketEls.count = document.querySelector("#marketsCount");
  marketEls.up = document.querySelector("#marketsUp");
  marketEls.down = document.querySelector("#marketsDown");
  marketEls.countdown = document.querySelector("#marketsCountdown");
  marketEls.search = document.querySelector("#marketsSearch");
  marketEls.table = document.querySelector("#marketsTable");
  marketEls.source = document.querySelector("#marketsSource");
}

function bindMarketEvents() {
  marketEls.refreshButton.addEventListener("click", () => refreshMarkets(true));
  marketEls.search.addEventListener("input", debounce(() => {
    marketState.search = marketEls.search.value.trim().toLowerCase();
    renderMarketsPage();
  }, 120));
  marketEls.table.addEventListener("click", (event) => {
    const sortButton = event.target.closest("[data-sort]");
    if (sortButton) {
      setMarketSort(sortButton.dataset.sort);
      return;
    }
    const groupButton = event.target.closest("[data-group-toggle]");
    if (groupButton) {
      const key = groupButton.dataset.groupToggle;
      if (marketState.collapsed.has(key)) {
        marketState.collapsed.delete(key);
      } else {
        marketState.collapsed.add(key);
      }
      renderMarketsPage();
    }
  });
}

async function refreshMarkets(force) {
  if (marketState.loading) {
    return;
  }
  marketState.loading = true;
  marketEls.refreshButton.disabled = true;
  marketEls.refreshButton.textContent = "Refreshing";
  try {
    const payload = await fetchJSON(`/api/markets${force ? "?refresh=1" : ""}`);
    marketState.items = payload.items || [];
    marketState.groups = payload.groups || {};
    renderMarketsPage(payload);
    const generated = payload.generatedAt ? new Date(payload.generatedAt) : new Date();
    marketEls.status.textContent = `Markets updated ${generated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
    marketEls.source.textContent = sourceText(payload.status || {});
  } catch (error) {
    marketEls.status.textContent = "Markets unavailable";
    marketEls.table.innerHTML = `<div class="market-empty">${escapeHTML(error.message || "Unable to load markets.")}</div>`;
  } finally {
    marketState.loading = false;
    marketEls.refreshButton.disabled = false;
    marketEls.refreshButton.textContent = "Refresh";
    marketState.nextRefreshAt = Date.now() + MARKET_REFRESH_SECONDS * 1000;
    updateMarketCountdown();
  }
}

function tickMarkets() {
  updateMarketCountdown();
  if (!marketState.loading && Date.now() >= marketState.nextRefreshAt) {
    refreshMarkets(false);
  }
}

function updateMarketCountdown() {
  const seconds = Math.max(0, Math.ceil((marketState.nextRefreshAt - Date.now()) / 1000));
  marketEls.countdown.textContent = `${seconds}s`;
}

function setMarketSort(key) {
  if (marketState.sortKey === key) {
    marketState.sortDirection = marketState.sortDirection === "asc" ? "desc" : "asc";
  } else {
    marketState.sortKey = key;
    marketState.sortDirection = key === "label" || key === "displaySymbol" ? "asc" : "desc";
  }
  renderMarketsPage();
}

function renderMarketsPage(payload) {
  const items = filteredMarketItems();
  marketEls.count.textContent = items.length;
  marketEls.up.textContent = items.filter((item) => item.changePct > 0).length;
  marketEls.down.textContent = items.filter((item) => item.changePct < 0).length;

  if (!items.length) {
    marketEls.table.innerHTML = `<div class="market-empty">No matching instruments.</div>`;
    return;
  }

  const groups = groupMarketItems(items);
  marketEls.table.innerHTML = Object.entries(groups)
    .map(([groupKey, groupItems]) => groupHTML(groupKey, groupItems))
    .join("");
  requestAnimationFrame(drawMarketSparklines);

  if (payload && payload.status && !payload.status.ok) {
    marketEls.status.textContent = "Market sources are degraded";
  }
}

function filteredMarketItems() {
  const query = marketState.search;
  const items = query
    ? marketState.items.filter((item) =>
        `${item.label} ${item.displaySymbol} ${item.symbol} ${item.assetClassLabel}`
          .toLowerCase()
          .includes(query)
      )
    : marketState.items.slice();
  return items.sort(compareMarketItems);
}

function groupMarketItems(items) {
  const groups = {};
  const groupOrder = Object.keys(marketState.groups);
  groupOrder.forEach((key) => {
    groups[key] = [];
  });
  items.forEach((item) => {
    const key = item.assetClass || "other";
    if (!groups[key]) {
      groups[key] = [];
    }
    groups[key].push(item);
  });
  return Object.fromEntries(Object.entries(groups).filter(([, groupItems]) => groupItems.length));
}

function groupHTML(groupKey, groupItems) {
  const collapsed = marketState.collapsed.has(groupKey);
  const label = marketState.groups[groupKey] || groupKey;
  const advancers = groupItems.filter((item) => item.changePct > 0).length;
  return `
    <section class="market-group ${collapsed ? "is-collapsed" : ""}">
      <button class="market-group-header" type="button" data-group-toggle="${escapeAttr(groupKey)}">
        <span>${escapeHTML(label)}</span>
        <strong>${groupItems.length}</strong>
        <small>${advancers} up</small>
      </button>
      <div class="market-table-wrap">
        <table class="instrument-table">
          <thead>
            <tr>
              ${headerCell("label", "Name")}
              ${headerCell("displaySymbol", "Ticker")}
              ${headerCell("value", "Last")}
              ${headerCell("changePct", "Change")}
              ${headerCell("dayRange", "Day Range")}
              ${headerCell("volume", "Volume")}
              ${headerCell("range52w", "52W Range")}
              <th>Trend</th>
            </tr>
          </thead>
          <tbody>
            ${groupItems.map((item) => rowHTML(item)).join("")}
          </tbody>
        </table>
      </div>
    </section>`;
}

function headerCell(key, label) {
  const active = marketState.sortKey === key;
  const direction = active ? marketState.sortDirection : "";
  return `
    <th>
      <button class="${active ? "is-active" : ""}" type="button" data-sort="${key}">
        ${escapeHTML(label)}${direction ? `<span>${direction === "asc" ? "ASC" : "DESC"}</span>` : ""}
      </button>
    </th>`;
}

function rowHTML(item) {
  const changeClass = item.changePct == null ? "" : item.changePct >= 0 ? "up" : "down";
  return `
    <tr>
      <td data-label="Name">
        <strong>${escapeHTML(item.label)}</strong>
        <span>${escapeHTML(item.assetClassLabel || "")}</span>
      </td>
      <td data-label="Ticker">${escapeHTML(item.displaySymbol || item.symbol)}</td>
      <td data-label="Last">${formatMarketPrice(item.value, item)}</td>
      <td data-label="Change" class="${changeClass}">${formatPercent(item.changePct)}</td>
      <td data-label="Day Range">${formatRange(item.low, item.high, item)}</td>
      <td data-label="Volume">${formatVolume(item.volume)}</td>
      <td data-label="52W Range">${formatRange(item.range52w && item.range52w.low, item.range52w && item.range52w.high, item)}</td>
      <td data-label="Trend"><canvas class="sparkline" data-symbol="${escapeAttr(item.symbol)}" width="140" height="42"></canvas></td>
    </tr>`;
}

function drawMarketSparklines() {
  const bySymbol = new Map(marketState.items.map((item) => [item.symbol, item]));
  document.querySelectorAll(".sparkline").forEach((canvas) => {
    const item = bySymbol.get(canvas.dataset.symbol);
    drawSparkline(canvas, item ? item.history || [] : [], item ? item.changePct : null);
  });
}

function drawSparkline(canvas, history, changePct) {
  const ctx = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(80, Math.floor(rect.width || canvas.width));
  const height = Math.max(28, Math.floor(rect.height || canvas.height));
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const values = history.map((point) => point.close).filter((value) => Number.isFinite(value));
  if (values.length < 2) {
    ctx.fillStyle = "rgba(99, 112, 131, 0.32)";
    ctx.fillRect(0, height / 2, width, 1);
    return;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min || 1;
  const color = changePct == null ? "#637083" : changePct >= 0 ? "#178457" : "#bd2f3d";
  ctx.lineWidth = 2;
  ctx.strokeStyle = color;
  ctx.beginPath();
  values.forEach((value, index) => {
    const x = (index / (values.length - 1)) * width;
    const y = height - 4 - ((value - min) / spread) * (height - 8);
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.stroke();
}

function compareMarketItems(a, b) {
  const direction = marketState.sortDirection === "asc" ? 1 : -1;
  const aValue = marketSortValue(a, marketState.sortKey);
  const bValue = marketSortValue(b, marketState.sortKey);
  if (typeof aValue === "string" || typeof bValue === "string") {
    return String(aValue).localeCompare(String(bValue)) * direction;
  }
  const left = Number.isFinite(aValue) ? aValue : -Infinity;
  const right = Number.isFinite(bValue) ? bValue : -Infinity;
  return (left - right) * direction;
}

function marketSortValue(item, key) {
  if (key === "dayRange") {
    return (item.high || 0) - (item.low || 0);
  }
  if (key === "range52w") {
    return item.range52w && item.range52w.high;
  }
  return item[key] == null ? "" : item[key];
}

async function fetchJSON(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function sourceText(status) {
  const sources = [];
  if (status.sources && status.sources.stooq) {
    sources.push("Stooq quotes");
  }
  if (status.sources && status.sources.yahoo) {
    sources.push("Yahoo history");
  }
  if (status.sources && status.sources.tradingView) {
    sources.push("TradingView bond yields");
  }
  if (!sources.length) {
    return "Market sources unavailable.";
  }
  const errors = status.historyErrors ? ` - ${status.historyErrors} history gaps` : "";
  return `${sources.join(" + ")}${errors}`;
}

function formatMarketPrice(value, item) {
  if (typeof value !== "number") {
    return "N/A";
  }
  if (item.assetClass === "bonds") {
    return `${value.toFixed(3)}%`;
  }
  const symbol = item.displaySymbol || item.symbol || "";
  if (symbol.includes("/") && value < 10) {
    return value.toFixed(4);
  }
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  if (Math.abs(value) < 10) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatPercent(value) {
  if (typeof value !== "number") {
    return "flat";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatRange(low, high, item = {}) {
  if (typeof low !== "number" || typeof high !== "number") {
    return "N/A";
  }
  if (item.assetClass === "bonds") {
    return `${low.toFixed(3)}% / ${high.toFixed(3)}%`;
  }
  return `${formatCompactNumber(low)} / ${formatCompactNumber(high)}`;
}

function formatVolume(value) {
  if (typeof value !== "number") {
    return "N/A";
  }
  return formatCompactNumber(value);
}

function formatCompactNumber(value) {
  return value.toLocaleString(undefined, {
    notation: Math.abs(value) >= 100000 ? "compact" : "standard",
    maximumFractionDigits: Math.abs(value) >= 1000 ? 2 : 4,
  });
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

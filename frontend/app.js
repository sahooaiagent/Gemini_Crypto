/* ═══════════════════════════════════════════════════════════════════
   GEMINI SCANNER — ENTERPRISE APPLICATION LOGIC
   ═══════════════════════════════════════════════════════════════════ */

const API_URL = 'http://localhost:8001';
let allResults = [];
let allHilegaResults = [];
let allCrossResults = [];
let allConflictResults = [];
let scanRunning = false;
let lastScanConfig = null;
let logPollInterval = null;
let currentSort = { col: null, asc: true };
let currentHilegaSort = { col: null, asc: true };
let currentCrossSort = { col: null, asc: true };
let currentConflictSort = { col: null, asc: true };
let currentPerformanceSort = { col: 'symbol', asc: true };
let performanceMonth = null;

// ── DOM REFS ──
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ══════════════════════════════════════════════════════════════
// INITIALIZATION
// ══════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initClock();
    initTickerTape();
    initScannerControls();
    initFilterControls();
    initMobileMenu();
    initThemeToggle();
    initTickerSpeedControl();
    setupPerformanceControls();
    setConnectionStatus(true);

    // Initial data fetch
    fetchMarketData();
    fetchResults();
    fetchTradeSetups();   // load setups on page open

    // Initialize performance tracker
    renderPerformanceTracker(loadPerformanceData().trades, getTodayKey());
    setInterval(updatePerformanceStatus, 5 * 60 * 1000);
    updatePerformanceStatus();

    // Refresh Setups button
    const refreshSetupsBtn = $('#refreshSetupsBtn');
    if (refreshSetupsBtn) refreshSetupsBtn.addEventListener('click', fetchTradeSetups);

    // Periodic refresh
    setInterval(fetchMarketData, 60000);
    setInterval(() => { if (!scanRunning) fetchResults(); }, 30000);

    // Clock-aligned 15-minute refresh (fires at :00, :15, :30, :45)
    scheduleAlignedSetupRefresh();
});

// ══════════════════════════════════════════════════════════════
// NAVIGATION
// ══════════════════════════════════════════════════════════════
function initNavigation() {
    $$('.nav-link').forEach(link => {
        link.addEventListener('click', () => {
            const tab = link.dataset.tab;
            $$('.nav-link').forEach(l => l.classList.remove('active'));
            link.classList.add('active');
            $$('.tab-content').forEach(t => t.classList.remove('active'));
            $(`#tab-${tab}`).classList.add('active');
            // Load content for specific tabs
            if (tab === 'performance') {
                fetchTradeSetups();
                fetchMarketHeatmap();
            }
            // Close mobile sidebar
            $('#sidebar').classList.remove('open');
        });
    });
}

function buildMonthOptions() {
    const select = document.createElement('select');
    const now = new Date();
    const options = [];
    for (let offset = 0; offset < 4; offset++) {
        const date = new Date(now.getFullYear(), now.getMonth() - offset, 1);
        const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
        const label = date.toLocaleString('en-US', { month: 'long', year: 'numeric' });
        options.push({ value: key, label });
    }
    return options;
}

function setupPerformanceControls() {
    const searchInput = $('#performanceSearchInput');
    const monthSelect = $('#performanceMonthSelect');
    if (monthSelect) {
        const options = buildMonthOptions();
        monthSelect.innerHTML = `<option value="">Current month</option>` + options.map(o => `<option value="${o.value}">${o.label}</option>`).join('');
        performanceMonth = monthSelect.value || getCurrentMonthKey();
        monthSelect.addEventListener('change', () => {
            performanceMonth = monthSelect.value || getCurrentMonthKey();
            renderPerformanceTracker(loadPerformanceData().trades, getTodayKey());
        });
    }
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            renderPerformanceTracker(loadPerformanceData().trades, getTodayKey());
        });
    }
    const headers = document.querySelectorAll('#performanceTrackerTable thead th.sortable');
    headers.forEach(th => {
        th.addEventListener('click', () => {
            const col = th.dataset.sort;
            if (!col) return;
            if (currentPerformanceSort.col === col) {
                currentPerformanceSort.asc = !currentPerformanceSort.asc;
            } else {
                currentPerformanceSort.col = col;
                currentPerformanceSort.asc = true;
            }
            renderPerformanceTracker(loadPerformanceData().trades, getTodayKey());
        });
    });
}

// ══════════════════════════════════════════════════════════════
// LIVE CLOCK
// ══════════════════════════════════════════════════════════════
function initClock() {
    const clockEl = $('#liveClock');
    function updateClock() {
        const now = new Date();
        clockEl.textContent = now.toLocaleString('en-US', {
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            hour12: false, day: '2-digit', month: 'short', year: 'numeric'
        });
    }
    updateClock();
    setInterval(updateClock, 1000);
}

// ══════════════════════════════════════════════════════════════
// TICKER TAPE
// ══════════════════════════════════════════════════════════════
let CRYPTO_TICKERS = []; // Populated dynamically from market-data

function initTickerTape() {
    renderTickerTape();
}

function renderTickerTape() {
    const track = $('#tickerTrack');
    if (!CRYPTO_TICKERS || CRYPTO_TICKERS.length === 0) {
        track.innerHTML = '<span class="ticker-item">Loading market data...</span>';
        return;
    }
    // Duplicate items for seamless loop
    const items = [...CRYPTO_TICKERS, ...CRYPTO_TICKERS, ...CRYPTO_TICKERS].map(idx => {
        const changeVal = parseFloat(idx.change) || 0;
        const changeCls = changeVal >= 0 ? 'change-up' : 'change-down';
        const arrow = changeVal >= 0 ? '▲' : '▼';
        return `
            <span class="ticker-item">
                <span class="name">${idx.name}</span>
                <span class="price">$${idx.price || 'N/A'}</span>
                <span class="${changeCls}">${arrow} ${idx.change}%</span>
            </span>
        `;
    }).join('');
    track.innerHTML = items;
}

async function fetchMarketData() {
    try {
        const res = await fetch(`${API_URL}/api/market-data`);
        if (res.ok) {
            const data = await res.json();
            if (data.indices) {
                CRYPTO_TICKERS = data.indices
                    .filter(item => !item.name || !item.name.toUpperCase().includes('USDC'))
                    .sort((a, b) => (a.name || '').localeCompare(b.name || ''))
                    .slice(0, 20);
                renderTickerTape();
                updatePerformanceStatus();
            }
        }
    } catch (e) {
        console.error("Failed to fetch market data:", e);
    }
}

// Old heatmap rendering is intentionally disabled because Market Heatmap now uses a dedicated endpoint
// and its own card layout via renderMarketHeatmap().
function renderHeatmap() {
    const grid = $('#heatmapGrid');
    if (!CRYPTO_TICKERS || CRYPTO_TICKERS.length === 0) {
        grid.innerHTML = '<div class="empty-state">Loading heatmap...</div>';
        return;
    }
    grid.innerHTML = CRYPTO_TICKERS.map(idx => {
        const changeVal = parseFloat(idx.change) || 0;
        const cls = changeVal > 0 ? 'positive' : changeVal < 0 ? 'negative' : 'neutral';
        const changeCls = changeVal >= 0 ? 'up' : 'down';
        return `
            <div class="heatmap-tile ${cls}">
                <span class="heatmap-name">${idx.name}</span>
                <span class="heatmap-price">$${idx.price || 'N/A'}</span>
                <span class="heatmap-change ${changeCls}">
                    <i class="fas fa-caret-${changeVal >= 0 ? 'up' : 'down'}"></i>
                    ${idx.change}%
                </span>
            </div>
        `;
    }).join('');
}

// ══════════════════════════════════════════════════════════════
// LIVE TRADE SETUPS
// ══════════════════════════════════════════════════════════════
// Returns ms until the next :00, :15, :30, or :45 minute mark
function msUntilNextQuarter() {
    const now = new Date();
    const mins = now.getMinutes();
    const secs = now.getSeconds();
    const ms   = now.getMilliseconds();
    const nextQuarterMin = (Math.floor(mins / 15) + 1) * 15;   // e.g. 19 → 30
    const minsLeft = nextQuarterMin - mins;
    return (minsLeft * 60 - secs) * 1000 - ms;
}

function scheduleAlignedSetupRefresh() {
    const delay = msUntilNextQuarter();
    const nextTime = new Date(Date.now() + delay);
    const hh = String(nextTime.getHours()).padStart(2, '0');
    const mm = String(nextTime.getMinutes()).padStart(2, '0');
    updateNextRefreshLabel(`Next auto-refresh at ${hh}:${mm}`);

    setTimeout(() => {
        fetchTradeSetups();
        fetchMarketHeatmap();
        // After first aligned fire, repeat exactly every 15 minutes
        setInterval(() => {
            fetchTradeSetups();
            fetchMarketHeatmap();
            const n = new Date(Date.now() + 15 * 60 * 1000);
            updateNextRefreshLabel(`Next auto-refresh at ${String(n.getHours()).padStart(2,'0')}:${String(n.getMinutes()).padStart(2,'0')}`);
        }, 15 * 60 * 1000);
    }, delay);
}

function updateNextRefreshLabel(text) {
    const el = $('#tradeSetupsTimestamp');
    if (el) el.textContent = text;
}

const PERFORMANCE_STORAGE_KEY = 'gemini_performance_tracker';

function getTodayKey() {
    return new Date().toISOString().slice(0, 10);
}

function getCurrentMonthKey() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function formatMonthLabel(monthKey) {
    if (!monthKey) return 'Unknown';
    const [year, month] = monthKey.split('-').map(Number);
    const date = new Date(year, month - 1, 1);
    return date.toLocaleString('en-US', { month: 'long', year: 'numeric' });
}

function isRoundQuarterTime(date) {
    const minutes = date.getMinutes();
    return minutes % 15 === 0;
}

function loadPerformanceData() {
    try {
        const raw = localStorage.getItem(PERFORMANCE_STORAGE_KEY);
        const data = raw ? JSON.parse(raw) : null;
        const today = getTodayKey();
        if (!data) {
            return { day: today, trades: [], history: {} };
        }

        if (!data.history) data.history = {};

        if (data.day && data.day !== today) {
            const priceIndex = buildPriceIndex();
            finalizeOutstandingTrades(data.trades, priceIndex);
            data.history[data.day] = {
                date: data.day,
                trades: data.trades,
                summary: computePerformanceSummary(data.trades)
            };
            data.trades = [];
            data.day = today;
            savePerformanceData(data);
            return data;
        }

        if (data.day !== today) {
            data.day = today;
            data.trades = [];
            data.history = data.history || {};
            savePerformanceData(data);
            return data;
        }

        const validTrades = data.trades.filter(trade => {
            if (!trade.created_at) return false;
            const createdAt = new Date(trade.created_at);
            return !Number.isNaN(createdAt) && isRoundQuarterTime(createdAt);
        });

        if (validTrades.length !== data.trades.length) {
            data.trades = validTrades;
            savePerformanceData(data);
        }

        return data;
    } catch (e) {
        console.warn('[PerformanceTracker] load error', e);
        return { day: getTodayKey(), trades: [], history: {} };
    }
}

function savePerformanceData(data) {
    localStorage.setItem(PERFORMANCE_STORAGE_KEY, JSON.stringify(data));
}

function resetPerformanceData() {
    const data = { day: getTodayKey(), trades: [], history: {} };
    savePerformanceData(data);
    renderPerformanceTracker(data.trades, data.day);
}

function parsePrice(value) {
    if (value === null || value === undefined) return null;
    if (typeof value === 'number') return value;
    return Number(String(value).replace(/[^0-9.\-]+/g, '')) || null;
}

function buildPriceIndex() {
    return (CRYPTO_TICKERS || []).reduce((map, item) => {
        if (!item || !item.name) return map;
        const symbol = item.name.toString().trim();
        const price = parsePrice(item.price);
        if (price !== null) {
            map[symbol] = price;
        }
        return map;
    }, {});
}

function normalizeSymbol(symbol) {
    if (!symbol) return '';
    return symbol.toString().replace(/\//g, '').replace(/:/g, '').replace(/USDT/g, '').trim();
}

function getClosurePrice(trade, priceIndex) {
    const currentPrice = getCurrentPrice(trade.symbol, priceIndex);
    if (currentPrice !== null) return currentPrice;
    const entry = parsePrice(trade.entry);
    return entry;
}

function finalizeOutstandingTrades(trades, priceIndex = {}) {
    trades.forEach(trade => {
        if (['Target 1 hit', 'Target 2 hit', 'Stopped out', 'Closed (EOD)'].includes(trade.status)) {
            return;
        }
        const price = getClosurePrice(trade, priceIndex);
        if (price === null) {
            trade.status = 'Closed (EOD)';
            trade.profit_loss = 'Closed';
            trade.closed_price = null;
            trade.updated_at = new Date().toISOString();
            return;
        }

        const isLong = trade.signal === 'LONG';
        const entry = parsePrice(trade.entry);
        const stopLoss = parsePrice(trade.stop_loss);
        const target1 = parsePrice(trade.target_1);
        const target2 = parsePrice(trade.target_2);

        if (isLong) {
            if (target2 !== null && price >= target2) {
                trade.status = 'Target 2 hit';
                trade.profit_loss = 'Profit';
            } else if (target1 !== null && price >= target1) {
                trade.status = 'Target 1 hit';
                trade.profit_loss = 'Profit';
            } else if (stopLoss !== null && price <= stopLoss) {
                trade.status = 'Stopped out';
                trade.profit_loss = 'Loss';
            } else {
                trade.status = 'Closed (EOD)';
                trade.profit_loss = price >= entry ? 'Profit' : 'Loss';
            }
        } else {
            if (target2 !== null && price <= target2) {
                trade.status = 'Target 2 hit';
                trade.profit_loss = 'Profit';
            } else if (target1 !== null && price <= target1) {
                trade.status = 'Target 1 hit';
                trade.profit_loss = 'Profit';
            } else if (stopLoss !== null && price >= stopLoss) {
                trade.status = 'Stopped out';
                trade.profit_loss = 'Loss';
            } else {
                trade.status = 'Closed (EOD)';
                trade.profit_loss = price <= entry ? 'Profit' : 'Loss';
            }
        }

        trade.closed_price = price;
        trade.updated_at = new Date().toISOString();
    });
}

function getCurrentPrice(symbol, index) {
    const lookup = (s) => index[s];
    if (!symbol) return null;
    const raw = symbol.toString().trim();
    if (lookup(raw) !== undefined) return lookup(raw);
    const normalized = normalizeSymbol(raw);
    if (lookup(normalized) !== undefined) return lookup(normalized);
    const full = raw.replace(/\s+/g, '').toUpperCase();
    if (lookup(full) !== undefined) return lookup(full);
    for (const key of Object.keys(index)) {
        if (key === raw || key === normalized || key.toUpperCase() === full) return index[key];
        if (key.includes(raw) || raw.includes(key)) return index[key];
        if (key.includes(normalized) || normalized.includes(key)) return index[key];
    }
    return null;
}

function shouldUpdateStatus(currentPrice, trade) {
    const entry = parsePrice(trade.entry);
    const stopLoss = parsePrice(trade.stop_loss);
    const target1 = parsePrice(trade.target_1);
    const target2 = parsePrice(trade.target_2);
    if (currentPrice === null || entry === null || stopLoss === null || target1 === null || target2 === null) {
        return null;
    }

    const isLong = trade.signal === 'LONG';
    if (isLong) {
        if (currentPrice <= stopLoss) return { status: 'Stopped out', profit_loss: 'Loss' };
        if (currentPrice >= target2) return { status: 'Target 2 hit', profit_loss: 'Profit' };
        if (currentPrice >= target1) return { status: 'Target 1 hit', profit_loss: 'Profit' };
        if (currentPrice >= entry) return { status: 'Triggered', profit_loss: 'In progress' };
    } else {
        if (currentPrice >= stopLoss) return { status: 'Stopped out', profit_loss: 'Loss' };
        if (currentPrice <= target2) return { status: 'Target 2 hit', profit_loss: 'Profit' };
        if (currentPrice <= target1) return { status: 'Target 1 hit', profit_loss: 'Profit' };
        if (currentPrice <= entry) return { status: 'Triggered', profit_loss: 'In progress' };
    }
    return null;
}

function estimateTradePnlPercent(trade) {
    const entry = parsePrice(trade.entry);
    const stopLoss = parsePrice(trade.stop_loss);
    const target1 = parsePrice(trade.target_1);
    const target2 = parsePrice(trade.target_2);
    const closedPrice = parsePrice(trade.closed_price);
    if (entry === null) {
        return null;
    }

    const isLong = trade.signal === 'LONG';
    const valueForPrice = (price) => isLong ? (price - entry) / entry * 100 : (entry - price) / entry * 100;

    switch (trade.status) {
        case 'Target 2 hit':
            return target2 !== null ? valueForPrice(target2) : null;
        case 'Target 1 hit':
            return target1 !== null ? valueForPrice(target1) : null;
        case 'Stopped out':
            return stopLoss !== null ? valueForPrice(stopLoss) : null;
        case 'Closed (EOD)':
            return closedPrice !== null ? valueForPrice(closedPrice) : null;
        default:
            return null;
    }
}

function computePerformanceSummary(trades) {
    const total = trades.length;
    const profitTrades = trades.filter(t => ['Target 1 hit', 'Target 2 hit', 'Closed (EOD)'].includes(t.status) && t.profit_loss === 'Profit').length;
    const lossTrades = trades.filter(t => ['Stopped out', 'Closed (EOD)'].includes(t.status) && t.profit_loss === 'Loss').length;
    const closedTrades = trades.filter(t => ['Target 1 hit', 'Target 2 hit', 'Stopped out', 'Closed (EOD)'].includes(t.status));
    const winRate = total ? (profitTrades / total * 100) : 0;
    const lossRate = total ? (lossTrades / total * 100) : 0;
    const pnlPercents = closedTrades.map(estimateTradePnlPercent).filter(v => v !== null);
    const netPnl = pnlPercents.reduce((acc, value) => acc + value, 0);
    const avgGain = pnlPercents.filter(v => v > 0).reduce((acc, value) => acc + value, 0) / Math.max(1, pnlPercents.filter(v => v > 0).length);
    const avgLoss = pnlPercents.filter(v => v < 0).reduce((acc, value) => acc + value, 0) / Math.max(1, pnlPercents.filter(v => v < 0).length);

    return {
        total,
        profitTrades,
        lossTrades,
        winRate,
        lossRate,
        netPnl,
        avgGain: Number.isFinite(avgGain) ? avgGain : 0,
        avgLoss: Number.isFinite(avgLoss) ? avgLoss : 0,
        closedCount: closedTrades.length
    };
}

function aggregateMonthlyPerformance(data, monthKey) {
    const allDays = [];
    if (data.history) {
        Object.values(data.history).forEach(item => {
            if (item.date.startsWith(monthKey)) {
                allDays.push(item);
            }
        });
    }
    const today = getTodayKey();
    if (data.day === today && data.trades && data.trades.length) {
        allDays.push({ date: data.day, trades: data.trades, summary: computePerformanceSummary(data.trades) });
    }

    const monthlyTrades = allDays.reduce((acc, day) => acc + (day.summary?.total || 0), 0);
    const monthlyProfitTrades = allDays.reduce((acc, day) => acc + (day.summary?.profitTrades || 0), 0);
    const monthlyLossTrades = allDays.reduce((acc, day) => acc + (day.summary?.lossTrades || 0), 0);
    const monthlyNetPnl = allDays.reduce((acc, day) => acc + (day.summary?.netPnl || 0), 0);
    const daysTracked = allDays.length;
    const monthlyWinRate = monthlyTrades ? (monthlyProfitTrades / monthlyTrades * 100) : 0;

    return {
        monthKey,
        monthLabel: formatMonthLabel(monthKey),
        daysTracked,
        monthlyTrades,
        monthlyProfitTrades,
        monthlyLossTrades,
        monthlyNetPnl,
        monthlyWinRate,
        dailySummaries: allDays.sort((a, b) => b.date.localeCompare(a.date))
    };
}

function formatPercent(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '—';
    const formatted = `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
    return formatted;
}

function renderPerformanceSummary(trades) {
    const summary = computePerformanceSummary(trades);
    const totalEl = $('#summaryTotalTrades');
    const profitEl = $('#summaryProfitTrades');
    const lossEl = $('#summaryLossTrades');
    const winRateEl = $('#summaryWinRate');

    if (totalEl) totalEl.textContent = `${summary.total}`;
    if (profitEl) profitEl.textContent = `${summary.profitTrades}`;
    if (lossEl) lossEl.textContent = `${summary.lossTrades}`;
    if (winRateEl) winRateEl.textContent = formatPercent(summary.winRate);

    const netLabel = $('#summaryNetPnl');
    if (netLabel) netLabel.textContent = formatPercent(summary.netPnl);
}

function renderMonthlySummary(data) {
    performanceMonth = performanceMonth || getCurrentMonthKey();
    const monthSummary = aggregateMonthlyPerformance(data, performanceMonth);
    const monthlyTradesEl = $('#summaryMonthlyTrades');
    const monthlyWinRateEl = $('#summaryMonthlyWinRate');
    const monthlyNetPnlEl = $('#summaryMonthlyNetPnl');
    const monthLabelEl = $('#summaryMonthLabel');

    if (monthlyTradesEl) monthlyTradesEl.textContent = `${monthSummary.monthlyTrades}`;
    if (monthlyWinRateEl) monthlyWinRateEl.textContent = formatPercent(monthSummary.monthlyWinRate);
    if (monthlyNetPnlEl) monthlyNetPnlEl.textContent = formatPercent(monthSummary.monthlyNetPnl);
    if (monthLabelEl) monthLabelEl.textContent = monthSummary.monthLabel;
}

function renderPerformanceHistory(data) {
    const historyBody = $('#performanceHistoryBody');
    if (!historyBody) return;
    const monthSummary = aggregateMonthlyPerformance(data, performanceMonth || getCurrentMonthKey());
    const rows = monthSummary.dailySummaries.map(day => {
        const summary = day.summary || computePerformanceSummary(day.trades || []);
        return `
            <tr>
                <td>${day.date}</td>
                <td>${summary.total}</td>
                <td>${summary.profitTrades}</td>
                <td>${summary.lossTrades}</td>
                <td>${formatPercent(summary.winRate)}</td>
                <td>${formatPercent(summary.netPnl)}</td>
            </tr>`;
    }).join('');

    if (!rows) {
        historyBody.innerHTML = '<tr><td colspan="6" class="empty-row">No daily performance history for this month.</td></tr>';
    } else {
        historyBody.innerHTML = rows;
    }
}

function updatePerformanceStatus() {
    const data = loadPerformanceData();
    if (!data.trades || data.trades.length === 0) {
        renderPerformanceTracker([], data.day);
        return;
    }

    const priceIndex = buildPriceIndex();
    let changed = false;

    data.trades.forEach(trade => {
        if (['Target 2 hit', 'Stopped out'].includes(trade.status)) {
            return;
        }
        const currentPrice = getCurrentPrice(trade.symbol, priceIndex);
        const update = shouldUpdateStatus(currentPrice, trade);
        if (!update) {
            return;
        }

        if (update.status !== trade.status) {
            trade.status = update.status;
            trade.profit_loss = update.profit_loss;
            trade.updated_at = new Date().toISOString();
            changed = true;
        }
    });

    if (changed) {
        savePerformanceData(data);
    }
    renderPerformanceTracker(data.trades, data.day);
}

function formatStatus(status) {
    switch (status) {
        case 'Target 1 hit': return '✅ Target 1';
        case 'Target 2 hit': return '🏆 Target 2';
        case 'Stopped out': return '🛑 Stopped';
        case 'In progress': return '⏳ In progress';
        case 'Triggered': return '▶️ Triggered';
        default: return '⏸️ Not triggered';
    }
}

function formatRecommendedTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    return `${hh}:${mm}`;
}

function renderPerformanceTracker(trades, day) {
    const table = $('#performanceTrackerTable');
    const tbody = table.querySelector('tbody');
    const dateEl = $('#performanceDate');
    if (dateEl) dateEl.textContent = `Tracking ${day}`;

    renderPerformanceSummary(trades || []);
    renderMonthlySummary(loadPerformanceData());
    renderPerformanceHistory(loadPerformanceData());

    const searchVal = ($('#performanceSearchInput')?.value || '').toLowerCase();
    let visibleTrades = (trades || []).filter(trade => {
        if (!searchVal) return true;
        return trade.symbol.toLowerCase().includes(searchVal) ||
               trade.signal.toLowerCase().includes(searchVal) ||
               trade.status.toLowerCase().includes(searchVal) ||
               (trade.profit_loss || '').toLowerCase().includes(searchVal) ||
               (trade.timeframe || '').toLowerCase().includes(searchVal);
    });

    if (currentPerformanceSort.col) {
        const numericCols = ['entry', 'stop_loss', 'target_1', 'target_2'];
        visibleTrades.sort((a, b) => {
            let va = a[currentPerformanceSort.col] || '';
            let vb = b[currentPerformanceSort.col] || '';
            if (numericCols.includes(currentPerformanceSort.col)) {
                va = parseFloat(va) || 0;
                vb = parseFloat(vb) || 0;
            } else {
                va = va.toString().toLowerCase();
                vb = vb.toString().toLowerCase();
            }

            if (va < vb) return currentPerformanceSort.asc ? -1 : 1;
            if (va > vb) return currentPerformanceSort.asc ? 1 : -1;
            return 0;
        });
    }

    table.querySelectorAll('thead th.sortable').forEach(th => {
        th.classList.remove('asc', 'desc');
        if (th.dataset.sort === currentPerformanceSort.col) {
            th.classList.add(currentPerformanceSort.asc ? 'asc' : 'desc');
        }
    });

    if (!visibleTrades || visibleTrades.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="empty-row">No matching performance trades found.</td></tr>`;
        return;
    }

    tbody.innerHTML = visibleTrades.map(trade => {
        const signalClass = trade.signal === 'LONG' ? 'signal-long' : 'signal-short';
        const updatedClass = trade.recommendation_updated ? 'trade-updated' : '';
        const statusClass = trade.status.replace(/\s+/g, '-').toLowerCase();
        const plClass = trade.profit_loss === 'Profit' ? 'pl-profit' : trade.profit_loss === 'Loss' ? 'pl-loss' : 'pl-neutral';
        const updateBadge = trade.recommendation_updated ? '<span class="updated-badge">Updated</span>' : '';

        return `
            <tr class="${signalClass} ${updatedClass}">
                <td>${trade.symbol}</td>
                <td><span class="signal-badge ${trade.signal.toLowerCase()}">${trade.signal}</span></td>
                <td>${formatRecommendedTime(trade.created_at)}</td>
                <td>$${trade.entry}</td>
                <td>$${trade.stop_loss}</td>
                <td>$${trade.target_1}</td>
                <td>$${trade.target_2}</td>
                <td><span class="status-badge ${statusClass}">${formatStatus(trade.status)} ${updateBadge}</span></td>
                <td><span class="pl-badge ${plClass}">${trade.profit_loss}</span></td>
            </tr>`;
    }).join('');
}

function updatePerformanceEntry(id, updater) {
    const data = loadPerformanceData();
    const trade = data.trades.find(t => t.id === id);
    if (!trade) return;
    updater(trade);
    trade.updated_at = new Date().toISOString();
    savePerformanceData(data);
    renderPerformanceTracker(data.trades, data.day);
}

function dedupeOpenTrades(data) {
    const openMap = {};
    const prioritized = {
        'Not triggered': 1,
        'Triggered': 2,
        'In progress': 3,
        'Target 1 hit': 4,
        'Target 2 hit': 5,
        'Stopped out': 6,
        'Closed (EOD)': 7
    };

    data.trades = data.trades.filter(trade => {
        if (['Target 1 hit', 'Target 2 hit', 'Stopped out', 'Closed (EOD)'].includes(trade.status)) {
            return true;
        }

        const key = `${trade.symbol}|${trade.signal}`;
        const existing = openMap[key];
        if (!existing) {
            openMap[key] = trade;
            return true;
        }

        const existingPriority = prioritized[existing.status] || 0;
        const currentPriority = prioritized[trade.status] || 0;
        if (currentPriority > existingPriority || new Date(trade.updated_at) > new Date(existing.updated_at)) {
            openMap[key] = trade;
            return false;
        }
        return false;
    });
}

function syncPerformanceTrackerWithSetups(setups, timestamp) {
    let referenceTime = timestamp ? new Date(timestamp) : new Date();
    if (Number.isNaN(referenceTime)) {
        referenceTime = new Date();
    }
    if (!isRoundQuarterTime(referenceTime)) {
        // Only track setups generated on round refresh times (e.g., 17:15, 17:30, 17:45, 18:00)
        renderPerformanceTracker(loadPerformanceData().trades, getTodayKey());
        return;
    }

    const data = loadPerformanceData();
    dedupeOpenTrades(data);
    let changed = false;
    const nowISO = new Date().toISOString();

    setups.forEach(setup => {
        const openTrade = data.trades.find(t =>
            t.symbol === setup.symbol &&
            t.signal === setup.signal &&
            !['Target 1 hit', 'Target 2 hit', 'Stopped out', 'Closed (EOD)'].includes(t.status)
        );

        if (openTrade) {
            const updateTargets = openTrade.stop_loss !== setup.stop_loss ||
                openTrade.target_1 !== setup.target_1 ||
                openTrade.target_2 !== setup.target_2 ||
                openTrade.timeframe !== setup.timeframe ||
                openTrade.setup_type !== setup.setup_type;

            if (openTrade.status === 'Not triggered') {
                openTrade.entry = setup.entry;
                openTrade.stop_loss = setup.stop_loss;
                openTrade.target_1 = setup.target_1;
                openTrade.target_2 = setup.target_2;
                openTrade.timeframe = setup.timeframe;
                openTrade.setup_type = setup.setup_type;
                openTrade.created_at = referenceTime.toISOString();
                openTrade.updated_at = nowISO;
                openTrade.recommendation_updated = true;
                openTrade.profit_loss = 'N/A';
                changed = true;
                return;
            }

            if (updateTargets) {
                openTrade.stop_loss = setup.stop_loss;
                openTrade.target_1 = setup.target_1;
                openTrade.target_2 = setup.target_2;
                openTrade.timeframe = setup.timeframe;
                openTrade.setup_type = setup.setup_type;
                openTrade.updated_at = nowISO;
                openTrade.recommendation_updated = true;
                changed = true;
            }
            return;
        }

        const id = `${setup.symbol}|${setup.entry}|${setup.target_1}|${setup.target_2}|${setup.timeframe}`;
        let existing = data.trades.find(t => t.id === id);
        if (!existing) {
            existing = {
                id,
                symbol: setup.symbol,
                signal: setup.signal,
                entry: setup.entry,
                stop_loss: setup.stop_loss,
                target_1: setup.target_1,
                target_2: setup.target_2,
                setup_type: setup.setup_type,
                timeframe: setup.timeframe,
                status: 'Not triggered',
                profit_loss: 'N/A',
                created_at: referenceTime.toISOString(),
                updated_at: nowISO,
                recommendation_updated: false
            };
            data.trades.push(existing);
            changed = true;
        }
    });

    if (changed) {
        savePerformanceData(data);
    }
    renderPerformanceTracker(data.trades, data.day);
}

async function fetchTradeSetups() {
    const grid = $('#tradeSetupsGrid');
    grid.innerHTML = `<div class="ts-placeholder ts-loading"><i class="fas fa-spinner fa-spin"></i><p>Fetching live setups from Binance…</p></div>`;
    try {
        const res = await fetch(`${API_URL}/api/trade-setups`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        renderTradeSetups(data.setups || [], data.timestamp || '');
    } catch (e) {
        grid.innerHTML = `<div class="ts-placeholder ts-error"><i class="fas fa-exclamation-triangle"></i><p>Could not load setups: ${e.message}</p></div>`;
    }
}

function renderTradeSetups(setups, timestamp) {
    const grid = $('#tradeSetupsGrid');
    // Show "Updated HH:MM · Next at HH:MM"
    const nextMs   = msUntilNextQuarter();
    const nextTime = new Date(Date.now() + nextMs);
    const nextStr  = `${String(nextTime.getHours()).padStart(2,'0')}:${String(nextTime.getMinutes()).padStart(2,'0')}`;
    const updStr   = timestamp ? timestamp.slice(11, 16) : '';  // "HH:MM" from timestamp
    updateNextRefreshLabel(`Updated ${updStr} · Next auto-refresh at ${nextStr}`);
    syncPerformanceTrackerWithSetups(setups, timestamp);

    if (!setups || setups.length === 0) {
        grid.innerHTML = `<div class="ts-placeholder"><i class="fas fa-search"></i><p>No high-quality setups found right now — market may be choppy. Try again in 15 min.</p></div>`;
        return;
    }

    grid.innerHTML = setups.map((s, i) => {
        const isLong  = s.signal === 'LONG';
        const sigCls  = isLong ? 'ts-long' : 'ts-short';
        const sigIcon = isLong ? 'fa-arrow-up' : 'fa-arrow-down';
        const rrColor = s.rr >= 2.5 ? 'ts-rr-great' : s.rr >= 1.8 ? 'ts-rr-good' : 'ts-rr-ok';
        const setupIcon = {
            'BREAKOUT':    'fa-bolt',
            'PULLBACK':    'fa-undo',
            'RANGE BOUNCE':'fa-arrows-left-right',
            'BREAKDOWN':   'fa-arrow-down-wide-short'
        }[s.setup_type] || 'fa-chart-line';
        const chgCls = s.price_change_24h >= 0 ? 'ts-chg-pos' : 'ts-chg-neg';
        const chgStr = `${s.price_change_24h >= 0 ? '+' : ''}${s.price_change_24h}%`;

        return `
        <div class="ts-card ts-card--${isLong ? 'long' : 'short'}" style="animation: fadeUp 0.35s ${i * 0.07}s var(--ease-out) both">
            <!-- Header -->
            <div class="ts-card-header">
                <div class="ts-coin">
                    <span class="ts-rank">#${i + 1}</span>
                    <span class="ts-symbol">${s.symbol}</span>
                    <span class="ts-setup-type"><i class="fas ${setupIcon}"></i> ${s.setup_type}</span>
                </div>
                <div class="ts-badges">
                    <span class="ts-signal ${sigCls}"><i class="fas ${sigIcon}"></i> ${s.signal}</span>
                    <span class="ts-chg ${chgCls}">${chgStr} 24h</span>
                </div>
            </div>

            <!-- Price levels -->
            <div class="ts-levels">
                <div class="ts-level ts-level--current">
                    <span class="ts-level-label">Current</span>
                    <span class="ts-level-value">$${s.current_price}</span>
                </div>
                <div class="ts-level ts-level--entry">
                    <span class="ts-level-label">⚡ Entry</span>
                    <span class="ts-level-value">$${s.entry}</span>
                </div>
                <div class="ts-level ts-level--sl">
                    <span class="ts-level-label">🛑 Stop Loss</span>
                    <span class="ts-level-value">$${s.stop_loss}</span>
                </div>
                <div class="ts-level ts-level--tp1">
                    <span class="ts-level-label">🎯 Target 1</span>
                    <span class="ts-level-value">$${s.target_1}</span>
                </div>
                <div class="ts-level ts-level--tp2">
                    <span class="ts-level-label">🏆 Target 2</span>
                    <span class="ts-level-value">$${s.target_2}</span>
                </div>
            </div>

            <!-- R:R bar -->
            <div class="ts-rr-wrap">
                <span class="ts-rr-label">Risk: <strong class="ts-risk">−${s.risk_pct}%</strong></span>
                <span class="ts-rr-badge ${rrColor}">Reward:Risk ${s.rr}:1</span>
                <span class="ts-rr-label">Reward: <strong class="ts-reward">+${s.reward_pct}%</strong></span>
            </div>

            <!-- Justification -->
            <ul class="ts-reasons">
                ${s.justification.map(r => `<li><i class="fas fa-check-circle"></i> ${r}</li>`).join('')}
            </ul>

            <!-- Footer -->
            <div class="ts-footer">
                <span class="ts-tf"><i class="fas fa-clock"></i> ${s.timeframe} candle close</span>
                <span class="ts-sl-note" title="Stop Loss is valid only on 15m candle CLOSE — ignore wicks">🕯️ SL on close</span>
                <span class="ts-vol">Vol: ${s.volume_ratio}×</span>
            </div>
        </div>`;
    }).join('');
}

// ══════════════════════════════════════════════════════════════
// MARKET HEATMAP
// ══════════════════════════════════════════════════════════════
async function fetchMarketHeatmap() {
    const grid = $('#heatmapGrid');
    grid.innerHTML = `<div class="hm-placeholder hm-loading"><i class="fas fa-spinner fa-spin"></i><p>Loading market heatmap…</p></div>`;
    try {
        const res = await fetch(`${API_URL}/api/market-heatmap`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        renderMarketHeatmap(data.heatmap || [], data.timestamp || '');
    } catch (e) {
        grid.innerHTML = `<div class="hm-placeholder hm-error"><i class="fas fa-exclamation-triangle"></i><p>Could not load heatmap: ${e.message}</p></div>`;
    }
}

function renderMarketHeatmap(heatmaps, timestamp) {
    const grid = $('#heatmapGrid');

    // Update timestamp display
    const nextMs = msUntilNextQuarter();
    const nextTime = new Date(Date.now() + nextMs);
    const nextStr = `${String(nextTime.getHours()).padStart(2,'0')}:${String(nextTime.getMinutes()).padStart(2,'0')}`;
    const updStr = timestamp ? timestamp.slice(11, 16) : '';  // "HH:MM" from timestamp
    const tsEl = $('#heatmapTimestamp');
    if (tsEl) tsEl.textContent = `Updated ${updStr} · Next auto-refresh at ${nextStr}`;

    if (!heatmaps || heatmaps.length === 0) {
        grid.innerHTML = `<div class="hm-placeholder"><i class="fas fa-chart-line"></i><p>No market data available</p></div>`;
        return;
    }

    grid.innerHTML = heatmaps.map((h, i) => {
        const isLong = h.signal === 'LONG';
        const sigCls = isLong ? 'ts-long' : 'ts-short';
        const sigIcon = isLong ? 'fa-arrow-up' : 'fa-arrow-down';
        const rrColor = h.rr >= 2.5 ? 'ts-rr-great' : h.rr >= 1.8 ? 'ts-rr-good' : 'ts-rr-ok';
        const setupIcon = {
            'BREAKOUT':    'fa-bolt',
            'BREAKDOWN':   'fa-arrow-down-wide-short',
            'PULLBACK':    'fa-undo'
        }[h.setup_type] || 'fa-chart-line';
        const chgCls = h.price_change_pct >= 0 ? 'ts-chg-pos' : 'ts-chg-neg';
        const chgStr = `${h.price_change_pct >= 0 ? '+' : ''}${h.price_change_pct}%`;

        return `
        <div class="ts-card ts-card--${isLong ? 'long' : 'short'}" style="animation: fadeUp 0.35s ${i * 0.07}s var(--ease-out) both">
            <div class="ts-card-header">
                <div class="ts-coin">
                    <span class="ts-rank">#${i + 1}</span>
                    <span class="ts-symbol">${h.symbol}</span>
                    <span class="ts-setup-type"><i class="fas ${setupIcon}"></i> ${h.setup_type}</span>
                </div>
                <div class="ts-badges">
                    <span class="ts-signal ${sigCls}"><i class="fas ${sigIcon}"></i> ${h.signal}</span>
                    <span class="ts-chg ${chgCls}">${chgStr} 24h</span>
                </div>
            </div>

            <div class="ts-levels">
                <div class="ts-level ts-level--current">
                    <span class="ts-level-label">Current</span>
                    <span class="ts-level-value">$${h.current_price}</span>
                </div>
                <div class="ts-level ts-level--entry">
                    <span class="ts-level-label">Entry</span>
                    <span class="ts-level-value">$${h.entry}</span>
                </div>
                <div class="ts-level ts-level--sl">
                    <span class="ts-level-label">Stop Loss</span>
                    <span class="ts-level-value">$${h.stop_loss}</span>
                </div>
                <div class="ts-level ts-level--tp1">
                    <span class="ts-level-label">Target 1</span>
                    <span class="ts-level-value">$${h.target_1}</span>
                </div>
                <div class="ts-level ts-level--tp2">
                    <span class="ts-level-label">Target 2</span>
                    <span class="ts-level-value">$${h.target_2}</span>
                </div>
            </div>

            <div class="ts-rr-wrap">
                <span class="ts-rr-label">Risk: <strong class="ts-risk">−${h.risk_pct}%</strong></span>
                <span class="ts-rr-badge ${rrColor}">Reward:Risk ${h.rr}:1</span>
                <span class="ts-rr-label">Reward: <strong class="ts-reward">+${h.reward_pct}%</strong></span>
            </div>

            ${(() => {
                const reasons = Array.isArray(h.justification) ? h.justification : [];
                return reasons.length ? `
                    <ul class="ts-reasons">
                        ${reasons.map(r => `<li><i class="fas fa-check-circle"></i> ${r}</li>`).join('')}
                    </ul>` : '';
            })()}

            <div class="ts-footer">
                <span class="ts-tf"><i class="fas fa-clock"></i> ${h.timeframe} candle close</span>
                <span class="ts-sl-note" title="Stop Loss is valid only on 15m candle CLOSE — ignore wicks">🕯️ SL on close</span>
                <span class="ts-vol">Vol: ${h.volume_24h || 'N/A'}×</span>
            </div>
        </div>`;
    }).join('');
}

// ══════════════════════════════════════════════════════════════
// FETCH & RENDER RESULTS
// ══════════════════════════════════════════════════════════════
async function fetchResults() {
    try {
        const res = await fetch(`${API_URL}/api/results`);
        if (!res.ok) return;
        const data = await res.json();
        allResults = data.results || [];
        allHilegaResults = data.hilega_results || [];
        allCrossResults = data.cross_results || [];
        allConflictResults = data.conflict_results || [];
        if (data.scan_time) {
            updateLastScanTime(data.scan_time);
        }
        populateTfFilter();
        populateHilegaTfFilter();
        populateCrossTfFilter();
        populateConflictTfFilter();
        renderResults();
        renderHilegaResults();
        renderCrossResults();
        renderConflictResults();
        updateStats();
    } catch (e) {
        // API may not have /api/results yet
    }
}

function populateTfFilter() {
    const select = $('#tfFilter');
    const currentVal = select.value;
    const tfMap = { '5min': '5m', '10min': '10m', '15min': '15m', '20min': '20m', '25min': '25m', '30min': '30m', '45min': '45m', '1hr': '1h', '2hr': '2h', '4hr': '4h', '6hr': '6h', '8hr': '8h', '12hr': '12h', '1 day': '1D', '2 day': '2D', '3 day': '3D', '4 day': '4D', '5 day': '5D', '6 day': '6D', '1 week': '1W', '1 month': '1M' };
    const tfs = [...new Set(allResults.map(r => r.Timeperiod))];
    select.innerHTML = '<option value="all">All Timeframes</option>' +
        tfs.map(tf => `<option value="${tf}">${tfMap[tf] || tf}</option>`).join('');
    select.value = tfs.includes(currentVal) ? currentVal : 'all';
}

// ── CPR Category badge helper ──────────────────────────────────────────────
function getCprBadge(category) {
    if (!category || category === 'N/A') return '<span class="cpr-badge cpr-na">—</span>';
    const cls = {
        'Extreme Narrow': 'cpr-extreme-narrow',
        'Narrow':         'cpr-narrow',
        'Normal':         'cpr-normal',
        'Wide':           'cpr-wide',
        'Extreme Wide':   'cpr-extreme-wide',
    }[category] || 'cpr-na';
    const icons = {
        'Extreme Narrow': '🔥',
        'Narrow':         '⚡',
        'Normal':         '—',
        'Wide':           '↔',
        'Extreme Wide':   '↔↔',
    };
    return `<span class="cpr-badge ${cls}" title="CPR: ${category}">${icons[category] || ''} ${category}</span>`;
}

function renderResults() {
    const body = $('#signalsBody');
    const empty = $('#emptyState');
    const countEl = $('#resultCount');
    const searchVal = ($('#searchInput').value || '').toLowerCase();
    const signalFilter = $('#signalFilterChips .chip.active')?.dataset?.filter || 'all';
    const tfFilter = $('#tfFilter').value;
    const scannerFilter = $('#scannerFilterChips .chip.active')?.dataset?.filter || 'all';

    // Group by (Crypto Name, Timeperiod, Signal) to detect multi-scanner matches
    const grouped = new Map();
    allResults.forEach(r => {
        const key = `${r['Crypto Name']}|${r.Timeperiod}|${r.Signal}`;
        if (!grouped.has(key)) {
            grouped.set(key, { ...r, scanners: [r.Scanner] });
        } else {
            const existing = grouped.get(key);
            if (!existing.scanners.includes(r.Scanner)) {
                existing.scanners.push(r.Scanner);
            }
        }
    });

    let filtered = [...grouped.values()].filter(r => {
        if (searchVal && !r['Crypto Name']?.toLowerCase().includes(searchVal)) return false;
        if (signalFilter !== 'all' && r.Signal !== signalFilter) return false;
        if (tfFilter !== 'all' && r.Timeperiod !== tfFilter) return false;
        if (scannerFilter !== 'all') {
            const s = r.Scanner || '';
            if (scannerFilter === 'Both') {
                if (s !== 'AMA Pro Pre' && s !== 'Qwen' && s !== 'Both') return false;
            } else if (scannerFilter === 'Both Now') {
                if (s !== 'AMA Pro Now' && s !== 'Qwen Now' && s !== 'Both Now') return false;
            } else if (s !== scannerFilter) return false;
        }
        return true;
    });

    // Sort
    if (currentSort.col) {
        const numericCols = ['Angle', 'TEMA Gap', 'RSI', 'Daily Change'];
        const isNumeric = numericCols.includes(currentSort.col);
        filtered.sort((a, b) => {
            let va = a[currentSort.col] || '';
            let vb = b[currentSort.col] || '';
            if (isNumeric) {
                va = parseFloat(String(va).replace(/[°%,]/g, '')) || 0;
                vb = parseFloat(String(vb).replace(/[°%,]/g, '')) || 0;
            } else {
                if (typeof va === 'string') va = va.toLowerCase();
                if (typeof vb === 'string') vb = vb.toLowerCase();
            }
            if (va < vb) return currentSort.asc ? -1 : 1;
            if (va > vb) return currentSort.asc ? 1 : -1;
            return 0;
        });
    }

    if (filtered.length === 0) {
        body.innerHTML = '';
        empty.style.display = 'block';
        countEl.textContent = '0 results';
        return;
    }

    empty.style.display = 'none';
    countEl.textContent = `${filtered.length} result${filtered.length !== 1 ? 's' : ''}`;


    body.innerHTML = filtered.map((r, i) => {
        const sigCls = r.Signal === 'LONG' ? 'long' : 'short';
        const sigIcon = r.Signal === 'LONG' ? 'fa-arrow-up' : 'fa-arrow-down';
        const changeStr = r['Daily Change'] || '—';
        const changeVal = parseFloat(changeStr);
        const changeCls = isNaN(changeVal) ? '' : (changeVal >= 0 ? 'change-positive' : 'change-negative');
        const name = r['Crypto Name'] || '—';
        const tfMap = { '5min': '5m', '10min': '10m', '15min': '15m', '20min': '20m', '25min': '25m', '30min': '30m', '45min': '45m', '1hr': '1h', '2hr': '2h', '4hr': '4h', '6hr': '6h', '8hr': '8h', '12hr': '12h', '1 day': '1D', '2 day': '2D', '3 day': '3D', '4 day': '4D', '5 day': '5D', '6 day': '6D', '1 week': '1W', '1 month': '1M' };
        const tfDisplay = tfMap[r.Timeperiod] || r.Timeperiod;
        const scannerVal = r.Scanner || '—';
        const badgeMap = {
            'Both': 'scanner-both',
            'Qwen': 'scanner-qwen',
            'AMA Pro Pre': 'scanner-ama',
            'AMA Pro Now': 'scanner-ama-now',
            'Qwen Now': 'scanner-qwen-now',
            'Both Now': 'scanner-both-now',
            'Both Pre': 'scanner-both-entry',
            'Long Conflict': 'scanner-conflict-long',
            'Short Conflict': 'scanner-conflict-short',
            'Qwen Pre': 'scanner-qwen-entry',
            'Qwen Now (Entry)': 'scanner-qwen-now-entry'
        };
        // Dynamic prefix matching for conflict state labels (e.g. "Long Conflict: SAFE")
        // and bar+1 labels (e.g. "Bar+1: ENTER (L)")
        function getScannerBadgeClass(scanner) {
            if (badgeMap[scanner]) return badgeMap[scanner];
            if (scanner.startsWith('Long Conflict'))  return 'scanner-conflict-long';
            if (scanner.startsWith('Short Conflict')) return 'scanner-conflict-short';
            if (scanner.startsWith('Bar+1'))          return 'scanner-bar1';
            return '';
        }
        const scannerBadgeCls = getScannerBadgeClass(r.Scanner);
        const isMultiMatch = r.scanners && r.scanners.length > 1;
        const matchCount = r.scanners ? r.scanners.length : 1;
        const rsiStr = r.RSI || '—';

        const colorStr = r.Color || 'N/A';
        const colorCls = colorStr === 'GREEN' ? 'change-positive' : colorStr === 'RED' ? 'change-negative' : '';
        const candleDisplay = colorStr === 'GREEN' ? 'Bullish' : colorStr === 'RED' ? 'Bearish' : colorStr === 'NEUTRAL' ? 'Neutral' : 'N/A';

        return `
            <tr style="animation: fadeUp 0.3s ${0.03 * i}s var(--ease-out) both" ${isMultiMatch ? 'class="multi-match-row"' : ''}>
                <td>
                    <strong>${name}</strong>
                    ${isMultiMatch ? `<span class="multi-match-count" title="Confirmed by ${matchCount} scanner types">✦ ${matchCount}</span>` : ''}
                </td>
                <td><span class="tf-badge">${tfDisplay}</span></td>
                <td>
                    <span class="signal-badge ${sigCls}">
                        <i class="fas ${sigIcon}"></i>
                        ${r.Signal}
                    </span>
                </td>
                <td class="mono">${r.Angle || '—'}</td>
                <td class="mono">${r['TEMA Gap'] || '—'}</td>
                <td class="mono">${rsiStr}</td>
                <td class="${changeCls}">${changeStr}</td>
                <td>${isMultiMatch
                    ? `<span class="scanner-multi-wrap">${r.scanners.map(s => { const cls = getScannerBadgeClass(s); return cls ? `<span class="scanner-badge ${cls}">${s}</span>` : `<span class="scanner-badge scanner-multi">${s}</span>`; }).join('')}</span>`
                    : (scannerBadgeCls ? `<span class="scanner-badge ${scannerBadgeCls}">${scannerVal}</span>` : scannerVal)
                }</td>
                <td><span class="ma-type-badge">${r['MA Type'] || '—'}</span></td>
                <td class="mono">${r.Timestamp || '—'}</td>
                <td class="${colorCls}"><strong>${candleDisplay}</strong></td>
                <td>${getCprBadge(r['CPR Category'])}</td>
            </tr>
        `;
    }).join('');
}

function renderHilegaResults() {
    const body = $('#hilegaSignalsBody');
    const empty = $('#hilegaEmptyState');
    const countEl = $('#hilegaResultCount');
    const searchVal = ($('#hilegaSearchInput').value || '').toLowerCase();
    const signalFilter = $('#hilegaSignalFilterChips .chip.active')?.dataset?.filter || 'all';
    const tfFilter = $('#hilegaTfFilter').value;

    let filtered = allHilegaResults.filter(r => {
        if (searchVal && !r['Crypto Name']?.toLowerCase().includes(searchVal)) return false;
        if (signalFilter !== 'all' && r.Signal !== signalFilter) return false;
        if (tfFilter !== 'all' && r.Timeperiod !== tfFilter) return false;
        return true;
    });

    // Sort
    if (currentHilegaSort.col) {
        const numericCols = ['Angle', 'RSI-TEMA', 'RSI', 'VWMA', 'Daily Change'];
        const isNumeric = numericCols.includes(currentHilegaSort.col);
        filtered.sort((a, b) => {
            let va = a[currentHilegaSort.col] || '';
            let vb = b[currentHilegaSort.col] || '';
            if (isNumeric) {
                va = parseFloat(String(va).replace(/[°%,]/g, '')) || 0;
                vb = parseFloat(String(vb).replace(/[°%,]/g, '')) || 0;
            } else {
                if (typeof va === 'string') va = va.toLowerCase();
                if (typeof vb === 'string') vb = vb.toLowerCase();
            }
            if (va < vb) return currentHilegaSort.asc ? -1 : 1;
            if (va > vb) return currentHilegaSort.asc ? 1 : -1;
            return 0;
        });
    }

    if (filtered.length === 0) {
        body.innerHTML = '';
        empty.style.display = 'block';
        countEl.textContent = '0 results';
        return;
    }

    empty.style.display = 'none';
    countEl.textContent = `${filtered.length} result${filtered.length !== 1 ? 's' : ''}`;

    body.innerHTML = filtered.map((r, i) => {
        const sigCls = r.Signal === 'LONG' ? 'long' : 'short';
        const sigIcon = r.Signal === 'LONG' ? 'fa-arrow-up' : 'fa-arrow-down';
        const changeStr = r['Daily Change'] || '—';
        const changeVal = parseFloat(changeStr);
        const changeCls = isNaN(changeVal) ? '' : (changeVal >= 0 ? 'change-positive' : 'change-negative');
        const name = r['Crypto Name'] || '—';
        const tfMap = { '5min': '5m', '10min': '10m', '15min': '15m', '20min': '20m', '25min': '25m', '30min': '30m', '45min': '45m', '1hr': '1h', '2hr': '2h', '4hr': '4h', '6hr': '6h', '8hr': '8h', '12hr': '12h', '1 day': '1D', '2 day': '2D', '3 day': '3D', '4 day': '4D', '5 day': '5D', '6 day': '6D', '1 week': '1W', '1 month': '1M' };
        const tfDisplay = tfMap[r.Timeperiod] || r.Timeperiod;
        const angleStr = r.Angle || '—';
        const rsiTemaStr = r['RSI-TEMA'] || '—';
        const rsiStr = r.RSI || '—';
        const vwmaStr = r.VWMA || '—';

        return `
            <tr style="animation: fadeUp 0.3s ${0.03 * i}s var(--ease-out) both">
                <td><strong>${name}</strong></td>
                <td><span class="tf-badge">${tfDisplay}</span></td>
                <td>
                    <span class="signal-badge ${sigCls}">
                        <i class="fas ${sigIcon}"></i>
                        ${r.Signal}
                    </span>
                </td>
                <td class="mono">${angleStr}</td>
                <td class="mono">${rsiTemaStr}</td>
                <td class="mono">${rsiStr}</td>
                <td class="mono">${vwmaStr}</td>
                <td class="${changeCls}">${changeStr}</td>
                <td class="mono">${r.Timestamp || '—'}</td>
                <td>${getCprBadge(r['CPR Category'])}</td>
            </tr>
        `;
    }).join('');
}

function populateHilegaTfFilter() {
    const select = $('#hilegaTfFilter');
    const currentVal = select.value;
    const tfMap = { '5min': '5m', '10min': '10m', '15min': '15m', '20min': '20m', '25min': '25m', '30min': '30m', '45min': '45m', '1hr': '1h', '2hr': '2h', '4hr': '4h', '6hr': '6h', '8hr': '8h', '12hr': '12h', '1 day': '1D', '1 week': '1W', '1 month': '1M' };
    const tfs = [...new Set(allHilegaResults.map(r => r.Timeperiod))];
    select.innerHTML = '<option value="all">All Timeframes</option>' +
        tfs.map(tf => `<option value="${tf}">${tfMap[tf] || tf}</option>`).join('');
    select.value = tfs.includes(currentVal) ? currentVal : 'all';
}

function getCrossScannerBadgeClass(scanner) {
    if (!scanner) return '';
    const s = scanner.toLowerCase();
    if (s.includes('cross up') && s.includes('vwma')) return 'scanner-cross-vwma-up';
    if (s.includes('cross dn') && s.includes('vwma')) return 'scanner-cross-vwma-dn';
    if (s.includes('cross up') && s.includes('alma')) return 'scanner-cross-alma-up';
    if (s.includes('cross dn') && s.includes('alma')) return 'scanner-cross-alma-dn';
    return '';
}

function renderCrossResults() {
    const body = $('#crossSignalsBody');
    const empty = $('#crossEmptyState');
    const countEl = $('#crossResultCount');
    const searchVal = ($('#crossSearchInput').value || '').toLowerCase();
    const signalFilter = $('#crossSignalFilterChips .chip.active')?.dataset?.filter || 'all';
    const tfFilter = $('#crossTfFilter').value;

    let filtered = allCrossResults.filter(r => {
        if (searchVal && !r['Crypto Name']?.toLowerCase().includes(searchVal)) return false;
        if (signalFilter !== 'all' && r['Signal Type'] !== signalFilter) return false;
        if (tfFilter !== 'all' && r.Timeperiod !== tfFilter) return false;
        return true;
    });

    // Sort
    if (currentCrossSort.col) {
        const numericCols = ['Angle', 'RSI Diff', 'RSI-VWMA', 'RSI-ALMA', 'RSI', 'VWMA', 'ALMA', 'Daily Change'];
        const isNumeric = numericCols.includes(currentCrossSort.col);
        filtered.sort((a, b) => {
            let va = a[currentCrossSort.col] || '';
            let vb = b[currentCrossSort.col] || '';
            if (isNumeric) {
                va = parseFloat(String(va).replace(/[°%,]/g, '')) || 0;
                vb = parseFloat(String(vb).replace(/[°%,]/g, '')) || 0;
            } else {
                if (typeof va === 'string') va = va.toLowerCase();
                if (typeof vb === 'string') vb = vb.toLowerCase();
            }
            if (va < vb) return currentCrossSort.asc ? -1 : 1;
            if (va > vb) return currentCrossSort.asc ? 1 : -1;
            return 0;
        });
    }

    if (filtered.length === 0) {
        body.innerHTML = '';
        empty.style.display = 'block';
        countEl.textContent = '0 results';
        return;
    }

    empty.style.display = 'none';
    countEl.textContent = `${filtered.length} result${filtered.length !== 1 ? 's' : ''}`;

    body.innerHTML = filtered.map((r, i) => {
        const signalType = r['Signal Type'] || '—';
        const sigCls = signalType === 'Cross UP' ? 'long' : 'short';
        const sigIcon = signalType === 'Cross UP' ? 'fa-arrow-up' : 'fa-arrow-down';
        const changeStr = r['Daily Change'] || '—';
        const changeVal = parseFloat(changeStr);
        const changeCls = isNaN(changeVal) ? '' : (changeVal >= 0 ? 'change-positive' : 'change-negative');
        const name = r['Crypto Name'] || '—';
        const tfMap = { '5min': '5m', '10min': '10m', '15min': '15m', '20min': '20m', '25min': '25m', '30min': '30m', '45min': '45m', '1hr': '1h', '2hr': '2h', '4hr': '4h', '6hr': '6h', '8hr': '8h', '12hr': '12h', '1 day': '1D', '2 day': '2D', '3 day': '3D', '4 day': '4D', '5 day': '5D', '6 day': '6D', '1 week': '1W', '1 month': '1M' };
        const tfDisplay = tfMap[r.Timeperiod] || r.Timeperiod;
        const candleStatus = r['Candle Status'] || '—';
        const candleCls = candleStatus === 'Confirmed' ? 'change-positive' : candleStatus === 'Forming' ? 'change-negative' : '';
        const candleBadge = candleStatus === 'Confirmed' ? '✓' : candleStatus === 'Forming' ? '◐' : '';
        const angleStr = r.Angle || '—';
        const rsiDiffStr = r['RSI-VWMA'] || r['RSI-ALMA'] || '—';
        const rsiStr = r.RSI || '—';
        const vwmaStr = r.VWMA || '—';
        const almaStr = r.ALMA || '—';
        const scannerVal = r.Scanner || '—';
        const scannerBadgeCls = r.Scanner ? getCrossScannerBadgeClass(r.Scanner) : '';

        return `
            <tr style="animation: fadeUp 0.3s ${0.03 * i}s var(--ease-out) both">
                <td><strong>${name}</strong></td>
                <td><span class="tf-badge">${tfDisplay}</span></td>
                <td>
                    <span class="signal-badge ${sigCls}">
                        <i class="fas ${sigIcon}"></i>
                        ${signalType}
                    </span>
                </td>
                <td class="${candleCls}"><strong>${candleBadge} ${candleStatus}</strong></td>
                <td class="mono">${angleStr}</td>
                <td class="mono">${rsiDiffStr}</td>
                <td class="mono">${rsiStr}</td>
                <td class="mono">${vwmaStr}</td>
                <td class="mono">${almaStr}</td>
                <td class="${changeCls}">${changeStr}</td>
                <td class="mono">${r.Timestamp || '—'}</td>
                <td>${scannerBadgeCls ? `<span class="scanner-badge ${scannerBadgeCls}">${scannerVal}</span>` : scannerVal}</td>
                <td>${getCprBadge(r['CPR Category'])}</td>
            </tr>
        `;
    }).join('');
}

function populateCrossTfFilter() {
    const select = $('#crossTfFilter');
    const currentVal = select.value;
    const tfMap = { '5min': '5m', '10min': '10m', '15min': '15m', '20min': '20m', '25min': '25m', '30min': '30m', '45min': '45m', '1hr': '1h', '2hr': '2h', '4hr': '4h', '6hr': '6h', '8hr': '8h', '12hr': '12h', '1 day': '1D', '1 week': '1W', '1 month': '1M' };
    const tfs = [...new Set(allCrossResults.map(r => r.Timeperiod))];
    select.innerHTML = '<option value="all">All Timeframes</option>' +
        tfs.map(tf => `<option value="${tf}">${tfMap[tf] || tf}</option>`).join('');
    select.value = tfs.includes(currentVal) ? currentVal : 'all';
}

function populateConflictTfFilter() {
    const select = $('#conflictTfFilter');
    const currentVal = select.value;
    const tfMap = { '5min': '5m', '10min': '10m', '15min': '15m', '20min': '20m', '25min': '25m', '30min': '30m', '45min': '45m', '1hr': '1h', '2hr': '2h', '4hr': '4h', '6hr': '6h', '8hr': '8h', '12hr': '12h', '1 day': '1D', '1 week': '1W', '1 month': '1M' };
    const tfs = [...new Set(allConflictResults.map(r => r.Timeperiod))];
    select.innerHTML = '<option value="all">All Timeframes</option>' +
        tfs.map(tf => `<option value="${tf}">${tfMap[tf] || tf}</option>`).join('');
    select.value = tfs.includes(currentVal) ? currentVal : 'all';
}

function renderConflictResults() {
    const body = $('#conflictSignalsBody');
    const empty = $('#conflictEmptyState');
    const countEl = $('#conflictResultCount');
    const searchVal = ($('#conflictSearchInput').value || '').toLowerCase();
    const signalFilter = $('#conflictSignalFilterChips .chip.active')?.dataset?.filter || 'all';
    const tfFilter = $('#conflictTfFilter').value;

    let filtered = allConflictResults.filter(r => {
        if (searchVal && !r['Crypto Name']?.toLowerCase().includes(searchVal)) return false;
        if (signalFilter !== 'all' && r.Signal !== signalFilter) return false;
        if (tfFilter !== 'all' && r.Timeperiod !== tfFilter) return false;
        return true;
    });

    // Sort
    if (currentConflictSort.col) {
        const numericCols = ['Angle', 'TEMA Gap', 'RSI', 'Daily Change'];
        const isNumeric = numericCols.includes(currentConflictSort.col);
        filtered.sort((a, b) => {
            let va = a[currentConflictSort.col] || '';
            let vb = b[currentConflictSort.col] || '';
            if (isNumeric) {
                va = parseFloat(String(va).replace(/[°%,]/g, '')) || 0;
                vb = parseFloat(String(vb).replace(/[°%,]/g, '')) || 0;
            } else {
                if (typeof va === 'string') va = va.toLowerCase();
                if (typeof vb === 'string') vb = vb.toLowerCase();
            }
            if (va < vb) return currentConflictSort.asc ? -1 : 1;
            if (va > vb) return currentConflictSort.asc ? 1 : -1;
            return 0;
        });
    }

    if (filtered.length === 0) {
        body.innerHTML = '';
        empty.style.display = 'block';
        countEl.textContent = '0 results';
        return;
    }

    empty.style.display = 'none';
    countEl.textContent = `${filtered.length} result${filtered.length !== 1 ? 's' : ''}`;

    const tfMap = { '5min': '5m', '10min': '10m', '15min': '15m', '20min': '20m', '25min': '25m', '30min': '30m', '45min': '45m', '1hr': '1h', '2hr': '2h', '4hr': '4h', '6hr': '6h', '8hr': '8h', '12hr': '12h', '1 day': '1D', '2 day': '2D', '3 day': '3D', '4 day': '4D', '5 day': '5D', '6 day': '6D', '1 week': '1W', '1 month': '1M' };

    function getConflictBadgeClass(scanner) {
        if (!scanner) return '';
        if (scanner.startsWith('Long Conflict'))  return 'scanner-conflict-long';
        if (scanner.startsWith('Short Conflict')) return 'scanner-conflict-short';
        if (scanner.startsWith('Bar+1'))          return 'scanner-bar1';
        return '';
    }

    // Extract state label from scanner string e.g. "Long Conflict: SAFE" → "SAFE"
    function getConflictState(scanner) {
        const parts = scanner.split(':');
        return parts.length > 1 ? parts.slice(1).join(':').trim() : scanner;
    }

    body.innerHTML = filtered.map((r, i) => {
        const sigCls = r.Signal === 'LONG' ? 'long' : 'short';
        const sigIcon = r.Signal === 'LONG' ? 'fa-arrow-up' : 'fa-arrow-down';
        const changeStr = r['Daily Change'] || '—';
        const changeVal = parseFloat(changeStr);
        const changeCls = isNaN(changeVal) ? '' : (changeVal >= 0 ? 'change-positive' : 'change-negative');
        const name = r['Crypto Name'] || '—';
        const tfDisplay = tfMap[r.Timeperiod] || r.Timeperiod;
        const scannerVal = r.Scanner || '—';
        const badgeCls = getConflictBadgeClass(scannerVal);
        const stateLabel = getConflictState(scannerVal);
        const colorStr = r.Color || 'N/A';
        const colorCls = colorStr === 'GREEN' ? 'change-positive' : colorStr === 'RED' ? 'change-negative' : '';
        const candleDisplay = colorStr === 'GREEN' ? 'Bullish' : colorStr === 'RED' ? 'Bearish' : colorStr === 'NEUTRAL' ? 'Neutral' : 'N/A';

        return `
            <tr style="animation: fadeUp 0.3s ${0.03 * i}s var(--ease-out) both">
                <td><strong>${name}</strong></td>
                <td><span class="tf-badge">${tfDisplay}</span></td>
                <td>
                    <span class="signal-badge ${sigCls}">
                        <i class="fas ${sigIcon}"></i>
                        ${r.Signal}
                    </span>
                </td>
                <td class="mono">${r.Angle || '—'}</td>
                <td class="mono">${r['TEMA Gap'] || '—'}</td>
                <td class="mono">${r.RSI || '—'}</td>
                <td class="${changeCls}">${changeStr}</td>
                <td>${badgeCls
                    ? `<span class="scanner-badge ${badgeCls}" title="${scannerVal}">${stateLabel}</span>`
                    : scannerVal}</td>
                <td><span class="ma-type-badge">${r['MA Type'] || '—'}</span></td>
                <td class="mono">${r.Timestamp || '—'}</td>
                <td class="${colorCls}"><strong>${candleDisplay}</strong></td>
                <td>${getCprBadge(r['CPR Category'])}</td>
            </tr>
        `;
    }).join('');
}

function updateStats() {
    const total = allResults.length;
    const longs = allResults.filter(r => r.Signal === 'LONG').length;
    const shorts = allResults.filter(r => r.Signal === 'SHORT').length;
    animateCounter('totalSignals', total);
    animateCounter('longSignals', longs);
    animateCounter('shortSignals', shorts);
}

// Instantly clears all dashboard stats and tables — called before a rescan so the
// user gets immediate visual feedback that a new scan is in progress.
function clearDashboard() {
    console.log('[clearDashboard] Resetting stat cards and tables.');
    // Zero out stat cards instantly (no animation)
    ['totalSignals', 'longSignals', 'shortSignals'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = '0';
        else console.warn('[clearDashboard] Element not found: #' + id);
    });
    // Show scanning indicator on Last Scan card
    const lastScanEl = $('#lastScanTime');
    if (lastScanEl) {
        lastScanEl.textContent = 'Scanning…';
        lastScanEl.title = '';
    } else {
        console.warn('[clearDashboard] Element not found: #lastScanTime');
    }
    // Clear result arrays and tables
    allResults = [];
    allHilegaResults = [];
    allCrossResults = [];
    allConflictResults = [];
    renderResults();
    renderHilegaResults();
    renderCrossResults();
    renderConflictResults();
    console.log('[clearDashboard] Done.');
}

function updateLastScanTime(timeStr) {
    if (!timeStr) return;
    const scanDate = new Date(timeStr);
    const now = new Date();
    const diffMs = now - scanDate;
    const diffMin = Math.floor(diffMs / 60000);

    let display;
    if (diffMin < 1) display = 'Just now';
    else if (diffMin < 60) display = `${diffMin}m ago`;
    else if (diffMin < 1440) display = `${Math.floor(diffMin / 60)}h ago`;
    else display = `${Math.floor(diffMin / 1440)}d ago`;

    $('#lastScanTime').textContent = display;
    $('#lastScanTime').title = `Last scan: ${timeStr}`;
}

function animateCounter(id, target) {
    const el = document.getElementById(id);
    if (!el) return;
    const current = parseInt(el.textContent) || 0;
    if (current === target) return;
    const duration = 600;
    const start = performance.now();
    function step(ts) {
        const progress = Math.min((ts - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(current + (target - current) * eased);
        if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
}

// ══════════════════════════════════════════════════════════════
// SCANNER CONTROLS
// ══════════════════════════════════════════════════════════════
function initScannerControls() {
    // Auto MA Type toggle — grey out the dropdown when auto is ON
    const autoMaToggle = $('#autoMaType');
    const maTypeGroup  = $('#maTypeGroup');
    const maTypeSelect = $('#maType');
    const applyAutoMaState = () => {
        const isAuto = autoMaToggle.checked;
        maTypeGroup.style.opacity  = isAuto ? '0.4' : '1';
        maTypeSelect.disabled      = isAuto;
    };
    applyAutoMaState();  // apply on load
    autoMaToggle.addEventListener('change', applyAutoMaState);

    // Index chip toggles
    $$('.index-chip').forEach(chip => {
        chip.addEventListener('click', () => chip.classList.toggle('active'));
    });

    // Scanner type chip toggles (fully independent — any combination can be selected)
    $$('.scanner-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            chip.classList.toggle('active');
        });
    });

    // Timeframe chip toggles
    $$('.tf-chip').forEach(chip => {
        chip.addEventListener('click', () => chip.classList.toggle('active'));
    });

    // Reset Timeframes button
    $('#resetTimeframesBtn').addEventListener('click', () => {
        $$('.tf-chip').forEach(chip => {
            chip.classList.remove('active');
        });
    });

    // Reset Scanner Type button
    $('#resetScannerTypeBtn').addEventListener('click', () => {
        $$('.scanner-chip').forEach(chip => {
            chip.classList.remove('active');
        });
        // Deactivate ALL button
        $('#allScannersBtn').classList.remove('active');
        // Update HILEGA RSI Setup visibility after resetting
        updateHilegaRsiSetupVisibility();
    });

    // All Scanners button
    $('#allScannersBtn').addEventListener('click', () => {
        const allBtn = $('#allScannersBtn');
        allBtn.classList.toggle('active');

        // If ALL is activated, deselect all individual chips
        if (allBtn.classList.contains('active')) {
            $$('.scanner-chip').forEach(chip => {
                chip.classList.remove('active');
            });
        }
        // Update HILEGA RSI Setup visibility (show if ALL is active since it includes HILEGA)
        if (allBtn.classList.contains('active')) {
            $('#hilegaRsiSetupSection').style.display = 'block';
        } else {
            updateHilegaRsiSetupVisibility();
        }
    });

    // Update scanner chip click behavior to deactivate ALL button
    $$('.scanner-chip').forEach(chip => {
        const originalListener = chip.onclick;
        chip.addEventListener('click', () => {
            // If any individual chip is clicked, deactivate ALL button
            $('#allScannersBtn').classList.remove('active');
        });
    });

    // HILEGA RSI Setup visibility and controls
    updateHilegaRsiSetupVisibility();
    $$('.scanner-chip').forEach(chip => {
        chip.addEventListener('click', updateHilegaRsiSetupVisibility);
    });

    // HILEGA RSI Mode change handler
    $('#hilegaRsiMode').addEventListener('change', updateAlmaFixedLengthsVisibility);
    updateAlmaFixedLengthsVisibility();

    // Run scan button
    $('#runScanBtn').addEventListener('click', () => runScan());

    // Refresh button — always triggers a rescan.
    // Uses the last scan config if available, otherwise reads from the Scanner UI (DOM).
    $('#refreshBtn').addEventListener('click', () => {
        console.log('[Refresh] Button clicked. scanRunning=', scanRunning, '| lastScanConfig=', lastScanConfig);
        runScan(lastScanConfig);
    });

    // Export CSV
    $('#exportCsvBtn').addEventListener('click', exportCSV);

    // Export Hilega CSV
    $('#exportHilegaCsvBtn').addEventListener('click', exportHilegaCSV);

    // Clear logs
    const clearLogHTML = `
            <div class="log-line system">
                <span class="log-ts">system</span>
                <span class="log-msg">Logs cleared</span>
            </div>
        `;
    $('#scannerClearLogsBtn').addEventListener('click', () => {
        $('#scannerLogOutput').innerHTML = clearLogHTML;
    });
}

// ══════════════════════════════════════════════════════════════
// HILEGA RSI SETUP VISIBILITY CONTROLS
// ══════════════════════════════════════════════════════════════
function updateHilegaRsiSetupVisibility() {
    const hilegaScanners = ['hilega_buy', 'hilega_sell'];
    const selectedScanners = Array.from($$('.scanner-chip.active')).map(c => c.dataset.scanner);
    const hasHilega = selectedScanners.some(s => hilegaScanners.includes(s));

    const setupSection = $('#hilegaRsiSetupSection');
    if (hasHilega) {
        setupSection.style.display = 'block';
    } else {
        setupSection.style.display = 'none';
    }
}

function updateAlmaFixedLengthsVisibility() {
    const rsiMode = $('#hilegaRsiMode').value;
    const lengthsRow = $('#almaFixedLengthsRow');
    const hint = $('#hilegaRsiModeHint');

    if (rsiMode === 'ALMA Fixed') {
        lengthsRow.style.display = 'flex';
        hint.textContent = 'ALMA Fixed: Use ALMA smoothing with custom fixed lengths (defaults: RSI=11, VWMA=21, TEMA=10)';
    } else {
        lengthsRow.style.display = 'none';
        if (rsiMode === 'ALMA') {
            hint.textContent = 'ALMA (Adaptive): Use ALMA smoothing with timeframe-adaptive lengths';
        } else if (rsiMode === 'RMA') {
            hint.textContent = 'RMA (Adaptive): Use RMA smoothing with timeframe-adaptive lengths (matches standard RSI)';
        }
    }
}

// ══════════════════════════════════════════════════════════════
// MODERN COLLAPSIBLE SECTIONS
// ══════════════════════════════════════════════════════════════
function initModernCollapse() {
    $$('.section-header-collapse').forEach(header => {
        header.addEventListener('click', () => {
            const targetId = header.dataset.collapse;
            const content = $(`#${targetId}`);

            if (content) {
                header.classList.toggle('collapsed');
                content.classList.toggle('collapsed');
            }
        });
    });
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    initModernCollapse();
});

async function runScan(overrideConfig = null) {
    console.log('[runScan] Called. scanRunning=', scanRunning, '| overrideConfig=', overrideConfig);

    if (scanRunning) {
        console.warn('[runScan] BLOCKED — scanRunning is true. Scan already in progress.');
        return;
    }

    let crypto_count, timeframes, adaptation_speed, min_bars_between, ma_type, auto_ma_type,
        enable_regime_filter, enable_volume_filter, enable_angle_filter,
        enable_tema_filter, enable_vwap_filter, enable_volume_filter_cross, enable_htf_rsi_filter,
        enable_cpr_narrow_filter,
        hilega_buy_rsi, hilega_sell_rsi, hilega_rsi_mode,
        alma_fixed_rsi_length, alma_fixed_vwma_length, alma_fixed_tema_length,
        scanner_type, scannerLabel;

    if (overrideConfig) {
        console.log('[runScan] Using saved lastScanConfig (rescan path).');
        // Rescan using last scan configuration
        ({ crypto_count, timeframes, adaptation_speed, min_bars_between, ma_type, auto_ma_type,
           enable_regime_filter, enable_volume_filter, enable_angle_filter,
           enable_tema_filter, enable_vwap_filter, enable_volume_filter_cross, enable_htf_rsi_filter,
           enable_cpr_narrow_filter,
           hilega_buy_rsi, hilega_sell_rsi, hilega_rsi_mode,
           alma_fixed_rsi_length, alma_fixed_vwma_length, alma_fixed_tema_length,
           scanner_type, scannerLabel } = overrideConfig);
        console.log('[runScan] Rescan config — timeframes:', timeframes, '| scanner_type:', scanner_type, '| crypto_count:', crypto_count);
    } else {
        console.log('[runScan] No saved config — reading from Scanner UI (DOM).');
        // Read configuration from DOM
        crypto_count = parseInt($('#cryptoCount').value) || 20;
        timeframes = Array.from($$('.tf-chip.active')).map(c => c.dataset.tf);
        adaptation_speed = $('#adaptationSpeed').value;
        min_bars_between = parseInt($('#minBarsBetween').value) || 3;
        auto_ma_type = $('#autoMaType').checked;
        ma_type = $('#maType').value || 'ALMA';

        // Get Advanced Filter toggles
        enable_regime_filter = $('#enableRegimeFilter').checked;
        enable_volume_filter = $('#enableVolumeFilter').checked;
        enable_angle_filter = $('#enableAngleFilter').checked;

        // Get Enterprise Cross Scanner Filter toggles
        const enable_tema_filter = $('#enableTemaFilter')?.checked || false;
        const enable_vwap_filter = $('#enableVwapFilter')?.checked || false;
        const enable_volume_filter_cross = $('#enableVolumeCrossFilter')?.checked || false;
        const enable_htf_rsi_filter = $('#enableHtfRsiFilter')?.checked || false;
        enable_cpr_narrow_filter = $('#enableCprNarrowFilter')?.checked || false;

        // Get HILEGA RSI thresholds
        hilega_buy_rsi = parseInt($('#hilegaBuyRsi').value) || 10;
        hilega_sell_rsi = parseInt($('#hilegaSellRsi').value) || 90;

        // Get HILEGA RSI Mode and parameters
        hilega_rsi_mode = $('#hilegaRsiMode').value;
        alma_fixed_rsi_length = parseInt($('#almaFixedRsiLength').value) || 11;
        alma_fixed_vwma_length = parseInt($('#almaFixedVwmaLength').value) || 21;
        alma_fixed_tema_length = parseInt($('#almaFixedTemaLength').value) || 10;

        // Check if ALL button is active
        const isAllActive = $('#allScannersBtn').classList.contains('active');

        // Get all selected scanner types
        const selectedScanners = isAllActive ? [] : Array.from($$('.scanner-chip.active')).map(c => c.dataset.scanner);

        console.log('[runScan] DOM read — timeframes:', timeframes, '| isAllActive:', isAllActive, '| selectedScanners:', selectedScanners);

        if (timeframes.length === 0) {
            console.warn('[runScan] BLOCKED — no timeframes selected in Scanner UI.');
            showToast('Select at least one timeframe', 'warning');
            return;
        }

        if (!isAllActive && selectedScanners.length === 0) {
            console.warn('[runScan] BLOCKED — no scanner type selected in Scanner UI.');
            showToast('Select at least one scanner type', 'warning');
            return;
        }

        // Determine scanner_type based on selections
        if (isAllActive) {
            scanner_type = 'all';
        } else if (selectedScanners.length === 1) {
            scanner_type = selectedScanners[0];
        } else {
            scanner_type = selectedScanners;
        }

        // Build scanner label for logging
        const scannerLabelsMap = { 'both': 'AMA Pro + Qwen', 'qwen': 'Qwen', 'ama_pro': 'AMA Pro', 'ama_pro_now': 'AMA Pro Now', 'qwen_now': 'Qwen Now', 'both_now': 'AMA Pro Now + Qwen Now', 'all': 'All Scanners', 'conflict_long': 'Long Conflict', 'conflict_short': 'Short Conflict', 'conflict_bar1': 'Bar+1 Action', 'rsi_cross_up_vwma': 'RSI Cross UP VWMA', 'rsi_cross_dn_vwma': 'RSI Cross DN VWMA', 'rsi_cross_up_alma': 'RSI Cross UP ALMA', 'rsi_cross_dn_alma': 'RSI Cross DN ALMA' };
        scannerLabel = isAllActive ? 'All Scanners' : (selectedScanners.length > 1 ? selectedScanners.map(s => scannerLabelsMap[s] || s).join(' + ') : (scannerLabelsMap[selectedScanners[0]] || selectedScanners[0]));

        // Save config for future rescans
        lastScanConfig = {
            crypto_count, timeframes, adaptation_speed, min_bars_between, ma_type, auto_ma_type,
            enable_regime_filter, enable_volume_filter, enable_angle_filter,
            enable_tema_filter, enable_vwap_filter, enable_volume_filter_cross, enable_htf_rsi_filter,
            enable_cpr_narrow_filter,
            hilega_buy_rsi, hilega_sell_rsi, hilega_rsi_mode,
            alma_fixed_rsi_length, alma_fixed_vwma_length, alma_fixed_tema_length,
            scanner_type, scannerLabel
        };
        console.log('[runScan] Config saved to lastScanConfig:', lastScanConfig);
    }

    console.log('[runScan] Proceeding — setting scanRunning=true and clearing dashboard.');
    scanRunning = true;
    $('#refreshBtn').disabled = true;
    const btn = $('#runScanBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>Scanning...</span>';
    btn.classList.remove('pulse-glow');

    // Immediately clear dashboard so the user sees a blank state before new results arrive
    clearDashboard();
    console.log('[runScan] Dashboard cleared. Starting API call to /api/scan...');

    // Show progress bar
    const progressWrap = $('#scanProgressWrap');
    progressWrap.classList.remove('hidden');
    updateProgress(0, 'Starting scan...');

    // Start log polling
    startLogPolling();

    // Simulate progress
    let prog = 0;
    const totalSteps = crypto_count * timeframes.length;
    const progInterval = setInterval(() => {
        if (!scanRunning) { clearInterval(progInterval); return; }
        prog = Math.min(prog + (90 / totalSteps / 2), 90);
        updateProgress(prog, `Analyzing top ${crypto_count} coins across ${timeframes.length} timeframes...`);
    }, 500);

    try {
        // Add scan start log
        addLogLine('info', `🔄 CRYPTO SCAN IN PROGRESS — Top ${crypto_count} Coins | TFs: ${timeframes.join(', ')} | Scanner: ${scannerLabel} | MA: ${ma_type} | Speed: ${adaptation_speed} | MinBars: ${min_bars_between}`);
        const res = await fetch(`${API_URL}/api/scan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                indices: ["CRYPTO"],
                timeframes,
                adaptation_speed,
                min_bars_between,
                crypto_count,
                scanner_type,
                ma_type,
                auto_ma_type,
                enable_regime_filter,  // Advanced filter toggles
                enable_volume_filter,
                enable_angle_filter,
                enable_tema_filter,
                enable_vwap_filter,
                enable_volume_filter_cross,
                enable_htf_rsi_filter,
                enable_cpr_narrow_filter,
                hilega_buy_rsi,
                hilega_sell_rsi,
                hilega_rsi_mode,
                alma_fixed_rsi_length,
                alma_fixed_vwma_length,
                alma_fixed_tema_length
            })
        });

        clearInterval(progInterval);

        if (!res.ok) throw new Error(`Server error: ${res.status}`);

        const data = await res.json();
        allResults = data.data || [];
        allHilegaResults = data.hilega_data || [];
        allCrossResults = data.cross_data || [];
        allConflictResults = data.conflict_data || [];

        const totalSignals = allResults.length + allHilegaResults.length + allCrossResults.length + allConflictResults.length;

        updateProgress(100, 'Scan complete!');
        const parts = [];
        if (allResults.length > 0) parts.push(`${allResults.length} AMA/Qwen`);
        if (allConflictResults.length > 0) parts.push(`${allConflictResults.length} Conflict`);
        if (allHilegaResults.length > 0) parts.push(`${allHilegaResults.length} HILEGA`);
        if (allCrossResults.length > 0) parts.push(`${allCrossResults.length} Cross`);
        addLogLine('success', `✅ SCAN COMPLETED — ${parts.length ? parts.join(' · ') : '0'} signal(s) found`);

        populateTfFilter();
        populateHilegaTfFilter();
        populateCrossTfFilter();
        populateConflictTfFilter();
        renderResults();
        renderHilegaResults();
        renderCrossResults();
        renderConflictResults();
        updateStats();
        updateLastScanTime(new Date().toISOString());
        fetchTradeSetups();   // refresh live setups after every scan

        showToast(`Scan complete! ${totalSignals} total signal(s) found.`, 'success');

        // Switch to dashboard tab to show results
        if (totalSignals > 0) {
            setTimeout(() => {
                $$('.nav-link').forEach(l => l.classList.remove('active'));
                $('#nav-dashboard').classList.add('active');
                $$('.tab-content').forEach(t => t.classList.remove('active'));
                $('#tab-dashboard').classList.add('active');
            }, 800);
        }

    } catch (err) {
        console.error('[runScan] ERROR during scan:', err);
        clearInterval(progInterval);
        updateProgress(0, 'Scan failed');
        addLogLine('error', `❌ Scan failed: ${err.message}`);
        showToast(`Scan failed: ${err.message}`, 'error');
    } finally {
        console.log('[runScan] Finally block — resetting scanRunning=false, re-enabling buttons.');
        scanRunning = false;
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-play"></i> <span>Run Scanner</span>';
        btn.classList.add('pulse-glow');
        $('#refreshBtn').disabled = false;
        stopLogPolling();

        setTimeout(() => {
            progressWrap.classList.add('hidden');
        }, 3000);
    }
}

function updateProgress(pct, detail) {
    $('#scanProgressBar').style.width = `${pct}%`;
    $('#scanProgressPct').textContent = `${Math.round(pct)}%`;
    if (detail) $('#scanProgressDetail').textContent = detail;
}

// ══════════════════════════════════════════════════════════════
// LOG POLLING
// ══════════════════════════════════════════════════════════════
function startLogPolling() {
    stopLogPolling();
    logPollInterval = setInterval(fetchLogs, 2000);
}
function stopLogPolling() {
    if (logPollInterval) { clearInterval(logPollInterval); logPollInterval = null; }
}

async function fetchLogs() {
    try {
        const res = await fetch(`${API_URL}/api/logs`);
        if (!res.ok) return;
        const data = await res.json();
        const logEl = $('#scannerLogOutput');

        if (data.logs && data.logs.length > 0) {
            logEl.innerHTML = data.logs.map(line => {
                const trimmed = (typeof line === 'string' ? line : '').trim();
                if (!trimmed) return '';
                let cls = '';
                if (trimmed.includes('ERROR') || trimmed.includes('error')) cls = 'error';
                else if (trimmed.includes('WARNING') || trimmed.includes('warning')) cls = 'warn';
                else if (trimmed.includes('SIGNAL') || trimmed.includes('✅') || trimmed.includes('COMPLETED')) cls = 'success';
                else if (trimmed.includes('INFO') || trimmed.includes('🔄') || trimmed.includes('Scanning') || trimmed.includes('Fetching')) cls = 'info';

                // Extract timestamp
                const tsMatch = trimmed.match(/^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})/);
                const ts = tsMatch ? tsMatch[1].split(' ')[1] : '';
                const msg = tsMatch ? trimmed.slice(tsMatch[0].length).replace(/^\s*-\s*/, '').replace(/^\s*INFO\s*-\s*/, '').replace(/^\s*ERROR\s*-\s*/, '').trim() : trimmed;

                return `<div class="log-line ${cls}"><span class="log-ts">${ts}</span><span class="log-msg">${msg}</span></div>`;
            }).join('');
            logEl.scrollTop = logEl.scrollHeight;
        }
    } catch (e) { /* Silently fail */ }
}

function addLogLine(cls, msg) {
    const now = new Date();
    const ts = now.toTimeString().slice(0, 8);
    const logEl = $('#scannerLogOutput');
    logEl.innerHTML += `<div class="log-line ${cls}"><span class="log-ts">${ts}</span><span class="log-msg">${msg}</span></div>`;
    logEl.scrollTop = logEl.scrollHeight;
}

// ══════════════════════════════════════════════════════════════
// FILTER CONTROLS
// ══════════════════════════════════════════════════════════════
function initFilterControls() {
    // Signal filter chips
    $$('#signalFilterChips .chip').forEach(chip => {
        chip.addEventListener('click', () => {
            $$('#signalFilterChips .chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            renderResults();
        });
    });

    // Search
    let searchTimeout;
    $('#searchInput').addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(renderResults, 200);
    });

    // Timeframe filter
    $('#tfFilter').addEventListener('change', renderResults);

    // Scanner filter chips
    $$('#scannerFilterChips .chip').forEach(chip => {
        chip.addEventListener('click', () => {
            $$('#scannerFilterChips .chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            renderResults();
        });
    });

    // Column sorting
    $$('#signalsTable th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const colMap = {
                name: 'Crypto Name',
                timeframe: 'Timeperiod',
                signal: 'Signal',
                angle: 'Angle',
                temagap: 'TEMA Gap',
                rsi: 'RSI',
                change: 'Daily Change',
                scanner: 'Scanner',
                cprcategory: 'CPR Category'
            };
            const col = colMap[th.dataset.col];
            if (currentSort.col === col) {
                currentSort.asc = !currentSort.asc;
            } else {
                currentSort.col = col;
                currentSort.asc = true;
            }

            // Update sort icons
            $$('#signalsTable th.sortable').forEach(t => {
                t.classList.remove('sorted-asc', 'sorted-desc');
            });
            th.classList.add(currentSort.asc ? 'sorted-asc' : 'sorted-desc');
            renderResults();
        });
    });

    // ═══ HILEGA FILTER CONTROLS ═══

    // Hilega signal filter chips
    $$('#hilegaSignalFilterChips .chip').forEach(chip => {
        chip.addEventListener('click', () => {
            $$('#hilegaSignalFilterChips .chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            renderHilegaResults();
        });
    });

    // Hilega search
    let hilegaSearchTimeout;
    $('#hilegaSearchInput').addEventListener('input', () => {
        clearTimeout(hilegaSearchTimeout);
        hilegaSearchTimeout = setTimeout(renderHilegaResults, 200);
    });

    // Hilega timeframe filter
    $('#hilegaTfFilter').addEventListener('change', renderHilegaResults);

    // Hilega column sorting
    $$('#hilegaSignalsTable th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const colMap = {
                name: 'Crypto Name',
                timeframe: 'Timeperiod',
                signal: 'Signal',
                angle: 'Angle',
                rsitema: 'RSI-TEMA',
                rsi: 'RSI',
                vwma: 'VWMA',
                change: 'Daily Change',
                cprcategory: 'CPR Category'
            };
            const col = colMap[th.dataset.col];
            if (currentHilegaSort.col === col) {
                currentHilegaSort.asc = !currentHilegaSort.asc;
            } else {
                currentHilegaSort.col = col;
                currentHilegaSort.asc = true;
            }

            // Update sort icons
            $$('#hilegaSignalsTable th.sortable').forEach(t => {
                t.classList.remove('sorted-asc', 'sorted-desc');
            });
            th.classList.add(currentHilegaSort.asc ? 'sorted-asc' : 'sorted-desc');
            renderHilegaResults();
        });
    });

    // ═══ CROSS FILTER CONTROLS ═══

    // Cross signal filter chips
    $$('#crossSignalFilterChips .chip').forEach(chip => {
        chip.addEventListener('click', () => {
            $$('#crossSignalFilterChips .chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            renderCrossResults();
        });
    });

    // Cross search
    let crossSearchTimeout;
    $('#crossSearchInput').addEventListener('input', () => {
        clearTimeout(crossSearchTimeout);
        crossSearchTimeout = setTimeout(renderCrossResults, 200);
    });

    // Cross timeframe filter
    $('#crossTfFilter').addEventListener('change', renderCrossResults);

    // Cross column sorting
    $$('#crossSignalsTable th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const colMap = {
                name: 'Crypto Name',
                timeframe: 'Timeperiod',
                signal: 'Signal Type',
                candle: 'Candle Status',
                angle: 'Angle',
                rsidiff: 'RSI Diff',
                rsi: 'RSI',
                vwma: 'VWMA',
                alma: 'ALMA',
                change: 'Daily Change',
                scanner: 'Scanner',
                cprcategory: 'CPR Category'
            };
            const col = colMap[th.dataset.col];
            if (currentCrossSort.col === col) {
                currentCrossSort.asc = !currentCrossSort.asc;
            } else {
                currentCrossSort.col = col;
                currentCrossSort.asc = true;
            }

            // Update sort icons
            $$('#crossSignalsTable th.sortable').forEach(t => {
                t.classList.remove('sorted-asc', 'sorted-desc');
            });
            th.classList.add(currentCrossSort.asc ? 'sorted-asc' : 'sorted-desc');
            renderCrossResults();
        });
    });

    // Conflict signal filter chips
    $$('#conflictSignalFilterChips .chip').forEach(chip => {
        chip.addEventListener('click', () => {
            $$('#conflictSignalFilterChips .chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            renderConflictResults();
        });
    });

    // Conflict search
    let conflictSearchTimeout;
    $('#conflictSearchInput').addEventListener('input', () => {
        clearTimeout(conflictSearchTimeout);
        conflictSearchTimeout = setTimeout(renderConflictResults, 200);
    });

    // Conflict timeframe filter
    $('#conflictTfFilter').addEventListener('change', renderConflictResults);
}

// ══════════════════════════════════════════════════════════════
// MOBILE MENU
// ══════════════════════════════════════════════════════════════
function initMobileMenu() {
    const btn = $('#hamburgerBtn');
    if (btn) {
        btn.addEventListener('click', () => {
            $('#sidebar').classList.toggle('open');
        });
    }
}

// ══════════════════════════════════════════════════════════════
// EXPORT CSV
// ══════════════════════════════════════════════════════════════
function exportCSV() {
    if (allResults.length === 0) {
        showToast('No data to export', 'warning');
        return;
    }
    const hasScanner = allResults.some(r => r.Scanner);
    const hasSignalType = allResults.some(r => r['Signal Type']);
    const headers = hasScanner
        ? ['Index', 'Timeframe', 'Signal', 'Angle', 'TEMA Gap', 'RSI', 'Daily Change', 'Scanner', 'Timestamp', 'Candle', 'Signal Type']
        : ['Index', 'Timeframe', 'Signal', 'Angle', 'TEMA Gap', 'RSI', 'Daily Change', 'Timestamp', 'Candle', 'Signal Type'];
    const rows = allResults.map(r => {
        const base = [r['Crypto Name'], r.Timeperiod, r.Signal, r.Angle, r['TEMA Gap'], r.RSI || 'N/A', r['Daily Change']];
        if (hasScanner) base.push(r.Scanner || '');
        base.push(r.Timestamp);
        const candleValue = r.Color === 'GREEN' ? 'Bullish' : r.Color === 'RED' ? 'Bearish' : r.Color === 'NEUTRAL' ? 'Neutral' : 'N/A';
        base.push(candleValue);
        base.push(r['Signal Type'] || 'CROSSOVER');
        return base;
    });
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `gemini_scan_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('CSV exported', 'success');
}

function exportHilegaCSV() {
    if (allHilegaResults.length === 0) {
        showToast('No Hilega data to export', 'warning');
        return;
    }
    const headers = ['Asset', 'Timeframe', 'Signal', 'Angle', 'RSI-TEMA', 'RSI', 'VWMA', 'Daily Change', 'Timestamp'];
    const rows = allHilegaResults.map(r => {
        return [
            r['Crypto Name'],
            r.Timeperiod,
            r.Signal,
            r.Angle || '',
            r['RSI-TEMA'] || '',
            r.RSI || '',
            r.VWMA || '',
            r['Daily Change'] || '',
            r.Timestamp
        ];
    });
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `gemini_hilega_scan_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Hilega CSV exported', 'success');
}

// ══════════════════════════════════════════════════════════════
// CONNECTION STATUS
// ══════════════════════════════════════════════════════════════
function setConnectionStatus(online) {
    const statusEl = $('#connectionStatus');
    const dot = statusEl.querySelector('.status-dot');
    const text = statusEl.querySelector('span');
    dot.className = `status-dot ${online ? 'online' : 'offline'}`;
    text.textContent = online ? 'Connected' : 'Disconnected';
}

// ══════════════════════════════════════════════════════════════
// TOAST NOTIFICATIONS
// ══════════════════════════════════════════════════════════════
function showToast(message, type = 'info') {
    const container = $('#toastContainer');
    const iconMap = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<i class="fas ${iconMap[type]}"></i><span>${message}</span>`;
    container.appendChild(toast);

    requestAnimationFrame(() => {
        requestAnimationFrame(() => toast.classList.add('show'));
    });

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 400);
    }, 4000);
}

// ══════════════════════════════════════════════════════════════
// THEME TOGGLE
// ══════════════════════════════════════════════════════════════
function initThemeToggle() {
    const toggleBtn = $('#themeToggle');
    const icon = toggleBtn.querySelector('i');

    // Load saved theme or default to dark
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(icon, savedTheme);

    // Toggle theme on button click
    toggleBtn.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        updateThemeIcon(icon, newTheme);

        showToast(`Switched to ${newTheme} theme`, 'info');
    });
}

function updateThemeIcon(icon, theme) {
    if (theme === 'light') {
        icon.classList.remove('fa-moon');
        icon.classList.add('fa-sun');
    } else {
        icon.classList.remove('fa-sun');
        icon.classList.add('fa-moon');
    }
}

// ══════════════════════════════════════════════════════════════
// TICKER SPEED CONTROL
// ══════════════════════════════════════════════════════════════
function initTickerSpeedControl() {
    const speedSlider = $('#tickerSpeed');
    if (!speedSlider) return;

    // Load saved speed or default to 45s
    const savedSpeed = localStorage.getItem('tickerSpeed') || '45';
    speedSlider.value = savedSpeed;
    document.documentElement.style.setProperty('--ticker-speed', savedSpeed + 's');

    // Update speed on slider change
    speedSlider.addEventListener('input', (e) => {
        const speed = e.target.value;
        document.documentElement.style.setProperty('--ticker-speed', speed + 's');
        localStorage.setItem('tickerSpeed', speed);
    });
}

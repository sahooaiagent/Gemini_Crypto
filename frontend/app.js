/* ═══════════════════════════════════════════════════════════════════
   GEMINI SCANNER — ENTERPRISE APPLICATION LOGIC
   ═══════════════════════════════════════════════════════════════════ */

const API_URL = 'http://localhost:8001';
let allResults = [];
let allHilegaResults = [];
let allCrossResults = [];
let allConflictResults = [];
let scanRunning = false;
let logPollInterval = null;
let currentSort = { col: null, asc: true };
let currentHilegaSort = { col: null, asc: true };
let currentCrossSort = { col: null, asc: true };
let currentConflictSort = { col: null, asc: true };

function isConflictScanner(scanner) {
    return (scanner || '').startsWith('Long Conflict')
        || (scanner || '').startsWith('Short Conflict')
        || (scanner || '').startsWith('Bar+1');
}

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
    setConnectionStatus(true);

    // Initial data fetch
    fetchMarketData();
    fetchResults();

    // Periodic refresh
    setInterval(fetchMarketData, 60000);
    setInterval(() => { if (!scanRunning) fetchResults(); }, 30000);
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
            // Close mobile sidebar
            $('#sidebar').classList.remove('open');
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
                CRYPTO_TICKERS = data.indices;
                renderTickerTape();
                renderHeatmap();
            }
        }
    } catch (e) {
        console.error("Failed to fetch market data:", e);
    }
}

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
// FETCH & RENDER RESULTS
// ══════════════════════════════════════════════════════════════
async function fetchResults() {
    try {
        const res = await fetch(`${API_URL}/api/results`);
        if (!res.ok) return;
        const data = await res.json();
        const rawResults = data.results || [];
        allConflictResults = rawResults.filter(r => isConflictScanner(r.Scanner));
        allResults = rawResults.filter(r => !isConflictScanner(r.Scanner));
        allHilegaResults = data.hilega_results || [];
        allCrossResults = data.cross_results || [];
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

function renderResults() {
    const body = $('#signalsBody');
    const empty = $('#emptyState');
    const countEl = $('#resultCount');
    const searchVal = ($('#searchInput').value || '').toLowerCase();
    const signalFilter = $('#signalFilterChips .chip.active')?.dataset?.filter || 'all';
    const tfFilter = $('#tfFilter').value;
    const scannerFilter = $('#scannerFilterChips .chip.active')?.dataset?.filter || 'all';

    let filtered = allResults.filter(r => {
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
        const rsiStr = r.RSI || '—';

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
                <td class="mono">${rsiStr}</td>
                <td class="${changeCls}">${changeStr}</td>
                <td>${scannerBadgeCls ? `<span class="scanner-badge ${scannerBadgeCls}">${scannerVal}</span>` : scannerVal}</td>
                <td><span class="ma-type-badge">${r['MA Type'] || '—'}</span></td>
                <td class="mono">${r.Timestamp || '—'}</td>
                <td class="${colorCls}"><strong>${candleDisplay}</strong></td>
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
        const numericCols = ['Angle', 'RSI-VWMA', 'RSI', 'VWMA', 'ALMA', 'Daily Change'];
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
        const rsiVwmaStr = r['RSI-VWMA'] || '—';
        const rsiStr = r.RSI || '—';
        const vwmaStr = r.VWMA || '—';
        const almaStr = r.ALMA || '—';

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
                <td class="mono">${rsiVwmaStr}</td>
                <td class="mono">${rsiStr}</td>
                <td class="mono">${vwmaStr}</td>
                <td class="mono">${almaStr}</td>
                <td class="${changeCls}">${changeStr}</td>
                <td class="mono">${r.Timestamp || '—'}</td>
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
    const tfMap = { '5min': '5m', '10min': '10m', '15min': '15m', '20min': '20m', '25min': '25m', '30min': '30m', '45min': '45m', '1hr': '1h', '2hr': '2h', '4hr': '4h', '6hr': '6h', '8hr': '8h', '12hr': '12h', '1 day': '1D', '2 day': '2D', '3 day': '3D', '4 day': '4D', '5 day': '5D', '6 day': '6D', '1 week': '1W', '1 month': '1M' };
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
    const typeFilter = $('#conflictTypeFilterChips .chip.active')?.dataset?.filter || 'all';

    let filtered = allConflictResults.filter(r => {
        if (searchVal && !r['Crypto Name']?.toLowerCase().includes(searchVal)) return false;
        if (signalFilter !== 'all' && r.Signal !== signalFilter) return false;
        if (tfFilter !== 'all' && r.Timeperiod !== tfFilter) return false;
        if (typeFilter !== 'all') {
            const s = r.Scanner || '';
            if (typeFilter === 'Bar+1') {
                if (!s.startsWith('Bar+1')) return false;
            } else {
                if (!s.startsWith(typeFilter)) return false;
            }
        }
        return true;
    });

    if (currentConflictSort.col) {
        const numericCols = ['Angle', 'TEMA Gap', 'RSI', 'Daily Change'];
        const isNumeric = numericCols.includes(currentConflictSort.col);
        filtered.sort((a, b) => {
            let va = a[currentConflictSort.col] || '';
            let vb = b[currentConflictSort.col] || '';
            if (isNumeric) {
                va = parseFloat(String(va).replace(/[°%,+]/g, '')) || 0;
                vb = parseFloat(String(vb).replace(/[°%,+]/g, '')) || 0;
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

    body.innerHTML = filtered.map((r, i) => {
        const sigCls = r.Signal === 'LONG' ? 'long' : 'short';
        const sigIcon = r.Signal === 'LONG' ? 'fa-arrow-up' : 'fa-arrow-down';
        const changeStr = r['Daily Change'] || '—';
        const changeVal = parseFloat(changeStr);
        const changeCls = isNaN(changeVal) ? '' : (changeVal >= 0 ? 'change-positive' : 'change-negative');
        const tfDisplay = tfMap[r.Timeperiod] || r.Timeperiod;
        const scannerVal = r.Scanner || '—';
        function getConflictBadgeClass(scanner) {
            if (scanner.startsWith('Long Conflict'))  return 'scanner-conflict-long';
            if (scanner.startsWith('Short Conflict')) return 'scanner-conflict-short';
            if (scanner.startsWith('Bar+1'))          return 'scanner-bar1';
            return '';
        }
        const badgeCls = getConflictBadgeClass(scannerVal);
        const colorStr = r.Color || 'N/A';
        const colorCls = colorStr === 'GREEN' ? 'change-positive' : colorStr === 'RED' ? 'change-negative' : '';
        const candleDisplay = colorStr === 'GREEN' ? 'Bullish' : colorStr === 'RED' ? 'Bearish' : colorStr === 'NEUTRAL' ? 'Neutral' : 'N/A';

        return `
            <tr style="animation: fadeUp 0.3s ${0.03 * i}s var(--ease-out) both">
                <td><strong>${r['Crypto Name'] || '—'}</strong></td>
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
                <td>${badgeCls ? `<span class="scanner-badge ${badgeCls}">${scannerVal}</span>` : scannerVal}</td>
                <td><span class="ma-type-badge">${r['MA Type'] || '—'}</span></td>
                <td class="mono">${r.Timestamp || '—'}</td>
                <td class="${colorCls}"><strong>${candleDisplay}</strong></td>
            </tr>
        `;
    }).join('');
}

function updateStats() {
    const total = allResults.length + allHilegaResults.length + allCrossResults.length + allConflictResults.length;
    const longs = allResults.filter(r => r.Signal === 'LONG').length
                + allHilegaResults.filter(r => r.Signal === 'LONG').length
                + allCrossResults.filter(r => r['Signal Type'] === 'Cross UP').length
                + allConflictResults.filter(r => r.Signal === 'LONG').length;
    const shorts = allResults.filter(r => r.Signal === 'SHORT').length
                 + allHilegaResults.filter(r => r.Signal === 'SHORT').length
                 + allCrossResults.filter(r => r['Signal Type'] === 'Cross DN').length
                 + allConflictResults.filter(r => r.Signal === 'SHORT').length;
    animateCounter('totalSignals', total);
    animateCounter('longSignals', longs);
    animateCounter('shortSignals', shorts);
}

function applyGlobalSignalFilter(filter) {
    // AMA table chips
    $$('#signalFilterChips .chip').forEach(c => c.classList.remove('active'));
    const amaChip = $(`#signalFilterChips .chip[data-filter="${filter}"]`);
    if (amaChip) amaChip.classList.add('active');

    // HILEGA table chips
    $$('#hilegaSignalFilterChips .chip').forEach(c => c.classList.remove('active'));
    const hilegaChip = $(`#hilegaSignalFilterChips .chip[data-filter="${filter}"]`);
    if (hilegaChip) hilegaChip.classList.add('active');

    // Cross table chips — map LONG→Cross UP, SHORT→Cross DN, all→all
    $$('#crossSignalFilterChips .chip').forEach(c => c.classList.remove('active'));
    const crossFilterMap = { 'LONG': 'Cross UP', 'SHORT': 'Cross DN', 'all': 'all' };
    const crossFilter = crossFilterMap[filter] || 'all';
    const crossChip = $(`#crossSignalFilterChips .chip[data-filter="${crossFilter}"]`);
    if (crossChip) crossChip.classList.add('active');

    // Conflict table chips
    $$('#conflictSignalFilterChips .chip').forEach(c => c.classList.remove('active'));
    const conflictChip = $(`#conflictSignalFilterChips .chip[data-filter="${filter}"]`);
    if (conflictChip) conflictChip.classList.add('active');

    // Visual active state on stat cards
    $$('.stat-card.clickable-stat').forEach(c => c.classList.remove('filter-active'));
    if (filter === 'LONG') $('#longSignalCard').classList.add('filter-active');
    else if (filter === 'SHORT') $('#shortSignalCard').classList.add('filter-active');

    renderResults();
    renderHilegaResults();
    renderCrossResults();
    renderConflictResults();
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
    // Index chip toggles
    $$('.index-chip').forEach(chip => {
        chip.addEventListener('click', () => chip.classList.toggle('active'));
    });

    // Scanner type chip toggles (multi-select: can select multiple)
    // HILEGA, Cross, and AMA/Qwen scanners are mutually exclusive
    $$('.scanner-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const scannerType = chip.dataset.scanner;
            const hilegaScanners = ['hilega_buy', 'hilega_sell'];
            const crossScanners = ['rsi_cross_up_vwma', 'rsi_cross_dn_vwma'];
            const amaScanners = ['ama_pro', 'qwen', 'both', 'ama_pro_now', 'qwen_now', 'both_now', 'all', 'conflict_long', 'conflict_short', 'conflict_bar1'];

            // Check if clicking a HILEGA scanner
            if (hilegaScanners.includes(scannerType)) {
                // If activating HILEGA, deactivate all AMA and Cross scanners
                if (!chip.classList.contains('active')) {
                    $$('.scanner-chip').forEach(c => {
                        if (amaScanners.includes(c.dataset.scanner) || crossScanners.includes(c.dataset.scanner)) {
                            c.classList.remove('active');
                        }
                    });
                }
                chip.classList.toggle('active');
            }
            // Check if clicking a Cross scanner
            else if (crossScanners.includes(scannerType)) {
                // If activating Cross, deactivate all AMA and HILEGA scanners
                if (!chip.classList.contains('active')) {
                    $$('.scanner-chip').forEach(c => {
                        if (amaScanners.includes(c.dataset.scanner) || hilegaScanners.includes(c.dataset.scanner)) {
                            c.classList.remove('active');
                        }
                    });
                }
                chip.classList.toggle('active');
            }
            // Check if clicking an AMA/Qwen scanner
            else if (amaScanners.includes(scannerType)) {
                // If activating AMA, deactivate all HILEGA and Cross scanners
                if (!chip.classList.contains('active')) {
                    $$('.scanner-chip').forEach(c => {
                        if (hilegaScanners.includes(c.dataset.scanner) || crossScanners.includes(c.dataset.scanner)) {
                            c.classList.remove('active');
                        }
                    });
                }
                chip.classList.toggle('active');
            }
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
    $('#runScanBtn').addEventListener('click', runScan);

    // Refresh button
    $('#refreshBtn').addEventListener('click', () => {
        fetchResults();
        fetchMarketData();
        showToast('Data refreshed', 'info');
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

async function runScan() {
    if (scanRunning) return;

    const crypto_count = parseInt($('#cryptoCount').value) || 20;
    const timeframes = Array.from($$('.tf-chip.active')).map(c => c.dataset.tf);
    const adaptation_speed = $('#adaptationSpeed').value;
    const min_bars_between = parseInt($('#minBarsBetween').value) || 3;
    const ma_type = $('#maType').value || 'ALMA';  // Get MA type selection

    // Get Advanced Filter toggles
    const enable_regime_filter = $('#enableRegimeFilter').checked;
    const enable_volume_filter = $('#enableVolumeFilter').checked;
    const enable_angle_filter = $('#enableAngleFilter').checked;

    // Get HILEGA RSI thresholds
    const hilega_buy_rsi = parseInt($('#hilegaBuyRsi').value) || 10;
    const hilega_sell_rsi = parseInt($('#hilegaSellRsi').value) || 90;

    // Get HILEGA RSI Mode and parameters
    const hilega_rsi_mode = $('#hilegaRsiMode').value;
    const alma_fixed_rsi_length = parseInt($('#almaFixedRsiLength').value) || 11;
    const alma_fixed_vwma_length = parseInt($('#almaFixedVwmaLength').value) || 21;
    const alma_fixed_tema_length = parseInt($('#almaFixedTemaLength').value) || 10;

    // Check if ALL button is active
    const isAllActive = $('#allScannersBtn').classList.contains('active');

    // Get all selected scanner types
    const selectedScanners = isAllActive ? [] : Array.from($$('.scanner-chip.active')).map(c => c.dataset.scanner);

    if (timeframes.length === 0) {
        showToast('Select at least one timeframe', 'warning');
        return;
    }

    if (!isAllActive && selectedScanners.length === 0) {
        showToast('Select at least one scanner type', 'warning');
        return;
    }

    // Determine scanner_type based on selections
    let scanner_type;
    if (isAllActive) {
        // "ALL" button is active - use 'all' string
        scanner_type = 'all';
    } else if (selectedScanners.length === 1) {
        // Single scanner - send as string
        scanner_type = selectedScanners[0];
    } else {
        // Multiple specific scanners - send as array
        scanner_type = selectedScanners;
    }

    scanRunning = true;
    const btn = $('#runScanBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>Scanning...</span>';
    btn.classList.remove('pulse-glow');

    // Show progress bar
    const progressWrap = $('#scanProgressWrap');
    progressWrap.classList.remove('hidden');
    updateProgress(0, 'Starting scan...');

    // Clear previous results
    allResults = [];
    allHilegaResults = [];
    allCrossResults = [];
    allConflictResults = [];
    renderResults();
    renderHilegaResults();
    renderCrossResults();
    renderConflictResults();
    updateStats();

    // Add scan start log
    const scannerLabels = { 'both': 'AMA Pro + Qwen', 'qwen': 'Qwen', 'ama_pro': 'AMA Pro', 'ama_pro_now': 'AMA Pro Now', 'qwen_now': 'Qwen Now', 'both_now': 'AMA Pro Now + Qwen Now', 'all': 'All Scanners', 'conflict_long': 'Long Conflict', 'conflict_short': 'Short Conflict', 'conflict_bar1': 'Bar+1 Action' };
    const scannerLabel = isAllActive ? 'All Scanners' : (selectedScanners.length > 1 ? selectedScanners.map(s => scannerLabels[s] || s).join(' + ') : (scannerLabels[selectedScanners[0]] || selectedScanners[0]));
    addLogLine('info', `🔄 CRYPTO SCAN IN PROGRESS — Top ${crypto_count} Coins | TFs: ${timeframes.join(', ')} | Scanner: ${scannerLabel} | MA: ${ma_type} | Speed: ${adaptation_speed} | MinBars: ${min_bars_between}`);

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
                ma_type,  // Add MA type to request
                enable_regime_filter,  // Advanced filter toggles
                enable_volume_filter,
                enable_angle_filter,
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
        const rawData = data.data || [];
        allConflictResults = rawData.filter(r => isConflictScanner(r.Scanner));
        allResults = rawData.filter(r => !isConflictScanner(r.Scanner));
        allHilegaResults = data.hilega_data || [];
        allCrossResults = data.cross_data || [];

        const totalSignals = allResults.length + allHilegaResults.length + allCrossResults.length + allConflictResults.length;

        updateProgress(100, 'Scan complete!');
        addLogLine('success', `✅ SCAN COMPLETED — ${allResults.length} AMA/Qwen | ${allConflictResults.length} Conflict | ${allHilegaResults.length} HILEGA | ${allCrossResults.length} Cross signal(s) found`);

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
        clearInterval(progInterval);
        updateProgress(0, 'Scan failed');
        addLogLine('error', `❌ Scan failed: ${err.message}`);
        showToast(`Scan failed: ${err.message}`, 'error');
    } finally {
        scanRunning = false;
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-play"></i> <span>Run Scanner</span>';
        btn.classList.add('pulse-glow');
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
    // Stat card click filters
    $('#totalSignalCard').addEventListener('click', () => applyGlobalSignalFilter('all'));
    $('#longSignalCard').addEventListener('click', () => applyGlobalSignalFilter('LONG'));
    $('#shortSignalCard').addEventListener('click', () => applyGlobalSignalFilter('SHORT'));

    // Signal filter chips
    $$('#signalFilterChips .chip').forEach(chip => {
        chip.addEventListener('click', () => {
            $$('#signalFilterChips .chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            // Clear stat card active state when using per-table filter
            $$('.stat-card.clickable-stat').forEach(c => c.classList.remove('filter-active'));
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
                scanner: 'Scanner'
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
                change: 'Daily Change'
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
                rsivwma: 'RSI-VWMA',
                rsi: 'RSI',
                vwma: 'VWMA',
                alma: 'ALMA',
                change: 'Daily Change'
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

    // ═══ CONFLICT FILTER CONTROLS ═══

    // Conflict signal filter chips
    $$('#conflictSignalFilterChips .chip').forEach(chip => {
        chip.addEventListener('click', () => {
            $$('#conflictSignalFilterChips .chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            $$('.stat-card.clickable-stat').forEach(c => c.classList.remove('filter-active'));
            renderConflictResults();
        });
    });

    // Conflict type filter chips
    $$('#conflictTypeFilterChips .chip').forEach(chip => {
        chip.addEventListener('click', () => {
            $$('#conflictTypeFilterChips .chip').forEach(c => c.classList.remove('active'));
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

    // Conflict column sorting
    $$('#conflictSignalsTable th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const colMap = {
                name: 'Crypto Name',
                timeframe: 'Timeperiod',
                signal: 'Signal',
                angle: 'Angle',
                temagap: 'TEMA Gap',
                rsi: 'RSI',
                change: 'Daily Change',
                scanner: 'Scanner'
            };
            const col = colMap[th.dataset.col];
            if (currentConflictSort.col === col) {
                currentConflictSort.asc = !currentConflictSort.asc;
            } else {
                currentConflictSort.col = col;
                currentConflictSort.asc = true;
            }
            $$('#conflictSignalsTable th.sortable').forEach(t => {
                t.classList.remove('sorted-asc', 'sorted-desc');
            });
            th.classList.add(currentConflictSort.asc ? 'sorted-asc' : 'sorted-desc');
            renderConflictResults();
        });
    });
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

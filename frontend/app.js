/* ═══════════════════════════════════════════════════════════════════
   GEMINI SCANNER — ENTERPRISE APPLICATION LOGIC
   ═══════════════════════════════════════════════════════════════════ */

const API_URL = 'http://localhost:8001';
let allResults = [];
let allHilegaResults = [];
let scanRunning = false;
let logPollInterval = null;
let currentSort = { col: null, asc: true };
let currentHilegaSort = { col: null, asc: true };

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
        allResults = data.results || [];
        allHilegaResults = data.hilega_results || [];
        if (data.scan_time) {
            updateLastScanTime(data.scan_time);
        }
        populateTfFilter();
        populateHilegaTfFilter();
        renderResults();
        renderHilegaResults();
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
                if (s !== 'AMA Pro' && s !== 'Qwen' && s !== 'Both') return false;
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
            'AMA Pro': 'scanner-ama',
            'AMA Pro Now': 'scanner-ama-now',
            'Qwen Now': 'scanner-qwen-now',
            'Both Now': 'scanner-both-now',
            'AMA Pro Previous (Entry)': 'scanner-ama-entry',
            'AMA Pro Now (Entry)': 'scanner-ama-now-entry',
            'Both Previous (Entry)': 'scanner-both-entry',
            'Both Now (Entry)': 'scanner-both-now-entry',
            'Qwen Previous (Entry)': 'scanner-qwen-entry',
            'Qwen Now (Entry)': 'scanner-qwen-now-entry'
        };
        const scannerBadgeCls = badgeMap[r.Scanner] || '';
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
        const numericCols = ['Angle', 'RSI-TEMA', 'RSI', 'Daily Change'];
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

function updateStats() {
    const total = allResults.length;
    const longs = allResults.filter(r => r.Signal === 'LONG').length;
    const shorts = allResults.filter(r => r.Signal === 'SHORT').length;
    animateCounter('totalSignals', total);
    animateCounter('longSignals', longs);
    animateCounter('shortSignals', shorts);
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
    // HILEGA scanners are mutually exclusive with AMA/Qwen scanners
    $$('.scanner-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const scannerType = chip.dataset.scanner;
            const hilegaScanners = ['hilega_buy', 'hilega_sell'];
            const amaScanners = ['ama_pro', 'qwen', 'both', 'ama_pro_now', 'qwen_now', 'both_now', 'all'];

            // Check if clicking a HILEGA scanner
            if (hilegaScanners.includes(scannerType)) {
                // If activating HILEGA, deactivate all AMA scanners
                if (!chip.classList.contains('active')) {
                    $$('.scanner-chip').forEach(c => {
                        if (amaScanners.includes(c.dataset.scanner)) {
                            c.classList.remove('active');
                        }
                    });
                }
                chip.classList.toggle('active');
            }
            // Check if clicking an AMA/Qwen scanner
            else if (amaScanners.includes(scannerType)) {
                // If activating AMA, deactivate all HILEGA scanners
                if (!chip.classList.contains('active')) {
                    $$('.scanner-chip').forEach(c => {
                        if (hilegaScanners.includes(c.dataset.scanner)) {
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

async function runScan() {
    if (scanRunning) return;

    const crypto_count = parseInt($('#cryptoCount').value) || 20;
    const timeframes = Array.from($$('.tf-chip.active')).map(c => c.dataset.tf);
    const adaptation_speed = $('#adaptationSpeed').value;
    const min_bars_between = parseInt($('#minBarsBetween').value) || 3;

    // Get HILEGA RSI thresholds
    const hilega_buy_rsi = parseInt($('#hilegaBuyRsi').value) || 10;
    const hilega_sell_rsi = parseInt($('#hilegaSellRsi').value) || 90;

    // Get all selected scanner types
    const selectedScanners = Array.from($$('.scanner-chip.active')).map(c => c.dataset.scanner);

    if (timeframes.length === 0) {
        showToast('Select at least one timeframe', 'warning');
        return;
    }

    if (selectedScanners.length === 0) {
        showToast('Select at least one scanner type', 'warning');
        return;
    }

    // Determine scanner_type based on selections
    let scanner_type;
    if (selectedScanners.includes('all')) {
        // "All" selected - use 'all' string
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
    renderResults();
    renderHilegaResults();
    updateStats();

    // Add scan start log
    const scannerLabels = { 'both': 'AMA Pro + Qwen', 'qwen': 'Qwen', 'ama_pro': 'AMA Pro', 'ama_pro_now': 'AMA Pro Now', 'qwen_now': 'Qwen Now', 'both_now': 'AMA Pro Now + Qwen Now', 'all': 'All Scanners' };
    const scannerLabel = selectedScanners.length > 1 ? selectedScanners.map(s => scannerLabels[s] || s).join(' + ') : (scannerLabels[selectedScanners[0]] || selectedScanners[0]);
    addLogLine('info', `🔄 CRYPTO SCAN IN PROGRESS — Top ${crypto_count} Coins | TFs: ${timeframes.join(', ')} | Scanner: ${scannerLabel} | Speed: ${adaptation_speed} | MinBars: ${min_bars_between}`);

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
                hilega_buy_rsi,
                hilega_sell_rsi
            })
        });

        clearInterval(progInterval);

        if (!res.ok) throw new Error(`Server error: ${res.status}`);

        const data = await res.json();
        allResults = data.data || [];
        allHilegaResults = data.hilega_data || [];

        const totalSignals = allResults.length + allHilegaResults.length;

        updateProgress(100, 'Scan complete!');
        if (allHilegaResults.length > 0) {
            addLogLine('success', `✅ SCAN COMPLETED — ${allHilegaResults.length} HILEGA signal(s) found`);
        } else {
            addLogLine('success', `✅ SCAN COMPLETED — ${allResults.length} signal(s) found`);
        }

        populateTfFilter();
        populateHilegaTfFilter();
        renderResults();
        renderHilegaResults();
        updateStats();
        updateLastScanTime(new Date().toISOString());

        if (allHilegaResults.length > 0) {
            showToast(`Scan complete! ${allHilegaResults.length} HILEGA signal(s) found.`, 'success');
        } else {
            showToast(`Scan complete! ${allResults.length} signal(s) found.`, 'success');
        }

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
    const headers = ['Asset', 'Timeframe', 'Signal', 'Angle', 'RSI-TEMA', 'RSI', 'Daily Change', 'Timestamp'];
    const rows = allHilegaResults.map(r => {
        return [
            r['Crypto Name'],
            r.Timeperiod,
            r.Signal,
            r.Angle || '',
            r['RSI-TEMA'] || '',
            r.RSI || '',
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

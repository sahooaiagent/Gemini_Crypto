/* ═══════════════════════════════════════════════════════════════════════════
   GEMINI SCANNER  ·  CHROME LAYER  ·  PHASE 2
   ───────────────────────────────────────────────────────────────────────────
   Adds a top bar (global scan status + clock + theme + ⌘K hint),
   a ⌘K command palette, and global keyboard shortcuts.
   Reads app.js state non-invasively via DOM observation.
   ═══════════════════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    // ──────────────────────────────────────── helpers
    const $  = (sel, root) => (root || document).querySelector(sel);
    const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

    function onReady(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn, { once: true });
        } else { fn(); }
    }

    function el(html) {
        const t = document.createElement('template');
        t.innerHTML = html.trim();
        return t.content.firstElementChild;
    }

    // ──────────────────────────────────────── TOP BAR
    function buildTopBar() {
        if ($('#gsTopBar')) return;
        const bar = el(`
            <div class="gs-topbar ds-topbar is-active" id="gsTopBar">
                <div class="gs-topbar__left">
                    <button class="gs-topbar__palette" id="gsPaletteTrigger" title="Open command palette">
                        <i class="fas fa-bolt"></i>
                        <span>Command</span>
                        <span class="ds-palette__kbd">
                            <span class="ds-kbd">⌘</span><span class="ds-kbd">K</span>
                        </span>
                    </button>
                </div>

                <div class="gs-topbar__center">
                    <div class="ds-topbar__status" id="gsScanStatus" role="status" aria-live="polite">
                        <span class="ds-topbar__dot is-idle"></span>
                        <span class="gs-topbar__status-text">Idle</span>
                    </div>
                </div>

                <div class="gs-topbar__right">
                    <div class="gs-topbar__clock" id="gsTopClock">—</div>
                    <button class="gs-topbar__iconbtn" id="gsShortcutsBtn" title="Shortcuts (?)">
                        <i class="far fa-keyboard"></i>
                    </button>
                    <button class="gs-topbar__iconbtn" id="gsThemeBtn" title="Toggle theme (t)">
                        <i class="fas fa-moon"></i>
                    </button>
                    <div class="ds-topbar__status gs-topbar__conn" id="gsConn" title="API connection">
                        <span class="ds-topbar__dot is-idle" id="gsConnDot"></span>
                        <span id="gsConnText">API</span>
                    </div>
                </div>
            </div>
        `);
        document.body.insertBefore(bar, $('.main-content'));
        return bar;
    }

    // ──────────────────────────────────────── COMMAND PALETTE
    const COMMANDS = [
        { id: 'tab-dashboard',    label: 'Go to · Dashboard',          icon: 'fa-chart-line',      kbd: ['1'],      run: () => switchTab('dashboard') },
        { id: 'tab-scanner',      label: 'Go to · Scanner',            icon: 'fa-radar',           kbd: ['2'],      run: () => switchTab('scanner') },
        { id: 'tab-performance',  label: 'Go to · Performance',        icon: 'fa-tachometer-alt',  kbd: ['3'],      run: () => switchTab('performance') },
        { id: 'tab-journal',      label: 'Go to · Trade Journal',      icon: 'fa-book-open',       kbd: ['4'],      run: () => switchTab('journal') },
        { id: 'tab-alerts',       label: 'Go to · Alerts',             icon: 'fa-bell',            kbd: ['5'],      run: () => switchTab('alerts') },
        { id: 'action-run',       label: 'Run Scanner',                icon: 'fa-rocket',          kbd: ['R'],      run: () => clickIfExists('#runScanBtn') },
        { id: 'action-refresh',   label: 'Refresh Data',               icon: 'fa-sync-alt',        kbd: [],         run: () => clickIfExists('#refreshBtn') },
        { id: 'action-theme',     label: 'Toggle Theme',               icon: 'fa-moon',            kbd: ['T'],      run: () => clickIfExists('#themeToggle') || toggleThemeFallback() },
        { id: 'action-search',    label: 'Focus Signal Search',        icon: 'fa-search',          kbd: ['/'],      run: () => focusIfExists('#searchInput') },
        { id: 'action-new-alert', label: 'New Alert',                  icon: 'fa-plus',            kbd: [],         run: () => { switchTab('alerts'); setTimeout(() => clickIfExists('#createAlertBtn'), 120); } },
        { id: 'action-clear-log', label: 'Clear Diagnostics Log',      icon: 'fa-trash-alt',      kbd: [],         run: () => { switchTab('scanner'); setTimeout(() => clickIfExists('#scannerClearLogsBtn'), 120); } },
        { id: 'action-shortcuts', label: 'Show Keyboard Shortcuts',    icon: 'fa-keyboard',        kbd: ['?'],      run: () => openShortcuts() },
    ];

    function switchTab(name) {
        const link = $(`.nav-link[data-tab="${name}"]`);
        if (link) link.click();
    }
    function clickIfExists(sel) {
        const n = $(sel);
        if (n) { n.click(); return true; }
        return false;
    }
    function focusIfExists(sel) {
        const n = $(sel);
        if (n) { n.focus(); n.select && n.select(); return true; }
        return false;
    }
    function toggleThemeFallback() {
        const cur = document.documentElement.getAttribute('data-theme') || 'dark';
        const next = cur === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        try { localStorage.setItem('theme', next); } catch (e) {}
    }

    function buildPalette() {
        if ($('#gsPalette')) return;
        const overlay = el(`
            <div class="ds-palette-overlay gs-palette-overlay" id="gsPalette" role="dialog" aria-label="Command palette">
                <div class="ds-palette gs-palette">
                    <input type="text" class="ds-palette__input gs-palette__input"
                           id="gsPaletteInput" placeholder="Type a command…" autocomplete="off">
                    <div class="ds-palette__list gs-palette__list" id="gsPaletteList"></div>
                    <div class="gs-palette__footer">
                        <span><span class="ds-kbd">↑</span><span class="ds-kbd">↓</span> navigate</span>
                        <span><span class="ds-kbd">⏎</span> run</span>
                        <span><span class="ds-kbd">Esc</span> close</span>
                    </div>
                </div>
            </div>
        `);
        document.body.appendChild(overlay);
    }

    let paletteState = { open: false, active: 0, filtered: COMMANDS };

    function openPalette() {
        paletteState.open = true;
        $('#gsPalette').classList.add('is-open');
        $('#gsPaletteInput').value = '';
        paletteState.filtered = COMMANDS;
        paletteState.active = 0;
        renderPaletteList();
        setTimeout(() => $('#gsPaletteInput').focus(), 10);
    }
    function closePalette() {
        paletteState.open = false;
        $('#gsPalette').classList.remove('is-open');
    }
    function renderPaletteList() {
        const list = $('#gsPaletteList');
        list.innerHTML = paletteState.filtered.map((c, i) => `
            <div class="ds-palette__item gs-palette__item ${i === paletteState.active ? 'is-active' : ''}"
                 data-cmd="${c.id}" data-idx="${i}">
                <i class="fas ${c.icon}"></i>
                <span>${c.label}</span>
                ${c.kbd.length ? `<span class="ds-palette__kbd">${c.kbd.map(k => `<span class="ds-kbd">${k}</span>`).join('')}</span>` : ''}
            </div>
        `).join('');
        $$('#gsPaletteList .gs-palette__item').forEach(it => {
            it.addEventListener('click', () => {
                const idx = parseInt(it.getAttribute('data-idx'), 10);
                runPaletteCommand(idx);
            });
        });
    }
    function filterPalette(q) {
        q = (q || '').trim().toLowerCase();
        if (!q) { paletteState.filtered = COMMANDS; }
        else {
            paletteState.filtered = COMMANDS.filter(c =>
                c.label.toLowerCase().includes(q) ||
                c.kbd.some(k => k.toLowerCase() === q));
        }
        paletteState.active = 0;
        renderPaletteList();
    }
    function runPaletteCommand(idx) {
        const cmd = paletteState.filtered[idx];
        if (!cmd) return;
        closePalette();
        setTimeout(() => { try { cmd.run(); } catch (e) { console.error(e); } }, 30);
    }

    // ──────────────────────────────────────── SHORTCUTS OVERLAY
    function buildShortcuts() {
        if ($('#gsShortcuts')) return;
        const overlay = el(`
            <div class="ds-palette-overlay gs-shortcuts-overlay" id="gsShortcuts" role="dialog" aria-label="Keyboard shortcuts">
                <div class="ds-palette gs-shortcuts-panel">
                    <div class="gs-shortcuts-header">
                        <h3>Keyboard Shortcuts</h3>
                        <button class="gs-topbar__iconbtn" id="gsShortcutsClose"><i class="fas fa-times"></i></button>
                    </div>
                    <div class="gs-shortcuts-body">
                        ${shortcutRow(['⌘', 'K'], 'Open command palette')}
                        ${shortcutRow(['/'], 'Focus signal search')}
                        ${shortcutRow(['R'], 'Run scanner')}
                        ${shortcutRow(['T'], 'Toggle theme')}
                        ${shortcutRow(['1'], 'Go to Dashboard')}
                        ${shortcutRow(['2'], 'Go to Scanner')}
                        ${shortcutRow(['3'], 'Go to Performance')}
                        ${shortcutRow(['4'], 'Go to Trade Journal')}
                        ${shortcutRow(['5'], 'Go to Alerts')}
                        ${shortcutRow(['?'], 'Show this panel')}
                        ${shortcutRow(['Esc'], 'Close overlays')}
                    </div>
                </div>
            </div>
        `);
        document.body.appendChild(overlay);
        $('#gsShortcutsClose').addEventListener('click', closeShortcuts);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeShortcuts();
        });
    }
    function shortcutRow(keys, label) {
        return `<div class="gs-shortcuts-row">
            <span class="gs-shortcuts-keys">${keys.map(k => `<span class="ds-kbd">${k}</span>`).join('')}</span>
            <span class="gs-shortcuts-label">${label}</span>
        </div>`;
    }
    function openShortcuts() { buildShortcuts(); $('#gsShortcuts').classList.add('is-open'); }
    function closeShortcuts() { const n = $('#gsShortcuts'); if (n) n.classList.remove('is-open'); }

    // ──────────────────────────────────────── CLOCK
    function initClock() {
        const node = $('#gsTopClock');
        if (!node) return;
        const tick = () => {
            const d = new Date();
            const h = String(d.getHours()).padStart(2, '0');
            const m = String(d.getMinutes()).padStart(2, '0');
            const s = String(d.getSeconds()).padStart(2, '0');
            node.textContent = `${h}:${m}:${s}`;
        };
        tick();
        setInterval(tick, 1000);
    }

    // ──────────────────────────────────────── SCAN STATUS OBSERVER
    // Non-invasive: watches #scanProgressWrap hidden class + #scanProgressPct text
    function initScanStatusWatcher() {
        const wrap = $('#scanProgressWrap');
        const pct  = $('#scanProgressPct');
        const statusEl = $('#gsScanStatus');
        if (!wrap || !statusEl) return;

        const dot  = statusEl.querySelector('.ds-topbar__dot');
        const text = statusEl.querySelector('.gs-topbar__status-text');

        function update() {
            const hidden = wrap.classList.contains('hidden');
            if (!hidden) {
                dot.classList.remove('is-idle', 'is-error');
                dot.classList.add('is-scanning');
                const p = pct ? pct.textContent : '';
                text.textContent = `Scanning${p ? ' · ' + p : ''}`;
                statusEl.classList.add('is-scanning');
            } else {
                dot.classList.remove('is-scanning', 'is-error');
                dot.classList.add('is-idle');
                // Try to read last scan time from #lastScanTime
                const lst = $('#lastScanTime');
                text.textContent = (lst && lst.textContent.trim() && lst.textContent.trim() !== '—')
                    ? `Last scan · ${lst.textContent.trim()}`
                    : 'Idle';
                statusEl.classList.remove('is-scanning');
            }
        }

        update();
        new MutationObserver(update).observe(wrap, { attributes: true, attributeFilter: ['class'] });
        if (pct) new MutationObserver(update).observe(pct, { childList: true, subtree: true, characterData: true });
        const lst = $('#lastScanTime');
        if (lst) new MutationObserver(update).observe(lst, { childList: true, subtree: true, characterData: true });
    }

    // ──────────────────────────────────────── CONNECTION STATUS MIRROR
    function initConnMirror() {
        const src = $('#connectionStatus');
        const dot = $('#gsConnDot');
        const txt = $('#gsConnText');
        if (!src || !dot) return;
        const update = () => {
            const srcDot = src.querySelector('.status-dot');
            const online = srcDot && srcDot.classList.contains('online');
            dot.classList.toggle('is-idle', !online);
            dot.style.background = online ? 'var(--accent-green)' : '';
            dot.style.boxShadow = online ? '0 0 0 3px var(--accent-green-dim)' : '';
            if (txt) txt.textContent = online ? 'API · Online' : 'API · Offline';
        };
        update();
        new MutationObserver(update).observe(src, { subtree: true, attributes: true, attributeFilter: ['class'] });
    }

    // ──────────────────────────────────────── SIDEBAR KBD HINTS
    function addSidebarKbdHints() {
        const map = { dashboard: '1', scanner: '2', performance: '3', journal: '4', alerts: '5' };
        Object.entries(map).forEach(([tab, k]) => {
            const link = $(`.nav-link[data-tab="${tab}"]`);
            if (!link || link.querySelector('.gs-nav-kbd')) return;
            const kbd = el(`<span class="gs-nav-kbd"><span class="ds-kbd">${k}</span></span>`);
            link.appendChild(kbd);
        });
    }

    // ──────────────────────────────────────── GLOBAL KEY BINDINGS
    function initKeyBindings() {
        document.addEventListener('keydown', (e) => {
            const typingInField = /^(input|textarea|select)$/i.test((e.target || {}).tagName || '');
            const anyOverlayOpen = paletteState.open || ($('#gsShortcuts') && $('#gsShortcuts').classList.contains('is-open'));

            // ⌘K / Ctrl+K — open palette
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                paletteState.open ? closePalette() : openPalette();
                return;
            }

            if (paletteState.open) {
                if (e.key === 'Escape') { e.preventDefault(); closePalette(); return; }
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    paletteState.active = Math.min(paletteState.active + 1, paletteState.filtered.length - 1);
                    renderPaletteList();
                    return;
                }
                if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    paletteState.active = Math.max(paletteState.active - 1, 0);
                    renderPaletteList();
                    return;
                }
                if (e.key === 'Enter') { e.preventDefault(); runPaletteCommand(paletteState.active); return; }
                return;
            }

            if ($('#gsShortcuts') && $('#gsShortcuts').classList.contains('is-open')) {
                if (e.key === 'Escape') { closeShortcuts(); return; }
            }

            // Don't capture bare keys while user types in an input
            if (typingInField) return;
            if (anyOverlayOpen) return;

            const k = e.key;
            if (k === '/') { e.preventDefault(); focusIfExists('#searchInput'); return; }
            if (k === '?') { e.preventDefault(); openShortcuts(); return; }
            if (k === 'Escape') { closeShortcuts(); return; }
            if (/^[1-5]$/.test(k)) {
                const tabs = { '1': 'dashboard', '2': 'scanner', '3': 'performance', '4': 'journal', '5': 'alerts' };
                e.preventDefault();
                switchTab(tabs[k]);
                return;
            }
            if (k.toLowerCase() === 'r' && !e.metaKey && !e.ctrlKey && !e.altKey) {
                e.preventDefault();
                clickIfExists('#runScanBtn');
                return;
            }
            if (k.toLowerCase() === 't' && !e.metaKey && !e.ctrlKey && !e.altKey) {
                e.preventDefault();
                clickIfExists('#themeToggle') || toggleThemeFallback();
                return;
            }
        });
    }

    // ──────────────────────────────────────── WIRE-UP
    function wireTopBar() {
        const trig = $('#gsPaletteTrigger');
        if (trig) trig.addEventListener('click', () => paletteState.open ? closePalette() : openPalette());

        const themeBtn = $('#gsThemeBtn');
        if (themeBtn) themeBtn.addEventListener('click', () => {
            clickIfExists('#themeToggle') || toggleThemeFallback();
            syncTopBarThemeIcon();
        });

        const sBtn = $('#gsShortcutsBtn');
        if (sBtn) sBtn.addEventListener('click', openShortcuts);

        syncTopBarThemeIcon();
        // Re-sync when html[data-theme] changes (driven by app.js)
        new MutationObserver(syncTopBarThemeIcon).observe(document.documentElement, {
            attributes: true, attributeFilter: ['data-theme']
        });
    }

    function syncTopBarThemeIcon() {
        const cur = document.documentElement.getAttribute('data-theme') || 'dark';
        const btn = $('#gsThemeBtn i');
        if (!btn) return;
        btn.className = 'fas ' + (cur === 'light' ? 'fa-sun' : 'fa-moon');
    }

    function wirePalette() {
        const overlay = $('#gsPalette');
        const input = $('#gsPaletteInput');
        overlay.addEventListener('click', (e) => { if (e.target === overlay) closePalette(); });
        input.addEventListener('input', (e) => filterPalette(e.target.value));
    }

    onReady(() => {
        buildTopBar();
        buildPalette();
        buildShortcuts();
        wireTopBar();
        wirePalette();
        initClock();
        initScanStatusWatcher();
        initConnMirror();
        addSidebarKbdHints();
        initKeyBindings();
    });
})();

/* ═══════════════════════════════════════════════════════════════════════════
   GEMINI SCANNER  ·  CONTENT POLISH  ·  PHASE 3
   ───────────────────────────────────────────────────────────────────────────
   Adds sparklines, volume sparkbars, gradient badges, row pulse animations,
   and subtle refinements to signal tables and scanner panels.
   ═══════════════════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    const $ = (sel, root) => (root || document).querySelector(sel);
    const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

    function onReady(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn, { once: true });
        } else { fn(); }
    }

    // ──────────────────────────────────────── SPARKLINE RENDERER
    // Mini SVG sparkline for stat cards (6 sample points)
    function renderSparkline(canvas, values = []) {
        if (!(canvas instanceof HTMLCanvasElement)) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width;
        const h = canvas.height;
        canvas.style.display = 'block';

        if (!values || values.length < 2) {
            ctx.fillStyle = 'var(--text-muted)';
            ctx.fillRect(0, h * 0.3, w, h * 0.4);
            return;
        }

        const min = Math.min(...values);
        const max = Math.max(...values);
        const range = max - min || 1;
        const pts = values.map((v, i) => ({
            x: (i / (values.length - 1)) * (w - 8) + 4,
            y: h - ((v - min) / range) * (h - 8) - 4
        }));

        // Clear
        ctx.clearRect(0, 0, w, h);

        // Gradient fill
        const grad = ctx.createLinearGradient(0, 0, 0, h);
        grad.addColorStop(0, 'rgba(34, 230, 166, 0.35)');
        grad.addColorStop(1, 'rgba(34, 230, 166, 0)');
        ctx.fillStyle = grad;

        // Polygon
        ctx.beginPath();
        ctx.moveTo(pts[0].x, h);
        pts.forEach(p => ctx.lineTo(p.x, p.y));
        ctx.lineTo(pts[pts.length - 1].x, h);
        ctx.closePath();
        ctx.fill();

        // Line
        ctx.strokeStyle = 'var(--accent-green)';
        ctx.lineWidth = 1.5;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        pts.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
        ctx.stroke();

        // Points
        ctx.fillStyle = 'var(--accent-green-hi)';
        pts.forEach(p => {
            ctx.beginPath();
            ctx.arc(p.x, p.y, 2, 0, 2 * Math.PI);
            ctx.fill();
        });
    }

    function initSparklines() {
        // Stat cards: inject mini sparklines
        $$('.stat-card').forEach(card => {
            const id = card.getAttribute('data-accent') || 'cyan';
            let canvas = card.querySelector('canvas');
            if (!canvas) {
                canvas = document.createElement('canvas');
                canvas.width = 64;
                canvas.height = 24;
                canvas.style.position = 'absolute';
                canvas.style.bottom = '12px';
                canvas.style.right = '16px';
                canvas.style.opacity = '0.6';
                card.style.position = 'relative';
                card.appendChild(canvas);
            }

            // Generate 6 random but trending values
            const base = Math.random() * 100;
            const trend = (Math.random() - 0.45) * 20;
            const vals = Array.from({ length: 6 }, (_, i) =>
                base + (i / 5) * trend + (Math.random() - 0.5) * 15);
            renderSparkline(canvas, vals);
        });
    }

    // ──────────────────────────────────────── VOLUME SPARKBAR
    // Renders a volume ratio (e.g. "3.2x") as a visual bar
    function renderVolumeBar(cell) {
        if (!cell) return;
        const txt = (cell.textContent || '').trim();
        const match = txt.match(/^([\d.]+)x?/);
        if (!match) return;

        const ratio = parseFloat(match[1]);
        if (!ratio || ratio < 1) return;

        // Map ratio to color intensity (1x=cyan, 5x=amber, 10x+=hot red)
        let fillClass = 'ds-sparkbar__fill';
        if (ratio >= 8) fillClass += ' ds-sparkbar__fill--extreme';
        else if (ratio >= 5) fillClass += ' ds-sparkbar__fill--hot';

        // Clamp width to 100% (at 10x ratio)
        const pct = Math.min((ratio / 10) * 100, 100);

        const html = `
            <div class="ds-sparkbar">
                <div class="ds-sparkbar__track">
                    <div class="${fillClass}" style="width: ${pct}%"></div>
                </div>
                <span class="ds-sparkbar__label">${ratio.toFixed(2)}x</span>
            </div>
        `;
        cell.innerHTML = html;
    }

    function enhanceVolumeCells() {
        // In BLAST results: Volume column (data-col="volume")
        $$('table td[data-col="volume"]').forEach(renderVolumeBar);

        // Also enhance any plain "3.2x" text in Volume columns
        $$('table th[data-col="volume"]').forEach(th => {
            const tbody = th.closest('table').querySelector('tbody');
            if (!tbody) return;
            $$('td', tbody).forEach((td, idx) => {
                const ths = $$('th', th.closest('table').querySelector('thead'));
                const colIdx = Array.from(ths).indexOf(th);
                if (Array.from(td.parentNode.children).indexOf(td) === colIdx) {
                    renderVolumeBar(td);
                }
            });
        });
    }

    // ──────────────────────────────────────── SIGNAL BADGE ENHANCEMENT
    function enhanceSignalBadges() {
        $$('table tbody td').forEach(td => {
            const txt = td.textContent.trim();
            if (txt === 'LONG' || txt === 'Cross UP') {
                td.classList.add('ds-badge', 'ds-badge--long');
                td.innerHTML = `<i class="fas fa-arrow-up"></i> ${txt}`;
            } else if (txt === 'SHORT' || txt === 'Cross DN') {
                td.classList.add('ds-badge', 'ds-badge--short');
                td.innerHTML = `<i class="fas fa-arrow-down"></i> ${txt}`;
            } else if (txt === 'OB') {
                td.classList.add('ds-badge', 'ds-badge--ob');
                td.innerHTML = `<i class="fas fa-fire"></i> OB`;
            } else if (txt === 'OS') {
                td.classList.add('ds-badge', 'ds-badge--os');
                td.innerHTML = `<i class="fas fa-snowflake"></i> OS`;
            }
        });
    }

    // ──────────────────────────────────────── ROW PULSE ON NEW RESULTS
    // Watch for table body mutations and pulse the new row
    function watchTableForPulse(tableId) {
        const table = $(tableId);
        if (!table) return;
        const tbody = table.querySelector('tbody');
        if (!tbody) return;

        let lastRowCount = tbody.querySelectorAll('tr').length;

        new MutationObserver(() => {
            const rows = tbody.querySelectorAll('tr');
            const current = rows.length;

            if (current > lastRowCount) {
                // New row(s) added — pulse the first new one
                const newIdx = lastRowCount;
                if (rows[newIdx]) {
                    rows[newIdx].classList.add('ds-row--fresh');
                    // Remove class after animation completes
                    setTimeout(() => rows[newIdx].classList.remove('ds-row--fresh'), 1600);
                }
            }

            lastRowCount = current;
        }).observe(tbody, { childList: true });
    }

    // ──────────────────────────────────────── STICKY HEADERS
    function initStickyHeaders() {
        $$('table thead th').forEach(th => {
            th.style.position = 'sticky';
            th.style.top = 'var(--topbar-h)';
            th.style.zIndex = '10';
        });
    }

    // ──────────────────────────────────────── ENHANCED SCANNER CONFIG
    function enhanceScannerConfig() {
        // Add subtle divider lines to config sections
        $$('.config-card-section').forEach(section => {
            section.style.borderBottom = '1px solid var(--glass-border)';
            section.style.paddingBottom = 'var(--space-5)';
            section.style.marginBottom = 'var(--space-5)';
        });

        // Highlight active scanner chips with glow
        $$('.scanner-chip.active, .tf-chip.active').forEach(chip => {
            chip.style.boxShadow = '0 0 0 1px var(--glass-border-hover), var(--shadow-glow-cyan)';
        });
    }

    // ──────────────────────────────────────── TIMESTAMP FORMATTER
    // Humanize "2:45 PM" to "just now" / "2m ago" where possible
    const timeAgoCache = new WeakMap();

    function formatTimeAgo(txt) {
        if (!txt || txt === '—') return txt;
        const match = txt.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)?/);
        if (!match) return txt;

        const now = new Date();
        const [hStr, mStr, ampm] = match.slice(1);
        let h = parseInt(hStr, 10);
        const m = parseInt(mStr, 10);

        if (ampm === 'PM' && h !== 12) h += 12;
        if (ampm === 'AM' && h === 12) h = 0;

        const t = new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, m);
        const ago = Math.round((now - t) / 1000);

        if (ago < 60) return 'just now';
        if (ago < 3600) return `${Math.floor(ago / 60)}m ago`;
        if (ago < 86400) return `${Math.floor(ago / 3600)}h ago`;
        return txt;
    }

    function enhanceTimestamps() {
        $$('table td').forEach(td => {
            if (td.textContent.match(/\d{1,2}:\d{2}\s*(AM|PM)?/)) {
                const orig = td.textContent.trim();
                const fmt = formatTimeAgo(orig);
                if (fmt !== orig) {
                    td.textContent = fmt;
                    td.title = orig; // Show original on hover
                }
            }
        });
    }

    // ──────────────────────────────────────── COPY-ON-CLICK
    function enableCopyOnClick() {
        $$('table td').forEach(td => {
            if (td.textContent.match(/^[A-Z]{3,}\/USDT$|^[0-9x.]+$|^[A-Z]+$/)) {
                td.style.cursor = 'pointer';
                td.title = 'Click to copy';
                td.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const text = td.textContent.trim();
                    navigator.clipboard.writeText(text).then(() => {
                        const orig = td.textContent;
                        td.textContent = '✓ Copied';
                        setTimeout(() => { td.textContent = orig; }, 1400);
                    });
                });
            }
        });
    }

    // ──────────────────────────────────────── COLLAPSIBLE SECTIONS (refinement)
    function refineCollapsibles() {
        $$('.section-header-collapse').forEach(header => {
            const icon = header.querySelector('.collapse-icon');
            if (!icon) return;
            header.style.cursor = 'pointer';
            header.style.transition = 'all var(--dur-fast) var(--ease-out)';

            const toggle = () => {
                const id = header.getAttribute('data-collapse');
                const content = $('#' + id);
                const isCollapsed = header.classList.contains('collapsed');

                if (isCollapsed) {
                    header.classList.remove('collapsed');
                    content.classList.remove('collapsed');
                    icon.style.transform = 'rotate(0deg)';
                } else {
                    header.classList.add('collapsed');
                    content.classList.add('collapsed');
                    icon.style.transform = 'rotate(-90deg)';
                }
            };

            if (!header.onclick && !header.getAttribute('data-bound')) {
                header.addEventListener('click', toggle);
                header.setAttribute('data-bound', '1');
                icon.style.transition = 'transform var(--dur-base) var(--ease-out)';
            }
        });
    }

    // ──────────────────────────────────────── WIRE-UP
    onReady(() => {
        // Phase 3 polish
        initSparklines();
        initStickyHeaders();
        enhanceVolumeCells();
        enhanceSignalBadges();
        enhanceScannerConfig();
        enhanceTimestamps();
        enableCopyOnClick();
        refineCollapsibles();

        // Watch all result tables for fresh row pulse
        $$('table').forEach(t => {
            const id = t.getAttribute('id');
            if (id) watchTableForPulse('#' + id);
        });

        // Re-enhance when new rows are added (e.g. after scan completes)
        const observer = new MutationObserver(() => {
            enhanceVolumeCells();
            enhanceSignalBadges();
            enhanceTimestamps();
            enableCopyOnClick();
        });

        $$('table tbody').forEach(tbody => {
            observer.observe(tbody, { childList: true, subtree: true });
        });

        // Listen for tab switches to re-enhance content
        $$('.nav-link').forEach(link => {
            link.addEventListener('click', () => {
                setTimeout(() => {
                    initSparklines();
                    enhanceVolumeCells();
                    enhanceSignalBadges();
                    enhanceTimestamps();
                    enableCopyOnClick();
                    refineCollapsibles();
                }, 100);
            });
        });
    });
})();

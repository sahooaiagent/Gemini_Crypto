/* ═══════════════════════════════════════════════════════════════════════════
   GEMINI SCANNER  ·  CONTENT POLISH  ·  PHASE 3 (MINIMAL)
   ───────────────────────────────────────────────────────────────────────────
   Lightweight polish: just gradient badges on signal cells.
   Removed: sparklines, sparkbars, MutationObserver (caused Trade Journal freeze).
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

    // ──────────────────────────────────────── SIGNAL BADGE ENHANCEMENT (SAFE)
    // Only targets cells with exact text matches — instant, no loops
    function enhanceSignalBadges() {
        // Trade Journal Signal column (Result column)
        $$('table tbody td').forEach(td => {
            // Early exit: if already enhanced or empty, skip
            if (td.classList.contains('ds-badge') || !td.textContent) return;

            const txt = td.textContent.trim();

            // Only enhance if it's a known signal type
            if (txt === 'LONG') {
                td.classList.add('ds-badge--long');
                td.innerHTML = `<i class="fas fa-arrow-up"></i> LONG`;
            } else if (txt === 'SHORT') {
                td.classList.add('ds-badge--short');
                td.innerHTML = `<i class="fas fa-arrow-down"></i> SHORT`;
            } else if (txt === 'Cross UP') {
                td.classList.add('ds-badge--long');
                td.innerHTML = `<i class="fas fa-arrow-up"></i> Cross UP`;
            } else if (txt === 'Cross DN') {
                td.classList.add('ds-badge--short');
                td.innerHTML = `<i class="fas fa-arrow-down"></i> Cross DN`;
            } else if (txt === 'OB') {
                td.classList.add('ds-badge--ob');
                td.innerHTML = `<i class="fas fa-fire"></i> OB`;
            } else if (txt === 'OS') {
                td.classList.add('ds-badge--os');
                td.innerHTML = `<i class="fas fa-snowflake"></i> OS`;
            }
        });
    }

    // ──────────────────────────────────────── INITIALIZE
    onReady(() => {
        // Only enhance signal badges — minimal, safe operation
        enhanceSignalBadges();
    });
})();
